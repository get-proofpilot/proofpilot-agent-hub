"""AuditPilot prompts.

Each `.md` file in this directory is one stage prompt. This module
loads them and re-exports as the named constants the engine uses.
"""
from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    return (_DIR / f"{name}.md").read_text()


SITE_ANALYSIS_SYSTEM = load_prompt("site_analysis_system")
RANKING_REALITY_SYSTEM = load_prompt("ranking_reality_system")
STRATEGIC_BRAIN_SYSTEM = load_prompt("strategic_brain_system")
SYNTHESIS_SYSTEM = load_prompt("synthesis_system")

__all__ = [
    "load_prompt",
    "SITE_ANALYSIS_SYSTEM",
    "RANKING_REALITY_SYSTEM",
    "STRATEGIC_BRAIN_SYSTEM",
    "SYNTHESIS_SYSTEM",
]
