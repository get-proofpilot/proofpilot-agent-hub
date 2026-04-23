"""Pydantic I/O models for Pilot Core."""
from pydantic import BaseModel


class ContextSnapshot(BaseModel):
    timestamp: str
    total_clients: int
    overdue_clients: list[str]
    attention_clients: list[str]


class BriefingRequest(BaseModel):
    include_details: bool = True


class EscalationRequest(BaseModel):
    urgency_threshold: str = "attention"
