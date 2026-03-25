# ProofPilot Agent Hub

AI-powered SEO operations platform for home service agencies. Run workflows against real client data, stream live via Claude Opus 4.6, export branded `.docx` documents.

**Live:** `https://proofpilot-agents.up.railway.app`
**Repo:** `https://github.com/get-proofpilot/proofpilot-agent-hub`

---

## Mission

ProofPilot Agent Hub exists to **remove Matthew from the fulfillment bottleneck**. Every workflow automated here frees hours that go toward closing new clients or building acquisition systems. The platform is on the critical path to scaling ProofPilot from ~$25-30K MRR to $5M+ ARR.

**Who uses it:**
- **Matthew** — runs workflows, reviews output, uses for prospect audits and sales
- **Jo Paula** — reviews and publishes content (needs Drive integration for zero-friction handoff)

**What success looks like:** A full month of content for one client takes <10 minutes of Matthew's time. Monthly reports auto-generate. Prospect audits close deals without manual research.

---

## Current State

**Phase 1 (Core Platform): COMPLETE**
- 25 live workflows with real-time SSE streaming
- Branded `.docx` export on every job
- SQLite persistence (jobs + clients) on Railway Volume
- Content Library with client grouping, search, and filters
- Per-client hub with activity tracking
- Workflow categories with sample output previews
- DataForSEO integration (30+ functions: SERP, Maps, Labs, Keywords, GBP, Difficulty, Backlinks, On-Page, AI Overviews, Trends)
- Search Atlas integration (organic data, backlinks, holistic audit scores)
- Programmatic Content Agent (bulk location/service/blog/comparison/cost-guide/best-in-city generation)
- Client CRUD API (`/api/clients` — create, read, update, soft-delete)
- Job approval system (`/api/jobs/{id}/approve`)
- Monthly Client Report workflow (data-backed, auto-pulls rankings + traffic + backlinks)
- Client Proposals workflow (data-backed with competitor analysis + ROI projections)
- Google Ads Copy generator (keyword data + headlines + extensions + negative keywords)
- Schema Generator (JSON-LD for LocalBusiness, FAQPage, Service, Article, etc.)
- Content Strategy ecosystem mapping (buyer personas, content pillars, 12-month calendar)
- P&L Statement generator
- Property Management marketing strategy
- SEO Research Agent ("the brain" — keyword clustering, content roadmap, AI search analysis)
- Competitor Intelligence Report (deep competitive teardown with gap analysis)
- AI Search Visibility Report (AI Overviews, featured snippets, knowledge panels)
- Backlink Audit (full backlink health with competitor comparison)
- On-Page Technical Audit (60+ metrics per page)
- GEO Content Citability Audit (CITE framework: Citable Structure, Information Density, Topical Authority, Entity Clarity)
- SEO Content Audit (paste content + keyword → full on-page analysis, no live URL needed)
- Technical SEO Review (crawl checklist + ready-to-paste JSON-LD schemas for any page type/platform)
- Programmatic SEO Strategy (template design, data sources, quality tiers, staged launch plan)
- Competitor SEO Analysis (Why-They-Win root cause + content/SERP feature gaps + 90-day action plan)

**Phase 2 (Client Data Layer): ~80% DONE**
- [x] Client CRUD API + SQLite table
- [x] Frontend client management
- [x] Job approval with badges
- [ ] Content approval filtering (All / Approved / Pending)
- [ ] Domain format validation on workflow launch
- [ ] TTL cleanup for `temp_docs/`

