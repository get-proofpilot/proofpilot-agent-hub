# SEO Page Builder Agent System — Design Plan

## Context

ProofPilot Agent Hub currently has 25 individual workflows that each do one thing (research OR writing OR audit). There's no pipeline concept — research output doesn't feed into writing, writing doesn't feed into page design. Every page build requires Matthew to manually run 3-5 separate workflows and stitch the outputs together.

The goal: build an agent orchestrator that chains **research → strategy → copywriting → page design → QA** into a single pipeline, producing production-ready HTML/CSS pages for service pages, location pages, and blog posts. This system borrows architecture patterns from Hermes Agent (memory, skills, delegation, cron) and leverages the 40+ existing Claude Code skills as the knowledge base for each sub-agent.

**Why this matters:** A full month of content for one client currently takes hours of Matthew's time. This should take <10 minutes — kick off the pipeline, review the output, approve.

---

## Architecture: Pipeline Engine with Specialized Agents

### Recommended Approach

Build a **pipeline engine inside the Agent Hub** that:
1. Chains multiple Claude API calls, each with a specialized system prompt built from existing skills
2. Passes typed artifacts between stages (research data → content brief → markdown copy → HTML page)
3. Stores per-client memory that improves output over time
4. Supports configurable approval gates (autopilot vs milestone review)
5. Runs headlessly via a scheduler for automated content production

This lives inside the existing FastAPI app — no separate service, no new infrastructure. It extends the current workflow pattern from "single Claude call" to "multi-stage pipeline."

### Why This Over Alternatives

**Alternative A (single mega-workflow):** Stuffing everything into one Claude call means a massive system prompt, context window exhaustion, and no ability to pass real data between stages. The research agent needs to call DataForSEO APIs; the copywriter needs to consume that data. These are fundamentally different tasks that need different contexts.

**Alternative B (full Hermes-style agent framework):** Over-engineered for this use case. Hermes is a general-purpose agent platform with terminal backends, messaging gateways, RL training. We need a focused pipeline engine for SEO page builds, not a general agent runtime.

**Alternative C (Claude Code as orchestrator):** Can't run headlessly. Can't be scheduled. Depends on a human having Claude Code open. Good for interactive use but not for production automation.

---

## System Components

### 1. Pipeline Engine (`backend/pipeline/`)

```
backend/pipeline/
  engine.py         — PipelineEngine: runs stages sequentially, manages artifacts, streams progress
  stages.py         — Stage definitions (research, strategy, copywrite, design, qa)
  artifacts.py      — Typed dataclasses for inter-stage data
  templates.py      — Page type configs (service_page, location_page, blog_post)
```

**How a pipeline runs:**

```
Pipeline("service-page", client="saiyan-electric", inputs={...})
  │
  ├─ Stage 1: RESEARCH
  │   System prompt: seo skills + DataForSEO tools
  │   Input: domain, service, location
  │   Output: ResearchArtifact(keywords, competitors, serp_data, content_gaps)
  │   [optional approval gate]
  │
  ├─ Stage 2: STRATEGY
  │   System prompt: blog-outline + blog-brief skills
  │   Input: ResearchArtifact + page_type config
  │   Output: StrategyArtifact(content_brief, heading_hierarchy, target_keywords, internal_links)
  │   [optional approval gate]
  │
  ├─ Stage 3: COPYWRITE
  │   System prompt: home-service-seo-content + stop-slop + brand voice corpus
  │   Input: StrategyArtifact + client memory
  │   Output: ContentArtifact(markdown, meta_tags, schema_json, faq_data)
  │   [optional approval gate]
  │
  ├─ Stage 4: DESIGN
  │   System prompt: page design instructions + brand system + HTML/CSS templates
  │   Input: ContentArtifact + page_type template + client brand
  │   Output: DesignArtifact(html, css, image_prompts, assets_manifest)
  │   [optional approval gate]
  │
  └─ Stage 5: QA REVIEW
      System prompt: blog-analyze + blog-seo-check + blog-geo + blog-factcheck skills
      Input: all previous artifacts
      Output: QAArtifact(score, issues[], approved: bool, recommendations)
```

