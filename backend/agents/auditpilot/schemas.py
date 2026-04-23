"""Pydantic I/O models for AuditPilot."""
from pydantic import BaseModel


class AuditRequest(BaseModel):
    domain: str
    service: str
    location: str
    monthly_revenue: str | None = None
    avg_job_value: str | None = None
    notes: str | None = None


class AuditStage(BaseModel):
    name: str
    status: str  # "running" | "done" | "error"
    output: dict | None = None
