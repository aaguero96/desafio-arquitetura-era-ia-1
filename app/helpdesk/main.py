import json
import os
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import classification, extraction, report, suggestion
from .adapters.gateway import GatewayLanguageModel
from .adapters.tickets_file import JsonlTicketSource
from .jobs import Jobs
from .ports import GenerationInterrupted, ModelUnavailable
from .schemas import Classification, JobStatus, OrderData, PeriodInput, TicketInput, TopicsReport

# Ponto de composição: só aqui se conhecem os adapters concretos e o ambiente.
MAX_OUTPUT_TOKENS = 2000
REPORT_RETRY_AFTER_SECONDS = 5

model = GatewayLanguageModel(os.environ["GATEWAY_URL"], os.environ["GATEWAY_API_KEY"], MAX_OUTPUT_TOKENS)
tickets = JsonlTicketSource(os.environ.get("TICKETS_FILE", "/data/tickets.jsonl"))
report_jobs = Jobs(workers=2)

app = FastAPI(title="Helpdesk")


@app.exception_handler(ModelUnavailable)
def model_unavailable(request: Request, error: ModelUnavailable) -> JSONResponse:
    # Falha explícita: nenhum destino permitido pela política de fallback respondeu.
    return JSONResponse(status_code=503, content={"detail": "Modelo indisponível no momento; tente novamente."})


@app.get("/health")
def health():
    return {"status": "ok"}


# F1: síncrona. O cliente espera na tela uma saída curta.
@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(ticket, model)


# F2: streaming (SSE). O atendente lê enquanto o texto chega.
@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> StreamingResponse:
    chunks = suggestion.suggest(ticket, model)
    # O primeiro trecho é buscado antes de enviar o status: se nenhum modelo
    # responder, ModelUnavailable vira 503 em vez de um stream vazio.
    first = next(chunks, "")
    return StreamingResponse(
        _sse(ticket.ticket_id, first, chunks),
        media_type="text/event-stream",
        # Sem buffer no caminho: o nginx da borda honra X-Accel-Buffering.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(ticket_id: str, first: str, rest: Iterator[str]) -> Iterator[str]:
    def event(data: dict, name: str | None = None) -> str:
        head = f"event: {name}\n" if name else ""
        return f"{head}data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        if first:
            yield event({"chunk": first})
        for chunk in rest:
            yield event({"chunk": chunk})
    except (GenerationInterrupted, ModelUnavailable):
        # O status 200 já foi enviado: o erro chega como evento dentro do stream.
        yield event({"ticket_id": ticket_id, "message": "A geração foi interrompida"}, "error")
        return
    yield event({"ticket_id": ticket_id}, "end")


# F4: síncrona. Alimenta uma automação; sem modelo confiável, falha explícita (503).
@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(ticket, model)


# F3: Asynchronous Request-Reply. Ninguém espera olhando; o painel consulta o status.
@app.post("/reports/topics", status_code=202)
def request_topics_report(period: PeriodInput) -> JSONResponse:
    report.check_period(period)
    job_id = report_jobs.submit(lambda progress: report.topics(period, model, tickets, progress))
    return JSONResponse(
        status_code=202,
        content={"id": job_id, "state": "pending"},
        headers={"Location": f"/reports/topics/status/{job_id}",
                 "Retry-After": str(REPORT_RETRY_AFTER_SECONDS)},
    )


@app.get("/reports/topics/status/{job_id}", response_model=None)
def topics_report_status(job_id: str) -> JobStatus | RedirectResponse:
    status = report_jobs.status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if status.state == "done":
        return RedirectResponse(f"/reports/topics/{job_id}", status_code=303)
    return status


@app.get("/reports/topics/{job_id}")
def topics_report(job_id: str) -> TopicsReport:
    result = report_jobs.result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado ou ainda não concluído")
    return result
