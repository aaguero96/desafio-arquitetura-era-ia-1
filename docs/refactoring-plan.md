# Plano de refatoração: da v1-coupled à v2-decoupled

Este documento é vivo: a seção 1 é o plano como foi escrito antes de mexer no código; as seções seguintes registram o piloto, a medição e as revisões que o piloto provocou. Nada foi apagado do plano original, para que dê para ver o que mudou e por quê.

## 1. Plano original (antes do piloto)

### Ponto de partida medido

`metrics/results/v1-coupled.csv`, gerado por `python metrics/coupling.py <checkout da v1-coupled>/app/helpdesk v1-coupled`:

| componente | Ca | Ce | I | A | D | leitura |
|---|---|---|---|---|---|---|
| config | 6 | 0 | 0,00 | 0,00 | 1,00 | zona de dor: todo mundo depende dele e ele guarda o que mais muda (modelo físico, provider, chave) |
| schemas | 5 | 0 | 0,00 | 0,00 | 1,00 | zona de dor pela fórmula, mas são tipos de valor do contrato HTTP, que é fixo |
| llm | 4 | 1 | 0,20 | 0,00 | 0,80 | zona de dor: 4 features dependem de um módulo concreto que conhece SDK, provider e credencial |
| tickets | 1 | 1 | 0,50 | 0,00 | 0,50 | na fronteira; concreto e lido só pelo relatório |
| classification, extraction, suggestion | 1 | 3 | 0,75 | 0,00 | 0,25 | perto da sequência principal |
| report | 1 | 4 | 0,80 | 0,00 | 0,20 | perto da sequência principal |
| main | 0 | 5 | 1,00 | 0,00 | 0,00 | na sequência principal (ponto de composição) |

A leitura da métrica bate com o diagnóstico: as dores 3 e 4 (provider fora derruba feature; trocar modelo exige deploy) moram exatamente em `llm` e `config`, os dois componentes concretos e muito usados.

### Componentes-alvo e estratégia

| alvo | problema | estratégia |
|---|---|---|
| `llm` | concreto, Ca=4, conhece SDK, provider e credencial | **aumentar A**: declarar a abstração `LanguageModel` (Protocol) e colocar a implementação que fala com o gateway atrás dela; **inverter a dependência** do provider: a aplicação chama o gateway por capacidade lógica, e o gateway decide o modelo físico |
| `config` | concreto, Ca=6, mistura credenciais, URLs e nomes de modelo | **reduzir Ca e o conteúdo volátil**: nomes físicos e chaves saem da aplicação (vão para `gateway/config.yaml` e `.env` do gateway); sobra só a URL e a chave virtual do gateway |
| `tickets` | concreto, lido direto pelo relatório | **inverter a dependência**: o relatório depende de uma fonte de tickets abstrata |
| `schemas` | zona de dor pela fórmula | nenhuma mudança: tipos de valor estáveis por natureza, candidato a exceção declarada no ADR da métrica |

### Critério de pronto (métrica + testes)

1. `python -m pytest tests/characterization -q` passa sem alterar nenhum arquivo de `tests/characterization/`.
2. Nenhum componente na zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5), exceto `schemas`, declarado estável por natureza.
3. O componente que chama o gateway tem D ≤ 0,5 e nenhum componente de feature o importa.
4. `grep -rE "gpt-fake|claude-fake|FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY" app/` não retorna nada.

### Piloto escolhido

`llm`, por ser o componente com maior D entre os que não são tipos de valor e o único que toca o provider: é onde o gateway entra. O piloto muda só `llm` (e o mínimo de `config` para ele funcionar: nomes lógicos no lugar de modelos físicos, URL e chave do gateway no lugar das chaves dos providers). As features continuam chamando `llm.call_openai`/`llm.call_anthropic`, para isolar o efeito do piloto na métrica.

## 2. Piloto: `llm`

O que mudou (só `llm` e o mínimo de `config`):

