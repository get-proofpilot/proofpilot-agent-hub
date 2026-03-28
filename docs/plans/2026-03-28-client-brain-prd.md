# PRD: Client Brain — Per-Client Intelligence System

**Date:** 2026-03-28
**Project:** ProofPilot Agent Hub
**Status:** Draft
**Author:** Matthew Anderson + Claude

---

## Problem

Agent Hub produces generic content. A service page for Saiyan Electric reads like it could be for any electrician in Phoenix. The workflows have no deep knowledge of who the client is, how they talk, what makes them different, or what their customers care about.

The result: every piece of content requires heavy manual editing to sound like the client, which defeats the purpose of automation.

## Goal

Every piece of content Agent Hub generates should read like it was written by someone who works at that company — not by a generic AI. The system should know each client's voice, differentiators, service details, and customer language, and inject that knowledge into every workflow automatically.

## Success Criteria

- A service page for Saiyan Electric sounds like Saiyan Electric, not like "Phoenix electrician"
- A blog post for Cedar Gold Group uses their formal, trust-building tone — not the same casual tone as Saiyan
- Content references real pricing, real service areas, real differentiators without Matthew typing them in each time
- New clients can be fully onboarded (brain populated) in under 30 minutes
- Content quality is high enough that Matthew approves 80%+ of output with zero or minor edits

---

## Architecture

### Client Brain Structure

Each client gets a structured intelligence profile stored in the existing `client_memory` table. The brain has five layers:

```
Client Brain
├── 1. Brand Identity (EXISTS — upgrade)
├── 2. Writing Voice (NEW)
├── 3. Business Intelligence (NEW)
├── 4. Content History (EXISTS — extend)
└── 5. Learnings (EXISTS — keep)
```

### Layer 1: Brand Identity (upgrade existing)

**What exists:** `brand_extractor.py` pulls colors, typography, CSS variables, logos, section patterns, component styles, CTA patterns, photography style, navigation, footer, social links, and schema data. Saved to `design_system` and `asset_catalog` memory types.

**What to add:**

| Element | Source | Memory Key |
|---------|--------|------------|
| Favicon / app icons | Website scrape | `asset_catalog:icons` |
| Button styles (primary, secondary, ghost) | CSS extraction | `design_system:button_styles` |
| Image treatment (rounded corners, shadows, overlays) | CSS/HTML analysis | `design_system:image_treatments` |
| Spacing system (section padding, content width) | CSS extraction | `design_system:spacing_system` |
| Animation/transition patterns | CSS extraction | `design_system:motion_system` |
| Brand marks beyond logo (badges, seals, trust icons) | Image + alt text analysis | `asset_catalog:trust_marks` |

**Implementation:** Extend the existing `BRAND_EXTRACTION_PROMPT` in `brand_extractor.py` to capture these additional elements. No new extraction pipeline needed — just a more thorough prompt and additional `save_brand_to_memory()` entries in `brand_memory.py`.

### Layer 2: Writing Voice (new)

A new extractor that analyzes the client's existing website copy and Google reviews to produce a voice profile.

**Memory type:** `brand_voice` (exists, currently only stores `tone` and `value_propositions`)

| Memory Key | Content | Source |
|------------|---------|--------|
| `voice_profile` | 3-5 sentence description of how this client communicates | Website copy analysis |
| `tone_attributes` | JSON: formality (1-5), technical depth (1-5), warmth (1-5), urgency (1-5) | Website copy analysis |
| `vocabulary_use` | Words and phrases the client actually uses | Website scrape |
| `vocabulary_avoid` | Generic/competitor patterns to avoid | Comparative analysis |
| `sentence_patterns` | Avg sentence length, paragraph length, use of questions, use of "you" | Website copy analysis |
| `sample_passages` | 3-5 best excerpts from existing website content | Website scrape, Claude selection |
| `customer_language` | Phrases and themes from Google reviews | GBP reviews via DataForSEO/Search Atlas |
| `tagline` | Primary tagline/slogan if present | Website scrape |

