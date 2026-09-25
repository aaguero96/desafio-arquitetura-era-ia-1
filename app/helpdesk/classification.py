from fastapi import HTTPException

from . import config, llm
from .schemas import Classification, TicketInput

CATEGORIES = {"delivery", "payment", "exchange_return", "product_defect", "other"}
PRIORITIES = {"low", "medium", "high"}


def classify(ticket: TicketInput) -> Classification:
    text = llm.call_openai(config.CLASSIFICATION_MODEL, "classify", ticket.text)
    data = llm.parse_json(text)
    if data.get("category") not in CATEGORIES or data.get("priority") not in PRIORITIES:
        raise HTTPException(status_code=502, detail="Classificação fora dos valores permitidos")
    return Classification(ticket_id=ticket.ticket_id, **data)
