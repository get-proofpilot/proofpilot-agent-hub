# StrategyPilot

SEO strategy document agent. Produces a 13-section roadmap document
covering footprint, competitive landscape, page systems, site
architecture, 90-day rollout, and ROI model.

## Endpoint

`POST /api/agents/strategy` → SSE stream + `.docx` export

## Inputs

| Field | Required | Description |
|---|---|---|
| `domain` | yes | Client site |
| `service` | yes | Service vertical |
| `location` | yes | City, State |
| `competitors` | no | Comma-separated competitor domains |
| `notes` | no | Additional context |

## Stages

1. Footprint (site classification + page inventory)
2. Competitive (SERP patterns + competitor page systems + gaps)
3. Page Systems (12-category taxonomy, prioritized)
4. ROI (3-scenario funnel model)
5. Synthesis (13-section markdown document)

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
curl -N -X POST http://localhost:8000/api/agents/strategy \
  -H "Content-Type: application/json" \
  -d '{"domain":"example.com","service":"plumber","location":"Mesa, AZ"}'
```