**Phase 3 (SEO Operations System): COMPLETE**
- [x] SEO Playbook split into two sidebar views: SOP & Templates + Operations
- [x] SOP & Templates: Framework (monthly rhythm), Month Calendar, SOP Reference (20 tasks with steps), My Clients
- [x] Operations Command Center: 5 commands (audit, monthly-plan, weekly-plan, wrap-up, workload)
- [x] Execution engine (`seo_executor.py`) — Anthropic API with vault data context, async streaming
- [x] Deep roadmap parsing — extracts specific page URLs, keywords, priorities from roadmap.yaml
- [x] 5-layer strategy framework for clients without roadmaps (service pages, sub-services, locations, blogs)
- [x] ClickUp two-way sync (`clickup_sync.py`) — push monthly plans as tasks, pull completion progress
- [x] Result persistence on Railway volume — saved results, history feed, retrieval by ID
- [x] Missing roadmap warnings in dashboard with strategy framework fallback
- [x] 9 clients with vault data (recurring.yaml, roadmap.yaml, context.md)

**What's NOT built yet (high priority per growth plan):**
- GBP Post workflow (Month 1 priority — highest client visibility)
- Google Drive integration (Phase 3 — zero-friction content handoff to Jo Paula)
- Scheduled automations / cron (makes the platform run without Matthew)

---

## What to Build Next

Ordered by business impact. Each item maps to the master growth plan at `~/Agency-Brain/strategy/master-growth-plan.md`.

| Priority | Feature | Why | Effort |
|----------|---------|-----|--------|
| 1 | **GBP Post Workflow** | Every client needs 8-12 posts/month. Currently manual. Highest visibility deliverable. | Low |
| 2 | **Google Drive Integration** | Approved content auto-uploads to client folders. Jo Paula's inbox becomes zero-friction. | Medium |
| 3 | **Finish Phase 2** | Content approval filters, domain validation, temp_docs cleanup. | Low |
| 4 | **Scheduled Automations** | Monthly reports on the 1st, GBP posts on the 28th, competitor monitoring daily. | High |
| 5 | **WordPress Direct Publish** | Push approved content straight to client WordPress sites as drafts. | Medium |

Full roadmap with implementation details: `ROADMAP.md`

---

## Working Conventions

### Local Development
```bash
cd ~/Documents/ProofPilot-Agent-Hub/backend
cp .env.example .env   # ANTHROPIC_API_KEY, SEARCHATLAS_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
.venv/bin/uvicorn server:app --reload
# → http://localhost:8000
```

### Deployment
- **Railway auto-deploys on push to main** — root dir is `/backend`
- Railway Volume persists SQLite at `/app/data/jobs.db`
- Set env vars: `railway variables set KEY=value`
- Always test locally before pushing — there's no staging environment
- Check deployment health: `https://proofpilot-agents.up.railway.app/health`

### Code Patterns
- **Python:** Python 3.11, FastAPI, async generators for SSE streaming
- **Frontend:** Pure HTML/CSS/JS SPA — no frameworks, no build step. All in `backend/web/`
- **Claude API:** Always use `claude-opus-4-6`, `thinking: {"type": "adaptive"}`, `max_tokens: 8000`. No prefills — Opus 4.6 returns 400 on assistant turn prefills
- **Streaming:** `client.messages.stream()` → `async for text in stream.text_stream` → `yield text`
- **New features:** Prefer editing existing files over creating new ones. The frontend is a single SPA — add views/modals to the existing `index.html`, `script.js`, `style.css`

### Git & Commits
- Work on `main` branch (single developer, Railway auto-deploys)
- Commit messages: describe what changed and why, not just "update files"
- Don't push untested code — Railway deploys immediately
- Dockerfile comment tracks version: update the `# Copy application code — vN (description)` line

### What NOT to Do
- Never auto-publish or auto-deploy content to client sites without approval
- Never use Search Atlas `content_genius`, `digital_pr`, `OTTO_SEO_Deployment`, `OTTO_Wildfire`, `gbp_posts_automation`, `gbp_posts_publication`, or `Content_Publication_Tools`
- Never commit `.env` files or API keys
- Don't over-engineer — this is a production tool for one agency, not a SaaS platform (yet)

---

## Development Workflow

When adding or modifying workflows, invoke superpowers skills in this order:

