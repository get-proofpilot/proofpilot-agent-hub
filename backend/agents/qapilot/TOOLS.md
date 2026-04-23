# TOOLS — QAPilot

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-opus-4-6 | 7-layer review synthesis | `ANTHROPIC_API_KEY` |

## Data / scraping

| Service | Used for | Env var |
|---|---|---|
| Firecrawl | Scraping live URLs when the request provides `url` instead of raw content | `FIRECRAWL_API_KEY` |

## Shared internal modules

| Module | Why we need it |
|---|---|
| `backend/agents/auditpilot/data_collector.firecrawl_scrape` | URL → markdown. Cross-agent reach — move to `backend/integrations/firecrawl.py` when that module exists. |
| `backend/utils/docx_generator.py` | Branded `.docx` export of the report |
| `backend/utils/db.py` | Job persistence |

## Prompt files (the source of truth)

- `prompts/qa_system.md` — full 7-layer review prompt (scoring, thresholds, tell-words)
- `prompts/qa_content_only.md` — content-only fallback (Layers 2 and 5 skipped)

Changing what QAPilot checks = editing these files, not `engine.py`.

## Storage

None. QAPilot is stateless — every call reviews the input from scratch.
