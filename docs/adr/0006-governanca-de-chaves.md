# 0006. Governança: chaves virtuais por consumidor, com orçamento e limite de requisições no gateway

- Status: aceita
- Data: 2026-09-27
- Nível: solução

## Contexto

Na v1, a aplicação usava as chaves dos providers diretamente, sem limite de gasto nem de volume (dor 1: um relatório abandonado gastou ~US$ 0,85 sem ninguém ver). O ADR 0002 fixou um teto de US$ 50 a cada 30 dias. Falta decidir como aplicar esse teto e como impedir que um consumidor descontrolado (um painel em loop, um bug de retry) consuma a cota dos outros, e em que ponto a recusa acontece.

## Opções consideradas

1. Contar tokens e gasto dentro da aplicação.
2. Usar a chave do provider com os limites da conta no fornecedor.
3. Chaves virtuais no gateway, uma por consumidor, cada uma com orçamento e/ou limite de requisições.

## Decisão

Opção 3. Cada consumidor tem sua chave virtual, declarada em `gateway/keys.json` e criada automaticamente na subida (ADR 0007):

| chave | usada por | modelos permitidos | orçamento | limite |
|---|---|---|---|---|
| `helpdesk-app` | serviço `app` | as 4 capacidades | US$ 50 a cada 30 dias (ADR 0002) | 600 requisições/min |
| `demo-budget` | roteiro de governança | `ticket-classifier` | US$ 0,0001 | — |
| `demo-rpm` | roteiro de governança | `ticket-classifier` | — | 1 requisição/min |

O gateway confere orçamento e limite **antes** de chamar o provider: a requisição recusada não gera chamada nem custo. O custo é calculado com os preços declarados em `gateway/config.yaml` (sem eles, o LiteLLM calcularia custo zero e o orçamento nunca estouraria).

A opção 1 espalharia contabilidade por cada serviço e não protegeria de um serviço que ignorasse a regra. A opção 2 limita a conta inteira da empresa, não um consumidor, e a recusa aconteceria no fornecedor, depois de a requisição ter saído.

O limite de 600/min da `helpdesk-app` fica bem acima do uso legítimo (o relatório do mês faz 34 chamadas em ~90 s) e serve de trava contra loops.

## Consequências

- Melhor: gasto e volume têm limite por consumidor; recusas são baratas e visíveis (`429` com o motivo).
- Pior: o gasto só é contabilizado quando a chamada termina; uma chamada que começa com saldo pode terminar acima do orçamento (na demonstração, a chave de US$ 0,0001 fecha em US$ 0,000135). O orçamento é um teto aproximado, não exato.
- Passa a ser necessário: um banco para o gateway guardar chaves e gasto (ADR 0007).

## Evidência

Roteiro de governança do README (executado):

- `demo-budget`: 1ª requisição `200`; 2ª `429 budget_exceeded` ("Current cost: 0.000135, Max budget: 0.0001").
- `demo-rpm`: 1ª requisição `200`; 2ª `429` ("Rate limit exceeded ... Limit type: requests. Current limit: 1").
- `/admin/calls` passou de 1 para 1 chamada na recusa por orçamento e de 2 para 2 na recusa por limite: as recusas não chegaram ao provider.