| Situation | Invoke | Before... |
|-----------|--------|-----------|
| Adding a new workflow or dashboard feature | `superpowers:brainstorming` | Any code changes |
| You have a ROADMAP.md spec and need implementation steps | `superpowers:writing-plans` | Writing code |
| Executing a plan (server.py + workflow file + frontend = 3 files) | `superpowers:executing-plans` | Starting implementation |
| Workflow errors, SSE failures, API issues | `superpowers:systematic-debugging` | Guessing at fixes |
| Adding test coverage (keyword gap, docx gen) | `superpowers:test-driven-development` | Writing implementation |
| Risky change before Railway push (auto-deploys on merge) | `superpowers:using-git-worktrees` | Starting the work |
| Building frontend + backend changes in parallel | `superpowers:dispatching-parallel-agents` | Sequential work |
| About to push to main | `superpowers:verification-before-completion` | Any git push |

---

## Agent Playbook

Use these patterns to work faster and smarter in Claude Code sessions.

### When to Use Sub-Agents

| Situation | Agent Type | Why |
|-----------|-----------|-----|
| Exploring unfamiliar code | `Explore` | Keeps main context clean for implementation |
| Researching APIs or libraries | `general-purpose` | Can web search + read docs without polluting your context |
| Planning multi-file changes | `Plan` | Designs approach before you start coding |
| Independent parallel tasks | Multiple `Task` agents | Run 2-3 research tasks simultaneously |
| Building frontend + backend in parallel | Separate `Task` agents | One for Python changes, one for JS/HTML |

### Session Start Checklist
Every new session should begin with understanding current state:
1. Read this CLAUDE.md (happens automatically)
2. Check `git status` and `git log --oneline -5` to see recent work
3. Check ROADMAP.md if building a new feature
4. Check `~/Agency-Brain/strategy/master-growth-plan.md` if making strategic decisions

### Effective Patterns
- **Research before coding:** Use an Explore agent to understand existing patterns before modifying code
- **Parallel research:** Launch 2-3 Explore agents simultaneously for different aspects of a problem
- **Keep context focused:** Use sub-agents for exploration, keep the main thread for implementation
- **Test incrementally:** After each significant change, test locally before moving to the next
- **Update this file:** After shipping a feature, update the "Current State" and "What to Build Next" sections

### When Adding a New Feature
1. Read ROADMAP.md for the spec (if it exists)
2. Read the relevant existing code (workflow files, server.py, script.js)
3. Follow the 5-Step Workflow Pattern (documented below) if it's a new workflow
4. Test locally with `uvicorn server:app --reload`
5. Commit with a descriptive message
6. Push to main (triggers Railway deploy)
7. Update CLAUDE.md "Current State" section

### Keeping This File Current
This CLAUDE.md is the project's memory. Update it when:
- A feature ships → move from "What to Build Next" to "Current State"
- A new priority emerges → add to "What to Build Next" with reasoning
- A pattern changes → update "Working Conventions"
- A new API is integrated → add to the technical reference section
- Tech debt is resolved → remove from known limitations

---

## Stack

| Layer | Tech |
|-------|------|
| AI | Claude Opus 4.6 via `anthropic` SDK (streaming + adaptive thinking) |
| Backend | Python 3.11 + FastAPI + uvicorn + SSE |
| Database | SQLite on Railway Volume (`/app/data/jobs.db`) |
| Frontend | Vanilla HTML/CSS/JS SPA (`backend/static/`) |
| Export | `python-docx` → branded `.docx` files |
| SEO Data | DataForSEO (SERP, Labs, Keywords, GBP, On-Page) |
| SEO Data | Search Atlas MCP (organic, backlinks, holistic audit, local SEO) |
| Deploy | Railway — auto-deploy on push, Dockerfile in `/backend` |

