# TOOLS.md

> Every integration this repo talks to, which Pilot uses it, what env var it needs.
> If a tool isn't in this table, it isn't wired up.

## Model providers

| Provider | Model | Used by | Env var | Notes |
|---|---|---|---|---|
| Anthropic | `claude-opus-4-6` | All workflow-producing Pilots (AuditPilot, StrategyPilot, AutoPilot, workflows/) | `ANTHROPIC_API_KEY` | Streaming + adaptive thinking. NEVER use assistant prefills — Opus 4.6 returns 400. Max tokens 8000. |
| Anthropic | `claude-sonnet-4-6` | PilotCore (briefings, escalations), SEO Operations executor | `ANTHROPIC_API_KEY` | Faster and cheaper for high-volume, lower-stakes summarization. |
| OpenRouter | Varies (Nano Banana, MiniMax, etc.) | RedditPilot (content generation), AutoPilot (image via Nano Banana) | `OPENROUTER_API_KEY` | Multi-model gateway for non-Claude tasks. |
| Google | Gemini (image gen) | AutoPilot AI (page images — optional path) | `GEMINI_API_KEY` | Fallback/alternative to Recraft. |

## Data providers

| Provider | Purpose | Used by | Env var |
|---|---|---|---|
| DataForSEO | SERP, Keyword Data, Labs, Backlinks, On-Page, AI Overviews, Trends, GBP (30+ functions) | AuditPilot, StrategyPilot, most `workflows/*` | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| Search Atlas (MCP) | Organic keywords, backlinks, holistic audit, local SEO, LLM visibility | workflows/*, future Pilot integrations | `SEARCHATLAS_API_KEY` |
| Firecrawl | Website crawling, scraping, structured extraction | AuditPilot (`data_collector.py`), QAPilot (reuses AuditPilot helper), site_crawler.py | `FIRECRAWL_API_KEY` |
| Recraft | AI image generation (brand-aware) | AutoPilot AI (`image_gen.py`) | `RECRAFT_API_KEY` |

## Client/workspace integrations

| Tool | Purpose | Used by | Env var |
|---|---|---|---|
| ClickUp | Push monthly plans as tasks, pull completion progress | `seo_executor.py`, SEO Operations | `CLICKUP_API_KEY`, `CLICKUP_WORKSPACE_ID` |
| Google Workspace CLI | Drive, Docs, Sheets, Gmail, Calendar, Tasks (MCP-style CLI invoked by vault agent) | PilotCore (future), vault sync scripts | Authorized via `matthew@getproofpilot.com` |
| Reddit (PRAW + Web client) | Read subreddit posts, post comments, manage accounts | RedditPilot (`core/reddit_client.py`, `platforms/reddit_web.py`) | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, per-account creds in `config.seeded.yaml` |

## Storage

| Store | What lives there | Env var / path |
|---|---|---|
| SQLite (`jobs.db`) | Jobs, clients, content, approvals, SEO results | `DATABASE_PATH` — default `/app/data/jobs.db` on Railway |
| Railway Volume (`/app/data`) | Persistent storage across deploys: DB, memory store, `redditpilot/config.yaml`, seo-results/ | `DOCS_DIR=/app/data` on Railway |
| `backend/vault_data/` | Client YAML synced from Obsidian (`_clients-index.yaml`, `clients/*/`) | Not an env var — synced via `scripts/sync-vault-data.sh` |
| `backend/memory/store.py` | Shared client-memory store (brand, design system, learnings) | Writes under `DOCS_DIR` |

## Search Atlas — **off-limits list**

These endpoints exist in the Search Atlas MCP but MUST NEVER be called
from this repo. They publish or modify client-facing assets outside our
approval workflow:

- `content_genius`
- `digital_pr`
- `linklab`
- `otto_ppc`
- `press_release`
- `OTTO_SEO_Deployment`
- `OTTO_Wildfire`
- `gbp_posts_automation`
- `gbp_posts_publication`
- `Content_Publication_Tools`

Approved Search Atlas namespaces are listed in `CLAUDE.md § Search Atlas MCP`.

## Environment variable matrix

Grouped by need. Full names and defaults in `backend/.env.example`.

**Required to boot:**
- `ANTHROPIC_API_KEY`
- `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`

**Required for specific Pilots:**
- AuditPilot / QAPilot: `FIRECRAWL_API_KEY`
- AutoPilot (images): `RECRAFT_API_KEY` (and/or `OPENROUTER_API_KEY` / `GEMINI_API_KEY`)
- RedditPilot: `OPENROUTER_API_KEY` + Reddit creds in `redditpilot/config.yaml`
- SEO Operations / ClickUp sync: `CLICKUP_API_KEY`, `CLICKUP_WORKSPACE_ID`
- Search Atlas: `SEARCHATLAS_API_KEY`

**Optional:**
- `DATABASE_PATH` (defaults to `./data/jobs.db` locally, `/app/data/jobs.db` on Railway)
- `DOCS_DIR` (defaults to `./data` locally, `/app/data` on Railway)
- `REDDITPILOT_CONFIG_PATH` (defaults to `$DOCS_DIR/redditpilot/config.yaml`)

## Never

- Commit `.env` or per-client API keys.
- Call off-limits Search Atlas endpoints.
- Hit DataForSEO live endpoints in loops — use standard queue for bulk jobs (10-20x cheaper).
- Hardcode credentials. Everything goes through `os.environ.get()` or the vault YAML.
