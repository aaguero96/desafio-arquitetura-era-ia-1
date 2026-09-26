from datetime import date
from typing import Protocol


class LanguageModel(Protocol):
    """Pede uma capacidade lógica; quem escolhe o modelo físico é o gateway."""

    def complete(self, capability: str, prompt: str) -> str: ...


class TicketSource(Protocol):
    """Fonte dos tickets usados no relatório."""

    def in_period(self, start: date, end: date) -> list[dict]: ...