**Extraction process:**

1. Scrape 3-5 pages of website content (home, about, 2-3 service pages)
2. Pull Google reviews (50 most recent) via existing DataForSEO integration
3. Send to Claude with a voice analysis prompt:
   - "Analyze this company's communication style across their website and customer reviews"
   - "Extract their distinctive patterns — not generic observations, but what makes THIS company's voice different"
4. Claude returns structured voice profile
5. Saved to `client_memory` via existing `ClientMemoryStore.save()`

**Cost estimate:** ~$0.03-0.05 per client (Haiku for initial extraction, Opus for voice synthesis). Runs once per client, cached.

### Layer 3: Business Intelligence (new)

Structured knowledge about what the client actually does, where, and why they're different.

**Memory type:** `business_intel` (new type — add to `VALID_TYPES` in `store.py`)

| Memory Key | Content | Source |
|------------|---------|--------|
| `service_catalog` | JSON array: each service with name, description, price range, time estimate, differentiator | Website + GBP + interview |
| `service_areas` | JSON: primary city, surrounding cities with drive times, neighborhoods | GBP data + DataForSEO geo |
| `differentiators` | JSON array: what makes them different (with evidence/specifics) | Website + reviews + interview |
| `owner_story` | 2-3 sentence founder/company origin story | Interview |
| `certifications` | Licenses, certifications, awards, memberships | Website + GBP |
| `customer_personas` | JSON: 2-3 typical customer types with their concerns and language | Review analysis |
| `competitive_position` | How they position against local competitors | Competitor research |
| `guarantees` | Service guarantees, warranties, policies | Website scrape |
| `response_time` | Typical response/scheduling speed | GBP data + website |
| `payment_methods` | Accepted payment, financing options | Website + GBP |

**Extraction process:**

1. Pull GBP profile data via existing `get_competitor_gmb_profiles()` in `dataforseo.py`
2. Scrape website for service pages, about page, FAQ
3. Analyze Google reviews for recurring themes (what customers praise, what they mention)
4. Claude synthesizes into structured business intel
5. Save to `client_memory`

**What auto-extraction cannot capture (requires interview):**

- Real pricing ranges (not always on website)
- Owner story and founding details
- Internal differentiators (response time guarantees, training standards)
- Strategic positioning decisions ("we don't compete on price, we compete on quality")

### Layer 4: Content History (extend existing)

**What exists:** `past_content` memory type tracks `{page_type, keyword, title, generated_at}`.

**What to add:**

| Memory Key | Content | Source |
|------------|---------|--------|
| `published_pages` | JSON array: URL, title, primary keyword, publish date, page type | Manual entry or auto-detect via sitemap |
| `internal_link_targets` | Key pages and their URLs for internal linking | Derived from published_pages |
| `keyword_coverage` | Keywords already targeted (to prevent cannibalization) | Derived from past_content + published_pages |

**Auto-populated:** Every time a content piece is approved in Agent Hub, `past_content` updates automatically. Published pages can be bootstrapped by crawling the client's sitemap.

### Layer 5: Learnings (keep as-is)

Already implemented. Manual entries that capture feedback from content reviews:
- "Client rejected long paragraphs in March review"
- "Always mention 24/7 emergency service in the intro"
- "Use 'your home' not 'the home'"

These accumulate over time and make the brain smarter per client.

---

## Onboarding Flow

### Phase A: Automated Research (no human input needed)

A new **Client Research Agent** orchestrates three extraction tasks:

```
Client Research Agent
├── 1. Brand Identity Extraction (existing brand_extractor.py — upgraded)
│   └── Scrapes website → design system, assets, visual identity
│
├── 2. Writing Voice Extraction (NEW)
│   └── Scrapes website copy + reviews → voice profile, tone, vocabulary
│
└── 3. Business Intelligence Extraction (NEW)
    └── GBP data + website + reviews → services, areas, differentiators
```