- `llm.py` ganhou a abstração `LanguageModel` (Protocol) e a implementação `GatewayModel`, que fala com o gateway no formato OpenAI usando a chave virtual da aplicação, com `max_retries=0` (retry passa a ser do gateway).
- `call_openai` e `call_anthropic` continuaram existindo, mas as duas passaram a delegar para o gateway.
- `config.py` perdeu as chaves e URLs dos providers e os nomes físicos; os quatro nomes de modelo viraram capacidades lógicas (`ticket-classifier`, `reply-writer`, `topic-analyzer`, `order-extractor`).
- O compose ganhou `gateway` (LiteLLM), `gateway-db` e `gateway-init`; o `app` deixou de receber `env_file: .env`.

Verificação: suíte de caracterização 15/15 sem alteração; `grep -rE "gpt-fake|claude-fake|FAKE_|sk-fake|sk-ant" app/` vazio.

Medição antes e depois (`metrics/results/pilot-llm.csv`):

| componente | antes (v1) Ca / Ce / I / A / D | depois do piloto Ca / Ce / I / A / D |
|---|---|---|
| llm | 4 / 1 / 0,20 / 0,00 / **0,80** | 4 / 1 / 0,20 / 0,50 / **0,30** |
| config | 6 / 0 / 0,00 / 0,00 / **1,00** | 6 / 0 / 0,00 / 0,00 / **1,00** |
| demais | iguais | iguais |

## 3. Revisão do plano (o que o piloto mostrou)

O número melhorou, mas a leitura do número disse que o plano original estava errado em dois pontos.

**Revisão 1: a abstração no mesmo módulo da implementação é melhora de fachada.** `llm` saiu da zona de dor porque A foi a 0,5, mas o Ca continuou 4: as quatro features ainda importam o módulo concreto que carrega o SDK e instancia o cliente na importação. Nenhuma feature depende do Protocol; todas dependem de `call_openai`/`call_anthropic`, que agora mentem no nome (as duas vão ao gateway). Se o jeito de falar com o gateway mudar (streaming, timeout por capacidade, tradução de erros), as quatro features recompilam junto. O plano passa a ser:

- separar a abstração em `ports.py` (`LanguageModel`, `TicketSource`, só Protocols) e a implementação em `adapters/gateway.py`, que declara explicitamente implementar a porta;
- as features recebem um `LanguageModel` por parâmetro e não importam o adapter; só `main.py`, o ponto de composição, conhece `adapters.gateway`;
- `call_openai`/`call_anthropic` somem: a feature pede `model.complete(<capacidade>, prompt)`.

**Revisão 2: esvaziar `config` não tirou `config` da zona de dor.** O piloto removeu dele tudo o que era volátil (chaves, URLs, modelos físicos) e mesmo assim D continuou 1,0 com Ca=6: o problema de `config` não era o conteúdo, era ser um saco de constantes de que todo mundo depende. Cada constante tem um dono natural:

- o nome da capacidade é parte do que a feature pede → constante na própria feature;
- URL e chave do gateway, caminho do arquivo de tickets → lidos no ponto de composição (`main.py`) e passados aos adapters pelo construtor;
- lote de 150 tickets por chamada → constante do relatório.

Com isso `config` deixa de existir, e o `tickets` concreto vira `adapters/tickets_file.py`, implementando a porta `TicketSource`.

**Critério de pronto revisado:** além dos itens da seção 1, nenhum componente de feature importa `adapters.*`, e `config` não existe mais.

## 4. Handoff para o agente de IA (escala)

**Agente:** Claude Code (subagente `general-purpose`), rodando no mesmo repositório, com acesso a shell e ao compose no ar. O piloto foi feito por mim (arquiteto); a escala foi entregue ao agente.

**O que entreguei ao agente:**

