# QAPilot

Internal QA agent for SEO deliverables. 7-layer review produces a
structured JSON report with PASS / CONDITIONAL PASS / FAIL verdict.

## Endpoint

`POST /api/agents/qa` → SSE stream + `.docx` export

## Inputs

| Field | Required | Description |
|---|---|---|
| `content` | one of | Raw markdown / HTML to review |
| `url` | one of | Live URL to scrape and review |
| `keyword` | yes | Target keyword |
| `client_name` | yes | Client for context |
| `business_type` | no | Narrows Layer 6 strategy checks |
| `title_tag` | no | Feeds Layer 2 |
| `meta_description` | no | Feeds Layer 2 |

## Output

JSON report with:
- `overall_score` (0-100)
- `verdict` (PASS / CONDITIONAL_PASS / FAIL)
- Per-layer findings (score, status, issues, warnings, notes)
- `top_3_fixes`
- `summary`

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
curl -N -X POST http://localhost:8000/api/agents/qa \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "keyword": "panel upgrade", "client_name": "All Thingz Electric"}'
```
