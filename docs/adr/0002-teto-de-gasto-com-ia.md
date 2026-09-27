# 0002. Teto de gasto com IA do helpdesk: US$ 50 a cada 30 dias

- Status: aceita
- Data: 2026-09-27
- Nível: corporativa

## Contexto

Na v1, gasto com IA não tinha dono nem limite. O diagnóstico (README, dor 1) mediu o pior caso: um único pedido do relatório mensal gastou cerca de US$ 0,85 (34 chamadas, 222 mil tokens de entrada e 12 mil de saída no `claude-fake-large`) e o resultado foi jogado fora, porque a borda já tinha devolvido `504` ao usuário. Nada impedia um painel de repetir o pedido a cada minuto.

Ordem de grandeza do uso esperado, com os preços do README do provider:

| operação | custo aproximado |
|---|---|
| F1 ou F4 (um ticket, `gpt-fake-large`) | US$ 0,0002 |
| F2 (um ticket, `claude-fake-large`, ~600 tokens de saída) | US$ 0,009 |
| F3 (mês inteiro, 34 lotes) | US$ 0,85 |

Um volume de 5.000 tickets por mês com F1, F2 e F4 em todos, mais alguns relatórios, fica perto de US$ 50.

## Opções consideradas

1. Sem teto, acompanhar a fatura no fim do mês.
2. Teto por feature.
3. Teto único para o helpdesk, aplicado na chave que a aplicação usa no gateway.

## Decisão

Opção 3: o helpdesk tem um teto de US$ 50 a cada 30 dias. É uma decisão de negócio (quanto a empresa aceita gastar com IA no atendimento), por isso fica neste nível; a forma de aplicá-la é técnica e está no ADR 0006 (orçamento na chave virtual `helpdesk-app`, com `budget_duration: 30d`).

Teto por feature (opção 2) foi descartado por ora: ainda não há histórico de uso real para dividir o valor, e dividir errado derruba uma feature enquanto sobra verba em outra.

## Consequências

- Melhor: o gasto tem limite conhecido e um dono; estourar vira evento visível, não surpresa na fatura.
- Pior: ao estourar o teto, as quatro features param de chamar modelos até o próximo período (o gateway recusa com `429 budget_exceeded` antes de chegar ao provider). É uma escolha consciente: melhor parar e ser notado do que gastar sem limite.
- Passa a ser necessário: revisar o valor quando houver histórico de uso real.

## Evidência

`gateway/keys.json`, chave `helpdesk-app`: `"max_budget": 50.0, "budget_duration": "30d"`. O efeito de um orçamento estourado é demonstrado no roteiro de governança do README com a chave `demo-budget`.
