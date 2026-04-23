# TOOLS — RedditPilot

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| OpenRouter | Varies (Nano Banana, MiniMax, Claude, etc.) | Content generation per persona | `OPENROUTER_API_KEY` |
| Anthropic | claude-opus-4-6 (optional) | Higher-stakes outputs | `ANTHROPIC_API_KEY` |

Model routing lives in `engines/llm_client.py` and is configurable per
opportunity class.

## Reddit platform

| Client | Path | Purpose |
|---|---|---|
| PRAW (Reddit API) | `core/reddit_client.py` | Authenticated reads + writes (official API) |
| Reddit Web client | `platforms/reddit_web.py` | Web scrape fallback when API quota is exhausted or data needs aren't API-exposed |

### Credentials
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — app-level
- Per-account cookies + credentials in `config.seeded.yaml` (encrypted at
  rest via cookie_manager)

## Storage

| Path | Contents | Lifetime |
|---|---|---|
| `core/database.py` (SQLite) | Opportunities, actions, performance, A/B results, failures, subreddit intel, account state | Persistent (Railway Volume) |
| `config.yaml` | Client roster, persona preferences, subreddit allow/deny lists | Persistent (Railway Volume: `$DOCS_DIR/redditpilot/config.yaml`) |
| `config.example.yaml` | Onboarding template copied to `$DOCS_DIR/redditpilot/config.yaml` on first run | Committed, read-only |

## Shared internal modules

| Module | Why |
|---|---|
| `core/resource_monitor.py` | Hard caps on API calls, tokens, posts per day |
| `safety/account_manager.py` | Account rotation, cooldowns, ban detection |
| `engines/ab_testing.py` | Variant assignment + result analysis |
| `engines/learning.py` | Performance → strategy feedback loop |

## Prompt files

In `prompts/`:
- `system_base.txt` — base system prompt
- `anti_ai_rules.txt` — detection-avoidance rules (no em dashes, tell-words, etc.)
- `persona_curious_learner.txt`, `persona_friendly_neighbor.txt`, `persona_helpful_expert.txt`, `persona_practical_diy.txt` — four voices
- `comment_*.txt`, `post_*.txt` — content-type templates

## Called from

- `backend/reddit_agent.py` (lazy singleton shim at backend root — future: absorbed into `router.py`)
- `backend/server.py` routes prefixed `/api/redditpilot/*`

## Never

- Post from an account without minimum age + karma. Thresholds in config.
- Post in subreddits absent from cached `subreddit_intel`.
- Disable the resource monitor or ban detection.
- Commit real account credentials — use `config.example.yaml` only.
