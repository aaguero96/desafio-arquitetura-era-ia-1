from . import config, llm
from .schemas import ReplySuggestion, TicketInput


def suggest(ticket: TicketInput) -> ReplySuggestion:
    text = llm.call_anthropic(config.SUGGESTION_MODEL, "suggest", ticket.text)
    return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
