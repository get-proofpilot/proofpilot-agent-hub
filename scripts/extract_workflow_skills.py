"""Extract a SKILL.md from each live workflow's SYSTEM_PROMPT.

One skill per workflow → backend/workflows/skills/pp-<slug>/SKILL.md.
Idempotent — overwrites each run. programmatic_content.py has 6
system prompts (one per content type) so its SKILL.md lists all six
with section headings.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


def _fence_for(text: str) -> str:
    """Return a backtick fence guaranteed to exceed any interior backtick run."""
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", text)), default=0)
    return "`" * max(longest + 1, 3)

WORKFLOWS = [
    ("website-seo-audit", "website_seo_audit", "Website & SEO Audit"),
    ("prospect-audit", "prospect_audit", "Prospect SEO Market Analysis"),
    ("keyword-gap", "keyword_gap", "Keyword Gap Analysis"),
    ("ai-search-report", "ai_search_report", "AI Search Visibility Report"),
    ("backlink-audit", "backlink_audit", "Backlink Audit"),
    ("onpage-audit", "onpage_audit", "On-Page Technical Audit"),
    ("geo-content-audit", "geo_content_audit", "GEO Content Citability Audit"),
    ("seo-content-audit", "seo_content_audit", "SEO Content Audit"),
    ("technical-seo-review", "technical_seo_review", "Technical SEO Review"),
    ("programmatic-seo-strategy", "programmatic_seo_strategy", "Programmatic SEO Strategy"),
    ("competitor-seo-analysis", "competitor_seo_analysis", "Competitor SEO Analysis"),
    ("seo-research", "seo_research_agent", "SEO Research & Content Strategy"),
    ("competitor-intel", "competitor_intel", "Competitor Intelligence Report"),
    ("schema-generator", "schema_generator", "Schema Generator"),
    ("monthly-report", "monthly_report", "Monthly Client Report"),
    ("proposals", "proposals", "Client Proposals"),
    ("google-ads-copy", "google_ads_copy", "Google Ads Copy"),
    ("content-strategy", "content_strategy", "Content Strategy"),
    ("pnl-statement", "pnl_statement", "P&L Statement"),
    ("property-mgmt-strategy", "property_mgmt_strategy", "Property Mgmt Strategy"),
    ("home-service-content", "home_service_content", "Home Service SEO Content"),
    ("seo-blog-post", "seo_blog_post", "SEO Blog Post"),
    ("service-page", "service_page", "Service Page"),
    ("location-page", "location_page", "Location Page"),
    ("programmatic-content", "programmatic_content", "Programmatic Content Agent"),
]


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _collect_str_constants(tree: ast.Module) -> dict[str, str]:
    """Collect top-level `NAME = "..."` string constants for f-string resolution."""
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    consts[target.id] = node.value.value
    return consts


def _resolve_joined_str(node: ast.JoinedStr, consts: dict[str, str]) -> str | None:
    """Resolve an f-string where every FormattedValue is a bare Name in ``consts``.

    Returns None if any interpolated expression can't be resolved statically.
    """
    parts: list[str] = []
    for piece in node.values:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            parts.append(piece.value)
        elif isinstance(piece, ast.FormattedValue):
            if (
                piece.conversion == -1
                and piece.format_spec is None
                and isinstance(piece.value, ast.Name)
                and piece.value.id in consts
            ):
                parts.append(consts[piece.value.id])
            else:
                return None
        else:
            return None
    return "".join(parts)


def extract_system_prompts(source: str, module: str = "<unknown>") -> list[tuple[str, str]]:
    """Return [(name, value)] for every top-level SYSTEM-ish string constant.

    Handles both plain string literals and f-strings whose interpolated
    expressions are simple references to other top-level string constants
    in the same module (e.g. proposals.py's ``SYSTEM_PROMPT = f"...{PRICING_TABLE}..."``).

    Prints a WARN line to stdout for any SYSTEM-named constant whose value
    can't be resolved statically (e.g. function calls, .format(), complex
    FormattedValue expressions), so they don't disappear silently.
    """
    tree = ast.parse(source)
    consts = _collect_str_constants(tree)
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and "SYSTEM" in target.id:
                value_node = node.value
                resolved_value: str | None = None
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    resolved_value = value_node.value
                elif isinstance(value_node, ast.JoinedStr):
                    resolved_value = _resolve_joined_str(value_node, consts)
                if resolved_value is not None:
                    out.append((target.id, resolved_value))
                else:
                    print(
                        f"WARN: {module}: SYSTEM constant {target.id} could not be resolved — skipping"
                    )
    return out


def build_skill_md(slug: str, module: str, title: str, prompts: list[tuple[str, str]]) -> str:
    description = (
        f"{title} — ProofPilot workflow. Invoke when the user asks for a "
        f"'{title.lower()}' or the workflow ID `{slug}`. Backend: "
        f"`POST /api/run-workflow` with `workflow_id: {slug}`."
    )
    body = [
        "---",
        f"name: pp-{slug}",
        f"description: {yaml_quote(description)}",
        "---",
        "",
        f"# {title}",
        "",
        f"ProofPilot workflow `{slug}`. Source: "
        f"`backend/workflows/{module}.py`.",
        "",
        "## When to trigger",
        "",
        f"- Someone says \"{title}\" or the workflow id `{slug}`.",
        f"- A request matches this workflow's purpose (see system prompt below).",
        "",
        "## How to run",
        "",
        "**Option A — via agent-hub API (preferred for production):**",
        "```bash",
        "curl -N -X POST https://proofpilot-agents.up.railway.app/api/run-workflow \\",
        "  -H 'Content-Type: application/json' \\",
        f"  -d '{{\"workflow_id\":\"{slug}\",\"client_name\":\"...\",\"inputs\":{{...}}}}'",
        "```",
        "",
        "**Option B — invoke this skill in-session** to use the same "
        "system prompt + Claude directly, without the API.",
        "",
        "## Input schema",
        "",
        f"See the `{slug}` entry in `CLAUDE.md` § *Workflow Input Schemas* "
        "for the exact keys.",
        "",
    ]

    if len(prompts) == 1:
        prompt_body = prompts[0][1].strip()
        fence = _fence_for(prompt_body)
        body += [
            "## System prompt",
            "",
            fence,
            prompt_body,
            fence,
            "",
        ]
    else:
        body.append("## System prompts")
        body.append("")
        body.append(
            f"This workflow has {len(prompts)} variants, one per content "
            "type. Choose the matching prompt based on the caller's "
            "`content_type` input."
        )
        body.append("")
        for name, value in prompts:
            value_body = value.strip()
            sub_fence = _fence_for(value_body)
            body += [
                f"### {name}",
                "",
                sub_fence,
                value_body,
                sub_fence,
                "",
            ]

    body += [
        "## Output format",
        "",
        "Produce the report as branded `.docx` — not just markdown.",
        "",
        "1. **Write the full report content as markdown** following the prompt/playbook above. "
        "This is your internal draft.",
        "2. **Render to `.docx`** using the `proofpilot-brand` skill's shared docx kit:",
        "   - Read `proofpilot-brand/skills/_shared/docx-kit/boilerplate.mjs` — the starter ESM "
        "template with helper functions (`createHeaderRow`, `createDataRow`, `createScoreRow`, "
        "`createCTABox`, etc.)",
        "   - Read `proofpilot-brand/skills/_shared/docx-kit/patterns.md` — idioms for tables, "
        "checklists, score cards, CTA boxes, typography hierarchy, spacing",
        "   - Read `proofpilot-brand/skills/_shared/brand.json` — the canonical colors, fonts, "
        "and docx half-points (do NOT hard-code values)",
        "3. **Write a one-off Node.js script** in a scratch location "
        "(e.g. `/tmp/generate-<slug>-<ts>.mjs`), run with `node`, and output the `.docx`.",
        "4. **File name:** `[Client-Name]-[Report-Name]-[YYYY-MM-DD].docx`.",
        "",
        "If the `proofpilot-brand` skill isn't loaded, invoke it first "
        "(it ships with the `proofpilot-auditpilot` / `pp-*` installer).",
        "",
        "## Notes",
        "",
        f"- Generated from `backend/workflows/{module}.py` by "
        "`scripts/extract_workflow_skills.py`. Do not edit directly.",
        "- Source of truth for prompt changes: the Python file.",
        "- Model: inherits from the calling agent (default: Opus 4.6).",
        "",
    ]

    return "\n".join(body)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workflows_dir = repo_root / "backend" / "workflows"
    skills_dir = workflows_dir / "skills"
    skills_dir.mkdir(exist_ok=True)

    written = 0
    for slug, module, title in WORKFLOWS:
        src = (workflows_dir / f"{module}.py").read_text(encoding="utf-8")
        prompts = extract_system_prompts(src, module=module)
        if not prompts:
            print(f"WARN {slug}: no SYSTEM prompt found in {module}.py — skipping")
            continue

        skill_dir = skills_dir / f"pp-{slug}"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            build_skill_md(slug, module, title, prompts), encoding="utf-8"
        )
        print(f"wrote: backend/workflows/skills/pp-{slug}/SKILL.md")
        written += 1

    print(f"\ndone — {written}/{len(WORKFLOWS)} workflow skills generated")


if __name__ == "__main__":
    main()