**Trigger:** New API endpoint `POST /api/clients/{id}/research` or a "Build Client Brain" button in the client hub.

**Duration:** 2-4 minutes total (fetching + Claude analysis).

**Output:** Client brain populated with 30-50 memory entries. Displayed in a "Client Brain" tab in the client hub for review.

### Phase B: Client Interview (optional, 5-10 minutes)

After automated research completes, the system presents what it found and asks targeted questions to fill gaps:

**Interview format:** Chat-style in Agent Hub (reuse the existing SSE streaming terminal). The agent asks one question at a time based on what's missing.

**Question bank (agent selects based on gaps):**

1. "I found these services on your website: [list]. What are the typical price ranges for each?"
2. "What's the owner's story? How did the company start?"
3. "I see your reviews mention [theme] a lot. Is that a deliberate part of your brand?"
4. "What's your typical response time when a customer calls?"
5. "Who's your main competitor in [city]? What do you do better than them?"
6. "Any certifications, awards, or memberships I should always mention?"
7. "Is there anything you never want in your marketing? (e.g., 'don't mention price matching')"
8. "How would you describe your company's personality in 2-3 words?"
9. "Do you offer financing? Emergency/same-day service? Warranties?"
10. "What do your best customers say when they recommend you?"

**The agent stores answers directly to client_memory as they come in.**

### Phase C: Review and Refine

After both phases, the full client brain is displayed in the client hub:

- Each section is editable (inline edit saves to `client_memory`)
- Matthew can add/remove/modify any entry
- A "Regenerate" button per section re-runs extraction with updated context
- A "Test Voice" button generates a sample paragraph using the brain and displays it for validation

---

## Prompt Injection

Every workflow gets the relevant client brain sections injected into its system prompt. The injection is **context-aware** — a blog post gets different brain sections than a service page design.

### Injection Map

| Workflow Type | Brain Sections Injected |
|---------------|----------------------|
| Service page (copy) | Writing Voice + Business Intel (service_catalog, differentiators, certifications) + Content History (internal links) + Learnings |
| Location page (copy) | Writing Voice + Business Intel (service_areas, service_catalog) + Content History (internal links) + Learnings |
| Blog post | Writing Voice + Business Intel (customer_personas, differentiators) + Content History (keyword_coverage, internal links) + Learnings |
| Page design (visual) | Brand Identity (full design system + assets) + Business Intel (CTA text, phone, guarantees) |
| SEO audit | Business Intel (service_catalog, service_areas, competitive_position) |
| Proposals | Writing Voice + Business Intel (full) |
| Monthly report | Business Intel (service_catalog, differentiators) + Content History |

### Implementation

New function in `memory/store.py`:

```python
def load_context_for_workflow(self, client_id: int, workflow_type: str) -> str:
    """Load the right brain sections for a given workflow type.

    Returns formatted markdown string ready for system prompt injection.
    Uses the injection map to select only relevant sections.
    """
```

This replaces the current `load_snapshot()` which dumps everything. The new function is selective — a blog post doesn't need CSS variables, and a page design doesn't need customer language.

### Integration with existing workflows

Each workflow's `run_*()` function already accepts `strategy_context: str`. The client brain replaces the manually-typed strategy context with auto-generated, structured context. No workflow signature changes needed.

The `event_stream()` function in `server.py` already passes `strategy_context` to workflows. We intercept here:

```python
# Before (current)
strategy_context = payload.get("strategy_context", "")

# After (with client brain)
memory_store = ClientMemoryStore(db_connect)
brain_context = memory_store.load_context_for_workflow(client_id, workflow_id)
strategy_context = brain_context + "\n\n" + payload.get("strategy_context", "")
```

Manual strategy context still works as an override/supplement — the brain is the baseline, Matthew can add per-run instructions on top.