Each stage is an async generator (same pattern as existing workflows) so it streams SSE tokens to the frontend in real-time.

**Artifacts** are persisted to SQLite between stages, so a pipeline can pause for approval and resume later without losing state.

### 2. Agent Prompts (Skills-as-System-Prompts)

Each stage loads relevant Claude Code skills at runtime and injects them into the system prompt. This is the key insight: **the 40+ skills we already have become the brains of each agent.**

#### Research Agent — Skills Map

| Skill | What It Provides | How It's Used |
|-------|-----------------|---------------|
| `seo` | Comprehensive SEO analysis framework | Overall research methodology |
| `seo-audit` | Full site audit with parallel delegation | Site health baseline |
| `seo-technical` | Crawlability, indexability, Core Web Vitals | Technical baseline |
| `competitor-seo` | Keyword gaps, content opportunities, backlink patterns | Competitive intelligence |
| `seo-geo` | AI Overviews, ChatGPT, Perplexity optimization | AEO opportunity mapping |
| `website-seo-audit` | Home service business audit template | Industry-specific audit |
| `blog-researcher` | Stats, sources, image discovery | Supporting data |

**Plus DataForSEO tools:** `get_keyword_search_volumes()`, `get_domain_ranked_keywords()`, `get_bulk_keyword_difficulty()`, `get_ai_search_landscape()`, `research_competitors()`, `get_backlink_summary()`

**Plus Search Atlas:** `Site_Explorer_Organic_Tool`, `Site_Explorer_Keyword_Research_Tool`, `Site_Explorer_Holistic_Audit_Tool`

#### Strategy Agent — Skills Map

| Skill | What It Provides | How It's Used |
|-------|-----------------|---------------|
| `blog-outline` | SERP-informed outline with H2/H3 hierarchy, word count targets | Page structure |
| `blog-brief` | Detailed content briefs with target keywords | Content specification |
| `blog-strategy` | Topic cluster architecture, hub-and-spoke design | Content ecosystem context |
| `seo-plan` | Strategic SEO planning with industry templates | Overall strategy framework |
| `content-strategy-spreadsheet` | Content ecosystem mapping | Multi-page coordination |
| `programmatic-seo` | Template design, data sources, quality tiers | Scale strategy |
| `blog-cannibalization` | Keyword overlap detection | Cannibalization avoidance |
| `seo-competitor-pages` | Competitor comparison page layouts | Page format intelligence |

#### Copywriter Agent — Skills Map

| Skill | What It Provides | How It's Used |
|-------|-----------------|---------------|
| `home-service-seo-content` | **THE CORE** — full 8-step workflow with brand voice training, chaos prompt, AEO, E-E-A-T | Primary writing methodology |
| `blog-write` | Article writing optimized for Google + AI citations | Blog post writing |
| `blog-persona` | NNGroup 4-dimension tone framework | Voice calibration |
| `stop-slop` | AI writing pattern removal | De-AIification pass |
| `blog-rewrite` | Optimization for December 2025 Core Update, E-E-A-T | Quality pass |
| `seo-content` | Content quality and E-E-A-T analysis | Self-evaluation |

**Per-client assets loaded from memory:**
- `brand_voice_corpus.md` — client writing samples
- `anti_ai_writing_style_guide_template.txt` — enforced style rules
- `chaos_prompt_template.md` — humanization pass
- `voice_guide_template.md` — client-specific voice guide

#### Page Designer Agent — Skills Map

