import os

from fastapi import FastAPI

from . import classification, extraction, report, suggestion
from .adapters.gateway import GatewayLanguageModel
from .adapters.tickets_file import JsonlTicketSource
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

# Ponto de composição: só aqui se conhecem os adapters concretos e o ambiente.
MAX_OUTPUT_TOKENS = 2000

model = GatewayLanguageModel(os.environ["GATEWAY_URL"], os.environ["GATEWAY_API_KEY"], MAX_OUTPUT_TOKENS)
tickets = JsonlTicketSource(os.environ.get("TICKETS_FILE", "/data/tickets.jsonl"))

app = FastAPI(title="Helpdesk")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(ticket, model)


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> ReplySuggestion:
    return suggestion.suggest(ticket, model)


@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(ticket, model)


@app.post("/reports/topics")
def topics_report(period: PeriodInput) -> TopicsReport:
    return report.topics(period, model, tickets)