---

## Monthly Sprint Feature

Once client brains are populated, the monthly sprint becomes:

### Input

Load from `content_roadmap` table (already exists) or paste a plan:

```
Service Pages:
- Panel Upgrade — keyword: "panel upgrade chandler az"
- EV Charger Installation — keyword: "ev charger install mesa az"

Location Pages:
- Mesa AZ — keyword: "electrician mesa az"
- Gilbert AZ — keyword: "electrician gilbert az"

Blog Posts:
- "How Much Does a Panel Upgrade Cost in Phoenix?" — keyword: "panel upgrade cost phoenix"
- "Signs You Need to Rewire Your Home" — keyword: "signs you need to rewire house"
- "EV Charger Installation Guide for Arizona Homeowners" — keyword: "ev charger installation arizona"
- "Emergency Electrician: When to Call and What to Expect" — keyword: "emergency electrician"
```

### Execution

```
POST /api/clients/{id}/sprint
{
  "items": [
    {"page_type": "service_page", "keyword": "panel upgrade chandler az", "title": "Panel Upgrade"},
    {"page_type": "location_page", "keyword": "electrician mesa az", "title": "Mesa AZ"},
    {"page_type": "blog_post", "keyword": "panel upgrade cost phoenix", "title": "How Much Does a Panel Upgrade Cost?"},
    ...
  ],
  "approval_mode": "output_only"
}
```

- Creates a pipeline run per item
- Each pipeline loads the client brain automatically
- Runs sequentially (or 2-3 parallel with configurable concurrency)
- Each piece goes through the existing pipeline stages: research → strategy → copywrite → QA
- QA stage checks brand voice compliance, differentiator coverage, SEO requirements, duplication

### Output

10 content pieces in the approval queue (Content Library), each with:
- QA score and notes
- Brand voice match indicator
- SEO checklist (keyword in H1, meta desc length, heading structure, internal links)
- "Approve" / "Edit" / "Regenerate" actions

### ClickUp Sync

When a content piece is approved:

```
PATCH https://api.clickup.com/api/v2/task/{task_id}
{
  "status": "complete"
}
```

Requires: ClickUp API token (env var), task ID mapping (stored in `content_roadmap` or `client_tasks` table).

---

## Database Changes

### New memory type

Add `business_intel` to `VALID_TYPES` in `memory/store.py`:

```python
BUSINESS_INTEL = "business_intel"
VALID_TYPES = {BRAND_VOICE, STYLE_PREFERENCES, PAST_CONTENT, LEARNINGS, DESIGN_SYSTEM, ASSET_CATALOG, BUSINESS_INTEL}
```

No schema changes needed — `client_memory` table already supports arbitrary types via the `memory_type` TEXT column.

### New table: sprint_runs

```sql
CREATE TABLE IF NOT EXISTS sprint_runs (
    sprint_id     TEXT PRIMARY KEY,
    client_id     INTEGER NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    items_json    TEXT NOT NULL DEFAULT '[]',
    pipeline_ids  TEXT NOT NULL DEFAULT '[]',       -- JSON array of pipeline_id refs
    created_at    TEXT NOT NULL,
    completed_at  TEXT
);
```

### ClickUp mapping column

```sql
ALTER TABLE content_roadmap ADD COLUMN clickup_task_id TEXT DEFAULT '';
ALTER TABLE content_roadmap ADD COLUMN clickup_list_id TEXT DEFAULT '';
```

---

## New Files

| File | Purpose |
|------|---------|
| `pipeline/voice_extractor.py` | Scrapes website copy + reviews, produces writing voice profile |
| `pipeline/business_researcher.py` | Pulls GBP + website + reviews, produces business intelligence |
| `pipeline/client_research_agent.py` | Orchestrates all three extractors (brand + voice + business) |
| `pipeline/brain_formatter.py` | Context-aware brain injection (replaces raw `load_snapshot()`) |
| `utils/clickup.py` | ClickUp API client (task status updates, task listing) |