| Skill | What It Provides | How It's Used |
|-------|-----------------|---------------|
| `frontend-design` | Production-grade frontend interfaces | HTML/CSS generation |
| `proofpilot-brand` | Brand colors, typography, formatting | Brand system |
| `seo-schema` | Schema.org JSON-LD structured data | Schema markup |
| `blog-schema` | BlogPosting, FAQ, BreadcrumbList schema | Blog-specific schema |
| `seo-images` | Image optimization (alt text, sizes, lazy loading) | Image specs |
| `blog-image` | AI image generation prompts via Gemini | Hero/feature images |
| `nano-banana` | Image generation prompt library | Image prompt crafting |
| `blog-chart` | SVG data visualization | Inline charts |

**Output:** Full HTML page with:
- Responsive CSS (mobile-first)
- Semantic HTML5 structure
- Schema.org JSON-LD in `<head>`
- Image placeholder slots with alt text and generation prompts
- WordPress-compatible class names and structure
- Inline CSS or separate stylesheet

#### QA Reviewer Agent — Skills Map

| Skill | What It Provides | How It's Used |
|-------|-----------------|---------------|
| `blog-analyze` | 5-category 100-point scoring system | Quality score |
| `blog-seo-check` | On-page SEO validation checklist | SEO compliance |
| `blog-factcheck` | Stat/claim verification against sources | Accuracy check |
| `blog-geo` | AI citation optimization audit (CITE framework) | AEO readiness |
| `geo-optimization` | AI search citability audit | Citability score |
| `seo-page` | Deep single-page SEO analysis | Technical SEO validation |
| `blog-reviewer` | Full quality assessment with issue detection | Final review |
| `eeat_checklist_template.md` | E-E-A-T compliance checklist | E-E-A-T verification |

### 3. Memory System (`backend/memory/`)

Inspired by Hermes Agent's memory architecture:

```
backend/memory/
  store.py          — ClientMemoryStore class
```

