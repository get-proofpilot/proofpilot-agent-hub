# ProofPilot Agency Hub — Project Context

## What This Is
ProofPilot Agency Hub is an AI-powered SEO operations platform. Agency owners run AI workflows against real client data — audits, market analyses, and content — that stream live via Claude Opus 4.6 and export to branded `.docx` documents.

**Live URL:** `https://proofpilot-agents.up.railway.app`

---

## Stack

### Frontend (`backend/static/`)
- Pure HTML / CSS / JavaScript SPA — no frameworks, no build step
- `index.html` — all views and markup (695+ lines)
- `style.css` — full dark theme with ProofPilot brand system
- `script.js` — CLIENTS, JOBS, WORKFLOWS data + view routing, SSE streaming, workflow launch

### Backend (`backend/`)
- Python 3.11 + FastAPI + Server-Sent Events (SSE)
- `server.py` — routes, SSE streaming, in-memory job store, `.docx` trigger, `/api/content` endpoint
- `workflows/` — one file per runnable workflow
- `utils/searchatlas.py` — Search Atlas MCP wrapper (async)
- `utils/dataforseo.py` — DataForSEO API client (all live endpoints)
- `utils/docx_generator.py` — ProofPilot branded Word document output
- Deployed on Railway — root dir = `/backend`, auto-deploy on push

### Run Locally
```bash
cd backend
cp .env.example .env   # add keys (see env vars section)
.venv/bin/uvicorn server:app --reload
# → http://localhost:8000
```

---

## Brand
- **Colors:** Dark Blue `#00184D`, Electric Blue `#0051FF`, Neon Green `#C8FF00`
- **CSS vars:** `--dark-blue`, `--elec-blue`, `--neon-green`, `--text`, `--text2`, `--text3`
- **Fonts:** Bebas Neue (display/headings), Martian Mono (terminal/code), Inter (body)
- **Base bg:** `#060D1F` — panels: `#0A1530` — panel headers: `#0E1D3E`
- **Transitions:** `--t-fast: 0.15s ease`, `--t-med: 0.22s ease`

---

## Live Workflows (7 Active)

| Workflow ID | Title | Data Sources | File |
|-------------|-------|-------------|------|
| `website-seo-audit` | Website & SEO Audit | Search Atlas + DataForSEO + DFS Labs | `workflows/website_seo_audit.py` |
| `prospect-audit` | Prospect SEO Market Analysis | Search Atlas + DataForSEO + Keyword Volumes + GBP + Difficulty | `workflows/prospect_audit.py` |
| `keyword-gap` | Keyword Gap Analysis | DataForSEO Labs (ranked keywords diff) + Search Atlas | `workflows/keyword_gap.py` |
| `home-service-content` | Home Service SEO Content | Claude only | `workflows/home_service_content.py` |
| `seo-blog-post` | SEO Blog Post | Claude only | `workflows/seo_blog_post.py` |
| `service-page` | Service Page | Claude only | `workflows/service_page.py` |
| `location-page` | Location Page | Claude only | `workflows/location_page.py` |

### How Workflows Work
1. Frontend POSTs to `/api/run-workflow` with `workflow_id`, `client_name`, `inputs`, `strategy_context`
2. Backend streams SSE tokens (`type: token`) as Claude generates
3. On completion: generates branded `.docx`, stores job, returns `type: done` with `job_id`, `client_name`, `workflow_title`, `workflow_id`
4. Frontend: shows live streaming terminal → download button → adds to Content Library

---

## ⚡ Adding a New Workflow (5-Step Pattern)

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
    # 1. Extract inputs: field = inputs.get("field", "").strip()
    # 2. Yield status: yield f"> Doing X for **{client_name}**...\n\n"
    # 3. Build user_prompt from inputs + strategy_context
    # 4. Stream:
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
# Import at top:
from workflows.{name} import run_{name}

# Add to WORKFLOW_TITLES dict:
"{workflow-id}": "Workflow Display Title",

# Add elif in event_stream():
elif req.workflow_id == "{workflow-id}":
    generator = run_{name}(client=client, inputs=req.inputs,
                           strategy_context=req.strategy_context or "",
                           client_name=req.client_name)
