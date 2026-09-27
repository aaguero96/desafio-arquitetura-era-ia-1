# 0003. LiteLLM Proxy self-hosted como AI Gateway, entre a aplicação e os providers

- Status: aceita
- Data: 2026-09-27
- Nível: solução

## Contexto

Na v1, a aplicação dependia de detalhes concretos e voláteis de cada provider: SDK, formato da API, nome do modelo, credencial. A métrica mostrou isso como `llm` (D = 0,80) e `config` (D = 1,00) na zona de dor, e o diagnóstico mostrou o efeito: trocar um modelo exigiu reconstruir e recriar o container (dor 4, 23 s fora do ar), e cada feature herdava as falhas do seu provider sem alternativa (dor 3). Credencial, custo, limites e resiliência estavam espalhados, ou simplesmente não existiam.

Restrições do desafio: o gateway precisa ser self-hosted e subir no compose, sem serviço externo; precisa oferecer nomes lógicos, chaves próprias, orçamento, limite de requisições, timeout, retry e fallback.

## Opções consideradas

1. Biblioteca dentro da aplicação (por exemplo, o SDK do LiteLLM importado no `app`).
2. Gateway próprio escrito em FastAPI.
3. LiteLLM Proxy self-hosted como serviço `gateway`.
4. Gateway SaaS: descartado de saída pela restrição de rodar localmente.

## Decisão

Opção 3, posicionado entre a aplicação e os providers: `app → gateway → provider-fake`. A aplicação fala com ele no formato OpenAI (um único SDK, um único adapter, `adapters/gateway.py`), pede uma capacidade lógica (ADR 0004) e se autentica com uma chave virtual (ADR 0006). O gateway é o único dono das chaves dos providers, dos modelos físicos, dos preços, dos retries e do fallback (ADR 0005).

Uma biblioteca na aplicação (opção 1) resolveria o formato, mas não tiraria as credenciais da aplicação nem permitiria trocar modelo sem reiniciar o `app`. Um gateway próprio (opção 2) daria controle total, mas reimplementaria chaves virtuais, orçamento por token e rate limit, que não são o foco. O LiteLLM é a sugestão do curso e o provider-fake já foi testado com a versão `v1.102.1`, que é a fixada no compose.

## Consequências

- Melhor: trocar o modelo de uma capacidade é editar `gateway/config.yaml` e reiniciar só o `gateway` (README, "Troca de modelo"); governança e resiliência ficam num lugar só.
- Pior: mais um salto de rede (medido: o primeiro trecho da F2 chega em ~0,85 s direto no provider e em ~0,85 s pelo gateway, sem diferença perceptível) e mais peças a operar: o gateway precisa de banco para as chaves virtuais (ADR 0007).
- Limitação encontrada: o LiteLLM não sabe o preço dos modelos simulados e calcularia custo zero; os preços do README do provider foram declarados em `gateway/config.yaml` (`input_cost_per_token`, `output_cost_per_token`), senão nenhum orçamento estouraria.
- O gateway sobe em ~45 s (migrações do banco); o compose só libera o `app` depois dele e do provisionamento das chaves.

## Evidência

- `docker compose ps` mostra o serviço `gateway` (imagem `ghcr.io/berriai/litellm:v1.102.1`).
- `/admin/calls` registra cada chamada com o modelo físico escolhido pelo gateway, enquanto `grep -rE "gpt-fake|claude-fake" app/` não retorna nada.
- `grep -rln "from openai" app/helpdesk` retorna só `app/helpdesk/adapters/gateway.py`.
