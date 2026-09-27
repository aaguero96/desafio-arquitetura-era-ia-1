import json
from collections.abc import Callable
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from threading import Lock

from fastapi import HTTPException

from .ports import LanguageModel, TicketSource
from .schemas import PeriodInput, Topic, TopicsReport

CAPABILITY = "topic-analyzer"
TICKETS_PER_CALL = 150
# Lotes em paralelo: o mês (34 lotes de ~10 s) sai em ~1,5 min em vez de ~6 min.
PARALLEL_CALLS = 4
# Um lote que não responde nisso (cadeia de fallback do gateway incluída) derruba a
# tarefa: ela chega a `failed` antes de 60 s e nunca fica presa em `running`.
TIMEOUT_SECONDS = 50


def check_period(period: PeriodInput) -> None:
    if period.start > period.end:
        raise HTTPException(status_code=422, detail="A data inicial é posterior à data final")


def topics(period: PeriodInput, model: LanguageModel, tickets: TicketSource,
           on_progress: Callable[[int, int], None] = lambda done, total: None) -> TopicsReport:
    check_period(period)
    selected = tickets.in_period(period.start, period.end)
    batches = [selected[first:first + TICKETS_PER_CALL] for first in range(0, len(selected), TICKETS_PER_CALL)]

    done = 0
    lock = Lock()
    on_progress(done, len(selected))

    def analyze(batch: list[dict]) -> dict:
        nonlocal done
        content = "\n".join(f"[{t['id']}] {t['text']}" for t in batch)
        answer = json.loads(model.complete(CAPABILITY, f"TASK: topics\n{content}", timeout=TIMEOUT_SECONDS))
        with lock:
            done += len(batch)
            on_progress(done, len(selected))
        return answer

    pool = ThreadPoolExecutor(PARALLEL_CALLS)
    futures = [pool.submit(analyze, batch) for batch in batches]
    finished, _ = wait(futures, return_when=FIRST_EXCEPTION)
    failed = next((f for f in finished if f.exception()), None)
    # Um lote falhou: os que nem começaram são cancelados e a falha sobe na hora,
    # sem esperar os lotes que ainda estão em andamento.
    pool.shutdown(wait=failed is None, cancel_futures=True)
    if failed:
        raise failed.exception()
    answers = [future.result() for future in futures]

    # Junta na ordem dos lotes, como na versão sequencial: o resultado não muda.
    totals: dict[str, dict] = {}
    for answer in answers:
        for item in answer["topics"]:
            current = totals.setdefault(item["topic"], {"count": 0, "examples": []})
            current["count"] += item["count"]
            current["examples"] = (current["examples"] + item["examples"])[:3]

    items = [Topic(topic=name, **data) for name, data in totals.items()]
    items.sort(key=lambda t: (-t.count, t.topic))
    return TopicsReport(start=period.start, end=period.end, total_tickets=len(selected), topics=items)
