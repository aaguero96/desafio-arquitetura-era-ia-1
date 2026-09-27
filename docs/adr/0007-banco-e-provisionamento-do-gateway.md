# 0007. Serviços `gateway-db` e `gateway-init`: banco do gateway e chaves criadas sem passo manual

- Status: aceita
- Data: 2026-09-27
- Nível: software

## Contexto

O requisito 5 pede chaves do próprio gateway, uma com orçamento e outra com limite de requisições (ADR 0006). No LiteLLM, chaves virtuais, gasto acumulado e orçamentos só existem com banco de dados (Postgres); sem banco, só há a chave mestra. E os critérios exigem que `cp .env.example .env && docker compose up -d --build --wait` suba tudo sem passo manual, então as chaves não podem ser criadas à mão pela interface ou por `curl`.

Esta decisão adiciona dois serviços ao compose além de `app` e `gateway`, e por isso precisa de justificativa própria.

## Opções consideradas

1. Usar só a chave mestra do gateway na aplicação, sem banco. Não atende o requisito: não há orçamento nem limite por chave.
2. Criar as chaves dentro do container do gateway, trocando o entrypoint por um script que sobe o LiteLLM em segundo plano e chama a API.
3. Banco dedicado (`gateway-db`) e um serviço de execução única (`gateway-init`) que cria as chaves declaradas em `gateway/keys.json` e termina.

## Decisão

Opção 3.

- **`gateway-db`** (`postgres:16-alpine`): existe porque chaves virtuais, orçamento e gasto por chave (requisito 5, governança mínima) exigem persistência no LiteLLM. É usado só pelo gateway.
- **`gateway-init`** (mesma imagem do LiteLLM, só para ter Python): roda `gateway/provision.py`, que espera o gateway ficar saudável e cria ou atualiza cada chave de `gateway/keys.json`, com o valor vindo do `.env`. É idempotente: numa nova subida, atualiza as chaves existentes e zera o gasto das chaves de demonstração, para o roteiro de governança ser repetível. O `app` só sobe depois dele (`condition: service_completed_successfully`).

A opção 2 esconderia o provisionamento dentro do processo do gateway, misturando dois ciclos de vida: um erro de provisionamento derrubaria o gateway, e reiniciar o gateway para trocar um modelo (ADR 0004) re-executaria o provisionamento. Com um serviço separado, a política de chaves fica declarada num arquivo versionado e o erro fica isolado e visível (`docker compose logs gateway-init`).

## Consequências

- Melhor: subida em um comando; política de chaves versionada em `gateway/keys.json`; nenhum passo manual.
- Pior: mais duas peças no compose; a subida do zero leva ~2 min (o gateway roda as migrações do banco antes de ficar saudável).
- O banco não tem volume nomeado: `docker compose down -v` apaga chaves e gasto. Como o `gateway-init` recria as chaves a cada subida, isso não quebra nada neste ambiente. Em produção, o banco precisaria de volume e backup.
- `docker compose up --wait` termina com código 0 mesmo com o `gateway-init` saindo (verificado com Compose v5.1.3), porque o serviço termina com sucesso.

## Evidência

- `docker compose logs gateway-init`: `chave helpdesk-app criada`, `chave demo-budget criada`, `chave demo-rpm criada` (ou `atualizada` nas subidas seguintes).
- `curl -s localhost:4000/key/list?return_full_object=true -H "Authorization: Bearer sk-gateway-master-0001"` lista as três chaves com `max_budget` e `rpm_limit`.
