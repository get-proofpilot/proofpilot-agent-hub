"""FastAPI router for Pilot Core.

Routes are currently mounted hand-rolled in backend/server.py for
backward compatibility. This router exists so a future cutover can
drop server.py wiring by just enabling the auto-mount in
backend/agents/__init__.py (already wired).

Keep the `/api/pilot/*` prefix — frontend and existing callers rely on it.
"""
from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import anthropic

from agents.pilotcore.briefing import generate_briefing
from agents.pilotcore.context_builder import build_context
from agents.pilotcore.escalation import run_escalation_check

router = APIRouter(tags=["pilotcore"])


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


@router.get("/context")
async def get_context() -> dict:
    return build_context()


@router.post("/briefing")
async def post_briefing() -> StreamingResponse:
    async def stream():
        async for chunk in generate_briefing(_client()):
            yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/escalation")
async def post_escalation() -> StreamingResponse:
    async def stream():
        async for chunk in run_escalation_check(_client()):
            yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")