### Key Files
```
backend/
  server.py                     — FastAPI app, routes, SSE streaming, workflow dispatch, SEO operations API
  seo_executor.py               — SEO command execution engine (audit, monthly-plan, weekly-plan, wrap-up, workload)
  clickup_sync.py               — ClickUp REST API integration (push tasks, pull progress)
  vault_data/                   — Client data synced from Obsidian vault
    _clients-index.yaml         — All 9 clients: tier, MRR, manager, services, cadence
    clickup_config.json          — Client → ClickUp space/folder ID mapping
    clients/{slug}/
      recurring.yaml             — Monthly task template (content, GBP, off-page, technical, reporting)
      roadmap.yaml               — Pages pipeline with URLs, keywords, priorities (8 of 9 clients)
      context.md                 — Client identity, services, contacts, key wins
  utils/
    dataforseo.py               — DataForSEO API client (30+ functions)
    searchatlas.py               — Search Atlas MCP wrapper
    docx_generator.py            — Branded Word document output
    db.py                        — SQLite schema, CRUD operations, seed data
  workflows/                    — 25 workflow modules (see Live Workflows section)
  web/
    index.html                   — Full SPA markup (all views including SEO Playbook)
    script.js                    — View routing, SSE streaming, workflow launch
    style.css                    — Light theme with ProofPilot brand system
    seo-playbook.js              — SEO Playbook + Operations frontend (5 tab views, Command Center)
    seo-playbook.css             — Playbook styles (light theme, matches parent brand)
```

---

## Brand System

| Element | Value |
|---------|-------|
| Dark Blue | `#00184D` / `--dark-blue` |
| Electric Blue | `#0051FF` / `--elec-blue` |
| Neon Green | `#C8FF00` / `--neon-green` |
| Base Background | `#060D1F` |
| Panel Background | `#0A1530` |
| Panel Headers | `#0E1D3E` |
| Display Font | Bebas Neue |
| Code Font | Martian Mono |
| Body Font | Inter |
| Transitions | `--t-fast: 0.15s ease`, `--t-med: 0.22s ease` |

### .docx Brand Rendering
- `# H1` → Bebas Neue 24pt Dark Blue
- `## H2` → Bebas Neue 15pt Electric Blue
- `### H3` → Calibri 12pt bold Dark Blue
- `---` → Electric Blue rule
- Bold, italic, bullets, numbered lists all supported

---

## Live Workflows (25 Active)

| Workflow ID | Title | Data Sources | File |
|-------------|-------|-------------|------|
| `website-seo-audit` | Website & SEO Audit | Search Atlas + DataForSEO + DFS Labs | `workflows/website_seo_audit.py` |
| `prospect-audit` | Prospect SEO Market Analysis | SA + DFS SERP + Keywords + GBP + Difficulty | `workflows/prospect_audit.py` |
| `keyword-gap` | Keyword Gap Analysis | DFS Labs (ranked keywords diff) + SA | `workflows/keyword_gap.py` |
| `ai-search-report` | AI Search Visibility Report | DFS SERP AI Overviews + Keywords + Trends | `workflows/ai_search_report.py` |
| `backlink-audit` | Backlink Audit | DFS Backlinks + Labs competitors | `workflows/backlink_audit.py` |
| `onpage-audit` | On-Page Technical Audit | DFS On-Page + SERP + Keywords | `workflows/onpage_audit.py` |
| `geo-content-audit` | GEO Content Citability Audit | Claude only | `workflows/geo_content_audit.py` |
| `seo-content-audit` | SEO Content Audit | Claude only | `workflows/seo_content_audit.py` |
| `technical-seo-review` | Technical SEO Review | Claude only | `workflows/technical_seo_review.py` |
| `programmatic-seo-strategy` | Programmatic SEO Strategy | Claude only | `workflows/programmatic_seo_strategy.py` |
| `competitor-seo-analysis` | Competitor SEO Analysis | Claude only | `workflows/competitor_seo_analysis.py` |
| `seo-research` | SEO Research & Content Strategy | DFS Labs + Keywords + AI + Trends + Backlinks | `workflows/seo_research_agent.py` |
| `competitor-intel` | Competitor Intelligence Report | DFS Labs + Backlinks + SERP + Keywords | `workflows/competitor_intel.py` |
| `schema-generator` | Schema Generator | Claude only | `workflows/schema_generator.py` |
| `monthly-report` | Monthly Client Report | DFS Labs + Backlinks + Trends + Keywords | `workflows/monthly_report.py` |
| `proposals` | Client Proposals | DFS Labs + SERP + Keywords | `workflows/proposals.py` |
| `google-ads-copy` | Google Ads Copy | DFS Keywords (volumes + CPC) | `workflows/google_ads_copy.py` |
| `content-strategy` | Content Strategy | DFS Keywords + Difficulty | `workflows/content_strategy.py` |
| `pnl-statement` | P&L Statement | Claude only | `workflows/pnl_statement.py` |
| `property-mgmt-strategy` | Property Mgmt Strategy | DFS Labs + Keywords | `workflows/property_mgmt_strategy.py` |
| `home-service-content` | Home Service SEO Content | Claude only | `workflows/home_service_content.py` |
| `seo-blog-post` | SEO Blog Post | Claude only | `workflows/seo_blog_post.py` |
| `service-page` | Service Page | Claude only | `workflows/service_page.py` |
| `location-page` | Location Page | Claude only | `workflows/location_page.py` |
| `programmatic-content` | Programmatic Content Agent | Claude + DFS (6 content types) | `workflows/programmatic_content.py` |

