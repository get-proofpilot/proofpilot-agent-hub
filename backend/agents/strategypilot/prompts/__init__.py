"""StrategyPilot prompts.

Each `.md` file in this directory is one stage prompt. This module
loads them and re-exports as the named constants the engine uses.
"""
from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    return (_DIR / f"{name}.md").read_text()


FOOTPRINT_SYSTEM = load_prompt("footprint_system")
COMPETITIVE_SYSTEM = load_prompt("competitive_system")
PAGE_SYSTEMS_SYSTEM = load_prompt("page_systems_system")
ROI_SYSTEM = load_prompt("roi_system")
SYNTHESIS_SYSTEM = load_prompt("synthesis_system")

__all__ = [
    "load_prompt",
    "FOOTPRINT_SYSTEM",
    "COMPETITIVE_SYSTEM",
    "PAGE_SYSTEMS_SYSTEM",
    "ROI_SYSTEM",
    "SYNTHESIS_SYSTEM",
]
