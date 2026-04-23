# CLAUDE.md — Template Pilot

Scoped Claude Code instructions for this agent. A session working on
this folder should behave as if THIS is the whole codebase — don't
leak conventions from other agents.

## What this agent does

One paragraph. What does this Pilot produce, for whom, and why does it
exist? This is the context a new contributor (human or AI) needs to make
correct edits.

## Entry points

- HTTP: `POST {manifest.route_prefix}/run` (see `router.py`)
- CLI: `python -m backend.agents.<agent_id>` (if applicable)

## Folder map

- `engine.py` — orchestration / main loop
- `prompts/` — system prompt + templates as `.md`
- `schemas.py` — Pydantic I/O models
- `router.py` — FastAPI routes (auto-mounted)
- `manifest.py` — metadata exposed to Agent Hub

## Hard rules

- Prompts are files, not Python strings. If you find a multi-line prompt
  inline, move it to `prompts/`.
- Do NOT import from sibling agents (`backend.agents.other_pilot`).
  Cross-agent calls go through `backend/core/` or via HTTP.
- Each new endpoint gets a Pydantic schema in `schemas.py`.
