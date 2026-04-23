# AGENTS.md

> Universal coding-agent brief for this repo. Any AI tool (Claude, Cursor, Copilot,
> Aider) should read this first. For deep business/product context, see [CLAUDE.md](./CLAUDE.md).
> For the roster of named Pilots this repo ships, see [agent-team-map.md](./agent-team-map.md).
> For every integration and env var, see [TOOLS.md](./TOOLS.md).

## What this is

**ProofPilot Agent Hub** — a FastAPI + Python backend that runs 25 SEO
workflows and 6 named "Pilots" (multi-stage agents) against real client
data. Streams output live via SSE, exports branded `.docx` files, and
deploys to Railway.

## Stack

- **Python 3.11**, FastAPI, uvicorn, SSE streaming via `async` generators.
- **Anthropic SDK** — Claude Opus 4.6 for workflows, Sonnet 4.6 for
  operations. Always enable `thinking: {"type": "adaptive"}`, `max_tokens: 8000`.
  Do NOT use assistant prefills (Opus 4.6 returns 400).
- **SQLite** on Railway Volume at `/app/data/jobs.db`.
- **Frontend**: vanilla HTML/CSS/JS SPA in `backend/web/`. No framework, no build step.
- **Deploy**: Railway auto-deploys on push to `main`. Root build dir is `/backend`.
  Dockerfile uses Python 3.11. There is no staging.
- **Tests**: `pytest` (scaffolded per agent, not yet comprehensive).

## Commands

```bash
# Install
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run locally (hot reload)
cd backend && .venv/bin/uvicorn server:app --reload   # http://localhost:8000

# Health
curl http://localhost:8000/health

# Test a pilot (SSE)
curl -N -X POST http://localhost:8000/api/agents/qa \
  -H "Content-Type: application/json" \
  -d '{"content":"...","keyword":"...","client_name":"..."}'

# Railway logs / env vars
railway logs
railway variables
railway variables set KEY=value
```

## Local install (Claude Code agents + skills)

Every Pilot in `backend/agents/` and every workflow in `backend/workflows/`
is available as a Claude Code agent or skill on your laptop. One command:

```bash
./scripts/install-local.sh
```

This creates symlinks in `~/.claude/agents/` (10 pilot agents, named
`proofpilot-<pilot>.md`) and `~/.claude/skills/` (10 pilot skills +
25 `pp-<workflow>` skills).

After install:
- From any Claude Code session, say *"use auditpilot to audit acme.com"*
  and `proofpilot-auditpilot` is invoked with its skill auto-loaded.
- `git pull` on this repo updates all agents/skills in place — no
  re-install needed.

Preview what would happen:

```bash
./scripts/install-local.sh --dry-run
```

Uninstall (only removes symlinks pointing into this repo — leaves
unrelated Claude Code skills alone):

```bash
./scripts/uninstall-local.sh
```

## File layout

```
agent-hub/
├── AGENTS.md                   # this file — universal standard
├── CLAUDE.md                   # Claude-specific master context (business, roadmap)
├── ROADMAP.md                  # what to build next
├── agent-team-map.md           # all 6 Pilots at a glance
├── TOOLS.md                    # every integration, env var, and which Pilot uses it
├── USER.md                     # operator profile (Matthew)
├── backend/
│   ├── server.py               # FastAPI app — mounts agent routers
│   ├── agents/                 # one folder per Pilot (see backend/agents/_template/)
│   ├── workflows/              # 25 single-pass SEO workflows (not multi-stage agents)
│   ├── pipeline/               # AutoPilot AI — 6-stage SEO page builder (pre-rename)
│   ├── redditpilot/            # RedditPilot — full outreach engine (pre-rename)
│   ├── scheduler/              # APScheduler for cron jobs
│   ├── utils/                  # DataForSEO, Search Atlas, docx gen, DB
│   ├── memory/                 # shared brand / client memory store
│   ├── vault_data/             # client YAML synced from Obsidian
│   └── web/                    # frontend SPA
└── docs/plans/                 # design docs per feature (YYYY-MM-DD-*.md)
```

## Conventions

### Code
- Python 3.11 syntax (`dict | None`, `str | None`, PEP 604 unions — fine).
- Async generators for streaming (`async def run(...) -> AsyncGenerator[str, None]`).
- Pydantic for request/response schemas (each agent has `schemas.py`).
- Env vars via `os.environ.get(...)` — never hardcode secrets.
- Prompts are `.md` files in `prompts/`, NOT multi-line Python strings.

### File organization
- Per-agent rule: each Pilot is self-contained in `backend/agents/<name>/`.
  Shape is documented in `backend/agents/_template/`.
- NO cross-agent imports (`from backend.agents.other_pilot` is forbidden).
  Shared utilities live in `backend/utils/` (and eventually `backend/core/`,
  `backend/integrations/`).
- NO new files at repo root without a reason. Most work goes in `backend/`.

### Commits
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`.
- Attribution is disabled globally — don't add Co-Authored-By.
- Main branch only (single-dev workflow, Railway auto-deploys).
- Test locally before pushing — no staging.

## Adding a new Pilot

1. `cp -r backend/agents/_template backend/agents/<pilot_id>`
2. Edit `manifest.py` — set `id`, `title`, `route_prefix`, `version`.
3. Replace `prompts/system.md` with the agent's prompt.
4. Write routes in `router.py`, logic in `engine.py`, models in `schemas.py`.
5. Add `SOUL.md`, `TOOLS.md`, and at least one sample to `examples/`.
6. Restart server — auto-discovery picks it up via `backend/agents/__init__.py`.

## Deploy

`git push origin main` → Railway auto-deploys. Takes ~2-3 min. Monitor:
```bash
railway logs --tail
curl https://proofpilot-agents.up.railway.app/health
```

Rollback = revert the commit and re-push. The Railway Volume (`/app/data`)
persists across deploys; the database and memory/ data survive.

## Never

- Commit `.env` or any secret.
- Use Search Atlas endpoints in `off-limits` list (see [TOOLS.md](./TOOLS.md)).
- Auto-publish to client sites without explicit approval.
- Push untested code (Railway has no staging).
- Use assistant prefills with Opus 4.6 (400 error).
- Add `Co-Authored-By` to commits (disabled globally).
