from .ports import LanguageModel
from .schemas import ReplySuggestion, TicketInput

CAPABILITY = "reply-writer"


def suggest(ticket: TicketInput, model: LanguageModel) -> ReplySuggestion:
    text = model.complete(CAPABILITY, f"TASK: suggest\n{ticket.text}")
    return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
