# provider-fake

Um provider de modelos de linguagem simulado. Ele imita dois providers distintos, cada um no seu formato nativo, com latência realista, contagem de tokens, preços e falhas sob comando. Existe para que o desafio seja reproduzível sem chave paga e para que o avaliador consiga provocar falhas e conferir o que aconteceu.

Não altere este diretório.

## Os dois providers

| Provider | Base URL no host | Base URL dentro do compose | Formato | Autenticação |
|---|---|---|---|---|
| `openai` | `http://localhost:8090/openai/v1` | `http://provider-fake:8090/openai/v1` | Chat Completions: `POST /chat/completions` | `Authorization: Bearer <FAKE_OPENAI_KEY>` |
| `anthropic` | `http://localhost:8090/anthropic` | `http://provider-fake:8090/anthropic` | Messages: `POST /v1/messages` | `x-api-key: <FAKE_ANTHROPIC_KEY>` |

As chaves aceitas estão no `.env.example` da raiz. Os SDKs oficiais funcionam apontando a base URL (testado com `openai` e `anthropic` em Python e em Node). Os dois formatos suportam streaming por SSE, no padrão de cada provider. `GET /openai/v1/models` e `GET /anthropic/v1/models` listam os modelos de cada um.

Como na API real, o formato Messages exige `max_tokens`. Nos dois formatos, `max_tokens` (e `max_completion_tokens` no formato OpenAI) trunca a saída e sinaliza o corte (`finish_reason: "length"` ou `stop_reason: "max_tokens"`).

## Modelos

| Modelo | Provider | Contexto | Tempo até o primeiro token | Velocidade | US$ por 1M tokens de entrada | US$ por 1M tokens de saída |
|---|---|---|---|---|---|---|
| `gpt-fake-large` | `openai` | 8.000 tokens | 800 ms | 40 tokens/s | 2,50 | 10,00 |
| `gpt-fake-mini` | `openai` | 8.000 tokens | 300 ms | 150 tokens/s | 0,15 | 0,60 |
| `claude-fake-large` | `anthropic` | 8.000 tokens | 800 ms | 40 tokens/s | 3,00 | 15,00 |
| `claude-fake-mini` | `anthropic` | 8.000 tokens | 300 ms | 150 tokens/s | 0,80 | 4,00 |

- Os modelos `large` dos dois providers são equivalentes entre si: mesma saída para a mesma entrada.
- Os modelos `mini` são mais rápidos e mais baratos, e têm qualidade inferior em pelo menos uma tarefa.
- Tokens são contados como `ceil(caracteres / 4)`. A entrada soma o texto de todas as mensagens (e do `system`, no formato Messages).
- A latência é real: o provider espera o tempo até o primeiro token e depois gera à velocidade do modelo. Sem streaming, a resposta chega inteira no fim.
- Entrada maior que o contexto do modelo gera `400`: `code: "context_length_exceeded"` no formato OpenAI, `invalid_request_error` no formato Messages.
- A saída é determinística: a mesma entrada no mesmo modelo gera sempre a mesma resposta.

## As quatro tarefas

O modelo simulado entende quatro tarefas (`classify`, `suggest`, `topics` e `extract`). A primeira linha da última mensagem do usuário define qual é; o resto da mensagem é o conteúdo. O system prompt e as instruções que você escrever não mudam o resultado.

```
TASK: classify
<texto de um ticket>
```

Saída: `{"category": "...", "priority": "..."}`, com `category` em `delivery`, `payment`, `exchange_return`, `product_defect`, `other` e `priority` em `low`, `medium`, `high`.

```
TASK: suggest
<texto de um ticket>
```

Saída: o texto de uma sugestão de resposta ao cliente, em português. É uma saída longa.

```
TASK: topics
[TK-00001] <texto do ticket>
[TK-00002] <texto do ticket>
...
```

Saída: `{"topics": [{"topic": "...", "count": n, "examples": ["TK-...", ...]}]}`, com até 3 exemplos por tema, ordenado por `count`. Os rótulos dos temas são em português. Linhas fora do formato `[id] texto` são ignoradas.

```
TASK: extract
<texto de um ticket>
```

Saída: `{"order_number": "#NNNNNN", "product": "..."}`, com `null` no campo que não for encontrado.

Sem uma linha `TASK:` reconhecida, o modelo responde um texto curto avisando que a tarefa não foi reconhecida. A saída JSON vem como texto no conteúdo da mensagem; não é preciso `response_format` nem tool use.

## Exemplos

curl, formato OpenAI:

```
curl -s localhost:8090/openai/v1/chat/completions \
  -H "Authorization: Bearer sk-fake-openai-0001" -H "Content-Type: application/json" \
  -d '{"model": "gpt-fake-large", "messages": [{"role": "user", "content": "TASK: classify\nMeu pedido #481516 não chegou, é urgente"}]}'
```

curl, formato Messages, com streaming:

```
curl -sN localhost:8090/anthropic/v1/messages \
  -H "x-api-key: sk-ant-fake-0001" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model": "claude-fake-large", "max_tokens": 2000, "stream": true, "messages": [{"role": "user", "content": "TASK: suggest\nMeu pedido #481516 não chegou"}]}'
```

