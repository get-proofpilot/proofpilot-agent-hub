"""AutoPilot AI — 6-stage SEO page builder.

Research → strategy → copywrite → design → images → QA, with a
revision loop that re-runs stages when QA scores below threshold.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
