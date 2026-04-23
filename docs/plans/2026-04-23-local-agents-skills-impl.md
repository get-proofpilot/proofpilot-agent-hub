# Local ProofPilot Agents + Skills — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development when run in-session) to implement this plan task-by-task.

**Goal:** Make every Pilot and workflow in the agent-hub repo available as a local Claude Code agent/skill on any team member's laptop, sourced via symlinks from one company GitHub repo.

**Architecture:** Source of truth stays in `~/ProofPilot/agent-hub/`. Each pilot folder is normalized to the cognitive-architecture pattern (AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, skill/, context/, examples/, memory/). An `agent.md` file per pilot carries Claude Code subagent frontmatter. The 25 live workflows each get a `backend/workflows/skills/pp-<slug>/SKILL.md` generated from their `SYSTEM_PROMPT` + input schema. A single `scripts/install-local.sh` symlinks everything into `~/.claude/agents/` and `~/.claude/skills/`. Idempotent, reversible via `uninstall-local.sh`.

**Tech Stack:** Bash (install script), Python 3.11 (scaffolders + extractor), existing `backend/agents/*/manifest.py` and `backend/workflows/*.py` as input. No new runtime dependencies.

**Repo:** `~/ProofPilot/agent-hub/` on branch `main`. Source: `github.com/get-proofpilot/proofpilot-agent-hub`.

**Design doc:** `docs/plans/2026-04-23-local-agents-skills-design.md` (commit `ac16939`).

---

## Preconditions checked 2026-04-23

- All 10 pilots have `CLAUDE.md`, `SOUL.md`, `TOOLS.md`, `skill/SKILL.md`.
- All 10 pilots are missing `agent.md`, `HEARTBEAT.md`, `context/`, `memory/MEMORY.md`.
- Repo root has `AGENTS.md` and `USER.md` (ready to symlink).
- 25 of 27 files in `backend/workflows/` have a top-level `SYSTEM_PROMPT` constant.
  - `programmatic_content.py` has 6 named system prompts (one per content type) — handle as one umbrella skill.
  - `page_design.py` is not in the live workflow registry — skip.
- Pattern already proven: `~/.claude/skills/proofpilot-brand → /Users/matthewanderson/proofpilot-brand/skills/proofpilot-brand`.

## Pilot roster (10)

`auditpilot, autopilot, gbppilot, pilotcore, projectpilot, qapilot, redditpilot, reportpilot, strategypilot, websitepilot`

## Workflow roster (25 live from CLAUDE.md)

```
ai-search-report, backlink-audit, competitor-intel, competitor-seo-analysis,
content-strategy, geo-content-audit, google-ads-copy, home-service-content,
keyword-gap, location-page, monthly-report, onpage-audit, pnl-statement,
programmatic-content, programmatic-seo-strategy, property-mgmt-strategy,
proposals, prospect-audit, schema-generator, seo-blog-post, seo-content-audit,
seo-research, service-page, technical-seo-review, website-seo-audit
```

---

## Task 1: Add symlinks for repo-root shared files into each pilot folder

**Why:** Cognitive architecture says every agent reads the same `AGENTS.md` + `USER.md`. Symlink instead of copy so edits to the root file propagate.

**Files:**
- Create: `backend/agents/<pilot>/AGENTS.md` → `../../../AGENTS.md` (10 symlinks)
- Create: `backend/agents/<pilot>/USER.md` → `../../../USER.md` (10 symlinks)

**Step 1: Create a shell helper script**

Create `scripts/scaffold_pilot_shared_symlinks.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PILOTS_DIR="$REPO_ROOT/backend/agents"

pilots=(auditpilot autopilot gbppilot pilotcore projectpilot qapilot redditpilot reportpilot strategypilot websitepilot)

for pilot in "${pilots[@]}"; do
  pilot_dir="$PILOTS_DIR/$pilot"
  if [[ ! -d "$pilot_dir" ]]; then
    echo "skip: $pilot (not a directory)"
    continue
  fi
  for shared in AGENTS.md USER.md; do
    target="$pilot_dir/$shared"
    if [[ -L "$target" ]]; then
      echo "ok:   $pilot/$shared (already linked)"
    elif [[ -e "$target" ]]; then
      echo "SKIP: $pilot/$shared exists as a real file — leave it"
    else
      ln -s "../../../$shared" "$target"
      echo "link: $pilot/$shared"
    fi
  done
done
```

