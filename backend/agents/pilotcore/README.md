# Pilot Core

Central AI coworker for ProofPilot operations. Aggregates client state,
generates morning briefings, and runs progressive escalation checks.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/pilot/context` | Full client snapshot (JSON) |
| POST | `/api/pilot/briefing` | Morning briefing (SSE, Slack format) |
| POST | `/api/pilot/escalation` | At-risk clients (SSE, urgency-tiered) |

## Inputs

None — Pilot Core reads global state from `backend/vault_data/` and
the SQLite jobs table. Frontend hits the endpoints on demand.

## Outputs

- **Context**: structured dict with per-client tier, MRR, status,
  days-since-last-work, roadmap progress.
- **Briefing**: Slack-formatted markdown, <300 words, grouped by
  🔴 Needs Attention / 🟡 Watch List / 🟢 On Track / 📋 Today's Priorities.
- **Escalation**: urgency-tiered findings (🔴 🟡 🔵) with recommended
  owner for each.

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
curl -N -X POST http://localhost:8000/api/pilot/briefing
```
