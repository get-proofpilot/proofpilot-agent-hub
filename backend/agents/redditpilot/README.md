# RedditPilot

Full Reddit outreach engine — subreddit scanning, opportunity
discovery, human-in-the-loop content generation, A/B testing, learning
loop. Runs in-process.

## Endpoints

Server.py exposes ~40 routes under `/api/reddit/*`. See the live
dashboard or [CLAUDE.md](./CLAUDE.md) for the full list.

Quickstart:
```bash
curl http://localhost:8000/api/reddit/status
curl http://localhost:8000/api/reddit/opportunities?limit=10
curl -X POST http://localhost:8000/api/reddit/control/scan
```

## Architecture

```
server.py  ──import──▶  shim.py  ──lazy─▶  orchestrator.py
                                                │
                             ┌──────────────────┼──────────────────┐
                             ▼                  ▼                  ▼
                         core/              engines/            platforms/
                         (DB, config,    (scanner, content,   (reddit_web,
                          PRAW, res)      learning, A/B)       PRAW wrap)
                             │                  │
                             └──────┬───────────┘
                                    ▼
                                 safety/
                         (accounts, cooldowns, bans)
```

## Config

On first boot, RedditPilot copies `config.seeded.yaml` to
`$DOCS_DIR/redditpilot/config.yaml` (or `./data/redditpilot/config.yaml`
locally). Subsequent changes happen through the dashboard — do NOT
edit the seeded template.

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
# Dashboard: http://localhost:8000/ → RedditPilot tab
```

## Test before deploy

- Restart the scheduler from the dashboard (NOT via cURL — the
  dashboard knows the right control action).
- Check `GET /api/reddit/status` returns configured=true.
- Check `GET /api/reddit/stats` returns non-zero account and client counts.
- Run one manual scan via `POST /api/reddit/control/scan` and inspect
  the opportunity feed.