### How Workflows Work
1. Frontend POSTs to `/api/run-workflow` with `workflow_id`, `client_name`, `inputs`, `strategy_context`
2. Backend streams SSE tokens (`type: token`) as Claude generates
3. On completion: generates branded `.docx`, persists to SQLite, returns `type: done`
4. Frontend: live streaming terminal → download button → adds to Content Library

---

## Adding a New Workflow (5-Step Pattern)

Every new workflow requires exactly these 5 changes:

### Step 1: Create `workflows/{name}.py`
```python
"""
Workflow description
inputs keys: domain, service, location, ...
"""
import anthropic
from typing import AsyncGenerator

SYSTEM_PROMPT = """You are ..."""

async def run_{name}(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str,
    client_name: str,
) -> AsyncGenerator[str, None]:
    # 1. Extract inputs
    # 2. Yield status message
    # 3. Build user_prompt
    # 4. Stream Claude response
    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

### Step 2: Register in `server.py`
```python
from workflows.{name} import run_{name}
# Add to WORKFLOW_TITLES dict
# Add elif in event_stream()
```

### Step 3: Add to `static/script.js` WORKFLOWS array
```javascript
{ id: '{workflow-id}', icon: '...', title: '...', desc: '...', time: '~X min',
  status: 'active', skill: '{workflow-id}', category: 'seo|content|business|dev' },
```

### Step 4: Add modal panel to `static/index.html`
Add a `div#modalInputs{Name}` with input fields matching the workflow's input schema.

### Step 5: Wire in `static/script.js` (3 places)
- `selectWorkflow()` — show/hide the modal panel
- `checkRunReady()` — validate required fields
- `launchWorkflow()` — collect inputs and add to liveWorkflows array

---

## Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/run-workflow` | POST | Start workflow → SSE stream |
| `/api/download/{job_id}` | GET | Download branded .docx |
| `/api/jobs/{job_id}` | GET | Job metadata + content preview |
| `/api/jobs/{job_id}/approve` | POST | Mark job as approved |
| `/api/jobs/{job_id}/approve` | DELETE | Remove approval |
| `/api/content` | GET | All completed jobs (content library) |
| `/api/clients` | GET | List all clients |
| `/api/clients` | POST | Create client |
| `/api/clients/{id}` | PATCH | Update client fields |
| `/api/clients/{id}` | DELETE | Soft-delete client |
| `/api/discover-cities` | POST | Find nearby cities (Haiku-powered) |

### SSE Event Types
```
type: "token" → { type, text }
type: "done"  → { type, job_id, client_name, workflow_title, workflow_id }
type: "error" → { type, message }
```

---

## Workflow Input Schemas

### `website-seo-audit`
```json
{ "domain": "allthingzelectric.com", "service": "electrician", "location": "Chandler, AZ", "notes": "optional" }
```