```
Add `SEARCHATLAS_API_KEY` guard only if the workflow uses Search Atlas.

### Step 3: Add to `static/script.js` WORKFLOWS array
```javascript
{
  id: '{workflow-id}',
  icon: '🔍',
  title: 'Workflow Title',
  desc: 'One sentence description.',
  time: '~X min',
  status: 'active',  // or 'soon'
  skill: '{workflow-id}'
},
```

### Step 4: Add modal panel to `static/index.html`
```html
<div id="modalInputs{WorkflowName}" style="display:none; flex-direction:column; gap:16px;">
  <!-- Required fields -->
  <div class="wf-modal-field">
    <label class="wf-field-label">Field Label <span class="req">*</span></label>
    <input type="text" id="wf{Name}Field" placeholder="e.g. value" oninput="checkRunReady()" />
  </div>
  <!-- Optional fields grouped in optional section -->
  <div class="wf-modal-optional-section">
    <div class="wf-modal-optional-label">Optional</div>
    <div class="wf-modal-field">
      <label class="wf-field-label">Optional Field <span class="opt">optional</span></label>
      <input type="text" id="wf{Name}OptField" placeholder="e.g. value" />
    </div>
  </div>
</div>
```

### Step 5: Wire in `static/script.js` (3 places)

**`selectWorkflow()` panels object:**
```javascript
'modalInputs{WorkflowName}': id === '{workflow-id}',
```
Also add all new field IDs to the reset list in `selectWorkflow()`.

**`checkRunReady()` — add validation block:**
```javascript
if (selectedWorkflow === '{workflow-id}') {
  // prospect-audit pattern: no clientVal check, use own name field
  // all others: clientVal already checked in else branch
  const field1 = document.getElementById('wf{Name}Field1')?.value.trim();
  const field2 = document.getElementById('wf{Name}Field2')?.value.trim();
  ready = !!(field1 && field2);
}
```

**`launchWorkflow()` — add inputs collection + live list:**
```javascript
} else if (selectedWorkflow === '{workflow-id}') {
  inputs = {
    field1: document.getElementById('wf{Name}Field1')?.value.trim() || '',
    field2: document.getElementById('wf{Name}Field2')?.value.trim() || '',
  };
}
// Add to liveWorkflows array:
const liveWorkflows = [..., '{workflow-id}'];
```

**Add required fields to the input event listener array:**
```javascript
['...existing...', 'wf{Name}Field1', 'wf{Name}Field2'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', checkRunReady);
});
```

---

## Required Environment Variables (Railway)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (Opus 4.6) |
| `SEARCHATLAS_API_KEY` | Search Atlas MCP API key |
| `DATAFORSEO_LOGIN` | DataForSEO account email |
| `DATAFORSEO_PASSWORD` | DataForSEO account password |

Set via: `railway variables set KEY=value`

---

## Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/run-workflow` | POST | Start workflow — returns SSE stream |
| `/api/download/{job_id}` | GET | Download branded .docx |
| `/api/jobs/{job_id}` | GET | Job metadata + content preview |
| `/api/content` | GET | All completed jobs as content library items |
| `/` | GET | Serves frontend SPA |

### SSE Event Types (from `/api/run-workflow`)
```
type: "token"  → { type, text }           — stream token to terminal
type: "done"   → { type, job_id, client_name, workflow_title, workflow_id }
type: "error"  → { type, message }
```

### WorkflowRequest Schema
```json
{
  "workflow_id": "website-seo-audit",
  "client_id": 1,
  "client_name": "All Thingz Electric",
  "inputs": { "domain": "allthingzelectric.com", "service": "electrician", "location": "Chandler, AZ" },
  "strategy_context": ""
}
```
**Note:** For `prospect-audit`, `client_id` is `0` (prospects are not clients yet). `client_name` is the prospect's business name.

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
Claude context includes: SA organic data + DataForSEO SERP competitors + keyword volumes + keyword difficulty + competitor GBP profiles.

### `keyword-gap`
```json
{ "domain": "allthingzelectric.com", "service": "electrician", "location": "Chandler, AZ",
  "competitor_domains": "competitor1.com, competitor2.com", "notes": "optional" }
```
`competitor_domains` is optional — auto-discovered via Maps/SERP if blank.

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

---

