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
