"""QAPilot prompts.

Each `.md` file in this directory is one prompt. This module loads them
and re-exports as the named constants the engine uses.
"""
from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    return (_DIR / f"{name}.md").read_text()


QA_SYSTEM = load_prompt("qa_system")
QA_CONTENT_ONLY = load_prompt("qa_content_only")

__all__ = ["load_prompt", "QA_SYSTEM", "QA_CONTENT_ONLY"]
