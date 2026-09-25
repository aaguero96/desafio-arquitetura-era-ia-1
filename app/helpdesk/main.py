from fastapi import FastAPI

from . import classification, extraction, report, suggestion
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

app = FastAPI(title="Helpdesk")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(ticket)


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> ReplySuggestion:
    return suggestion.suggest(ticket)


@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(ticket)


@app.post("/reports/topics")
def topics_report(period: PeriodInput) -> TopicsReport:
    return report.topics(period)
