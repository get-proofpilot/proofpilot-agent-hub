"""AuditPilot — multi-stage sales audit agent.

Firecrawl site crawl + DataForSEO (keywords, SERP, backlinks) +
8-dimension Strategic Brain + Sales Audit v2 document synthesis.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
