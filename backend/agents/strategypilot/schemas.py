"""Pydantic I/O models for StrategyPilot."""
from pydantic import BaseModel


class StrategyRequest(BaseModel):
    domain: str
    service: str
    location: str
    competitors: str | None = None
    notes: str | None = None


class PageRecommendation(BaseModel):
    title: str
    url_slug: str
    primary_keyword: str
    search_volume: int
    priority: str  # P1 | P2 | P3