Python:

```python
from openai import OpenAI
from anthropic import Anthropic

oa = OpenAI(base_url="http://localhost:8090/openai/v1", api_key="sk-fake-openai-0001")
r = oa.chat.completions.create(model="gpt-fake-large",
    messages=[{"role": "user", "content": "TASK: extract\nQuero trocar o pedido #605065"}])
print(r.choices[0].message.content, r.usage)

an = Anthropic(base_url="http://localhost:8090/anthropic", api_key="sk-ant-fake-0001")
with an.messages.stream(model="claude-fake-large", max_tokens=2000,
        messages=[{"role": "user", "content": "TASK: suggest\nMeu pedido não chegou"}]) as s:
    for trecho in s.text_stream:
        print(trecho, end="", flush=True)
```

Node:

```js
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";

const oa = new OpenAI({ baseURL: "http://localhost:8090/openai/v1", apiKey: "sk-fake-openai-0001" });
const r = await oa.chat.completions.create({ model: "gpt-fake-mini",
  messages: [{ role: "user", content: "TASK: classify\nFui cobrado duas vezes" }] });

const an = new Anthropic({ baseURL: "http://localhost:8090/anthropic", apiKey: "sk-ant-fake-0001" });
const m = await an.messages.create({ model: "claude-fake-mini", max_tokens: 500,
  messages: [{ role: "user", content: "TASK: extract\nPedido #605065 veio quebrado" }] });
```

Os SDKs oficiais repetem automaticamente algumas falhas (ex.: `429` e `5xx`) por padrão. Cada tentativa aparece como uma chamada separada em `/admin/calls`.

## Usando com o LiteLLM Proxy

Trecho mínimo de `model_list`, testado com a imagem `ghcr.io/berriai/litellm:v1.102.1`. Nomes lógicos, chaves virtuais, orçamentos, retries e fallbacks ficam por sua conta.

O LiteLLM não conhece os preços dos modelos simulados: sem declará-los na configuração (ver a tabela de Modelos e a documentação do LiteLLM sobre custo por token), ele calcula custo zero e nenhum orçamento estoura.

```yaml
model_list:
  - model_name: <nome lógico>
    litellm_params:
      model: openai/gpt-fake-large
      api_base: http://provider-fake:8090/openai/v1
      api_key: os.environ/FAKE_OPENAI_KEY
  - model_name: <outro nome lógico>
    litellm_params:
      model: anthropic/claude-fake-large
      api_base: http://provider-fake:8090/anthropic
      api_key: os.environ/FAKE_ANTHROPIC_KEY
```

## Administração

Os endpoints de administração não exigem autenticação.

```
POST /admin/failures
{"provider": "openai", "model": "gpt-fake-large", "mode": "error_500"}
```

- `provider`: `openai` ou `anthropic`
- `model`: opcional. Sem ele, o modo vale para o provider inteiro. Com ele, vale só para aquele modelo e tem precedência sobre o modo do provider (dá para derrubar o provider e manter um modelo específico em `normal`).
- `mode`: um dos abaixo

| Modo | Comportamento |
|---|---|
| `normal` | Responde normalmente |
| `error_500` | Responde `500` na hora, no formato de erro do provider |
| `error_429` | Responde `429` na hora, com header `Retry-After: 2` |
| `timeout` | Segura a conexão por 300 s sem enviar nenhum byte e então responde `504` |
| `slow` | Multiplica por 10 o tempo até o primeiro token e o intervalo entre tokens |
| `midstream_error` | Em streaming, envia cerca de um quarto da resposta e interrompe com um evento de erro no formato do provider (o SDK levanta exceção no meio da leitura). Sem streaming, responde `500` na hora |

```
GET  /admin/failures           modos configurados e o modo efetivo de cada modelo
GET  /admin/calls?last=N       últimas N chamadas de inferência recebidas (padrão 50), da mais recente para a mais antiga
POST /admin/reset              volta tudo ao modo normal e limpa o registro de chamadas
GET  /health                   200 {"status": "ok"}
```

Cada item de `/admin/calls` tem: `id`, `ts`, `provider`, `model`, `task`, `stream`, `status`, `input_tokens`, `output_tokens` e `duration_ms`.

- Toda requisição de inferência é registrada, inclusive as que falham (`401`, `400`, `404` e os modos de falha).
- O registro acontece no recebimento. `status` é o status que o provider devolve (ou vai devolver, no modo `timeout`; no `midstream_error` em streaming, passa de `200` para `500` quando o erro é enviado), `duration_ms` fica `null` enquanto a chamada não termina, e `output_tokens` fica `null` quando não houve geração completa.
- O registro guarda as últimas 5.000 chamadas, em memória. Reiniciar o container limpa tudo.

Exemplos:

```
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "mode": "error_500"}'
curl -s "localhost:8090/admin/calls?last=10"
curl -s -X POST localhost:8090/admin/reset
```

## Testes do próprio provider

Com o compose no ar:

```
pip install -r provider-fake/tests/requirements.txt
pytest provider-fake/tests -q
```