### `prospect-audit`
```json
{ "domain": "steadfastplumbingaz.com", "service": "plumber", "location": "Gilbert, AZ",
  "monthly_revenue": "$45,000", "avg_job_value": "$450", "notes": "optional sales context" }
```

### `keyword-gap`
```json
{ "domain": "allthingzelectric.com", "service": "electrician", "location": "Chandler, AZ",
  "competitor_domains": "competitor1.com, competitor2.com", "notes": "optional" }
```

### `home-service-content`
```json
{ "business_type": "electrician", "location": "Chandler, AZ", "keyword": "panel upgrade", "service_focus": "residential" }
```

### `seo-blog-post`
```json
{ "business_type": "electrician", "location": "Chandler, AZ", "keyword": "how much does it cost to rewire a house",
  "audience": "homeowners", "tone": "conversational", "internal_links": "optional", "notes": "optional" }
```

### `service-page`
```json
{ "business_type": "electrician", "service": "panel upgrade", "location": "Chandler, AZ",
  "differentiators": "same-day service, master electrician", "price_range": "$1,200–$3,500", "notes": "optional" }
```

### `location-page`
```json
{ "business_type": "plumber", "primary_service": "plumbing repair", "target_location": "Mesa, AZ",
  "home_base": "Chandler, AZ", "local_details": "optional local context", "services_list": "optional", "notes": "optional" }
```

### `geo-content-audit`
```json
{ "content": "full page content (paste)", "target_queries": "queries AI should cite this for",
  "business_type": "optional", "location": "optional", "competitor_urls": "optional", "notes": "optional" }
```

### `seo-content-audit`
```json
{ "content": "full page content (paste)", "keyword": "primary target keyword",
  "title_tag": "optional", "meta_description": "optional", "url": "optional",
  "business_type": "optional", "notes": "optional" }
```

### `technical-seo-review`
```json
{ "domain": "allthingzelectric.com", "platform": "WordPress", "business_type": "electrician",
  "location": "Chandler, AZ", "page_types": "optional", "known_issues": "optional", "notes": "optional" }
```

### `programmatic-seo-strategy`
```json
{ "business_type": "electrician", "service": "panel upgrade", "location": "Phoenix, AZ",
  "page_type": "location-pages", "scale": "optional", "data_assets": "optional",
  "competitors": "optional", "notes": "optional" }
```

### `competitor-seo-analysis`
```json
{ "domain": "allthingzelectric.com", "competitors": "comp1.com, comp2.com", "service": "electrician",
  "location": "Chandler, AZ", "keywords": "optional", "notes": "optional" }
```

---

## SEO Operations System

The SEO Playbook is split into two sidebar views in the Agent Hub:

### SOP & Templates (reference for the team)
| Tab | Purpose |
|-----|---------|
| Framework | Monthly rhythm (weeks 1-4), priority matrix, decision tree, time allocation |
| Month Calendar | Visual calendar with task distribution across working days |
| SOP Reference | 20 task types with step-by-step processes, time estimates, category filters |
| My Clients | Client cards with tier badges, MRR, manager filter, workload summary |

### Operations (command execution)
| Command | Scope | What It Does |
|---------|-------|-------------|
| `audit` | Per client | Compares planned vs actual deliverables with severity scorecard |
| `monthly-plan` | Per client | Generates month plan from roadmap (specific pages) or strategy framework (gap analysis) |
| `weekly-plan` | All clients | Prioritized checklist by manager with page URLs across portfolio |
| `wrap-up` | Per client | Month-end summary + client email draft + next month preview |
| `workload` | All clients | Team capacity analysis, hours per manager, rebalancing suggestions |

### How Commands Execute
1. Frontend sends `POST /api/seo/execute` with command + client slug
2. `seo_executor.py` reads vault data (recurring.yaml, roadmap.yaml, context.md)
3. Builds purpose-specific prompt with client context injected
4. Calls Anthropic AsyncAnthropic Messages API with streaming
5. Results stream via SSE to the Command Center UI
6. Output saved to Railway volume (`/app/data/seo-results/`)

