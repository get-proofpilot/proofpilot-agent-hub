# TOOLS — AuditPilot

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-opus-4-6 | All 4 stages (site analysis, ranking reality, Strategic Brain, synthesis) | `ANTHROPIC_API_KEY` |

## Data / scraping

| Service | Used for | Env var |
|---|---|---|
| Firecrawl | Site crawl, homepage scrape, content extraction | `FIRECRAWL_API_KEY` |
| DataForSEO — SERP (Maps + Organic) | Top-10 rankings for 10 core keywords, local pack | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Keywords Data | Monthly search volumes | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Labs Ranked Keywords | Prospect's actual ranked keywords | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Labs Competitors | Competitor domains in market | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Backlinks Summary | Domain authority + backlink count | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| DataForSEO — Business Data (GMB) | Competitor GBP profiles | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |

## Shared internal modules

| Module | Why |
|---|---|
| `backend/utils/dataforseo.py` | All DataForSEO calls |
| `backend/utils/docx_generator.py` | Branded Sales Audit v2 `.docx` |
| `backend/utils/db.py` | Job persistence |

## Prompt files (the source of truth)

- `prompts/site_analysis_system.md` — Stage 1 crawl-to-structured-JSON
- `prompts/ranking_reality_system.md` — Stage 2 rankings + indexing gap
- `prompts/strategic_brain_system.md` — Stage 3, 8-dimension invisibility analysis
- `prompts/synthesis_system.md` — Stage 4, 8-section Sales Audit v2 doc

## Storage

None per-agent. Jobs go to shared SQLite; `.docx` files go to
`temp_docs/` for download.

## Called by other Pilots

- QAPilot imports `firecrawl_scrape` from `data_collector.py`. When
  `backend/integrations/firecrawl.py` exists, both should import from there.
