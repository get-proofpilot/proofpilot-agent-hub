# AutoPilot AI

6-stage SEO page builder with a QA-driven revision loop. Given a client,
page type, and target keyword, produces a publishable HTML page in the
client's brand with trade-accurate imagery.

## Endpoints (currently in `server.py`, will move to `router.py`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/pipeline/run` | Start a page build (SSE stream) |
| GET | `/api/pipeline/{pipeline_id}` | Job status + metadata |
| GET | `/api/pipeline/{pipeline_id}/artifact/{stage}` | Raw stage artifact |
| GET | `/api/pipeline/{pipeline_id}/output/{stage}` | Rendered stage output |
| POST | `/api/pipeline/{pipeline_id}/approve` | Mark page as approved |
| POST | `/api/pipeline/{pipeline_id}/reject` | Reject, optional revision notes |
| POST | `/api/pipeline/batch` | Queue a sprint of multiple pages |
| POST | `/api/pipeline/batch/{pipeline_id}/start` | Kick off a queued sprint |
| GET | `/api/pipeline/templates` | Available page-type templates |

## Inputs

| Field | Required | Description |
|---|---|---|
| `client_id` | yes | Which client the page is for |
| `page_type` | yes | `service_page` \| `location_page` \| `blog_post` |
| `target_keyword` | yes | Primary keyword (drives strategy + copywrite) |
| `service` | sometimes | Required for service_page |
| `location` | sometimes | Required for location_page |
| `notes` | no | Extra context for the operator interview |

## Output

- Full HTML page at `/api/pipeline/{id}/output/design`
- Images in client asset catalog
- QA report with score + findings
- Branded `.docx` summary

## Run locally

```bash
cd backend
.venv/bin/uvicorn server:app --reload
curl -N -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"client_id":"all-thingz-electric","page_type":"service_page","target_keyword":"panel upgrade","service":"panel upgrade"}'
```

## Architecture

See `docs/plans/2026-03-28-autopilot-ai-architecture.md`.
