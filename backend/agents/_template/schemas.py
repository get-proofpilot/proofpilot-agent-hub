"""Pydantic I/O models for this Pilot.

Keeps route contracts typed and self-documenting. Imported by router.py
and engine.py so request validation and internal function signatures
stay in sync.
"""
from pydantic import BaseModel


class RunRequest(BaseModel):
    client_name: str
    notes: str | None = None


class RunResponse(BaseModel):
    job_id: str
    status: str
