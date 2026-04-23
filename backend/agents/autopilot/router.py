"""FastAPI router for AutoPilot AI.

Existing hand-rolled routes live in backend/server.py under /api/pipeline/*.
This router exists for future cutover to auto-mount — until then it's
a parallel path under the same prefix. Kept intentionally empty (just
a health endpoint) so the auto-mount doesn't collide with server.py's
production routes during the migration.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["autopilot"])


@router.get("/_health")
async def health() -> dict:
    return {"status": "ok", "agent": "autopilot"}
