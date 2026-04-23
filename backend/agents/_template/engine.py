"""Core agent logic.

Conventions:
- Entry point is an async function (streaming SSE or returning JSON).
- Heavy integration imports stay inside the function body for faster boot.
- Prompts come from prompts/*.md via a tiny loader — never embedded strings.
"""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file relative to this agent's prompts/ directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


async def run(inputs: dict) -> dict:
    """Replace with real logic."""
    return {"echo": inputs}
