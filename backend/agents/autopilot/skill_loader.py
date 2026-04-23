"""
Skill Loader — reads Claude Code skills from disk and builds agent system prompts.

Skills are SKILL.md files with YAML frontmatter. They contain expert-level
instructions that become the "brain" of each pipeline agent. Templates and
reference files within skill directories are also loadable.

Search order:
  1. backend/skills/ (bundled with the repo for Railway deployment)
  2. ~/.claude/skills/ (local Claude Code skills)
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories to search for skills (first match wins)
_BUNDLED_SKILLS = Path(__file__).parent.parent / "skills"
_USER_SKILLS = Path.home() / ".claude" / "skills"

SKILL_DIRS = [_BUNDLED_SKILLS, _USER_SKILLS]


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (--- delimited) from skill content."""
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            body = content[end + 4:].lstrip("\n")
            return body if body else content
    return content


def _find_skill_dir(skill_name: str) -> Optional[Path]:
    """Find the directory for a skill by name across all search paths."""
    for base in SKILL_DIRS:
        if not base.exists():
            continue
        # Direct match: base/skill-name/SKILL.md
        direct = base / skill_name
        if (direct / "SKILL.md").exists():
            return direct
        # Nested match: base/category/skill-name/SKILL.md
        for match in base.rglob(f"{skill_name}/SKILL.md"):
            return match.parent
    return None


def load_skill(skill_name: str, strip_frontmatter: bool = True) -> str:
    """Load a skill's SKILL.md content by name. Returns empty string if not found."""
    skill_dir = _find_skill_dir(skill_name)
    if not skill_dir:
        logger.debug("Skill not found: %s", skill_name)
        return ""

    skill_file = skill_dir / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    if strip_frontmatter:
        content = _strip_frontmatter(content)
    return content


def load_skill_file(skill_name: str, relative_path: str) -> str:
    """Load a supporting file from within a skill directory.

    Example: load_skill_file("home-service-seo-content", "templates/chaos_prompt_template.md")
    """
    skill_dir = _find_skill_dir(skill_name)
    if not skill_dir:
        return ""

    target = skill_dir / relative_path
    # Prevent path traversal
    try:
        target.resolve().relative_to(skill_dir.resolve())
    except ValueError:
        logger.warning("Path traversal attempt: %s / %s", skill_name, relative_path)
        return ""

    if target.exists() and target.is_file():
        return target.read_text(encoding="utf-8")
    return ""


def list_skill_files(skill_name: str) -> list[str]:
    """List all files in a skill directory (relative paths)."""
    skill_dir = _find_skill_dir(skill_name)
    if not skill_dir:
        return []
    return [str(f.relative_to(skill_dir)) for f in skill_dir.rglob("*") if f.is_file()]


# ─── Stage → Skill Mapping ────────────────────────────────────────────────

STAGE_SKILLS: dict[str, list[str]] = {
    "research": [
        "seo",
        "competitor-seo",
        "seo-geo",
        "website-seo-audit",
    ],
    "strategy": [
        "blog-outline",
        "blog-brief",
        "programmatic-seo",
    ],
    "copywrite": [
        "home-service-seo-content",
        "stop-slop",
    ],
    "design": [
        "seo-schema",
    ],
    "qa": [
        "blog-analyze",
        "blog-seo-check",
        "blog-geo",
        "geo-optimization",
    ],
}

# Skill templates loaded for the copywriter (per-client assets)
COPYWRITER_TEMPLATES = [
    ("home-service-seo-content", "templates/anti_ai_writing_style_guide_template.txt"),
    ("home-service-seo-content", "templates/chaos_prompt_template.md"),
    ("home-service-seo-content", "templates/eeat_checklist_template.md"),
    ("home-service-seo-content", "templates/voice_guide_template.md"),
]


def build_stage_prompt(
    stage: str,
    base_prompt: str,
    page_type: str = "",
    client_memory: str = "",
    extra_context: str = "",
) -> str:
    """Assemble the full system prompt for a pipeline stage.

    Loads the relevant skills and templates, then combines with:
    - base_prompt: the stage-specific instructions
    - page_type context
    - client memory (frozen snapshot)
    - extra_context: artifact data from previous stages
    """
    parts = [base_prompt]

    # Load skills for this stage
    skill_names = STAGE_SKILLS.get(stage, [])
    for name in skill_names:
        content = load_skill(name)
        if content:
            # Truncate very long skills to avoid context bloat
            if len(content) > 8000:
                content = content[:8000] + "\n\n[... skill content truncated for context efficiency]"
            parts.append(f"\n---\n## Reference: {name}\n{content}")

    # Load copywriter templates
    if stage == "copywrite":
        for skill_name, template_path in COPYWRITER_TEMPLATES:
            tmpl = load_skill_file(skill_name, template_path)
            if tmpl:
                label = template_path.split("/")[-1].replace("_", " ").replace(".md", "").replace(".txt", "")
                parts.append(f"\n---\n## {label}\n{tmpl}")

    # Client memory
    if client_memory:
        parts.append(f"\n---\n## Client Context (from memory)\n{client_memory}")

    # Previous stage artifacts
    if extra_context:
        parts.append(f"\n---\n## Data from Previous Stages\n{extra_context}")

    return "\n\n".join(parts)
