# 0009. Leitura da métrica de acoplamento, com `schemas` declarado estável por natureza

- Status: aceita
- Data: 2026-09-27
- Nível: software

## Contexto

A régua é fixa (requisito 3): Ca, Ce, I = Ce/(Ce+Ca), A = classes abstratas (herdam de `Protocol` ou `ABC`) / classes, D = |A + I − 1|, por módulo `.py` de `app/helpdesk/`. `metrics/coupling.py` implementa essa régua; `tests/metrics/test_coupling.py` confere o script contra valores calculados à mão num pacote sintético (subpasta, `from ..x import`, import absoluto `helpdesk.x`, `Protocol` e `abc.ABC`). Para a `v1-coupled`, os números do script batem com a conta manual de todos os módulos (por exemplo, `config`: importado por 6 módulos e sem imports internos, então Ca=6, Ce=0, I=0, A=0 e D=1).

A zona de dor é A < 0,5, I < 0,5 e D ≥ 0,5: um componente concreto e muito usado, que é difícil de mudar e ainda assim muda.

## Leitura das três medições

| componente | v1-coupled (Ca/Ce/I/A/D) | v2-decoupled | main |
|---|---|---|---|
| config | 6/0/0,00/0,00/**1,00** (dor) | removido | removido |
| llm | 4/1/0,20/0,00/**0,80** (dor) | removido | removido |
| tickets | 1/1/0,50/0,00/0,50 | virou `adapters.tickets_file` | idem |
| ports | — | 6/0/0,00/1,00/0,00 | 7/0/0,00/0,50/0,50 |
| adapters.gateway | — | 1/1/0,50/0,00/0,50 | 1/1/0,50/0,00/0,50 |
| adapters.tickets_file | — | 1/1/0,50/0,00/0,50 | 1/1/0,50/0,00/0,50 |
| jobs | — | — | 1/1/0,50/0,00/0,50 |
| features (4) | 1/3/0,75/0,00/0,25 (report: 1/4/0,80/0,00/0,20) | 1/2/0,67/0,00/0,33 | 1/2/0,67/0,00/0,33 |
| main | 0/5/1,00/0,00/0,00 | 0/7/1,00/0,00/0,00 | 0/9/1,00/0,00/0,00 |
| schemas | 5/0/0,00/0,00/**1,00** | 5/0/0,00/0,00/**1,00** | 6/0/0,00/0,00/**1,00** |

- **O que saiu da zona de dor e por quê:** `config` e `llm` concentravam o fan-in (Ca=6 e Ca=4) sendo concretos e voláteis (modelo, provider, credencial). O fan-in foi transferido para `ports`, que é abstrato: quem é muito usado passou a ser o que menos muda. O piloto mostrou que só pôr um Protocol dentro de `llm` baixava D sem mudar a dependência real (plano, revisão 1).
- **`ports` na main (A=0,5, D=0,5):** ganhou `ModelUnavailable` e `GenerationInterrupted`, que são parte do contrato da porta: é por eles que as features e o ponto de composição sabem que nenhum destino respondeu ou que o stream quebrou, sem conhecer exceções do SDK. Isso baixou A de 1,0 para 0,5 e deixou `ports` fora da zona de dor (A não é < 0,5), mas no limite. A leitura: exceções são tipos de valor estáveis, e o que muda (o SDK) está do outro lado da porta.
- **Adapters e `jobs` com I=0,5, D=0,5:** concretos, usados só pelo ponto de composição e dependendo só de abstrações ou tipos (`ports`, `schemas`). Ficam fora da zona de dor (I não é < 0,5). Isso é consequência da estrutura, não um ajuste: o adapter importa a porta porque a implementa e traduz erros para ela; `jobs` importa `schemas` porque devolve `JobStatus`.
- **Features perto da sequência principal (D=0,33):** instáveis como devem ser: dependem de `ports` e `schemas` e ninguém além do `main` depende delas.

## Opções consideradas para `schemas`

1. Tornar `schemas` abstrato ou instável para sair da zona (por exemplo, Protocols para os modelos pydantic, ou imports artificiais).
2. Declarar `schemas` estável por natureza.

## Decisão

Opção 2, com justificativa. `schemas` contém só tipos de valor pydantic (`TicketInput`, `Classification`, `OrderData`, `PeriodInput`, `Topic`, `TopicsReport`, `JobStatus`) que espelham o contrato HTTP das quatro features, que o enunciado declara fixo ("as quatro features são fixas no que recebem e no resultado que produzem"). Eles não mudam quando o modelo, o provider, o gateway ou o modo de execução mudam; nas três versões, a única mudança foi acrescentar `JobStatus` e remover `ReplySuggestion` quando o contrato da F2 e da F3 foi evoluído de propósito. Muito usado e concreto é o esperado de tipos de valor; a opção 1 seria desenhar código em função da fórmula.

Não entram na exceção, por regra: o componente que chama o gateway (`adapters.gateway`) e os componentes das features. Nenhum deles está na zona de dor.

## Consequências

- `schemas` fica na zona de dor pela fórmula, declarado aqui. Se algum dia passar a conter lógica ou dependências de infraestrutura, a exceção deixa de valer.
- A régua não é ajustada: o mesmo `metrics/coupling.py` mede as três versões.

## Evidência

- `metrics/results/v1-coupled.csv`, `v2-decoupled.csv` e `main.csv`, com os gráficos `.png` correspondentes.
- `git worktree add ../v1 v1-coupled && python metrics/coupling.py ../v1/app/helpdesk v1-coupled` reproduz o CSV versionado da v1.
- `python -m pytest tests/metrics -q` confere o script contra valores calculados à mão.