**Step 2: Make executable + run**

```bash
chmod +x scripts/scaffold_pilot_shared_symlinks.sh
./scripts/scaffold_pilot_shared_symlinks.sh
```

Expected output: 20 `link:` lines (10 pilots × 2 files).

**Step 3: Verify**

```bash
ls -la backend/agents/auditpilot/AGENTS.md backend/agents/auditpilot/USER.md
```

Expected: both shown as symlinks resolving to `../../../AGENTS.md` and `../../../USER.md`.

**Step 4: Commit**

```bash
git add scripts/scaffold_pilot_shared_symlinks.sh backend/agents/*/AGENTS.md backend/agents/*/USER.md
git commit -m "chore(agents): symlink AGENTS.md + USER.md into every pilot folder"
```

---

## Task 2: Scaffold HEARTBEAT.md, context/, memory/ across all 10 pilots

**Why:** Cognitive architecture needs these three files/folders present. Fill with minimal templates; content grows per-pilot over time.

**Files:**
- Create: `scripts/scaffold_pilot_cognitive_gaps.py`
- Create (per pilot): `HEARTBEAT.md`, `context/README.md`, `memory/MEMORY.md` (30 files total)

**Step 1: Write the scaffolder**

Create `scripts/scaffold_pilot_cognitive_gaps.py`:

```python
"""Scaffold missing cognitive-architecture files across all 10 pilots.

Creates HEARTBEAT.md, context/README.md, memory/MEMORY.md in each
backend/agents/<pilot>/ folder if they don't already exist. Idempotent.
"""
from __future__ import annotations

from pathlib import Path

PILOTS = [
    "auditpilot", "autopilot", "gbppilot", "pilotcore", "projectpilot",
    "qapilot", "redditpilot", "reportpilot", "strategypilot", "websitepilot",
]

HEARTBEAT_TEMPLATE = """# HEARTBEAT — {title}

> Scheduled tasks, recurring operations, and health checks for {title}.
> Cron entries, retention policies, and monitoring live here.

## Scheduled ops

_None yet. Add cron entries as they're configured._

## Health checks

_None yet. Add health-check endpoints or smoke tests as they're written._

## Retention

_None yet. Add data retention policies as they're decided._
"""

CONTEXT_README_TEMPLATE = """# Context — {title}

> Business knowledge this pilot needs: ICP, offer details, processes,
> client conventions. One file per topic. Loaded on demand by the
> skill when relevant.

_No context files yet._
"""

MEMORY_TEMPLATE = """# Memory — {title}

> Persistent memory index for {title}. What the pilot has learned
> from past runs: patterns, corrections, client-specific adjustments.

_No memories yet._
"""


def scaffold(pilot_dir: Path, pilot: str) -> list[str]:
    title = pilot[0].upper() + pilot[1:]
    created: list[str] = []

    heartbeat = pilot_dir / "HEARTBEAT.md"
    if not heartbeat.exists():
        heartbeat.write_text(HEARTBEAT_TEMPLATE.format(title=title))
        created.append(str(heartbeat.relative_to(pilot_dir.parents[2])))

    context_dir = pilot_dir / "context"
    context_dir.mkdir(exist_ok=True)
    context_readme = context_dir / "README.md"
    if not context_readme.exists():
        context_readme.write_text(CONTEXT_README_TEMPLATE.format(title=title))
        created.append(str(context_readme.relative_to(pilot_dir.parents[2])))

    memory_dir = pilot_dir / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text(MEMORY_TEMPLATE.format(title=title))
        created.append(str(memory_file.relative_to(pilot_dir.parents[2])))

    return created


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    pilots_dir = repo_root / "backend" / "agents"
    total_created: list[str] = []

    for pilot in PILOTS:
        pilot_dir = pilots_dir / pilot
        if not pilot_dir.is_dir():
            print(f"SKIP {pilot}: directory missing")
            continue
        created = scaffold(pilot_dir, pilot)
        for path in created:
            print(f"create: {path}")
        total_created.extend(created)

    if not total_created:
        print("nothing to create — all pilots already scaffolded")
    else:
        print(f"\ndone — {len(total_created)} files created")


if __name__ == "__main__":
    main()
```

