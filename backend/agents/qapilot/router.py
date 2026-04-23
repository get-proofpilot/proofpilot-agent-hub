"""FastAPI router for QAPilot.

Existing hand-rolled route lives in backend/server.py at /api/agents/qa.
This router exists for future cutover to auto-mount — until then it's a
parallel path under the same prefix (auto-mount is opt-in via
backend/agents/__init__.py, and server.py still owns production).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["qapilot"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "qapilot"}
