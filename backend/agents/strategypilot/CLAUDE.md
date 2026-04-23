# CLAUDE.md — StrategyPilot

## What this agent does

StrategyPilot is the **SEO strategy director**. Given a client site,
service, and location, it produces a full 13-section strategy document
covering current state, competitor gaps, page systems to build, site
architecture, 90-day rollout, 12-month future state, ROI model, and KPI
framework.

Unlike AuditPilot (which is a sales document), StrategyPilot produces
the **roadmap for fulfillment** — the document that drives 6-12 months
of SEO work for a client.

## Entry point

- `POST /api/agents/strategy` — SSE stream, `.docx` at the end

## The 5 stages (prompt-encoded)

1. **Footprint** (`footprint_system.md`) — classify what exists on the
   site using industry archetype + 10 page categories.
2. **Competitive** (`competitive_system.md`) — SERP pattern analysis,
   competitor page systems, gap analysis, question mining.
3. **Page Systems** (`page_systems_system.md`) — 12-category taxonomy
   (A-L) of what pages the client should build, prioritized by 10
   factors (revenue proximity, demand confidence, intent quality, etc).
4. **ROI** (`roi_system.md`) — 3-scenario funnel model (conservative /
   realistic / aggressive) with traffic → leads → revenue math.
5. **Synthesis** (`synthesis_system.md`) — 13-section strategy doc.

## Folder map

- `engine.py` — 5-stage orchestrator
- `research.py` — DataForSEO collection (imports from AuditPilot's
  `data_collector` for Firecrawl scrape)
- `prompts/` — one `.md` per stage

## Hard rules

- The 12-category page taxonomy (A-L) is load-bearing. Do NOT add or
  remove categories without updating both `page_systems_system.md` and
  the CLAUDE.md above.
- The 10-factor prioritization is also prompt-encoded. Keep it there.
- Write for a business owner, not an SEO. Fifth-grade reading level.
  NO em dashes, semicolons in body copy, or "comprehensive" / "leverage".
  Enforced by synthesis prompt.
- Tables are first-class output. Don't let the engine strip them.