**Step 2: Run scaffolder**

```bash
python3 scripts/scaffold_pilot_cognitive_gaps.py
```

Expected output (first run): 30 `create:` lines (10 pilots × 3 files).

**Step 3: Run a second time to verify idempotence**

```bash
python3 scripts/scaffold_pilot_cognitive_gaps.py
```

Expected: `nothing to create — all pilots already scaffolded`.

**Step 4: Commit**

```bash
git add scripts/scaffold_pilot_cognitive_gaps.py backend/agents/*/HEARTBEAT.md backend/agents/*/context/ backend/agents/*/memory/
git commit -m "chore(agents): scaffold HEARTBEAT.md + context/ + memory/ across all 10 pilots"
```

---

## Task 3: Generate agent.md (Claude Code subagent frontmatter) per pilot

**Why:** Claude Code expects agent files in `~/.claude/agents/<name>.md` with YAML frontmatter. Generate one `agent.md` per pilot with the pilot's identity condensed from SOUL.md + CLAUDE.md + manifest.py, then symlink into `~/.claude/agents/`.

**Files:**
- Create: `scripts/generate_pilot_agents.py`
- Create (per pilot): `backend/agents/<pilot>/agent.md` (10 files)

**Step 1: Define model assignments inline in the script**

```python
MODELS = {
    "auditpilot": "opus",
    "autopilot": "opus",
    "gbppilot": "sonnet",
    "pilotcore": "opus",
    "projectpilot": "sonnet",
    "qapilot": "sonnet",
    "redditpilot": "sonnet",
    "reportpilot": "sonnet",
    "strategypilot": "opus",
    "websitepilot": "sonnet",
}
```

**Step 2: Write the generator**

Create `scripts/generate_pilot_agents.py`:

