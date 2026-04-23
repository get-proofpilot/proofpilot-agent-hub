# TOOLS — StrategyPilot

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-opus-4-6 | All 5 stages (footprint, competitive, page systems, ROI, synthesis) | `ANTHROPIC_API_KEY` |

## Data / scraping

| Service | Used for | Env var |
|---|---|---|
| Firecrawl (via AuditPilot's `data_collector`) | Site crawl to classify existing pages | `FIRECRAWL_API_KEY` |
| DataForSEO — Labs Ranked Keywords | Both prospect and competitor ranked-keyword lists | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — SERP (Organic + Maps) | Competitor page systems analysis, SERP pattern detection | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Keywords Data | Volumes + CPC for money keyword prioritization | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Labs Keyword Difficulty | Competitive difficulty for prioritization | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |

## Shared internal modules

| Module | Why |
|---|---|
| `backend/agents/auditpilot.data_collector` | `firecrawl_scrape` + DataForSEO SERP helpers (cross-agent reach — will move to `integrations/`) |
| `backend/utils/dataforseo.py` | All DataForSEO calls |
| `backend/utils/docx_generator.py` | Branded 13-section strategy `.docx` |

## Prompt files (the source of truth)

- `prompts/footprint_system.md` — Stage 1 site classification + page inventory
- `prompts/competitive_system.md` — Stage 2 SERP patterns, competitor gaps, question mining
- `prompts/page_systems_system.md` — Stage 3 12-category taxonomy + 10-factor prioritization
- `prompts/roi_system.md` — Stage 4 3-scenario funnel model
- `prompts/synthesis_system.md` — Stage 5 13-section doc

The A-L taxonomy and the 10-factor prioritization both live in
`page_systems_system.md`. They are load-bearing — do not re-encode in Python.

## Storage

None per-agent. Shared SQLite + `temp_docs/` for artifacts.
