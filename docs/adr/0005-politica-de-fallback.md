# 0005. Política de fallback: técnico para todas as capacidades, modelo fraco decidido por feature

- Status: aceita
- Data: 2026-09-27
- Nível: solução

## Contexto

Diagnóstico da v1 (dor 3): com a Anthropic em `error_500`, a F2 devolveu `500` depois de 3 chamadas (retries padrão do SDK); com a Anthropic em `timeout`, a borda cortou a F2 com `504` aos 30 s, e o SDK ainda esperaria até 600 s por tentativa, com 2 retries. Nada caía para outro provider.

Dois tipos de fallback, com naturezas diferentes:

- **Técnico:** trocar para um modelo equivalente em outro provider. Os `large` dos dois providers dão a mesma saída para a mesma entrada, então não há perda.
- **Modelo fraco:** responder com um `mini` quando nenhum `large` está disponível. É mais rápido e barato, mas pior. É decisão de produto: uma resposta pior é melhor que nenhuma resposta, para quem consome esta feature?

## Evidência: o que o `mini` devolve em cada tarefa

Chamadas diretas no provider-fake, mesmas entradas nos dois tamanhos (tickets reais de `data/tickets.jsonl`):

| tarefa | amostra | divergência `mini` × `large` | exemplo |
|---|---|---|---|
| `classify` | 300 tickets | **0 de 300** | nenhuma |
| `extract` | 300 tickets | **90 de 300 (30%)**: `order_number` errado em 45, `product` errado em 54 | TK-00002, "nota fiscal 530720 (...) pedido #605065": `large` → `#605065`; `mini` → `#530720`. TK-00007, "notebook 14 polegadas": `large` → produto; `mini` → `null` |
| `suggest` | 3 tickets | texto diferente e mais curto: ~267 tokens contra ~600 | mesma abertura ("Olá! Sinto muito pelo transtorno..."), omite parágrafos de prazo e próximos passos |
| `topics` | 5 lotes de 150 (0, 5, 12, 20, 33) | **nenhuma**: temas, contagens e exemplos idênticos | lote 0: 15 temas, soma 150 nos dois |

## Opções consideradas

1. Sem fallback: cada feature presa ao seu provider (v1).
2. Fallback técnico para todas e modelo fraco para todas.
3. Fallback técnico para todas; modelo fraco decidido feature por feature, a partir da evidência acima e de quem consome a feature.

## Decisão

Opção 3. Toda capacidade tem fallback técnico para o `large` do outro provider. O modelo fraco é decidido por feature:

### F1 Classificar ticket: aceita `mini` (`gpt-fake-mini`)

O cliente está esperando a confirmação na tela. Na evidência, o `mini` classificou igual ao `large` em 300 de 300 tickets. Falhar deixaria o ticket sem categoria e o cliente sem confirmação; o `mini` entrega o mesmo resultado mais rápido. Aceitar.

### F2 Sugerir resposta: aceita `mini` (`claude-fake-mini`)

Quem consome é o atendente, que lê e edita antes de enviar. O `mini` produz uma sugestão mais curta e menos completa, mas coerente e com a mesma abertura. Uma sugestão parcial que o atendente completa é melhor que nenhuma; o erro é barato porque há revisão humana. Aceitar.

### F3 Relatório de temas: aceita `mini` (`claude-fake-mini`)

Painel interno, sem ninguém esperando. Na evidência, o `mini` devolveu temas, contagens e exemplos idênticos ao `large` nos 5 lotes testados. Como não há diferença observável e o relatório é agregado (um lote um pouco pior dilui no mês), aceitar é melhor do que falhar o relatório inteiro por causa de um lote.

### F4 Extrair dados do pedido: **não** aceita `mini`, falha explicitamente

