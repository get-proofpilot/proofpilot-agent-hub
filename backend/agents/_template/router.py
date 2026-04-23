"""FastAPI router for this Pilot.

Auto-discovery mounts this at `manifest.route_prefix`.
"""
from fastapi import APIRouter

router = APIRouter(tags=["template"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "template"}
