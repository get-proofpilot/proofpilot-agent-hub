# Agent Team Map

> The Pilots that ship with this repo, what each owns, how they wire together.
> For per-agent deep-dives, see `backend/agents/<name>/CLAUDE.md`.

## Roster

| Pilot | Location | Route prefix | Purpose | Output |
|---|---|---|---|---|
| **Pilot Core** | `backend/agents/pilotcore/` | `/api/pilot/*` | Central AI coworker — aggregates client context, morning briefings, escalation checks | JSON + Slack-formatted SSE |
| **AuditPilot** | `backend/agents/auditpilot/` | `/api/agents/audit` | 4-stage sales audit (Firecrawl crawl → DataForSEO ranking reality → 8-dimension Strategic Brain → Sales Audit v2 doc) | SSE + branded `.docx` |
| **StrategyPilot** | `backend/agents/strategypilot/` | `/api/agents/strategy` | 5-stage SEO strategy (footprint → competitive → 12-category page taxonomy → ROI model → 13-section doc) | SSE + branded `.docx` |
| **QAPilot** | `backend/agents/qapilot/` | `/api/agents/qa` | 7-layer quality review for SEO deliverables (accuracy, on-page, content, AI detection, visual, strategy, consistency) | SSE + structured JSON report |
| **AutoPilot AI** | `backend/pipeline/` *(will move to `backend/agents/autopilot/`)* | `/api/pipeline/*` | 6-stage SEO page builder (research → strategy → copywrite → design → images → QA) with revision loop | SSE + full HTML/CSS/assets |
| **RedditPilot** | `backend/redditpilot/` *(will move to `backend/agents/redditpilot/`)* | `/api/redditpilot/*` | Reddit outreach engine — subreddit scanning, opportunity discovery, human-in-the-loop comment/post generation, A/B testing, learning loop | JSON + scheduled autonomous cycles |

## What each Pilot produces

### Pilot Core — **operational intelligence for Matthew**
Doesn't produce client deliverables. Reads vault + job DB + (future) Slack/Gmail/Calendar MCP and produces:
- Morning briefing (Slack format, <300 words)
- Escalation alerts (🔴 overdue / 🟡 at-risk / 🔵 note)
- Full client context snapshot (JSON)

### AuditPilot — **sales documents that close prospects**
Input: prospect domain + service vertical + location.
Output: 8-section Sales Audit v2 doc that makes invisibility visceral before explaining the technical reasons.

### StrategyPilot — **fulfillment roadmaps for existing clients**
Input: client domain + service + location (+ optional competitor list).
Output: 13-section strategy doc with 6-12 months of SEO work for the team to execute.

### QAPilot — **quality gate before work goes to clients**
Input: raw content OR live URL + target keyword + client.
Output: PASS / CONDITIONAL_PASS / FAIL with per-layer findings and top-3 fixes.

### AutoPilot AI — **ready-to-publish SEO pages**
Input: client + page type (service / location / blog) + target keyword.
Output: full HTML page with client's brand system applied, 5+ images, QA-validated (score ≥ 80 or 3 revision rounds max).

### RedditPilot — **authentic Reddit engagement at scale**
Input: nothing (runs autonomously). Configured per client via YAML.
Output: daily opportunity queue + generated replies/posts with human approval; learning loop tunes subreddit targeting and voice over time.

## Wiring

```
                                ┌──────────────────┐
                                │  server.py       │
                                │  (FastAPI app)   │
                                └────────┬─────────┘
                                         │
                    mount_agents()       │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
           ┌────────▼──────┐    ┌────────▼──────┐    ┌────────▼──────┐
           │  PilotCore    │    │   AuditPilot  │    │ StrategyPilot │
           │  /api/pilot/* │    │ /api/agents/  │    │ /api/agents/  │
           │               │    │    audit      │    │   strategy    │
           └───────────────┘    └───────┬───────┘    └───────┬───────┘
                                        │                    │
                                        │ Firecrawl scrape   │ (reuses
                                        │ DataForSEO SERP    │  auditpilot.
                                        │                    │  data_collector)
                                        │                    │
           ┌───────────────┐    ┌───────▼───────┐    ┌────────────────┐
           │    QAPilot    │    │   AutoPilot   │    │   RedditPilot  │
           │  /api/agents/ │    │  /api/        │    │  /api/         │
           │      qa       │    │  pipeline/*   │    │  redditpilot/* │
           └───────────────┘    └───────────────┘    └────────────────┘
                    │                    │                    │
                    │                    │                    │
                ┌───▼────────────────────▼────────────────────▼───┐
                │   Shared: utils/ (DataForSEO, Search Atlas,     │
                │   docx_generator, db, memory store, vault_data) │
                └─────────────────────────────────────────────────┘
```

## Cross-Pilot calls

Today there is exactly ONE legitimate cross-agent import:

- `backend/agents/qapilot/engine.py` imports `firecrawl_scrape` from
  `backend/agents/auditpilot/data_collector.py`.

This is a shared utility by history, not by design. When `backend/integrations/
firecrawl.py` exists, both Pilots should import from there, and the cross-agent
reach goes away.

**Rule:** no other cross-agent imports. Shared logic goes in `backend/utils/`
(current) or `backend/core/` and `backend/integrations/` (future).

## Orchestration

Pilot Core is the **orchestrator**, in the sense that it's the AI coworker
that knows about all the other Pilots and can sequence them on Matthew's
behalf. But there's no central "router agent" — each Pilot has its own
route and can be invoked independently.

Pattern for future work: Pilot Core should be able to say "run AuditPilot
for this prospect, then draft an email with the key findings" — but the
per-Pilot HTTP routes are the public interface, not a shared Python API.

## Adding a new Pilot

See [AGENTS.md § Adding a new Pilot](./AGENTS.md#adding-a-new-pilot).
