"""Pydantic I/O models for QAPilot."""
from pydantic import BaseModel


class QARequest(BaseModel):
    content: str | None = None
    url: str | None = None
    keyword: str
    client_name: str
    business_type: str | None = None
    title_tag: str | None = None
    meta_description: str | None = None


class LayerFinding(BaseModel):
    layer: int
    name: str
    score: int | None
    status: str
    critical_issues: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []


class QAReport(BaseModel):
    overall_score: int
    verdict: str
    layers: list[LayerFinding]
    top_3_fixes: list[str]
    summary: str
