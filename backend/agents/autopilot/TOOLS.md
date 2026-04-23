# TOOLS — AutoPilot AI

> Currently in `backend/pipeline/` — moves to `backend/agents/autopilot/`.

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-opus-4-6 | Research, strategy, copywrite, design prompt, QA stages | `ANTHROPIC_API_KEY` |
| Recraft | Varies (recraft-v2, recraft-v3) | Generic trade photography, realistic scenes | `RECRAFT_API_KEY` |
| OpenRouter → Nano Banana | `google/gemini-2.5-flash-image-preview` (via OpenRouter chat/completions) | Brand-loaded images (real brand logos, truck wraps, branded products), composited edits | `OPENROUTER_API_KEY` |
| Google | Gemini (native API, alternate path) | Image generation fallback | `GEMINI_API_KEY` |

## Data / scraping

| Service | Used for | Env var |
|---|---|---|
| Firecrawl | Brand extraction (homepage + key pages), voice extraction, competitor research | `FIRECRAWL_API_KEY` |
| DataForSEO (via shared utils) | Keyword data for target-keyword validation | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |

## Shared internal modules

| Module | Why |
|---|---|
| `backend/memory/store.py` | Client memory — design_system, asset_catalog, brand_voice, business_intel, learnings |
| `backend/utils/docx_generator.py` | Not used for final HTML, but for reports of the pipeline run |
| `backend/utils/db.py` | Job persistence |

## Pipeline stages

Orchestrated in `engine.py` via `stages.py`:

1. **Research** — Firecrawl + competitor scrape → business intelligence
2. **Strategy** — page type selection, section picks, keyword intent
3. **Copywrite** — Claude Opus writes to the brand voice profile
4. **Design** — CSS/HTML with brand tokens, self-hosted fonts detected
   from the live site
5. **Images** — Recraft / Nano Banana per slot, respecting brand rules
6. **QA** — scoring against rubric; < 80 = parse directives → re-run
   copywrite/design → loop up to 3 rounds; regression triggers patcher

See `docs/plans/2026-03-28-autopilot-ai-architecture.md`.

## Key helpers

| File | Role |
|---|---|
| `brand_extractor.py` | Live site → design system (colors, fonts, layouts) |
| `brand_memory.py` | Persisted brand profile + design prompt formatting |
| `voice_extractor.py` | Live site → voice profile used by copywrite |
| `business_researcher.py` | Business intel aggregator |
| `client_research_agent.py` | Per-client brain builder |
| `brain_formatter.py` | Context injection per workflow type |
| `image_gen.py` | Recraft + Nano Banana routing + slot-filling |
| `design_prompt.py` | Shared design prompt used by Claude + Gemini paths |
| `skill_loader.py` | Loads Claude Code skills into stage prompts |
| `interview_agent.py` | Structured interview with the client operator |
| `sprint_runner.py` | Multi-page sprint orchestration |
| `page_types/` | One config per page type (service_page, location_page, blog_post) |

## Storage

| Path | Contents | Lifetime |
|---|---|---|
| `backend/memory/store.py` → `$DOCS_DIR/memory/` | Per-client brand + memory | Persistent (Railway Volume) |
| `temp_docs/` | Per-job generated HTML, images, assets | Transient (TTL cleanup planned) |

## Never

- Use real brand logos (Generac, Square D, Carrier) unless the client
  is licensed or has approved.
- Ship a page with a QA score < 80. Revise or reject.
- Skip brand extraction. Generic output is unacceptable.
- Run > 3 revision rounds. Escalate to human instead.