Alimenta uma automação de troca e devolução sem revisão humana, onde um campo errado gera uma troca errada, que custa frete, estoque e cliente. O `mini` errou o número do pedido em 15% dos tickets, e o erro é o pior possível: um número bem formado (`#530720`) que passa na validação `^#\d{6}$` e é o de outra coisa (a nota fiscal). Não há como a aplicação detectar esse erro. Sem `large`, a F4 responde `503` e a automação tenta de novo depois; uma resposta pior aqui é pior que nenhuma.

## Onde mora cada mecanismo

| mecanismo | onde | configuração |
|---|---|---|
| timeout por tentativa | gateway | `timeout` (4 s em F1/F4, 20 s em F3) e `stream_timeout` (4 s em F2), por capacidade, em `gateway/config.yaml` |
| retry com backoff | gateway | `num_retries: 2` e `retry_policy`: 2 retries para `5xx` e `429`, **0 para timeout**; backoff exponencial do LiteLLM (medido: ~1 s, ~1,5 s e ~2,2 s entre tentativas) |
| fallback técnico e fraco | gateway | `router_settings.fallbacks`, em ordem: `<capacidade>-alt`, depois `<capacidade>-weak` quando existe |
| sem cooldown | gateway | `disable_cooldowns: true`: todo pedido tenta o primário primeiro (circuit breaker está fora de escopo) |
| timeout do chamador | aplicação | F1/F4: 13 s; F2: 15 s sem dados; F3: 50 s por lote. Maiores que a cadeia do gateway no cenário de falha, menores que o limite da borda e do requisito |
| sem retry na aplicação | aplicação | SDK com `max_retries=0` em `adapters/gateway.py`, para não multiplicar os retries do gateway |
| erro explícito | aplicação | `ModelUnavailable` → `503`; `GenerationInterrupted` → evento `error` no stream; falha no relatório → `failed` com motivo |

Timeout não tem retry: um provider travado não costuma destravar em 4 s, e esperar de novo estouraria o orçamento de latência (F1: 3 s no normal, 15 s com falha). Timeout cai direto no próximo destino.

**Tentativas máximas por destino:** primário 3, fallback técnico 3, modelo fraco 3 (1 + 2 retries em `5xx`/`429`; 1 em timeout).

**Streaming (F2):** o LiteLLM só faz fallback se a falha acontece antes do primeiro trecho. Se o texto já começou a chegar e o provider falha (`midstream_error`), o erro sobe até a aplicação, que o entrega ao atendente como evento `error` dentro do stream. Emendar o texto de outro modelo no meio da sugestão produziria um texto incoerente.

## Consequências

- Melhor: a queda de um provider não derruba feature nenhuma; a queda dos dois `large` derruba só a F4, e de forma explícita.
- Pior: no pior caso (os dois `large` em `5xx`), a F1 leva ~10 s (3 + 3 tentativas com backoff antes do `mini`), dentro dos 15 s mas longe dos 3 s do modo normal; a F4 leva ~9,5 s para responder `503`.
- Passa a ser necessário: reavaliar a decisão da F3 e da F1 se o comportamento do `mini` mudar; a comparação `large` × `mini` deve ser refeita a cada troca de modelo.

## Evidência

`/admin/calls` nos cenários do critério (também automatizados em `tests/acceptance/`):

- F1, `gpt-fake-large` em `error_500`: `openai gpt-fake-large 500` ×3, depois `anthropic claude-fake-large 200`; resposta `200` em 5,9 s.
- Os dois `large` em `error_500`: F1 → `gpt-fake-large 500` ×3, `claude-fake-large 500` ×3, `gpt-fake-mini 200`; F4 → os mesmos 6 `500` e `503 {"detail": "Modelo indisponível no momento; tente novamente."}`, nenhuma chamada a `mini`.
- F1 com a OpenAI em `timeout`: `openai gpt-fake-large 504` (cortada em 4 s), `anthropic claude-fake-large 200`; resposta em 5,1 s.
- F2 com `claude-fake-large` em `midstream_error`: uma única chamada, trechos seguidos de `event: error`.