### 5-Layer Strategy Framework (No-Roadmap Fallback)
When a client has no `roadmap.yaml`, monthly-plan uses gap analysis:
1. **Service Pages** — from context.md "Services They Offer" section
2. **Sub-Service Pages** — specializations for top services
3. **Location Pages** — cities in their market area
4. **Location + Service Combos** — high-intent paired pages
5. **Blog Content** — AEO-optimized, cost guides, how-to posts

Tasks get named `Service Page 1 | [Name]` and flagged for SEO manager review.

### ClickUp Integration
- **Push**: `POST /api/seo/clickup/sync-plan` creates monthly list + tasks from recurring.yaml
- **Pull**: `GET /api/seo/clickup/progress` returns completion rates per client
- Config: `vault_data/clickup_config.json` maps client folders to ClickUp space/folder IDs
- API key: `CLICKUP_API_KEY` env var on Railway

### Vault Data Sync
Client data comes from the Obsidian vault via `scripts/sync-vault-data.sh`:
```bash
./scripts/sync-vault-data.sh  # copies YAML/MD files to vault_data/
git add vault_data/ && git commit && git push  # triggers Railway deploy
```

### SEO Operations API
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/seo/playbook-data` | GET | All client data for dashboard rendering |
| `/api/seo/clients` | GET | Raw clients-index.yaml as JSON |
| `/api/seo/execute` | POST | Execute command → SSE stream |
| `/api/seo/results` | GET | List past operation results |
| `/api/seo/results/{id}` | GET | Retrieve specific result |
| `/api/seo/clickup/sync-plan` | POST | Push monthly plan to ClickUp |
| `/api/seo/clickup/progress` | GET | Pull ClickUp completion per client |
| `/api/seo/clickup/progress/{slug}` | GET | Detailed ClickUp tasks for one client |
| `/api/seo/refresh-data` | POST | Re-read vault data |

### Environment Variables (SEO Operations)
| Variable | Required | Description |
|----------|----------|-------------|
| `CLICKUP_API_KEY` | Yes | ClickUp personal API token |
| `CLICKUP_WORKSPACE_ID` | Yes | ClickUp workspace ID (9006070686) |
| `DOCS_DIR` | No | Path for result persistence (default: `/app/data` on Railway) |

---

## DataForSEO Integration

**Auth:** Basic auth (`DATAFORSEO_LOGIN:DATAFORSEO_PASSWORD`, base64)
**Pricing:** ~$0.002/call live SERP, ~$0.0006 standard queue
**Client:** `utils/dataforseo.py`

### Implemented Functions (30+)
| Function | API Category | Used In |
|----------|-------------|---------|
| `get_local_pack()` | SERP — Maps | website-seo-audit, prospect-audit, keyword-gap |
| `get_organic_serp()` | SERP — Organic | website-seo-audit, prospect-audit, keyword-gap, onpage-audit |
| `get_serp_with_ai_overview()` | SERP — Advanced | ai-search-report |
| `research_competitors()` | SERP — Maps + Organic | audits, keyword-gap, seo-research, competitor-intel, proposals |
| `get_keyword_search_volumes()` | Keywords Data | prospect-audit, keyword-gap, seo-research, content-strategy, google-ads-copy |
| `get_bulk_keyword_difficulty()` | Labs — Difficulty | prospect-audit, seo-research, content-strategy |
| `get_domain_ranked_keywords()` | Labs — Rankings | website-seo-audit, keyword-gap, seo-research, competitor-intel, monthly-report |
| `get_domain_rank_overview()` | Labs — Overview | seo-research, competitor-intel, monthly-report, proposals, property-mgmt |
| `get_backlink_summary()` | Backlinks | backlink-audit, seo-research, competitor-intel, monthly-report |
| `get_referring_domains()` | Backlinks | backlink-audit |
| `get_backlink_anchors()` | Backlinks | backlink-audit |
| `get_backlink_competitors()` | Labs — Competitors | backlink-audit, competitor-intel |
| `get_full_backlink_profile()` | Backlinks (parallel) | backlink-audit |
| `get_instant_page_audit()` | On-Page | onpage-audit |
| `get_ai_search_landscape()` | SERP — AI Overviews | ai-search-report, seo-research, competitor-intel |
| `get_keyword_trends()` | Trends — Google | ai-search-report, seo-research, monthly-report |
| `get_competitor_gmb_profiles()` | Business Data | prospect-audit |
| `get_location_research()` | SERP + Keywords | programmatic-content |
| `build_service_keyword_seeds()` | (utility) | Multiple workflows |
| Format helpers (15+) | (formatters) | All data-powered workflows |

### Still Available But Not Yet Used
| Category | Endpoints | Use Case |
|----------|----------|----------|
| Business Data | `google/reviews` | Review intelligence |
| Content Analysis | `search/live`, `rating/live` | Brand monitoring |

---

## Search Atlas MCP

Configured in Claude Code global config. Key: `SEARCHATLAS_API_KEY`.

### Approved Tools
| Namespace | Capabilities |
|-----------|-------------|
| `Site_Explorer_Organic_Tool` | Organic keywords, pages, competitors |
| `Site_Explorer_Backlinks_Tool` | Referring domains, backlinks |
| `Site_Explorer_Analysis_Tool` | Position distribution |
| `Site_Explorer_Holistic_Audit_Tool` | SEO pillar scores |
| `Site_Explorer_Keyword_Research_Tool` | Keyword research |
| `local_seo` | Grids, Business, Data, Analytics |
| `gbp` | Locations (read), Reviews, Stats, Tasks |
| `llm_visibility` | Visibility Analysis, Sentiment |

### Off-Limits (never use)
`content_genius`, `digital_pr`, `linklab`, `otto_ppc`, `press_release`, `OTTO_SEO_Deployment`, `OTTO_Wildfire`, `gbp_posts_automation`, `gbp_posts_publication`, `Content_Publication_Tools`

---

## Frontend Views

| View | Description |
|------|-------------|
| Dashboard | KPIs, live task queue, client roster |
| AI Skills | 8 workflow cards organized by category (SEO, Content, Business, Dev) |
| Clients | Client list with add/edit, active/inactive toggle |
| Agent Tasks | Job history with status, client links |
| **SOP & Templates** | SEO Playbook reference: Framework, Month Calendar, SOP Reference, My Clients |
| **Operations** | SEO Command Center: audit/plan/wrap-up execution, ClickUp sync, results feed |
| Content | Content Library — grouped by client, searchable, filterable |
| Reports | Report cards (placeholder) |
| Activity Log | Terminal-style log stream |
| Client Hub | Per-client activity view (click any client name) |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key (Opus 4.6 for workflows, Sonnet 4.6 for SEO operations) |
| `SEARCHATLAS_API_KEY` | Yes | Search Atlas MCP API key |
| `DATAFORSEO_LOGIN` | Yes | DataForSEO account email |
| `DATAFORSEO_PASSWORD` | Yes | DataForSEO account password |
| `CLICKUP_API_KEY` | Yes | ClickUp personal API token for task sync |
| `CLICKUP_WORKSPACE_ID` | Yes | ClickUp workspace ID |
| `DATABASE_PATH` | No | SQLite path (default: `./data/jobs.db`) |
| `DOCS_DIR` | No | Persistent storage path (default: `/app/data` on Railway) |

---

## Known Limitations

| Issue | Impact | Planned Fix |
|-------|--------|-------------|
| US-only location parsing | International clients get wrong format | DFS appendix/locations API |
| No domain format validation | Invalid domains sent to APIs | Phase 2.4 |
| `temp_docs/` not cleaned up | Disk fills over time | TTL cleanup in Phase 2.4 |
| No test coverage | Risky deploys | Add pytest for keyword gap, docx gen |
| No request logging | Hard to debug production issues | Structured logging |
