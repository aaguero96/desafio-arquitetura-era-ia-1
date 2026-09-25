import re

from fastapi import HTTPException

from . import config, llm
from .schemas import OrderData, TicketInput

ORDER_FORMAT = re.compile(r"^#\d{6}$")


def extract(ticket: TicketInput) -> OrderData:
    text = llm.call_openai(config.EXTRACTION_MODEL, "extract", ticket.text)
    data = llm.parse_json(text)
    order_number = data.get("order_number")
    if order_number is not None and not ORDER_FORMAT.match(order_number):
        raise HTTPException(status_code=502, detail="Número de pedido em formato inválido")
    return OrderData(ticket_id=ticket.ticket_id, order_number=order_number, product=data.get("product"))