**Storage:** SQLite table `client_memory` (not files — we're on Railway)

```sql
CREATE TABLE client_memory (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    memory_type TEXT,  -- 'brand_voice', 'style_preferences', 'past_content', 'learnings'
    key TEXT,
    value TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(client_id, memory_type, key)
);
```

**Memory types:**
- `brand_voice` — Client writing samples, tone preferences, vocabulary
- `style_preferences` — Layout preferences, section ordering, CTA style
- `past_content` — Summaries of previously generated pages (for internal linking, avoiding repetition)
- `learnings` — Agent observations ("this client prefers shorter paragraphs", "client rejected formal tone")

**How memory is used:**
- At pipeline start, all memory for the client is loaded
- Memory is injected into the copywriter and designer agent system prompts as a frozen snapshot (Hermes pattern)
- After QA review, the QA agent can write new learnings to memory
- After human approval/rejection, feedback is captured as a learning

### 4. Page Type Templates (`backend/pipeline/page_types/`)

Each page type defines:
- Which stages to run and in what order
- Default system prompt additions per stage
- Required vs optional inputs
- HTML template skeleton
- Expected output structure

```python
PAGE_TYPES = {
    "service-page": {
        "stages": ["research", "strategy", "copywrite", "design", "qa"],
        "research_focus": "commercial_intent",  # focus on money keywords
        "content_target": "800-1200 words",
        "html_template": "service_page.html",
        "required_inputs": ["domain", "service", "location"],
        "optional_inputs": ["differentiators", "price_range", "competitors"],
    },
    "location-page": {
        "stages": ["research", "strategy", "copywrite", "design", "qa"],
        "research_focus": "local_intent",  # focus on "[service] in [city]"
        "content_target": "600-1000 words",
        "html_template": "location_page.html",
        "required_inputs": ["domain", "primary_service", "target_location"],
        "optional_inputs": ["home_base", "local_details", "services_list"],
    },
    "blog-post": {
        "stages": ["research", "strategy", "copywrite", "design", "qa"],
        "research_focus": "informational_intent",  # focus on questions, how-tos
        "content_target": "1500-2500 words",
        "html_template": "blog_post.html",
        "required_inputs": ["domain", "keyword", "business_type", "location"],
        "optional_inputs": ["audience", "tone", "internal_links"],
    },
}
```

### 5. Scheduler (`backend/scheduler/`)

Inspired by Hermes cron but simpler — SQLite-backed, APScheduler in-process:

```
backend/scheduler/
  jobs.py           — CRUD for scheduled pipeline jobs (SQLite table)
  scheduler.py      — APScheduler instance, checks for due jobs every 60s
  runner.py         — Executes a pipeline run from a scheduled job config
```

```sql
CREATE TABLE scheduled_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    client_id INTEGER REFERENCES clients(id),
    pipeline_type TEXT,  -- 'service-page', 'location-page', 'blog-post'
    inputs_json TEXT,    -- serialized pipeline inputs
    schedule TEXT,       -- cron expression or interval ("every 7d", "0 9 1 * *")
    next_run_at TEXT,
    last_run_at TEXT,
    last_status TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);
```

Use cases:
- "Generate 4 blog posts for Saiyan Electric every Monday at 9am"
- "Run a location page batch for all 12 cities on the 1st of each month"
- "Auto-generate monthly content calendar for all active clients"

### 6. Frontend Pipeline UI

New views in the SPA:

**Pipeline Builder** — Select page type, client, fill inputs, choose approval mode, launch
**Pipeline Monitor** — Shows stages with progress indicators, intermediate artifacts, approval gates
**Batch Builder** — Queue multiple pages (e.g., "12 location pages for 12 cities")
**Schedule Manager** — Create/edit/pause scheduled pipeline jobs

SSE streaming shows which stage is active and streams the current agent's output in real-time.

### 7. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/run` | POST | Start a pipeline (returns pipeline_id, streams SSE) |
| `/api/pipeline/{id}` | GET | Pipeline status + artifacts |
| `/api/pipeline/{id}/approve` | POST | Approve current stage, advance pipeline |
| `/api/pipeline/{id}/reject` | POST | Reject with feedback, re-run current stage |
| `/api/pipeline/batch` | POST | Queue a batch of pipelines |
| `/api/pipeline/templates` | GET | Available page types and their configs |
| `/api/memory/{client_id}` | GET | Client memory entries |
| `/api/memory/{client_id}` | POST | Add/update memory entry |
| `/api/schedule` | GET/POST/PATCH/DELETE | CRUD for scheduled jobs |

---

## Skill Loading Architecture

Skills are loaded from `~/.claude/skills/` at runtime. On Railway, these will be baked into the Docker image or loaded from a mounted volume.

```python
class SkillLoader:
    """Loads Claude Code skill content for injection into agent system prompts."""

    SKILL_DIRS = [
        Path.home() / ".claude" / "skills",           # User skills
        Path(__file__).parent.parent / "skills",       # Bundled skills
    ]

    def load_skill(self, skill_name: str) -> str:
        """Load SKILL.md content for a given skill name."""
        for base_dir in self.SKILL_DIRS:
            skill_path = base_dir / skill_name / "SKILL.md"
            if skill_path.exists():
                return skill_path.read_text()
            # Check nested paths (e.g., category/skill-name)
            for match in base_dir.rglob(f"{skill_name}/SKILL.md"):
                return match.read_text()
        return ""

    def load_skill_template(self, skill_name: str, template_path: str) -> str:
        """Load a template file from within a skill directory."""
        ...

    def build_agent_prompt(self, stage: str, page_type: str, client_memory: dict) -> str:
        """Assemble the full system prompt for a pipeline stage."""
        skills = STAGE_SKILLS[stage]  # Map of stage → skill names
        prompt_parts = [BASE_PROMPTS[stage]]
        for skill_name in skills:
            content = self.load_skill(skill_name)
            if content:
                prompt_parts.append(f"\n## Skill: {skill_name}\n{content}")
        if client_memory:
            prompt_parts.append(f"\n## Client Memory\n{format_memory(client_memory)}")
        return "\n\n".join(prompt_parts)
```

### Skills Deployment for Railway

Two options:
1. **Copy skills into repo** — `backend/skills/` directory with the specific skills needed (keeps deployment self-contained)
2. **Docker volume mount** — Mount skills directory at runtime (more flexible, easier to update)

Recommended: Option 1 for core skills needed by the pipeline, option 2 for user-created skills.

---

## Critical Files to Create/Modify

### New Files
```
backend/pipeline/
  __init__.py
  engine.py              — PipelineEngine class
  stages.py              — Stage runner functions (research, strategy, copywrite, design, qa)
  artifacts.py           — Dataclass definitions for inter-stage data
  skill_loader.py        — Load skills from disk, build agent prompts

backend/pipeline/page_types/
  __init__.py
  service_page.py        — Service page pipeline config + HTML template
  location_page.py       — Location page pipeline config + HTML template
  blog_post.py           — Blog post pipeline config + HTML template

backend/memory/
  __init__.py
  store.py               — ClientMemoryStore (SQLite-backed)

backend/scheduler/
  __init__.py
  jobs.py                — Scheduled job CRUD
  scheduler.py           — APScheduler integration
  runner.py              — Pipeline execution from scheduled job

backend/skills/                  — Bundled skill content for Railway deployment
  home-service-seo-content/      — (copied from ~/.claude/skills/)
  ... (other key skills)
```

### Modified Files
```
backend/server.py          — New pipeline API routes, scheduler startup
backend/utils/db.py        — New tables: pipeline_runs, pipeline_artifacts, client_memory, scheduled_jobs
backend/static/script.js   — Pipeline builder/monitor UI, schedule manager
backend/static/index.html  — New views for pipeline UI
backend/static/style.css   — Pipeline stage indicators, approval gate UI
backend/requirements.txt   — Add APScheduler, (optional: jinja2 for HTML templates)
```

### Existing Files Reused (Not Modified)
```
backend/utils/dataforseo.py    — All 30+ functions used by research agent
backend/utils/searchatlas.py   — MCP wrapper used by research agent
backend/utils/docx_generator.py — Still generates .docx alongside HTML
backend/workflows/              — Existing workflows remain untouched
```

---

## Implementation Phases

### Phase 1: Pipeline Engine Core (foundation)
- `artifacts.py` — dataclass definitions
- `skill_loader.py` — skill loading from disk
- `engine.py` — PipelineEngine with sequential stage execution + SSE streaming
- `stages.py` — research stage only (to validate the pattern)
- `db.py` updates — pipeline_runs, pipeline_artifacts tables
- `server.py` — `/api/pipeline/run` endpoint

### Phase 2: All Stages + Page Types
- Complete all 5 stages (strategy, copywrite, design, qa)
- Service page, location page, blog post configs
- HTML templates for each page type
- Approval gates (pause/resume)

### Phase 3: Memory System
- `client_memory` table
- ClientMemoryStore class
- Memory injection into copywriter/designer prompts
- Memory capture from QA feedback

### Phase 4: Scheduler
- `scheduled_jobs` table
- APScheduler integration
- Pipeline execution from scheduled jobs
- Batch pipeline support

### Phase 5: Frontend
- Pipeline builder view
- Pipeline monitor with stage progress
- Batch builder
- Schedule manager

---

## Verification Plan

1. **Unit test:** SkillLoader finds and loads skills correctly
2. **Integration test:** Single-stage pipeline (research only) runs end-to-end with DataForSEO
3. **Full pipeline test:** Service page pipeline runs all 5 stages, produces HTML output
4. **Memory test:** Client memory persists across pipeline runs, affects output
5. **Scheduler test:** Scheduled job triggers pipeline at correct time
6. **SSE test:** Frontend receives streaming tokens from each pipeline stage
7. **Manual QA:** Generate a service page for Saiyan Electric, compare quality to current manual process
