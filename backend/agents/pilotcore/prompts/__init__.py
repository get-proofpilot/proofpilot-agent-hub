"""Prompt loader — reads .md files relative to this directory."""
from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    return (_DIR / f"{name}.md").read_text()
