"""FastAPI router for RedditPilot.

Existing hand-rolled routes live in backend/server.py under /api/reddit/*.
This router exists for future cutover to auto-mount — until then it's
a parallel health endpoint under the same prefix (server.py keeps the
40+ production routes).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["redditpilot"])


@router.get("/_health")
async def health() -> dict:
    return {"status": "ok", "agent": "redditpilot"}
