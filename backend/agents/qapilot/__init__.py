"""QAPilot — internal QA agent for SEO deliverables.

7-layer quality review covering accuracy, on-page SEO, content quality,
AI detection, visual/UX, strategy alignment, and cross-page consistency.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
