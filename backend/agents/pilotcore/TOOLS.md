# TOOLS — Pilot Core

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-sonnet-4-6 | Briefings + escalation checks (higher volume, lower stakes) | `ANTHROPIC_API_KEY` |

## Data sources (read-only)

| Path | Contents |
|---|---|
| `backend/vault_data/_clients-index.yaml` | All 9 clients: tier, MRR, manager, cadence |
| `backend/vault_data/clients/<slug>/roadmap.yaml` | Planned pages |
| `backend/vault_data/clients/<slug>/recurring.yaml` | Monthly task template |
| `backend/vault_data/clients/<slug>/context.md` | Client identity, services, contacts |
| SQLite `jobs` table (via `backend/utils/db.py`) | Job history for days-since-last-work |

## Planned sources (not wired yet)

- Slack MCP — team channel activity
- Gmail MCP — client emails needing action
- Google Calendar MCP — upcoming deadlines
- Granola MCP — meeting action items
- Fireflies MCP — deeper transcripts

## Shared internal modules

| Module | Why |
|---|---|
| `backend/utils/db.py` | `get_all_jobs()` for recent work history |

## Storage

None. Pilot Core is stateless — it reads fresh each call.

## Never

- Write to `vault_data/` — it's synced FROM the Obsidian vault, not TO it.
- Cache client data longer than a single request. Freshness beats speed.
