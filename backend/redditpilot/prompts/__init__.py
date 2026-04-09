"""External prompt templates for RedditPilot content generation.

Templates use {variable} placeholders that get filled at runtime.
Load templates with PromptLoader or read them directly as text files.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """Load a prompt template by name (without .txt extension)."""
    template_path = PROMPTS_DIR / f"{name}.txt"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    return template_path.read_text()


def list_templates() -> list[str]:
    """List all available template names."""
    return [p.stem for p in PROMPTS_DIR.glob("*.txt")]


def render_template(name: str, **kwargs) -> str:
    """Load and render a template with the given variables.

    Missing variables are left as {variable_name} placeholders.
    """
    template = load_template(name)
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template
