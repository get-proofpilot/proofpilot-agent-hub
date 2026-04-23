"""Template agent — copy this folder to scaffold a new Pilot.

Every Pilot exports `router` and `manifest`; backend/agents/__init__.py
auto-discovers and mounts them on FastAPI boot.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
