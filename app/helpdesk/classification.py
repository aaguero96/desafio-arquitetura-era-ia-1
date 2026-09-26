import json

from fastapi import HTTPException

from .ports import LanguageModel
from .schemas import Classification, TicketInput

CAPABILITY = "ticket-classifier"
CATEGORIES = {"delivery", "payment", "exchange_return", "product_defect", "other"}
PRIORITIES = {"low", "medium", "high"}


def classify(ticket: TicketInput, model: LanguageModel) -> Classification:
    text = model.complete(CAPABILITY, f"TASK: classify\n{ticket.text}")
    data = json.loads(text)
    if data.get("category") not in CATEGORIES or data.get("priority") not in PRIORITIES:
        raise HTTPException(status_code=502, detail="Classificação fora dos valores permitidos")
    return Classification(ticket_id=ticket.ticket_id, **data)
