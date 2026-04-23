"""FastAPI router for StrategyPilot.

Existing hand-rolled route lives in backend/server.py at /api/agents/strategy.
This router exists for future cutover to auto-mount.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["strategypilot"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "strategypilot"}
