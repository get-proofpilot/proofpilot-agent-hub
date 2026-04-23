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
