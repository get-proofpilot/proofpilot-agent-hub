# AuditPilot

Multi-stage sales audit agent. Crawls a prospect site, pulls DataForSEO
ranking data, runs the 8-dimension Strategic Brain, and synthesizes a
branded Sales Audit v2 document.

## Endpoint

`POST /api/agents/audit` → SSE stream + `.docx` export

## Inputs

| Field | Required | Description |
|---|---|---|
| `domain` | yes | Prospect's domain (e.g., `allthingzelectric.com`) |
| `service` | yes | Service vertical (e.g., `electrician`) |
| `location` | yes | City, State (e.g., `Chandler, AZ`) |
| `monthly_revenue` | no | Adds specificity to ROI section |
| `avg_job_value` | no | Adds specificity to ROI section |
| `notes` | no | Sales context |

## Stages

1. Site Analysis (Firecrawl + LLM)
2. Ranking Reality Check (DataForSEO SERP + ranked keywords)
3. Strategic Brain (8 dimensions of invisibility)
4. Synthesis (Sales Audit v2 document)

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
curl -N -X POST http://localhost:8000/api/agents/audit \
  -H "Content-Type: application/json" \
  -d '{"domain":"example.com","service":"plumber","location":"Mesa, AZ"}'
```