## Claude API Config (all workflows)
- **Model:** `claude-opus-4-6`
- **Thinking:** `{"type": "adaptive"}` — Opus 4.6 native, no `budget_tokens` needed
- **Max tokens:** `8000`
- **Streaming:** `client.messages.stream()` → `async for text in stream.text_stream`
- **No prefills** — Opus 4.6 returns 400 on assistant turn prefills, use system prompt instructions instead

---

## DataForSEO — Implementation Status

**Auth:** Basic auth with `DATAFORSEO_LOGIN:DATAFORSEO_PASSWORD` (base64 encoded)
**Pricing:** ~$0.002/call live SERP, ~$0.0006 standard queue (66% cheaper for non-realtime)
**Docs:** https://docs.dataforseo.com/v3/

### Implemented Functions (`utils/dataforseo.py`)

| Function | Endpoint | Used In |
|----------|----------|---------|
| `get_local_pack()` | `serp/google/maps/live/advanced` | website-seo-audit, prospect-audit, keyword-gap |
| `get_organic_serp()` | `serp/google/organic/live/advanced` | website-seo-audit, prospect-audit, keyword-gap |
| `research_competitors()` | Both above in parallel | Both audits, keyword-gap |
| `get_competitor_sa_profiles()` | Search Atlas cross-reference | Both audits |
| `get_keyword_search_volumes()` | `keywords_data/google_ads/search_volume/live` | prospect-audit, keyword-gap |
| `get_domain_ranked_keywords()` | `dataforseo_labs/google/ranked_keywords/live` | website-seo-audit ✅, keyword-gap ✅ |
| `get_bulk_keyword_difficulty()` | `dataforseo_labs/google/bulk_keyword_difficulty/live` | prospect-audit ✅ |
| `get_competitor_gmb_profiles()` | `business_data/google/my_business_search/live` | prospect-audit ✅ |
| `build_service_keyword_seeds()` | (utility) | prospect-audit, keyword-gap |
| `format_keyword_volumes()` | (formatter) | prospect-audit |
| `format_domain_ranked_keywords()` | (formatter) | website-seo-audit |
| `format_keyword_difficulty()` | (formatter) | prospect-audit |
| `format_competitor_gmb_profiles()` | (formatter) | prospect-audit |
| `format_full_competitor_section()` | (formatter) | Both audits |

### DataForSEO API Capabilities (Full Map)

| Category | Key Endpoints | Best Use |
|----------|--------------|---------|
| **SERP** | `google/organic`, `google/maps`, `google/local_services` | Competitor discovery, rank tracking |
| **Keywords Data** | `google_ads/search_volume`, `keywords_for_site`, `ad_traffic_by_keywords` | Volume, CPC, content ideas |
| **DFS Labs** | `ranked_keywords`, `bulk_keyword_difficulty`, `domain_intersection`, `domain_rank_overview` | Gap analysis, difficulty, traffic estimates |
| **Business Data** | `google/my_business_info`, `google/my_business_search`, `google/reviews` | GBP profiles, competitor reviews |
| **On-Page** | `task_post`, `summary`, `pages`, `resources` | Technical audit (task-based, 2-10 min) |
| **Content Analysis** | `search/live`, `summary/live`, `rating/live` | Brand monitoring, sentiment |
| **Domain Analytics** | `technologies/domain_technologies`, `whois/overview` | Tech stack, domain age |
| **Backlinks** | `summary`, `referring_domains`, `competitors` | Link profile, gap |
| **Trends** | `google_trends/explore`, `subregion_interests` | Seasonality, geographic demand |

---

## Priority Roadmap — Next Builds

### Phase 3 — Advanced Workflows
1. **On-Page Technical Audit** — async task-based DFS crawl → `workflows/onpage_audit.py` with polling (tasks take 2-10 min, store task_id, poll)
2. **Monthly Client Report** — aggregate SA + DFS data + job history → `workflows/monthly_report.py`
3. **GBP Audit Workflow** — compare client GBP completeness vs competitors (photos, categories, attributes, Q&A)
4. **Review Intelligence** — pull competitor reviews → sentiment themes for prospect audit
5. **Seasonality Report** — Google Trends subregion data → content calendar timing

### Phase 4 — Platform Infrastructure
6. **Persistent job storage** — replace in-memory `jobs` dict with SQLite or Redis (jobs lost on Railway restart)
7. **Client data persistence** — CLIENTS array is currently hardcoded in script.js; needs a real data layer
8. **Scheduled automations** — cron-triggered workflow runs for monthly reports
9. **On-Page async polling** — background task system for multi-minute DFS crawl jobs

