# 0008. Modo de execução por feature: F1 e F4 síncronas, F2 em streaming, F3 assíncrona

- Status: aceita
- Data: 2026-09-27
- Nível: solução

## Contexto

Na v1, as quatro features respondiam de forma síncrona, com o resultado inteiro no corpo. O diagnóstico mostrou onde isso quebra:

- **dor 1:** o relatório do mês leva ~5 min e a borda corta qualquer resposta sem bytes por 30 s (`edge/nginx.conf`, `proxy_read_timeout 30s`). Resultado: `504` aos 30 s, e a aplicação continuou gastando tokens por mais 5 min;
- **dor 2:** a sugestão leva 16,2 s e só aparece inteira no fim; o atendente olha para uma tela parada.

Latências medidas no provider (modo normal): `large` com ~0,8 s até o primeiro token e 40 tokens/s. A F1 e a F4 saem em ~1,2 s; a F2 gera ~600 tokens (~16 s); a F3 são 34 lotes de ~10 s.

A mudança de modo é uma evolução do contrato e por isso veio depois da tag `v2-decoupled`. As perguntas da árvore de decisão: alguém está esperando agora? cabe no orçamento de latência? é consumível aos poucos?

## Decisão

### F1 Classificar ticket: síncrona

- **Alguém está esperando agora?** Sim: o cliente, na abertura do ticket, esperando a confirmação na tela.
- **Cabe no orçamento de latência?** Sim: saída curta, de valores fixos, ~1,2 s no `large` contra um orçamento de 3 s. Mesmo no pior caso de fallback (~10 s) cabe nos 15 s do requisito e nos 30 s da borda.
- **É consumível aos poucos?** Não: `{"category", "priority"}` só tem valor completo; meio JSON não serve para nada.

Streaming não traria ganho em uma resposta de 1 s que não se consome aos poucos. Assíncrono obrigaria o cliente a fazer polling para um resultado que chega antes do primeiro polling. Timeout explícito de 13 s na aplicação; sem nenhum destino disponível, `503`.

### F2 Sugerir resposta: streaming (SSE)

- **Alguém está esperando agora?** Sim: o atendente, olhando a tela.
- **Cabe no orçamento de latência?** Não como resposta inteira: 16 s de tela parada é a dor 2.
- **É consumível aos poucos?** Sim: é texto longo, e o atendente começa a ler e editar assim que ele aparece.

Streaming muda a espera percebida: o primeiro trecho chega em ~0,85 s em vez de 16 s. Assíncrono seria errado aqui, porque alguém está olhando agora e polling atrasaria cada trecho. Contrato: `Content-Type: text/event-stream`, eventos `data: {"chunk": ...}`, `event: end` no fim e `event: error` se a geração quebrar no meio (o `200` já foi enviado). Se nenhum destino responde antes do primeiro trecho, a resposta é `503` em vez de um stream vazio. O header `X-Accel-Buffering: no` impede que o nginx da borda acumule os trechos.

### F3 Relatório de temas: assíncrona (Asynchronous Request-Reply)

- **Alguém está esperando agora?** Não: é um painel interno, "ninguém fica esperando olhando para ele".
- **Cabe no orçamento de latência?** Não: o mês inteiro são 34 chamadas de ~10 s. Mesmo em paralelo leva ~1,5 min, muito além dos 30 s da borda.
- **É consumível aos poucos?** Não: temas e contagens do mês só fazem sentido completos.

Streaming não resolveria: manteria a conexão aberta por minutos e ainda entregaria o resultado só no fim, resolvendo o `504` "por acidente" (bytes para enganar a borda) sem resolver o problema. Callback está descartado porque o painel "não expõe callback". Contrato: `202 Accepted` com `Location: /reports/topics/status/{id}` e `Retry-After: 5`; o status responde `200` com `pending`, `running` (com `progress: "feitos/total"`) ou `failed` (com `reason`), e `303 See Other` para `/reports/topics/{id}` quando chega a `done`. Um lote que não responde em 50 s derruba a tarefa, que chega a `failed` antes de 60 s e nunca fica presa em `running`.

A tarefa processa até 4 lotes em paralelo e junta os resultados na ordem dos lotes, então o relatório é idêntico ao sequencial (a suíte de caracterização compara com o snapshot da v1). Quando um lote falha, os lotes que ainda não começaram são cancelados, para não gastar tokens num relatório que já falhou.

### F4 Extrair dados do pedido: síncrona

- **Alguém está esperando agora?** Sim: a automação de troca e devolução, que chama e espera o resultado para seguir.
- **Cabe no orçamento de latência?** Sim: ~1,2 s, com o mesmo perfil da F1.
- **É consumível aos poucos?** Não: é um registro com dois campos que alimenta outra máquina.

Síncrona, com timeout de 13 s. Sem `large` disponível, a resposta é `503` explícito (ADR 0005), para a automação não seguir com dado incerto.

## Consequências

- Melhor: nenhuma feature termina em `504` da borda; o atendente vê texto em ~0,85 s; o relatório do mês sai em ~1,5 min, e quem pediu acompanha o progresso.
- Pior: a F3 passa a ter estado (ADR 0010) e o cliente precisa fazer polling; a F2 exige cliente que entenda SSE.
- O contrato de F2 e F3 mudou: `tests/characterization/` na `main` foi atualizado para o contrato novo, mas o conteúdo continua sendo comparado com os snapshots da v1 (mesmo texto, mesmo relatório).

## Evidência

Medido pela borda (`localhost:8000`), automatizado em `tests/acceptance/`:

- F1: `200` em 1,35 s.
- F2: `curl -N` com primeiro trecho em 0,86–1,0 s, total ~16,5 s, 607 eventos terminando em `event: end`. Com `midstream_error`: trechos e depois `event: error` com `{"ticket_id": "TK-00042", "message": "A geração foi interrompida"}`.
- F3: `202` em 0,04 s; progresso `150/5000` → `5000/5000`; `303` aos ~90 s; `total_tickets` igual a 5000; 34 chamadas `topics` em `/admin/calls`. Com os dois providers em `error_500`: `failed` aos 14 s com `reason: "topic-analyzer: nenhum destino respondeu (InternalServerError 500)"`. Com os dois em `timeout`: `failed` aos 52 s.
