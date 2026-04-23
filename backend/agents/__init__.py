"""ProofPilot agents package — auto-discovery and router mounting.

Each subdirectory is a self-contained Pilot (see _template/ for shape).
`mount_agents(app)` walks this package, imports each agent's manifest +
router, and attaches the router to the FastAPI app at the prefix the
manifest declares.

Adding a new agent = drop a folder matching _template/. No server.py
edits required.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Folders the loader should skip. Names starting with "_" are also skipped.
_EXCLUDED: set[str] = set()


def discover_agents() -> list[tuple[str, object, object]]:
    """Return list of (module_name, manifest, router) triples for valid agents."""
    found: list[tuple[str, object, object]] = []
    for _, name, ispkg in pkgutil.iter_modules(__path__):
        if not ispkg or name.startswith("_") or name in _EXCLUDED:
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as exc:
            logger.warning("agents: failed to import %s: %s", name, exc)
            continue
        manifest = getattr(mod, "manifest", None)
        router = getattr(mod, "router", None)
        if manifest is None or router is None:
            logger.debug("agents: %s has no manifest+router; skipping auto-mount", name)
            continue
        found.append((name, manifest, router))
    return found


def mount_agents(app: "FastAPI") -> list[dict]:
    """Mount every discoverable agent onto the FastAPI app.

    Returns the list of mounted manifests (as dicts) — useful for the
    frontend sidebar / `/api/agents` index endpoint.
    """
    mounted: list[dict] = []
    for name, manifest, router in discover_agents():
        app.include_router(router, prefix=manifest.route_prefix)
        mounted.append(manifest.as_dict())
        logger.info(
            "agents: mounted %s at %s (v%s)",
            manifest.id,
            manifest.route_prefix,
            manifest.version,
        )
    return mounted
