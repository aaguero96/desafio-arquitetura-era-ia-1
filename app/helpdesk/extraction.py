import json
import re

from fastapi import HTTPException

from .ports import LanguageModel
from .schemas import OrderData, TicketInput

# O cliente espera na tela: a resposta (com ou sem fallback) sai antes dos 15 s.
TIMEOUT_SECONDS = 13
CAPABILITY = "order-extractor"
ORDER_FORMAT = re.compile(r"^#\d{6}$")


def extract(ticket: TicketInput, model: LanguageModel) -> OrderData:
    text = model.complete(CAPABILITY, f"TASK: extract\n{ticket.text}", timeout=TIMEOUT_SECONDS)
    data = json.loads(text)
    order_number = data.get("order_number")
    if order_number is not None and not ORDER_FORMAT.match(order_number):
        raise HTTPException(status_code=502, detail="Número de pedido em formato inválido")
    return OrderData(ticket_id=ticket.ticket_id, order_number=order_number, product=data.get("product"))