```python
"""Generate agent.md (Claude Code subagent markdown) for every pilot.

Reads backend/agents/<pilot>/manifest.py for id/title/description,
then reads SOUL.md + skill/SKILL.md to build the body.
Writes backend/agents/<pilot>/agent.md.

Idempotent — overwrites existing agent.md each run so edits to
SOUL.md / manifest.py propagate. Do NOT edit agent.md directly;
edit the source files and re-run.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

PILOTS = [
    "auditpilot", "autopilot", "gbppilot", "pilotcore", "projectpilot",
    "qapilot", "redditpilot", "reportpilot", "strategypilot", "websitepilot",
]

MODELS = {
    "auditpilot": "opus", "autopilot": "opus", "gbppilot": "sonnet",
    "pilotcore": "opus", "projectpilot": "sonnet", "qapilot": "sonnet",
    "redditpilot": "sonnet", "reportpilot": "sonnet",
    "strategypilot": "opus", "websitepilot": "sonnet",
}


def load_manifest(pilot_dir: Path) -> dict:
    """Import manifest.py without importing its parent package."""
    manifest_path = pilot_dir / "manifest.py"
    spec = importlib.util.spec_from_file_location(
        f"manifest_{pilot_dir.name}", manifest_path
    )
    module = importlib.util.module_from_spec(spec)
    # manifest.py imports from agents._template.manifest — add to sys.path
    import sys
    backend_dir = pilot_dir.parents[1]
    sys.path.insert(0, str(backend_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    m = module.manifest
    return {
        "id": m.id, "title": m.title, "description": m.description,
        "version": m.version, "icon": m.icon, "category": m.category,
        "tags": list(m.tags),
    }


def extract_when_to_trigger(skill_md: str) -> str:
    """Pull the 'When to Trigger' section from SKILL.md (best-effort)."""
    match = re.search(
        r"## When to Trigger\s*\n(.*?)(?=\n## |\Z)",
        skill_md, re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def build_agent_md(pilot: str, pilot_dir: Path) -> str:
    manifest = load_manifest(pilot_dir)
    soul = (pilot_dir / "SOUL.md").read_text() if (pilot_dir / "SOUL.md").exists() else ""
    skill_md = (pilot_dir / "skill" / "SKILL.md").read_text() if (pilot_dir / "skill" / "SKILL.md").exists() else ""

    triggers = extract_when_to_trigger(skill_md)
    model = MODELS.get(pilot, "sonnet")

    # Description is the one-liner Claude uses to decide when to invoke.
    # Keep it under 200 chars and name the pilot + triggers explicitly.
    description = manifest["description"].replace("\n", " ").strip()
    if len(description) > 200:
        description = description[:197] + "..."

    frontmatter = (
        "---\n"
        f"name: proofpilot-{pilot}\n"
        f"description: {description}\n"
        f"model: {model}\n"
        "tools: [\"*\"]\n"
        "---\n\n"
    )

    body = (
        f"# {manifest['title']}\n\n"
        f"{manifest['icon']} **Category:** {manifest['category']} · "
        f"**Version:** {manifest['version']} · "
        f"**Tags:** {', '.join(manifest['tags'])}\n\n"
        f"## Identity\n\n"
        f"See [SOUL.md](./SOUL.md) for full voice + values.\n\n"
    )

    if triggers:
        body += f"## When to use\n\n{triggers}\n\n"

    body += (
        "## How it runs\n\n"
        f"Backend: `POST {re.search(r'route_prefix=\"([^\"]+)\"', (pilot_dir / 'manifest.py').read_text()).group(1) if (pilot_dir / 'manifest.py').exists() else ''}`. "
        "See [CLAUDE.md](./CLAUDE.md) for orchestration + stages, "
        "[TOOLS.md](./TOOLS.md) for integrations, "
        "[skill/SKILL.md](./skill/SKILL.md) for the full playbook.\n\n"
        "## Source of truth\n\n"
        f"`backend/agents/{pilot}/` in `get-proofpilot/proofpilot-agent-hub`. "
        f"The skill at `~/.claude/skills/proofpilot-{pilot}/` loads automatically "
        "when this agent runs. To update behavior, edit the source files and "
        "`git pull` on each laptop.\n\n"
        "_This file is generated by `scripts/generate_pilot_agents.py`. "
        "Do not edit directly — edit SOUL.md, manifest.py, or skill/SKILL.md._\n"
    )

    return frontmatter + body


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    pilots_dir = repo_root / "backend" / "agents"

    for pilot in PILOTS:
        pilot_dir = pilots_dir / pilot
        if not pilot_dir.is_dir():
            print(f"SKIP {pilot}: directory missing")
            continue
        agent_md_path = pilot_dir / "agent.md"
        content = build_agent_md(pilot, pilot_dir)
        agent_md_path.write_text(content)
        print(f"wrote: {agent_md_path.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
```

**Step 3: Run it**

```bash
python3 scripts/generate_pilot_agents.py
```

Expected output: 10 `wrote:` lines.

**Step 4: Spot-check one agent.md**

```bash
cat backend/agents/auditpilot/agent.md | head -20
```

Expected: YAML frontmatter with `name: proofpilot-auditpilot`, `model: opus`, sensible `description`, body referencing SOUL.md and skill/SKILL.md.

**Step 5: Commit**

```bash
git add scripts/generate_pilot_agents.py backend/agents/*/agent.md
git commit -m "feat(agents): generate agent.md subagent files for all 10 pilots"
```

---

## Task 4: Extract 25 workflow skills from SYSTEM_PROMPT constants

**Why:** Each of 25 live workflows should be invokable as its own skill in `~/.claude/skills/pp-<slug>/`. Extract the SYSTEM_PROMPT from each Python file into a SKILL.md that mirrors what the FastAPI backend already uses.

**Files:**
- Create: `scripts/extract_workflow_skills.py`
- Create (per workflow): `backend/workflows/skills/pp-<slug>/SKILL.md` (25 files)

**Step 1: Define the workflow registry**

The 25 live workflows come from `backend/server.py`'s `WORKFLOW_TITLES`. Map each to its Python file + CLAUDE.md input schema:

```python
# In the script (source: CLAUDE.md § Live Workflows + Workflow Input Schemas)
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
```

**Step 2: Write the extractor**

Create `scripts/extract_workflow_skills.py`:

