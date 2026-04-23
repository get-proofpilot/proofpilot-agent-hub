# CLAUDE.md — Pilot Core

## What this agent does

Pilot Core is the **central AI coworker** for ProofPilot operations. It
aggregates state from all 9 clients (vault YAML + job history + ClickUp
progress) into a single snapshot, generates morning briefings for
Matthew, and runs progressive escalation checks that surface at-risk
clients before they churn.

Unlike the specialist Pilots (AuditPilot, StrategyPilot, QAPilot,
AutoPilot, RedditPilot), Pilot Core doesn't produce client
deliverables. It produces **operational intelligence for Matthew**.

## Entry points

- `GET /api/pilot/context` — JSON snapshot of all clients
- `POST /api/pilot/briefing` — SSE stream, Slack-formatted morning update
- `POST /api/pilot/escalation` — SSE stream, at-risk client findings

## Folder map

- `context_builder.py` — reads `vault_data/_clients-index.yaml` +
  per-client `roadmap.yaml` / `recurring.yaml` + SQLite job history.
- `briefing.py` — Slack-formatted morning briefing via Claude Sonnet.
- `escalation.py` — urgency-tiered (🔴 🟡 🔵) at-risk findings.
- `prompts/` — `briefing_system.md`, `escalation_system.md`.
- `router.py` — FastAPI routes (for auto-mount; server.py still
  mounts hand-rolled for now).

## Data sources

- `backend/vault_data/` — client YAML synced from Obsidian vault.
- `backend/utils/db.py` — SQLite `jobs` table for recent work history.
- Future: Slack MCP, Gmail MCP, Google Calendar MCP, Granola MCP.

## Hard rules

- NEVER modify `vault_data/` from this agent. It's a read-only mirror.
- Briefings go to Slack — use single asterisks (`*bold*`), not double.
  No em dashes, no `#` headings. The prompt enforces this.
- Tier 1 clients get escalated faster than Tier 3. The escalation
  prompt encodes the exact day-thresholds; don't override in code.
