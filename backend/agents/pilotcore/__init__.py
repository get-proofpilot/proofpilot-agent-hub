"""Pilot Core — central AI coworker for ProofPilot operations.

Aggregates client state, generates morning briefings, and runs
progressive escalation checks across the full client roster.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