- as seções 1 a 3 deste plano, com a instrução explícita de executar a **revisão** da seção 3, não o plano original;
- a estrutura alvo, arquivo por arquivo: `ports.py` só com Protocols (`LanguageModel`, `TicketSource`), `adapters/gateway.py` como único usuário do SDK, `adapters/tickets_file.py`, features recebendo dependências por parâmetro e com a própria constante `CAPABILITY`, `main.py` como ponto de composição, e a remoção de `llm.py`, `config.py` e `tickets.py`;
- as restrições: não tocar em `tests/`, `provider-fake/`, `edge/`, `data/`, `gateway/`, `compose.yaml`, `metrics/`, `docs/`; nenhum nome físico nem chave em `app/`; não commitar;
- os quatro juízes, com os comandos exatos, que ele devia rodar antes de devolver: rebuild do `app`, suíte de caracterização (15 passed; "se falhar, conserte o app, nunca os testes"), script de métrica (nenhum componente na zona de dor exceto `schemas`; `adapters.gateway` com I ≥ 0,5) e grep de `adapters` nas features (vazio).

**Como a métrica e os testes decidiram o aceite.** O relatório do agente não foi aceito pela palavra dele: repeti os juízes de forma independente depois que ele terminou.

| juiz | resultado reportado | resultado na minha reexecução |
|---|---|---|
| `pytest tests/characterization -q` | 15 passed | 15 passed |
| `/admin/calls` depois de F3 e F4 | não pedido | `claude-fake-large topics 200`, `gpt-fake-large extract 200`: as chamadas chegam pelo gateway aos `large` |
| métrica | só `schemas` na zona de dor | idem (tabela abaixo) |
| `grep adapters` nas features / `grep gpt-fake\|claude-fake\|FAKE_` em `app/` | vazio | vazio |

Também li o diff inteiro: o agente não mudou prompt, ordem de lotes, validações nem status HTTP; as únicas decisões dele foram docstrings curtas e um comentário marcando o ponto de composição. Aceito sem retrabalho. Se algum juiz falhasse, a instrução era devolver o diff ao agente com a saída do juiz, e não ajustar teste ou régua.

## 5. Medição da v2-decoupled

`metrics/results/v2-decoupled.csv`:

| componente | Ca | Ce | I | A | D |
|---|---|---|---|---|---|
| ports | 6 | 0 | 0,00 | 1,00 | 0,00 |
| adapters.gateway | 1 | 1 | 0,50 | 0,00 | 0,50 |
| adapters.tickets_file | 1 | 1 | 0,50 | 0,00 | 0,50 |
| classification, extraction, suggestion, report | 1 | 2 | 0,67 | 0,00 | 0,33 |
| main | 0 | 7 | 1,00 | 0,00 | 0,00 |
| schemas | 5 | 0 | 0,00 | 0,00 | 1,00 |

Critério de pronto: atendido. O fan-in que antes estava em `config` (Ca=6) e `llm` (Ca=4), dois módulos concretos, agora está em `ports` (Ca=6), que é totalmente abstrato (A=1, D=0): quem é muito usado é o que menos muda. `schemas` segue como exceção declarada (ADR da métrica). `adapters.gateway` ficou no limite (I=0,5): o próximo passo (requisito 5/6, na `main`) faz o adapter traduzir erros do SDK para exceções da porta, o que é uma necessidade funcional (fallback explícito, evento de erro no stream), não um ajuste para a fórmula.

## 6. Depois da tag: o que a `main` mudou na estrutura

A `main` evoluiu o contrato (streaming na F2, assíncrono na F3, resiliência no gateway), não a arquitetura:

- `ports.LanguageModel` ganhou `stream()` e o parâmetro `timeout` (o orçamento de latência é da feature, não do adapter), e `ports` ganhou `ModelUnavailable` e `GenerationInterrupted`. O adapter traduz os erros do SDK para essas exceções; features e ponto de composição nunca veem uma exceção do `openai`.
- Entrou `jobs.py` (estado das tarefas assíncronas, ADR 0010).
- Medição (`metrics/results/main.csv`): nenhum componente na zona de dor além de `schemas`. `ports` foi de A=1,0 para 0,5 por causa das duas exceções, e continua fora da zona. `jobs`, como os adapters, ficou em I=0,5.
