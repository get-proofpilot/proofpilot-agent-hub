"""Pydantic I/O models for AutoPilot AI."""
from pydantic import BaseModel


class PipelineRunRequest(BaseModel):
    client_id: str
    page_type: str  # service_page | location_page | blog_post
    target_keyword: str
    service: str | None = None
    location: str | None = None
    notes: str | None = None


class StageUpdate(BaseModel):
    stage: str  # research | strategy | copywrite | design | images | qa
    status: str  # running | done | error
    round: int = 1


class PipelineResult(BaseModel):
    pipeline_id: str
    status: str  # running | complete | failed | revision
    stages: list[StageUpdate]
    qa_score: int | None = None
