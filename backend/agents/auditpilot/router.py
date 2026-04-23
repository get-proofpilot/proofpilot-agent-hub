"""FastAPI router for AuditPilot.

Existing hand-rolled route lives in backend/server.py at /api/agents/audit.
This router exists for future cutover to auto-mount.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["auditpilot"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "auditpilot"}
