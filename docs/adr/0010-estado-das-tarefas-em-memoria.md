# 0010. Estado das tarefas assíncronas em memória, na própria aplicação

- Status: aceita
- Data: 2026-09-27
- Nível: software

## Contexto

A F3 passou a ser assíncrona (ADR 0008): o `POST` devolve `202` e o trabalho continua depois. Alguém precisa guardar o estado de cada tarefa (`pending`, `running`, `done`, `failed`), o progresso, o motivo da falha e o resultado, e alguém precisa executar o trabalho. O enunciado deixa fora de escopo sobreviver a um reinício da aplicação e deduplicar pedidos, e exige ADR para qualquer serviço novo (fila, banco, worker).

## Opções consideradas

1. Fila e worker separados (por exemplo, Redis com um serviço `worker`) e estado no Redis.
2. Estado no Postgres do gateway.
3. Estado em memória na própria aplicação, com um pool de threads executando as tarefas.

## Decisão

Opção 3: `app/helpdesk/jobs.py` guarda as tarefas num dicionário em memória e as executa num `ThreadPoolExecutor` de 2 workers; cada tarefa usa até 4 chamadas em paralelo (`report.PARALLEL_CALLS`). Qualquer exceção leva a tarefa a `failed` com motivo; o timeout de 50 s por lote garante que ela não fique presa em `running`.

A opção 1 ganharia sobrevivência a reinício e escala horizontal, que não são requisitos, e cobraria duas peças novas a operar e justificar. A opção 2 misturaria dados da aplicação no banco de outro serviço, acoplando o helpdesk ao esquema do gateway.

## Consequências

- Melhor: nenhuma peça nova no compose; o contrato 202/303 funciona com uma instância.
- Pior: reiniciar o `app` perde tarefas em andamento e resultados prontos (o status passa a responder `404`); com mais de uma réplica do `app`, o status teria de cair na mesma instância que recebeu o pedido. Os resultados ficam em memória até o próximo reinício.
- Quando reinício ou várias réplicas virarem requisito, esta decisão é substituída pela opção 1, e a interface de `jobs.py` (`submit`, `status`, `result`) é o ponto de troca.

## Evidência

- `docker compose ps` não tem fila, worker nem banco da aplicação.
- Pedido do mês: `202` em 0,04 s; status `running` com `progress` de `0/5000` a `5000/5000`; `303` aos ~90 s.
