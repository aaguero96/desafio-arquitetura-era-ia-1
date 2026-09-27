# 0004. Capacidades lógicas por feature e mapeamento para modelos físicos

- Status: aceita
- Data: 2026-09-27
- Nível: solução

## Contexto

Na v1, `config.py` guardava o nome físico do modelo de cada feature (`gpt-fake-large`, `claude-fake-large`), e trocar um nome exigia rebuild do `app` (dor 4). Com o gateway (ADR 0003), a aplicação pode pedir algo mais estável que um modelo: uma capacidade. A pergunta é qual a granularidade dessas capacidades e onde mora o mapeamento.

## Opções consideradas

1. Capacidades por tamanho (`llm-large`, `llm-small`), compartilhadas entre features.
2. Uma capacidade por feature, com o nome do que ela faz.
3. Uma capacidade por tarefa do modelo e por destino (primário, fallback), todas conhecidas pela aplicação.

## Decisão

Opção 2. Cada feature pede a sua capacidade, com nome de negócio; o mapeamento para o modelo físico mora só em `gateway/config.yaml`:

| capacidade | feature | primário | fallback técnico | modelo fraco |
|---|---|---|---|---|
| `ticket-classifier` | F1 | `gpt-fake-large` | `claude-fake-large` | `gpt-fake-mini` |
| `reply-writer` | F2 | `claude-fake-large` | `gpt-fake-large` | `claude-fake-mini` |
| `topic-analyzer` | F3 | `claude-fake-large` | `gpt-fake-large` | `claude-fake-mini` |
| `order-extractor` | F4 | `gpt-fake-large` | `claude-fake-large` | nenhum (ADR 0005) |

Os primários mantêm a distribuição da v1 (F1 e F4 na OpenAI, F2 e F3 na Anthropic), o que preservou a saída que a suíte de caracterização fixou na `v2-decoupled`. Os destinos de fallback são capacidades internas do gateway (`<capacidade>-alt` e `<capacidade>-weak`) que a aplicação nunca pede diretamente.

Capacidades por tamanho (opção 1) foram descartadas porque a política de fallback é diferente por feature (ADR 0005): a F4 não aceita modelo fraco e a F1 aceita, e com uma capacidade compartilhada essa decisão voltaria para dentro da aplicação. A opção 3 vazaria a política de fallback para o código.

Os modelos físicos são declarados uma vez, com preço, no bloco `physical_models` (âncoras YAML); cada capacidade referencia um deles. Trocar o modelo é trocar a âncora.

## Consequências

- Melhor: a aplicação só conhece quatro nomes estáveis; trocar modelo, provider ou fallback não toca em `app/`.
- Pior: capacidades demais se o número de features crescer muito; nesse ponto vale agrupar features com o mesmo perfil.
- Passa a ser necessário: toda feature nova declarar sua capacidade e sua linha na política de fallback.

## Evidência

- `grep -rn "CAPABILITY =" app/helpdesk` mostra uma capacidade por feature.
- Roteiro "Troca de modelo" do README: após trocar a âncora de `ticket-classifier` e reiniciar só o `gateway`, a próxima F1 aparece em `/admin/calls` como `anthropic claude-fake-large classify 200`, com o `StartedAt` do `app` inalterado.
