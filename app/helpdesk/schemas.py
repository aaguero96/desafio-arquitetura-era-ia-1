from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class TicketInput(BaseModel):
    ticket_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Classification(BaseModel):
    ticket_id: str
    category: str
    priority: str


class OrderData(BaseModel):
    ticket_id: str
    order_number: str | None
    product: str | None


class PeriodInput(BaseModel):
    start: date
    end: date


class Topic(BaseModel):
    topic: str
    count: int
    examples: list[str]


class TopicsReport(BaseModel):
    start: date
    end: date
    total_tickets: int
    topics: list[Topic]


class JobStatus(BaseModel):
    state: Literal["pending", "running", "done", "failed"]
    progress: str | None = None
    reason: str | None = None
