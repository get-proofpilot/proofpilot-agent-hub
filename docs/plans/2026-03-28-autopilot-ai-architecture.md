# AutoPilot AI — Architecture & Reference

**ProofPilot's SEO Specialist Agent**
Creates full service pages, location pages, and blogs on autopilot.

---

## What It Does

AutoPilot AI takes a client + keyword + service and produces a production-ready HTML page with:
- Real SEO data from DataForSEO (keyword volumes, difficulty, SERP analysis, competitor data)
- Brand-matched design using the client's actual fonts, colors, logos, and layout patterns
- AI-generated photography via Recraft
- Self-correcting QA that revises until quality threshold is met

## Pipeline Architecture

```
┌──────────┐   ┌──────────┐   ┌───────────┐   ┌────────┐   ┌────────┐   ┌────┐
│ RESEARCH │ → │ STRATEGY │ → │ COPYWRITE │ → │ DESIGN │ → │ IMAGES │ → │ QA │
└──────────┘   └──────────┘   └───────────┘   └────────┘   └────────┘   └──┬─┘
  DataForSEO     Content         Brand           HTML/CSS     Recraft       │
  keywords       brief           voice           @font-face   5+ images    │
  SERP data      sections        E-E-A-T         two-col                    │
  competitors    word targets    internal links   responsive              score < 80?
                                                                            │ yes
                                                                   ┌────────┘
                                                                   ▼
                                                          ┌─────────────────┐
                                                          │  REVISION LOOP  │
                                                          │                 │
                                                          │  Parse QA       │
                                                          │  directives     │
                                                          │       │         │
                                                          │  ┌────┴────┐    │
                                                          │  ▼         ▼    │
                                                          │ copy     design │
                                                          │ fixes    patch  │
                                                          │  └────┬────┘    │
                                                          │       ▼         │
                                                          │   re-run QA     │
                                                          │       │         │
                                                          │  score ≥ 80?    │
                                                          │  yes → DONE     │
                                                          │  dropped? →     │
                                                          │    REVERT       │
                                                          │  max 3 rounds   │
                                                          └─────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/pipeline/engine.py` | Pipeline orchestrator — stage execution, revision loop, design patcher, artifact persistence |
| `backend/pipeline/stages.py` | Stage runners — research, strategy, copywrite, design, images, QA prompts and logic |
| `backend/pipeline/artifacts.py` | Typed artifacts passed between stages (ResearchArtifact, StrategyArtifact, ContentArtifact, DesignArtifact, QAArtifact) |
| `backend/pipeline/brand_extractor.py` | Scrapes client website → extracts colors, fonts (@font-face woff2), logos, nav, section patterns |
| `backend/pipeline/brand_memory.py` | Saves brand data to client memory, formats as "CRITICAL BUILD DIRECTIVES" for design prompt |
| `backend/pipeline/brain_formatter.py` | Context-aware memory injection — gives each stage only the memory it needs |
| `backend/pipeline/skill_loader.py` | Loads Claude Code skills (stop-slop, seo-schema, etc.) into stage prompts |
| `backend/pipeline/image_gen.py` | Image generation via Recraft API (with Nano Banana fallback) |
| `backend/pipeline/design_prompt.py` | Shared design prompt for Claude + Gemini paths |
| `backend/pipeline/page_types/` | Page-type-specific templates and configurations |
| `backend/memory/store.py` | Client memory store (SQLite) — brand_voice, design_system, asset_catalog, business_intel, learnings |

## Stage Details

### 1. Research
- **Input:** domain, service, location, keyword, competitors
- **Data sources:** DataForSEO (keyword volumes, difficulty, SERP, AI Overviews, backlinks, competitor research)
- **Output:** `ResearchArtifact` — keyword analysis, SERP analysis, competitor gaps, recommendations

### 2. Strategy
- **Input:** Research artifact
- **Output:** `StrategyArtifact` — content brief with page structure, section plan, word count targets, SEO specs, FAQ questions

### 3. Copywrite
- **Input:** Strategy brief + client brand voice from memory
- **Skills loaded:** home-service-seo-content, stop-slop
- **Output:** `ContentArtifact` — full page content in markdown with title tag, meta description, FAQ JSON
- **Revision behavior:** Receives QA feedback + previous content, fixes specific issues without restarting

### 4. Design
- **Input:** Content markdown + client design system from brand memory
- **Brand injection:** CRITICAL BUILD DIRECTIVES (logo URL, @font-face CSS, phone, nav links) + CSS custom properties + section patterns + component styles
- **Key patterns:** Two-column text+image layouts, self-hosted fonts, `.micro` labels, location pill tags, large decorative process numbers, sticky header with logo
- **Output:** `DesignArtifact` — complete HTML document with embedded CSS, Schema.org JSON-LD, OG tags

### 5. Images
- **Input:** Design HTML with `data-prompt` placeholders
- **Generation:** Recraft API (realistic_image style), max 6 images per page
- **Output:** Updated HTML with real image URLs replacing placeholders

