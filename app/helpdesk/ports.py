from collections.abc import Iterator
from datetime import date
from typing import Protocol


class ModelUnavailable(Exception):
    """Nenhum destino da capacidade respondeu (primário, fallback técnico e, se houver, modelo fraco)."""


class GenerationInterrupted(Exception):
    """A geração começou a chegar e foi interrompida no meio."""


class LanguageModel(Protocol):
    """Pede uma capacidade lógica; quem escolhe o modelo físico é o gateway."""

    def complete(self, capability: str, prompt: str, *, timeout: float) -> str: ...

    def stream(self, capability: str, prompt: str, *, timeout: float) -> Iterator[str]: ...


class TicketSource(Protocol):
    """Fonte dos tickets usados no relatório."""

    def in_period(self, start: date, end: date) -> list[dict]: ...