---

## Search Atlas MCP Integration

MCP server configured in Claude Code global config.
**API Key:** `SEARCHATLAS_API_KEY` env var.

### Approved Tools
| Namespace | Tools |
|-----------|-------|
| `Site_Explorer_Organic_Tool` | `get_organic_keywords`, `get_organic_pages`, `get_organic_competitors` |
| `Site_Explorer_Backlinks_Tool` | `get_site_referring_domains`, `get_site_backlinks` |
| `Site_Explorer_Analysis_Tool` | `get_position_distribution` |
| `Site_Explorer_Holistic_Audit_Tool` | `get_holistic_seo_pillar_scores` |
| `Site_Explorer_Keyword_Research_Tool` | keyword research |
| `local_seo` | Grids, Business, Data, Analytics |
| `gbp` | Locations (read), Reviews, Stats, Tasks |
| `llm_visibility` | Visibility Analysis, Sentiment |

### Off-Limits (never use)
`content_genius`, `digital_pr`, `linklab`, `otto_ppc`, `press_release`, `OTTO_SEO_Deployment`, `OTTO_Wildfire`, `gbp_posts_automation`, `gbp_posts_publication`, `Content_Publication_Tools`

**Rule:** Never auto-publish or auto-deploy. SA is data + analysis only.

---

## Frontend Views

| View ID | Nav Label | Description |
|---------|-----------|-------------|
| `dashboard` | Dashboard | KPIs, live task queue, client roster |
| `workflows` | AI Skills | 7 active workflow cards + coming soon |
| `clients` | Clients | 14 clients — active/inactive toggle, clickable → client hub |
| `jobs` | Agent Tasks | Job list with progress, client names clickable → hub |
| `reports` | Reports | Report cards |
| `content` | Content | Content Library — client-organized document library |
| `logs` | Activity Log | Terminal-style log stream |
| `ads` | Ad Studio | Ad creative placeholder |
| `campaigns` | Campaigns | Placeholder |
| `client-hub` | (no nav) | Per-client hub — accessed by clicking any client name |

### Content Library
- Every completed workflow adds a document card to the library
- Grouped by client with search + type + client filters
- Syncs from `GET /api/content` on every navigation (survives page refresh within server session)
- `CONTENT_ITEMS` array in script.js, `addToContentLibrary()` called from SSE `done` handler

### Client Hub
- Accessed by clicking any client name (dashboard roster, clients table, jobs list)
- 4 columns: In Progress, Completed, Needs Attention, Upcoming Automations
- "Run Workflow" button pre-selects the client in the workflow modal
- `showClientHub(clientId)` → `renderClientHub()` in script.js

---

## .docx Generator

File: `utils/docx_generator.py`

**Markdown elements rendered:**
- `# H1` → Bebas Neue 24pt Dark Blue
- `## H2` → Bebas Neue 15pt Electric Blue
- `### H3` → Calibri 12pt bold Dark Blue
- `- bullet` / `* bullet` → List Bullet style
- `1. numbered` → List Number style
- `---` → Electric Blue rule (90 chars, 7pt)
- `**bold**` → bold run
- `*italic*` → italic run
- Empty lines → 2pt spacer paragraph

**Brand colors:**
- `DARK_BLUE = RGBColor(0x00, 0x18, 0x4D)`
- `ELEC_BLUE = RGBColor(0x00, 0x51, 0xFF)`

**Output:** `backend/temp_docs/{job_id}.docx` — ephemeral, lost on Railway restart

---

## Known Limitations / Tech Debt

| Issue | Impact | Fix |
|-------|--------|-----|
| In-memory job store | Jobs lost on Railway restart | Add SQLite/Redis persistence |
| Hardcoded CLIENTS in script.js | Can't add clients without code edit | Add `/api/clients` CRUD endpoint |
| Content Library ephemeral | Cleared on server restart | Persist to DB with job store |
| Location parsing US-only | International clients get wrong format | Use DFS appendix/locations API |
| No input validation on domain format | Invalid domains sent to APIs | Add regex validation |
| `temp_docs/` not cleaned up | Disk fills over time | Add TTL cleanup job |
