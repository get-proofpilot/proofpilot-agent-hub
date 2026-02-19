# ProofPilot Agency Hub — Project Context

## What This Is
ProofPilot Agency Hub is an SEO operations dashboard UI for an AI-powered SEO agency tool. It allows agency owners to manage clients, run AI-powered SEO workflows, monitor agent tasks, and generate ad creative — all from a single dashboard.

## Current State
- **Frontend** — HTML/CSS/JS SPA with real client data (14 clients)
- **Backend live on Railway** — FastAPI + Claude API streaming, `.docx` generation
- **Session 2 pending** — UI input fields + SSE wiring not yet connected

## Stack

### Frontend
- Pure HTML / CSS / JavaScript (no frameworks, no build step)
- `index.html` — all views and markup
- `style.css` — all styles (dark-blue / electric-blue / neon-green brand)
- `script.js` — data models, view routing, rendering, terminal animation

### Backend (`backend/`)
- Python + FastAPI
- `server.py` — routes, SSE streaming, job store
- `workflows/home_service_content.py` — first real workflow (claude-opus-4-6)
- `utils/docx_generator.py` — ProofPilot branded Word doc output
- Deployed on Railway — see URL below

## Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/run-workflow` | POST | Start workflow — returns SSE stream |
| `/api/download/{job_id}` | GET | Download branded .docx |
| `/api/jobs/{job_id}` | GET | Job metadata + content preview |

**Railway URL:** `https://bubbly-consideration-production-25c1.up.railway.app`

**Required env var on Railway:** `ANTHROPIC_API_KEY`

### Run locally
```bash
cd backend
cp .env.example .env   # add real API key
.venv/bin/uvicorn server:app --reload
# → http://localhost:8000
```

## Brand
- **Name:** ProofPilot Agency Hub
- **Colors:** Dark Blue `#00184D`, Electric Blue `#0051FF`, Neon Green `#C8FF00`
- **Fonts:** Bebas Neue (display), Martian Mono (code/mono), Inter (body)

## Views
| View | Route | Description |
|------|-------|-------------|
| Dashboard | `dashboard` | KPIs, agent terminal, task queue, client roster, alerts, ad preview |
| Workflows | `workflows` | 11 active skill cards + 5 coming soon + run launcher |
| Clients | `clients` | Client table with active/inactive toggle |
| Agent Tasks | `jobs` | Job list with progress bars + filter tabs |
| Reports | `reports` | Report cards grid |
| Content | `content` | Content pieces grid |
| Activity Log | `logs` | Terminal-style log stream |
| Ad Studio | `ads` | Ad creative cards |
| Campaigns | `campaigns` | Placeholder |

## Active Workflows (wired up = backend ready)
| Workflow ID | Status |
|-------------|--------|
| `home-service-content` | ✅ Backend ready, UI wiring = Session 2 |
| All others | 🔜 Backend routes exist, workflow modules = future sessions |

## Key Functions (script.js)
- `showView(viewId)` — SPA routing
- `renderDashboard()` — renders all dashboard panels
- `renderWorkflows()` — renders workflow cards + populates client dropdown
- `toggleClientStatus(id)` — flips active/inactive, cascades to dropdown + roster
- `launchWorkflow()` — currently mock only (Session 2 wires this to the API)
- `startTerminal()` — typewriter animation (Session 2 replaces with real SSE stream)

## Session Roadmap
| Session | What was built |
|---------|---------------|
| 1 ✅ | FastAPI backend, Home Service Content workflow, .docx generator, Railway deploy |
| 2 🔜 | Structured input fields + strategy context panel in Workflows UI, SSE wiring |
| 3 🔜 | Results modal on stream complete, copy button, .docx download trigger |
| 4 🔜 | ProofPilot branded .docx polish, add more workflow modules |
| 5 🔜 | Connect remaining 10 active workflows |

## Working in This Repo
- Open `index.html` directly in a browser — no build step needed
- All edits to `script.js` or `style.css` reflect immediately on refresh
- Backend changes: push to GitHub → Railway auto-deploys (connected via CLI upload for now)
- API key lives only in Railway env vars — never in any file