### Modified files

| File | Changes |
|------|---------|
| `memory/store.py` | Add `BUSINESS_INTEL` type, add `load_context_for_workflow()` method |
| `pipeline/brand_extractor.py` | Extend extraction prompt for icons, button styles, spacing, trust marks |
| `pipeline/brand_memory.py` | Add save functions for new brand identity elements |
| `server.py` | Add `/api/clients/{id}/research` endpoint, `/api/clients/{id}/sprint` endpoint, brain context injection in `event_stream()` |
| `static/script.js` | Client Brain tab in client hub, sprint launcher UI, interview chat UI |
| `static/index.html` | Client Brain view markup, sprint modal |
| `static/style.css` | Client Brain styles |
| `utils/db.py` | Sprint runs table, ClickUp columns on content_roadmap |

---

## Build Sequence

### Phase 1: Writing Voice + Business Intelligence Extractors (highest impact)

1. Build `voice_extractor.py` — website copy + review analysis → voice profile
2. Build `business_researcher.py` — GBP + website → service catalog, areas, differentiators
3. Build `client_research_agent.py` — orchestrates brand + voice + business extractors
4. Add `POST /api/clients/{id}/research` endpoint
5. Add `load_context_for_workflow()` to memory store
6. Wire brain injection into `event_stream()` in server.py
7. Test: generate a service page for Saiyan Electric with brain vs. without — validate quality difference

### Phase 2: Client Hub UI + Interview

8. Add "Client Brain" tab to client hub (displays all memory entries by section)
9. Add "Build Brain" button that triggers the research agent
10. Add inline editing for all brain entries
11. Build interview chat flow (SSE-streamed, agent asks gap-filling questions)
12. Add "Test Voice" button (generates sample paragraph for validation)

### Phase 3: Monthly Sprint

13. Build sprint runner (batch pipeline execution from content plan)
14. Add sprint UI (load plan, configure, launch, track progress)
15. Add QA stage brand voice compliance check
16. Add sprint history view

### Phase 4: ClickUp Integration

17. Build `utils/clickup.py` (API client)
18. Add ClickUp task mapping to content_roadmap
19. Auto-update ClickUp task status on content approval
20. Optional: pull monthly plan from ClickUp into content_roadmap

---

## Cost Estimates

| Operation | Cost per client | Frequency |
|-----------|----------------|-----------|
| Full brain build (brand + voice + business) | ~$0.08-0.15 | Once per client + occasional refresh |
| Brain injection into workflow | ~$0.00 | Every workflow run (just prompt text) |
| Monthly sprint (10 content pieces) | ~$0.80-1.20 (Opus) | Monthly per client |
| ClickUp API calls | Free (within limits) | Per content approval |

---

## Paperclip Migration Path

Everything built here is portable:

- **Client brains** = SQLite data, exportable to Paperclip's Postgres as "company context"
- **Voice extractor** = standalone skill, runs as a Paperclip agent
- **Business researcher** = standalone skill, runs as a Paperclip agent
- **Sprint runner** = maps to Paperclip's heartbeat-triggered task delegation
- **QA agent** = standalone skill, runs as a Paperclip governance gate
- **ClickUp sync** = runs as a Paperclip agent or plugin

When ProofPilot scales to 15+ autonomous clients, each client becomes a Paperclip company with its own agent team and the client brain becomes that company's persistent context.

---

## Out of Scope (for now)

- Google Drive integration (separate Phase 3 per ROADMAP.md)
- WordPress direct publish (separate Phase 5 per ROADMAP.md)
- Multi-seat access for Jo Paula (separate feature)
- Automated brain refresh on schedule (future — run research agent monthly to catch website changes)
- Client-facing brain view (future — when Agent Hub becomes SaaS)
