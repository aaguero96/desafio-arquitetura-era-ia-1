from collections.abc import Iterator

from .ports import LanguageModel
from .schemas import TicketInput

CAPABILITY = "reply-writer"
# Tempo máximo sem receber texto (antes do primeiro trecho e entre trechos).
# Cobre a cadeia de fallback do gateway antes do primeiro trecho.
IDLE_TIMEOUT_SECONDS = 15


def suggest(ticket: TicketInput, model: LanguageModel) -> Iterator[str]:
    """Trechos da sugestão, na ordem em que o modelo os gera."""
    return model.stream(CAPABILITY, f"TASK: suggest\n{ticket.text}", timeout=IDLE_TIMEOUT_SECONDS)
