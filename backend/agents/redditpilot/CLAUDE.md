# CLAUDE.md — RedditPilot

## What this agent does

RedditPilot is ProofPilot's **Reddit outreach engine**. It scans
subreddits for opportunities (questions in a client's vertical),
generates persona-appropriate comments and posts, A/B-tests variants,
and learns from performance over time — all with a human-in-the-loop
gate by default.

Runs in-process via a lazy singleton managed by `shim.py`. Routes are
currently hand-rolled in `backend/server.py` under `/api/reddit/*`.

## Entry points

Server.py exposes ~40 endpoints under `/api/reddit/*`. Key ones:

- `GET /api/reddit/status` / `GET /api/reddit/stats` / `GET /api/reddit/insights`
- `GET /api/reddit/clients` / `GET /api/reddit/clients/{slug}`
- `GET /api/reddit/opportunities` / `GET /api/reddit/actions`
- `POST /api/reddit/control/{action}` — scan / learn / pause / resume / emergency_stop
- `GET /api/reddit/config-template` — returns the seeded YAML for onboarding
- Account CRUD at `/api/reddit/accounts*`

## Folder map

- `shim.py` — lazy-load singleton, path resolution, ~40 helper functions
  called from server.py. This is the ONLY module server.py imports from
  the agent. Everything else is internal.
- `orchestrator.py` — main RedditPilot class (scan loop, post scheduling,
  learning cadence).
- `core/` — foundational modules:
  - `config.py` — YAML config schema + loader
  - `database.py` — SQLite schema and queries
  - `reddit_client.py` — PRAW client wrapper
  - `business_manager.py` — per-client state
  - `cookie_manager.py` — encrypted cookie storage
  - `resource_monitor.py` — hard caps (API calls, tokens, posts/day)
- `engines/` — the intelligence:
  - `scanner.py` — subreddit opportunity scanning
  - `discovery.py` — new subreddit candidate discovery
  - `content_generator.py` / `content_curator.py` — produce + filter drafts
  - `research_engine.py` — per-opportunity research
  - `strategy.py` — persona + subreddit targeting
  - `ab_testing.py` — variant assignment + analysis
  - `learning.py` — performance → strategy feedback loop
  - `subreddit_intel.py` — cached subreddit modpol + culture
  - `llm_client.py` — OpenRouter routing
- `platforms/` — Reddit interface:
  - `reddit_web.py` — web fallback when API quota exhausted
- `safety/` — guardrails:
  - `account_manager.py` — account rotation, cooldowns, ban detection
- `integrations/` — agent-local integrations
- `utils/` — agent-local utilities
- `prompts/` — persona and content prompts (`.txt`, already extracted long ago)
- `config.example.yaml` / `config.seeded.yaml` — onboarding + seeded client roster

## Config path resolution

Order (in `shim.py`):
1. `$REDDITPILOT_CONFIG_PATH`
2. `$DOCS_DIR/redditpilot/config.yaml` (Railway volume — survives deploys)
3. `./data/redditpilot/config.yaml` (local dev)

Seeded template: `backend/agents/redditpilot/config.seeded.yaml` (bundled
in the Docker image). Copied to the above path on first boot if nothing exists.

## Hard rules

- NEVER post without human approval unless auto-post is enabled for the
  account + opportunity class AND confidence exceeds threshold.
- NEVER operate on a subreddit without cached intel in `subreddit_intel`.
- NEVER post from a new account — accounts need age + karma minimums
  (enforced in `safety/account_manager.py`).
- NEVER commit real account credentials — `config.example.yaml` only.
- The `_stop_reddit_agent()` shutdown hook in server.py MUST run — it
  gracefully closes the orchestrator. Don't wrap it in broader try/except
  that swallows failures.

## Debugging

- Logger name: `proofpilot.reddit_agent` (preserved from the old shim).
- `failures` table in SQLite captures every exception with context.
- `resource_monitor.py` enforces hard caps — check its state if cycles
  aren't running.
- Never tail the config file for changes — restart the scheduler.
