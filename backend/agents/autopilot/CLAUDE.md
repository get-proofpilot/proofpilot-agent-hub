# CLAUDE.md — AutoPilot AI

## What this agent does

AutoPilot is the **SEO page builder**. Given a client, a page type
(service / location / blog), and a target keyword, it produces a full
publishable HTML page with brand-native design, trade-accurate imagery,
and a QA-validated score ≥ 80.

It is the single feature most responsible for removing Matthew from
the fulfillment bottleneck. A full month of content for one client
should take < 10 minutes of his time.

## Entry points

- `POST /api/pipeline/run` — start a page build
- `GET /api/pipeline/{pipeline_id}` — status
- `GET /api/pipeline/{pipeline_id}/artifact/{stage}` — stage output
- `GET /api/pipeline/{pipeline_id}/output/{stage}` — stage render
- `POST /api/pipeline/{pipeline_id}/approve|reject`
- `POST /api/pipeline/batch` — sprint mode (multiple pages)

Routes are currently hand-rolled in `backend/server.py`. This agent's
`router.py` is a scaffold for the future cutover.

## The 6 stages

1. **Research** (`stages.py::run_research`) — Firecrawl the client site
   and competitors, produce a business-intel brief.
2. **Strategy** (`stages.py::run_strategy`) — choose page sections,
   keyword intent, internal link plan.
3. **Copywrite** (`stages.py::run_copywrite`) — Opus writes to the
   voice profile from `voice_extractor.py`.
4. **Design** (`stages.py::run_design`) — HTML/CSS using the brand
   system from `brand_extractor.py` + `brand_memory.py`.
5. **Images** (`stages.py::run_images`) — Recraft for generic trade
   photography; Nano Banana (via OpenRouter) for brand-loaded images.
6. **QA** (`stages.py::run_qa`) — score against the rubric. If < 80,
   parse directives → re-run copywrite/design → loop up to 3 rounds.
   The lightweight design patcher applies CSS-level fixes to prevent
   regression on round 2+.

See `docs/plans/2026-03-28-autopilot-ai-architecture.md` for the full
architecture doc.

## Folder map

- `engine.py` — `PipelineEngine`, run lifecycle, SSE streaming
- `stages.py` — the 6 stage runners (STAGE_RUNNERS registry)
- `artifacts.py` — typed artifacts passed between stages
- `brand_extractor.py` — live site → design system
- `brand_memory.py` — persisted brand + prompt formatting
- `brain_formatter.py` — context-aware memory injection per workflow
- `business_researcher.py` — business-intel aggregator
- `client_research_agent.py` — per-client brain builder
- `voice_extractor.py` — live site → voice profile
- `design_prompt.py` — shared design prompt (Claude + Gemini paths)
- `gemini_design.py` — alternate Gemini design path
- `image_gen.py` — Recraft + Nano Banana routing
- `interview_agent.py` — structured client-operator interview
- `skill_loader.py` — loads Claude Code skills into stage prompts
- `sprint_runner.py` — multi-page sprint orchestration
- `page_types/` — one config per page type (`service_page`, `location_page`, `blog_post`)
- `prompts/` — extract inline prompt strings here over time
- `examples/` — shipped pages, brand extractions, revision stories

## Hard rules

- NEVER publish. AutoPilot produces artifacts; Jo Paula publishes.
- NEVER skip the QA stage. Score ≥ 80 or revise or reject.
- NEVER run > 3 revision rounds. Escalate instead.
- NEVER reuse real brand logos (Generac, Square D, Carrier, etc.)
  unless the client is licensed or approved. Routes:
  Nano Banana = branded, Recraft = generic.
- NEVER invent brand. If `brand_extractor.py` fails, stop. The client
  site is the source of truth.

## Known tech-debt (as of this move)

- `sprint_runner.py` uses Python 3.10+ syntax (`dict | None`). Works
  on Railway (Python 3.11). Breaks some local venvs if run with 3.9.
- Inline prompt strings in `stages.py` — extract to `prompts/*.md` when
  touching them.
- `client_research_agent.py` and `engine.py` still do inline
  `from agents.autopilot.X import Y` for lazy-load; this is fine.