```python
"""Extract a SKILL.md from each live workflow's SYSTEM_PROMPT.

One skill per workflow → backend/workflows/skills/pp-<slug>/SKILL.md.
Idempotent — overwrites each run. programmatic_content.py has 6
system prompts (one per content type) so its SKILL.md lists all six
with section headings.
"""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

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


def extract_system_prompts(source: str) -> list[tuple[str, str]]:
    """Return [(name, value)] for every top-level SYSTEM-ish string constant."""
    tree = ast.parse(source)
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and "SYSTEM" in target.id:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    out.append((target.id, node.value.value))
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
        f"description: {description}",
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
        body += [
            "## System prompt",
            "",
            "```",
            prompts[0][1].strip(),
            "```",
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
            body += [
                f"### {name}",
                "",
                "```",
                value.strip(),
                "```",
                "",
            ]

    body += [
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
        src = (workflows_dir / f"{module}.py").read_text()
        prompts = extract_system_prompts(src)
        if not prompts:
            print(f"WARN {slug}: no SYSTEM prompt found in {module}.py — skipping")
            continue

        skill_dir = skills_dir / f"pp-{slug}"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(build_skill_md(slug, module, title, prompts))
        print(f"wrote: backend/workflows/skills/pp-{slug}/SKILL.md")
        written += 1

    print(f"\ndone — {written}/{len(WORKFLOWS)} workflow skills generated")


if __name__ == "__main__":
    main()
```

**Step 3: Run it**

```bash
python3 scripts/extract_workflow_skills.py
```

Expected output: 25 `wrote:` lines (or 24 + 1 WARN if `programmatic_content.py` parsing edge-cases hit). Any WARN output is a bug — fix the parser before continuing.

**Step 4: Spot-check two skills (one simple, one multi-prompt)**

```bash
head -40 backend/workflows/skills/pp-keyword-gap/SKILL.md
head -40 backend/workflows/skills/pp-programmatic-content/SKILL.md
```

Expected: `pp-keyword-gap` has one ``` block of system prompt. `pp-programmatic-content` has 6 labeled prompts (LOCATION_PAGE_SYSTEM, SERVICE_PAGE_SYSTEM, BLOG_POST_SYSTEM, COMPARISON_POST_SYSTEM, COST_GUIDE_SYSTEM, BEST_IN_CITY_SYSTEM).

**Step 5: Commit**

```bash
git add scripts/extract_workflow_skills.py backend/workflows/skills/
git commit -m "feat(workflows): extract 25 skill/ folders from workflow SYSTEM_PROMPTs"
```

---

## Task 5: Write install-local.sh

**Why:** Any team member clones the repo and runs one command to get 10 agents + 35 skills installed into their `~/.claude/`.

**Files:**
- Create: `scripts/install-local.sh`

**Step 1: Write the script**

Create `scripts/install-local.sh`:

```bash
#!/usr/bin/env bash
# Install ProofPilot Pilots + workflow skills into ~/.claude/ via symlinks.
#
# Usage:
#   ./scripts/install-local.sh             # install
#   ./scripts/install-local.sh --dry-run   # print what would happen, don't link
#
# Idempotent. Refuses to overwrite non-symlink targets.

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_SRC="$REPO_ROOT/backend/agents"
WORKFLOW_SKILLS_SRC="$REPO_ROOT/backend/workflows/skills"

CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_SKILLS="$HOME/.claude/skills"

mkdir -p "$CLAUDE_AGENTS" "$CLAUDE_SKILLS"

linked=0
skipped=0
errors=0

link_one() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    echo "ERROR: source missing: $src"
    ((errors++))
    return
  fi

  if [[ -L "$dst" ]]; then
    local current
    current="$(readlink "$dst")"
    if [[ "$current" == "$src" ]]; then
      echo "ok:   $(basename "$dst") (already linked)"
      ((skipped++))
      return
    else
      echo "relink: $(basename "$dst") (was → $current)"
      $DRY_RUN || { rm "$dst"; ln -s "$src" "$dst"; }
      ((linked++))
      return
    fi
  elif [[ -e "$dst" ]]; then
    echo "ERROR: $dst exists and is not a symlink — refusing to overwrite"
    ((errors++))
    return
  fi

  echo "link: $(basename "$dst") → $src"
  $DRY_RUN || ln -s "$src" "$dst"
  ((linked++))
}

# --- Pilot agents ---
pilots=(auditpilot autopilot gbppilot pilotcore projectpilot qapilot redditpilot reportpilot strategypilot websitepilot)
for pilot in "${pilots[@]}"; do
  agent_src="$AGENTS_SRC/$pilot/agent.md"
  skill_src="$AGENTS_SRC/$pilot/skill"
  link_one "$agent_src" "$CLAUDE_AGENTS/proofpilot-$pilot.md"
  link_one "$skill_src" "$CLAUDE_SKILLS/proofpilot-$pilot"
done

# --- Workflow skills ---
if [[ -d "$WORKFLOW_SKILLS_SRC" ]]; then
  for skill_dir in "$WORKFLOW_SKILLS_SRC"/pp-*; do
    [[ -d "$skill_dir" ]] || continue
    name="$(basename "$skill_dir")"
    link_one "$skill_dir" "$CLAUDE_SKILLS/$name"
  done
fi

echo ""
echo "Summary: $linked linked · $skipped already-linked · $errors errors"
$DRY_RUN && echo "(dry-run — nothing was actually changed)"
[[ $errors -eq 0 ]] || exit 1
```

**Step 2: Make executable**

```bash
chmod +x scripts/install-local.sh
```

**Step 3: Dry-run verify**

```bash
./scripts/install-local.sh --dry-run
```

Expected: prints 45 `link:` lines (10 pilot agents + 10 pilot skills + 25 workflow skills), `0 errors`, summary note about dry-run.

**Step 4: Commit**

```bash
git add scripts/install-local.sh
git commit -m "feat(scripts): add install-local.sh to symlink pilots + workflow skills into ~/.claude/"
```

---

## Task 6: Write uninstall-local.sh

**Why:** Let team members cleanly remove ProofPilot agents/skills without blowing up unrelated symlinks.

**Files:**
- Create: `scripts/uninstall-local.sh`

**Step 1: Write the script**

Create `scripts/uninstall-local.sh`:

```bash
#!/usr/bin/env bash
# Remove ProofPilot agent/skill symlinks installed by install-local.sh.
# Only removes symlinks whose target resolves into this repo — safe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_SKILLS="$HOME/.claude/skills"

removed=0

remove_if_ours() {
  local path="$1"
  [[ -L "$path" ]] || return
  local target
  target="$(readlink "$path")"
  # Resolve relative symlinks by checking if the absolute path lives in our repo
  local abs_target
  abs_target="$(cd "$(dirname "$path")" && cd "$(dirname "$target")" 2>/dev/null && pwd)/$(basename "$target")" || abs_target=""
  if [[ "$abs_target" == "$REPO_ROOT"* ]] || [[ "$target" == "$REPO_ROOT"* ]]; then
    rm "$path"
    echo "removed: $path"
    ((removed++))
  fi
}

# Pilot agents
for agent_link in "$CLAUDE_AGENTS"/proofpilot-*.md; do
  [[ -e "$agent_link" || -L "$agent_link" ]] || continue
  remove_if_ours "$agent_link"
done

# Pilot + workflow skills
for skill_link in "$CLAUDE_SKILLS"/proofpilot-* "$CLAUDE_SKILLS"/pp-*; do
  [[ -e "$skill_link" || -L "$skill_link" ]] || continue
  remove_if_ours "$skill_link"
done

echo ""
echo "Summary: $removed symlinks removed"
```

**Step 2: Make executable + commit**

```bash
chmod +x scripts/uninstall-local.sh
git add scripts/uninstall-local.sh
git commit -m "feat(scripts): add uninstall-local.sh"
```

---

## Task 7: Smoke-test install end-to-end

**Why:** Prove the install actually produces a working symlink graph before documenting it.

**Step 1: Check current state of existing ProofPilot symlinks**

```bash
ls -la ~/.claude/agents/proofpilot-* 2>/dev/null || echo "no proofpilot-* agents yet"
ls -la ~/.claude/skills/proofpilot-* 2>/dev/null | head -5
ls -la ~/.claude/skills/pp-* 2>/dev/null | head -5 || echo "no pp-* skills yet"
```

Expected: existing `proofpilot-brand`, `proofpilot-pnl`, etc. skills resolve to `/Users/matthewanderson/proofpilot-brand/...`. No agents named `proofpilot-*pilot` yet. No `pp-*` skills yet.

**Step 2: Run the installer**

```bash
./scripts/install-local.sh
```

Expected: 10 agent links + 10 pilot skill links + 25 workflow skill links. `0 errors`. Any pre-existing `proofpilot-brand` etc. skills are left alone (they're not named `proofpilot-<pilot>pilot`).

**Step 3: Verify targets resolve**

```bash
ls -la ~/.claude/agents/proofpilot-auditpilot.md
readlink ~/.claude/skills/proofpilot-auditpilot
readlink ~/.claude/skills/pp-website-seo-audit
```

Expected: all three resolve into `~/ProofPilot/agent-hub/backend/...`. Links not broken.

**Step 4: Re-run installer to prove idempotence**

```bash
./scripts/install-local.sh
```

Expected: 45 `ok:` lines (already linked), `0 errors`.

**Step 5: No commit for this task** — it's validation only. If issues emerge, file a fix commit against whichever script is broken.

---

## Task 8: Document local install in AGENTS.md

**Why:** Repo-root `AGENTS.md` is the first thing a new teammate reads. It should tell them how to get local agents + skills running.

**Files:**
- Modify: `AGENTS.md` (add a "Local install" section)

**Step 1: Add the section**

Insert a new `## Local install` section in `AGENTS.md` after the `## Commands` section. Content:

```markdown
## Local install (Claude Code agents + skills)

Every Pilot in `backend/agents/` and every workflow in `backend/workflows/`
is available as a Claude Code agent or skill on your laptop. One command:

```bash
./scripts/install-local.sh
```

This creates symlinks in `~/.claude/agents/` (10 pilot agents, named
`proofpilot-<pilot>pilot.md`) and `~/.claude/skills/` (10 pilot skills +
25 `pp-<workflow>` skills).

After install:
- From any Claude Code session, say *"use auditpilot to audit acme.com"*
  and `proofpilot-auditpilot` is invoked with its skill auto-loaded.
- `git pull` on this repo updates all agents/skills in place — no
  re-install needed.

Uninstall:

```bash
./scripts/uninstall-local.sh
```

Only removes symlinks pointing into this repo.
```

**Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): document local-install flow in AGENTS.md"
```

---

## Task 9: Push everything to main

**Why:** Close out the feature. Railway auto-deploys but none of this touches runtime — the server is unchanged.

**Step 1: Review the full commit chain**

```bash
git log --oneline origin/main..HEAD
```

Expected: 7 new commits (Tasks 1, 2, 3, 4, 5, 6, 8 — Task 7 has no commit).

**Step 2: Push**

```bash
git push origin main
```

**Step 3: Verify Railway deploy is green (purely runtime sanity)**

```bash
sleep 120
curl -s https://proofpilot-agents.up.railway.app/health
```

Expected: `{"status":"ok"}` or equivalent. No new routes, no behavior change.

**Step 4: Final verification**

```bash
ls ~/.claude/agents/proofpilot-*.md | wc -l       # expect: 10
ls -d ~/.claude/skills/proofpilot-*pilot | wc -l  # expect: 10
ls -d ~/.claude/skills/pp-* | wc -l               # expect: 25
```

Expected: 10, 10, 25.

---

## Success criteria (from design doc)

- [x] `./scripts/install-local.sh` runs clean.
- [x] `~/.claude/agents/proofpilot-*.md` has 10 symlinks, all into `agent-hub/`.
- [x] `~/.claude/skills/` has 10 `proofpilot-*pilot` symlinks + 25 `pp-*` symlinks.
- [x] Typing *"use auditpilot"* in a Claude Code session outside the repo invokes `proofpilot-auditpilot` with its skill auto-loaded.
- [x] Second run of installer reports 0 errors (idempotent).

## Follow-ups (out of scope for this plan)

- Fill real content into `context/` and `memory/MEMORY.md` per pilot as learnings accumulate.
- `HEARTBEAT.md` gains cron entries once APScheduler jobs are configured.
- Windows support (not on the team today).
- Publish `proofpilot-agent-hub` as a Claude Code plugin for zero-clone install.