### 6. QA
- **Input:** All previous artifacts
- **Scoring:** 5 categories × 20 points = 100 total (Content Quality, SEO, E-E-A-T, Technical, AEO)
- **Output:** `QAArtifact` — scores, human-readable review, structured `REVISION_DIRECTIVES`
- **Directive format:** `[COPYWRITE] Fix: ...` and `[DESIGN] Fix/Patch: ...`

## Revision Loop

Triggered automatically when QA score < 80 (configurable via `run.revision_threshold`).

**Behaviors:**
- Routes `[COPYWRITE]` directives to copywrite stage, `[DESIGN]` to design stage
- `[DESIGN] Patch: selector | property | value` — lightweight CSS fix via regex (no full regeneration)
- `[DESIGN] Fix: ...` — full design stage re-run
- Backs up all artifacts before each round
- **Reverts to best version** if score drops (prevents regression)
- Stops after 3 rounds or if score plateaus
- SSE events: `revision_start`, `revision_complete` with score trajectory

## Brand Extraction System

**Endpoint:** `POST /api/clients/{id}/onboard`
**Trigger:** Auto-runs when pipeline starts if `design_system` memory is missing for the client

**What it extracts:**
- Color palette (primary, secondary, accent, background, text, dark)
- Typography (heading font, body font, sizes, weights, line-heights)
- **Self-hosted font files** — `@font-face` woff2 URLs from the client's server
- Logo URLs (filtered to exclude tracking pixels like Facebook/analytics)
- Navigation structure
- Footer content (phone, email, address, copyright)
- Social media links
- Schema.org JSON-LD data
- Section patterns (hero, trust bar, services, process, FAQ, CTA, footer)
- Component styles (buttons, cards, badges)
- CTA patterns (primary text, phone prominence)
- Photography style
- Brand voice and value propositions

**Storage:** Client memory table (`client_memory`) with types: `design_system`, `asset_catalog`, `brand_voice`, `business_intel`

## Client Memory Types

| Type | Keys | Used By |
|------|------|---------|
| `design_system` | color_palette, typography, font_files, css_custom_properties, section_patterns, component_styles, cta_patterns, photography_style, layout_patterns, design_system_css | Design stage |
| `asset_catalog` | logos, hero_images, portfolio_images, team_images, social_links, schema_data, navigation, footer | Design stage, Image stage |
| `brand_voice` | tone, value_propositions, business_info | Copywrite stage |
| `business_intel` | service_catalog, differentiators, certifications, guarantees, service_areas, customer_personas, competitive_position | Strategy, Copywrite |
| `past_content` | page_type:keyword entries, qa-score entries | Copywrite (internal linking), QA (quality tracking) |
| `learnings` | Agent observations about the client | All stages |

## SSE Event Types

| Event | When | Payload |
|-------|------|---------|
| `brand_extracted` | Auto brand extraction ran | `{message}` |
| `stage_start` | Stage begins | `{stage, stage_index, total_stages, revision_round?}` |
| `token` | Streaming text chunk | `{text, stage}` |
| `stage_complete` | Stage finished | `{stage, stage_index, output_length, method?}` |
| `revision_start` | Revision loop begins | `{round, max_rounds, previous_score, threshold, stages_to_revise, directive_count}` |
| `revision_complete` | Revision round done | `{round, previous_score, new_score, improved}` |
| `pipeline_complete` | All done | `{pipeline_id, stages_completed, final_score, revision_rounds, revision_history}` |
| `awaiting_approval` | Paused for approval | `{stage, pipeline_id, message}` |
| `error` | Failure | `{message, stage?}` |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_revisions` | 3 | Max revision rounds before shipping |
| `revision_threshold` | 80 | QA score needed to skip revision |
| `approval_mode` | autopilot | autopilot / milestone / output_only |
| `max_tokens` (design) | 16000 | Token budget for design stage |
| `max_tokens` (copywrite) | 12000 | Token budget for copywrite stage |

## Page Types Supported

- **Service page** — e.g., "Roof Replacement in Shoreview, MN"
- **Location page** — e.g., "Electrician in Chandler, AZ"
- **Blog post** — e.g., "How Much Does a Roof Replacement Cost in Minnesota?"

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/start` | POST | Start a new AutoPilot pipeline run |
| `/api/pipeline/{id}/status` | GET | Get pipeline status and artifacts |
| `/api/pipeline/{id}/approve` | POST | Approve and continue a paused pipeline |
| `/api/clients/{id}/onboard` | POST | Run brand extraction for a client |
| `/api/clients/{id}/memory` | GET | View client memory entries |

## Cost Per Page (approximate)

| Component | Cost |
|-----------|------|
| DataForSEO research | ~$0.01-0.03 |
| Claude Sonnet (6 stages × ~8K tokens) | ~$0.15-0.25 |
| Claude Haiku (brand extraction) | ~$0.01 |
| Recraft images (5 × $0.04) | ~$0.20 |
| Revision rounds (1-3 × ~$0.10) | ~$0.10-0.30 |
| **Total per page** | **~$0.50-0.80** |
