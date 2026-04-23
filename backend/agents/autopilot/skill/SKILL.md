---
name: autopilot
description: >
  AutoPilot: ProofPilot's named agent for generating production-ready SEO pages via the
  7-stage pipeline (Research, Strategy, Copywrite, Design, Design Enrich, Images, QA).
  Uses GLM for design + Gemini for polish pass. Runs on VPS via SSH.
  Do NOT improvise if unavailable.
  Aliases: AutoPilot, Auto Pilot, autopilot-ai, "generate page", "content sprint", "build service page"
tags: [autopilot, seo, content, generation, pipeline, autopilot-ai, auto-pilot]
---

# AutoPilot

## When to Trigger

Load this skill when ANY of these happen:
- Someone says "AutoPilot", "Auto Pilot", "use autopilot", "run autopilot"
- Someone asks to "generate a page", "create a service page", "build a homepage"
- Someone asks for a "content sprint" or "batch content generation"
- Someone asks to "redesign" a page with new SEO content
- After any content generation request for a ProofPilot client

## CRITICAL: Do NOT Improvise

AutoPilot is a real tool running on the VPS. If you cannot reach it, STOP and tell the user:
"AutoPilot is not reachable. The VPS or SSH connection may be down. I cannot generate content without the actual pipeline."

Do NOT "manually follow the methodology" or "build content directly." The whole point is the pipeline's built-in skills, brand extraction, client memory, and multi-stage QA loop. An LLM freestyling content is NOT AutoPilot.

## Architecture

- **Location:** Hostinger VPS `187.124.234.21`
- **Backend:** `/root/Autopilot/backend/`
- **Database:** `/root/Autopilot/backend/jobs.db` (SQLite)
- **Env file:** `/root/Autopilot/.env` (DATABASE_PATH). LLM keys come from `~/.hermes/.env` (ANTHROPIC_TOKEN, FIRECRAWL_API_KEY).
- **Models:** xiaomi/mimo-v2-pro (default, via OpenRouter), deepseek/deepseek-v3.2, z-ai/glm-5.1, qwen/qwen3-235b-a22b, claude-sonnet-4, claude-opus-4, claude-haiku-4.5. OpenRouter models go through `openrouter.ai/api/v1`; Anthropic models go through subscription OAuth token.
- **DO NOT USE for page gen:** Haiku (wireframe quality), Gemini 3 Flash (truncates mid-CSS, 62/100).
- **DEPRECATED:** `qwen/qwen3.6-plus:free` is dead (404). Use `qwen/qwen3.6-plus` (paid) or `qwen/qwen3-235b-a22b`.

## 7-Stage Pipeline (Updated Apr 8 2026)

1. **Research** — Keyword, SERP, competitor analysis via DataForSEO
2. **Strategy** — Content brief, H-tag structure, differentiation
3. **Copywrite** — Full SEO-optimized page copy with anti-slop, E-E-A-T, voice guide
4. **Design** — Complete HTML+CSS with brand-matched design system (auto-extracted). 32K max tokens.
5. **Design Enrich** — Polish pass: Gemini adds icons, hover effects, visual depth, section dividers to the Design stage output WITHOUT changing content or structure. 32K max tokens. Falls back to CSS-merge if Gemini truncates.
6. **Images** — Generation of image prompts for placeholder replacement
7. **QA** — Automated quality review with revision directives that loop back to copywrite/design/design_enrich

Output: Production-ready HTML file with QA score.

## Three-Brain Design Architecture (Apr 23 2026 — canonical)

**Read this first:** `references/three-brain-architecture.md`

Every AutoPilot design run now has three explicit stages with distinct brains:

1. **Brand Brain** — captures what the brand IS (logo, colors, fonts, real assets). Reporter, no opinions. Output: `brand-brain.json` + verdict PRESERVE+ELEVATE / PARTIAL ANCHOR / INVENT.
2. **Designer Brain** — decides what to preserve, elevate, or invent. Reads the Brand Brain's facts + gold-standard playbook + inspiration guide, produces a concrete `design-spec.md`. Hard rule: **don't add colors the logo doesn't have**; **don't replace typography that has brand equity unless the current type is truly generic**.
3. **Website Brain** — executor. Applies the spec to a template from the WebsitePilot library. No re-deciding, no re-inventing.

Doctrine files:
- `references/three-brain-architecture.md` — the sequenced architecture
- `references/brand-archaeology.md` — Brand Brain procedure + schema
- `references/design-strategist.md` — Designer Brain procedure + spec template
- `references/gold-standard-playbook.md` — cross-vertical patterns + "remove the logo" success test
- `references/inspiration/inspiration-guide.md` — ProofPilot's canonical list of gold-standard home-service sites (Hook Agency, 180 Sites, Be The Anomaly, Get Local Leads) + the 3 pillars (Cohesive · Detail · Dynamic)

## Running locally (no API, no VPS)

When AutoPilot runs inside a Claude Code session (not the Railway backend):

- Brand Brain = Claude + Playwright + Python (Pillow for logo pixel analysis) + Bash (asset downloads). Prefer Firecrawl if available (better `extract` schema for brand fields); fallback: Playwright page.evaluate + raw HTML parsing.
- Designer Brain = Claude reasoning. No model swap needed.
- Website Brain = Claude writing/editing TS/TSX/CSS on a cloned WebsitePilot template.

Dispatched as sequential subagents in the same session. Each reads the previous stage's output file.

## Design Quality Upgrades (Apr 23 2026)

**Observed failure mode** when running AutoPilot locally (Claude Code skill mode): demos looked "template-skinned" — didn't pull the client's real logo, didn't use their actual colors, didn't feel custom. The root cause: Research stage pulled brand signals as a JSON blob that Design stage ignored, jumping straight from "strategy" to "render HTML."

**The fix: two sub-stages added before Design runs.**

### Stage 1.5 — Brand Archaeology (mandatory)

Aggressively pull the client's real brand assets: download the logo PNG, analyze its dominant colors pixel-by-pixel, capture typography (including @font-face URLs), download every non-stock authentic photo (fleet, team, storefront), pull favicon + OG image, note voice signals.

Reference doctrine: `references/brand-archaeology.md` in this skill.

Output: `brand-archaeology-v2.json` consumed by the next stage.

**Verdict format:** end every archaeology with PRESERVE+ELEVATE / PARTIAL ANCHOR / INVENT. Most clients are PARTIAL ANCHOR — the common mistake is treating them as INVENT and ignoring real equity.

### Stage 2.5 — Design Strategist (mandatory)

Takes Brand Archaeology + Strategy + the gold-standard playbook and produces a concrete brand spec the Design stage executes against. Decides: palette, typography trio, THE committed motif (one, not three), THE signature section-transition (one move, committed), button system, icon system, photography strategy, motion.

Reference doctrine: `references/design-strategist.md`.

Output: `brand-spec-v2.md` document with an "Implementation Order" section the Design stage follows priority-by-priority.

### Gold-standard playbook

Every design run references `references/gold-standard-playbook.md`: the three pillars (Cohesive · Detail · Dynamic), the cross-site patterns (committed metaphor, one signature section-transition, unusual primary color, extreme type weight contrast, authentic photography over stock), the anti-patterns, and the "remove the logo" success test.

### The success test (mandatory QA gate)

Before marking any demo done, answer 5 questions. All must be "yes":
1. Remove the logo — can a visitor still tell what the business does, who it serves, and what vibe it has?
2. Next to 5 template sites in the same vertical — does this one stand out as clearly more designed?
3. Print black-and-white — does the hierarchy still read?
4. Scroll at 50% speed — do section transitions feel rhythmic?
5. Would the client's target customer describe this as "designed FOR" their company, or "a website that happens to be for" their company?

If any answer is "no," the site is template-level. Go back to Design Strategist.

### Recommended Model Configuration (Best Quality)
```
--model "xiaomi/mimo-v2-pro" \
--model-map "design:z-ai/glm-5.1,design_enrich:google/gemini-3-flash-preview,qa:google/gemini-2.5-pro-preview"
```
This uses MIMO for research/strategy/copy (reliable, fast), GLM for design (best aesthetics),
Gemini Flash for enrichment (icons, hover effects, visual polish), and Gemini 2.5 Pro for QA (best reasoning, catches section truncation, missing images, broken links).

### Why Gemini 2.5 Pro for QA (Apr 8 2026)
- MIMO QA tends to give generous scores and vague feedback
- Gemini 2.5 Pro gives the same scores but with SPECIFIC, ACTIONABLE directives
- New QA prompt includes Section Completeness Audit: compares copy H2s vs design H2s
- QA now sees full page HTML (first 12K + last 8K) instead of just first 8000 chars
- QA now reviews design_enrich output (not just raw design) for accurate assessment
- Cost: ~$0.10-0.15 per page ($1.25/$10 per M tokens on OpenRouter)

### Why This Architecture
- **GLM 5.1** produces the best visual design of all models tested, but sometimes truncates at 16K tokens (fixed to 32K).
- **Gemini 3 Flash** has excellent design instincts (icons, rich styling) but cannot generate complete pages (truncates mid-CSS when building from scratch). Perfect for ENHANCING existing HTML.
- **MIMO** is the most reliable completer — best at research, strategy, copy, and QA where full completion matters.
- The two-phase design (GLM builds, Gemini polishes) combines each model's strength.

### Design Enrich Stage Details (`pipeline/stages.py: run_design_enrich`)
- Takes the Design stage's full HTML and enhances it
- Adds: Lucide icons, hover effects, card shadows, section dividers, heading accents, footer polish
- Uses DESIGN_ENRICH_PROMPT (explicitly says "enhance, don't rebuild")
- **CSS Integrity Check (CRITICAL — Apr 8 2026):** Gemini Flash's biggest failure mode is NOT truncation — it's CSS replacement. Despite the prompt saying "enhance, don't rebuild," Gemini rewrites the full page at similar size but generates brand-new CSS that only includes "polish" styles (hover effects, heading accents). All structural/layout CSS from GLM (`.section`, `.two-col`, `.footer-grid`, `.trust-bar`, `.faq-answer`, etc.) gets silently dropped — up to 39 classes can be missing. Result: page renders as completely unstyled HTML despite being the right file size. The old 70% size check missed this completely because the output was the same size — just wrong CSS.
- **Two-layer fallback in `run_design_enrich()`:**
  1. Size check: if enriched output <70% of original → merge CSS (original logic)
  2. CSS class audit: extract all classes used in HTML, compare against classes defined in CSS. If 3+ critical structural classes are missing → auto-merge GLM's original CSS underneath Gemini's polish CSS. Critical classes checked: `section`, `two-col`, `container`, `card`, `footer-grid`, `footer-col`, `site-footer`, `trust-bar`, `location-tags`, `warning-grid`, `panel-grid`, `process-steps`, `trust-grid`, `cta-banner`, `faq-answer`, `hero-bg`, `section-alt`, `section-dark`, `section-warm`.
- **How to diagnose broken design_enrich output:** Check HTML classes vs CSS classes: `html_classes = set(re.findall(r'class="([^"]*)"', html))` vs `css_classes = set(re.findall(r'\.([a-zA-Z][\w-]*)', css))`. If `len(missing) > 10`, the CSS integrity check failed or wasn't triggered.
- Registered in STAGE_RUNNERS and ARTIFACT_TYPES (reuses DesignArtifact)
- In revision loop, `design_enrich` auto-re-runs after any `design` revision

## Smart Revision Loop (Deployed Apr 8 2026)

Upgraded `engine.py` `_run_revision_loop()` with intelligent exit logic:
1. If QA says APPROVED and score >= threshold: done (green light)
2. If QA says NEEDS_REVISION but score >= threshold: force ONE revision to fix real issues
3. After that one revision, accept if still above threshold (QA being picky, not stuck)
4. Anti-loop: if score improves < 3 points between rounds OR drops, stop (diminishing returns)
5. Below threshold: always revise (same as before)

Also fixed: `design_profile` added to VALID_TYPES in `memory/store.py` (was blocking reference page injection).

## QA Stage Upgrades (Deployed Apr 8 2026)

Three critical fixes to the QA stage in `pipeline/stages.py`:

1. **Section Completeness Audit**: QA now extracts H2 headings from both copywrite markdown and design HTML, compares them, and flags missing sections. Design Completeness replaced Technical Quality as category 4 (still 20 points).

2. **Full Page Visibility**: QA previously only saw the first 8000 chars of design HTML (~20% of a 40KB page). Now it gets: first 12K + last 8K chars (for pages >24K), or the full HTML (for pages <=24K). This means QA can actually see the footer, FAQs, and bottom sections.

3. **Design Enrich Awareness**: QA now reviews the design_enrich output (Gemini's polished version) instead of just the raw GLM design output.

4. **Gemini 2.5 Pro**: Produces specific, actionable revision directives instead of vague feedback. Catches missing images, broken links, HTML typos, and placeholder content that MIMO QA missed.

5. **QA max_tokens**: Increased from 8192 to 12000 to accommodate longer, more thorough reviews.

## Design Quality Improvements (Deployed Apr 8 2026)

Five modules enhance the Design stage to produce pages matching the client's actual site:

### 1. Reference Page Injection (`pipeline/reference_page_scraper.py`)
Before Design, scrapes a matching page from the client's live site via Firecrawl, extracts
CSS + HTML skeleton, injects into design prompt as "match this exact design."

**CRITICAL PITFALL:** Firecrawl SDK uses `doc.raw_html` (snake_case) NOT `doc.rawHtml` (camelCase).
API format name is `rawHtml` but SDK attribute is `raw_html`. Fixed in `firecrawl_scraper.py`.

### 2. Client Design Profiles (persistent templates)
Extracted skeleton saved to `client_memory` (type: `design_profile`). Future pages reuse it.
Clear to force re-scrape: `DELETE FROM client_memory WHERE memory_type='design_profile'`

### 3. Per-Vertical Design Prompts (`pipeline/vertical_prompts.py`)
5 verticals: `home_services`, `luxury_creative`, `healthcare`, `real_estate`, `professional_services`.
Auto-detects from client name/domain/service. Appended to DESIGN_BASE_PROMPT.

### 4. Visual QA Loop (`pipeline/visual_qa.py`)
After Design, screenshots generated page + client's live site, sends both to Claude Vision.
If similarity below 8/10, generates `[DESIGN] Fix:` directives for the revision loop.
Wired into `engine.py` between stage completion and `_run_revision_loop()`.

### 5. Remaining Gap: Smart Image Handling (PENDING)
Still uses placeholder.jpg + Stage 5 AI generation (frequently fails on credits).
Next: pull client portfolio images during brand extraction, use as defaults.

## Model Comparison Results (Apr 8 2026)

Same page: San Clemente Wedding Photographer (Adam Levinstein, Client #2)

| Model              | QA Score | Revisions | HTML Size | Verdict |
|--------------------|----------|-----------|-----------|---------|
| MIMO v2 Pro        | 77/100   | 1         | 57KB      | Most reliable, full completion |
| DeepSeek v3.2      | 76/100   | 1         | 38KB      | Concise, reliable |
| GLM 5.1            | 71/100   | 2         | 48KB      | BEST DESIGN, but truncated at 16K tokens |
| Gemini 3 Flash     | 62/100   | 1         | 22KB      | Best polish/icons, but truncates when building from scratch |
| Opus 4             | Failed   | —         | —         | 429 from gateway contention |

### Hybrid Pipeline Results (GLM design + Gemini enrich)
| Client             | Vertical          | QA Score | Revisions | Verdict |
|--------------------|-------------------|----------|-----------|---------|
| Dolce Electric     | home_services     | **88/100** | 2       | **BEST SCORE EVER.** Home services vertical prompt + hybrid pipeline. |
| Adam Levinstein    | luxury_creative   | 75/100   | 1         | 32K tokens fixed truncation (was 67/100 at 16K). |
| Adam Levinstein    | luxury_creative   | 67/100   | 3         | With 16K tokens, GLM truncated every round. |

### With Gemini 2.5 Pro QA (Apr 8 2026)
| Client             | Vertical          | QA Model   | First Score | Final Score | Revisions | Key Findings |
|--------------------|-------------------|------------|-------------|-------------|-----------|--------------|
| Dolce Electric     | home_services     | Gemini 2.5 Pro | 60/100 | **89/100** | 1 | Caught missing schema, incomplete FAQ (3/6 Qs), WCAG contrast fail, low word count. All fixed in revision. |
| Dolce Electric     | home_services     | MIMO       | 88/100 | 88/100 | 0 | Missed all the above issues. "Approved" with vague praise. |

| All Thingz Electric (old brand) | home_services | Gemini 2.5 Pro | 83/100 | 83/100 | 0 | Wrong brand colors (#000 primary). Caught truncation, low word count, missing FAQs. No revision (pre-smart-loop). |
| All Thingz Electric (fixed brand) | home_services | Gemini 2.5 Pro | 77/100 | **88/100** | 1 | Correct brand (#0073E6 blue, Poppins). Smart revision loop fired: expanded copy, added schema, restored FAQs. 58KB final page, 1 missing CSS class. |

**Key insight:** Gemini 2.5 Pro's first-pass score is *lower* because it catches real issues. But the revision loop fixes them, producing a genuinely better final page. MIMO QA rubberstamps pages that have real problems.

### Matthew's Design Assessment (Visual Review)
- **GLM 5.1** — "Best design and elements without many mistakes. Really good from a design perspective."
- **Gemini 3 Flash** — "Good from having icons and richer styling and just better design, but got cut off. Half-assed but what it did, it did well."
- **MIMO v2 Pro** — Good full output but less visually distinctive.
- **Matthew's conclusion:** "If we had GLM do most of the work and then Gemini came through and did some improvements, that would get us the best output." → This is the hybrid pipeline.

### Production Strategy
- **Best quality:** `--model-map "design:z-ai/glm-5.1,design_enrich:google/gemini-3-flash-preview,qa:google/gemini-2.5-pro-preview"` with MIMO as base model. This is the default for all production runs.
- **Most reliable (budget):** MIMO for everything (single model, 77/100, no truncation).
- **Opus is NOT viable** for production — Anthropic sub contention with gateway. OpenRouter Opus too expensive for volume. Matthew confirmed: "it seems like Opus might not be the best option with how it's currently set up."
- **Critical finding:** max_tokens=32000 is required for GLM design. At 16K, GLM truncates mid-CSS every time, burning 3 revision rounds to reach only 67/100. At 32K, it completes on the first try (75/100) or second try (88/100).
- **FIXED (Apr 8 2026): NEEDS_REVISION now forces revision.** Gemini 2.5 Pro QA sometimes flags NEEDS_REVISION with critical issues but scores above threshold (e.g., 83/100). The smart revision loop in `engine.py` now handles this: if QA says NEEDS_REVISION but score >= threshold, it forces ONE revision round to address flagged issues. After that revision, it accepts if still above threshold. Anti-loop: stops if score improves < 3 points or drops between rounds.

## LLM & Scraping Architecture (Updated Apr 8 2026)

**Dual LLM routing in `pipeline/stages.py`:**
- `_stream_openrouter()` is the central router. Checks `_OPENROUTER_MODELS` set.
- **OpenRouter path**: `openai.AsyncOpenAI` with `base_url="https://openrouter.ai/api/v1"`. Models: `xiaomi/mimo-v2-pro`, `qwen/qwen3-235b-a22b`, `qwen/qwen3.6-plus`, `google/gemini-2.5-pro-preview`, `google/gemini-3-flash-preview`, `openai/gpt-4.1`, `z-ai/glm-4.7`, `z-ai/glm-5.1`, `deepseek/deepseek-v3.2`.
- **Anthropic path**: `anthropic.AsyncAnthropic` with OAuth token. Models: `claude-sonnet-4-20250514`, `claude-opus-4-20250514`, `claude-haiku-4-5-20251001`.

**Anthropic subscription** (for Anthropic-routed models only):
- OAuth tokens (`sk-ant-***REDACTED****`) require beta headers: `oauth-2025-04-20`, `claude-code-20250219`
- Shared with Slack gateway — Sonnet/Opus will 429 when Pilot is active

**Prefer OpenRouter models** to avoid Anthropic rate limit contention with the gateway.

**External APIs:** DataForSEO (keywords), OpenRouter (LLMs + images), Firecrawl (scraping).

## Setup (every new sandbox session)

```bash
pip3 install paramiko -q --break-system-packages
```

Then connect via SSH:
```python
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('187.124.234.21', username='root', password='***REDACTED***')
```

## Verify Connection First

```bash
cd /root/Autopilot/backend && source /root/Autopilot/.env && \
PYTHONPATH=/root/Autopilot/backend python3 autopilot_agent.py clients
```

If this fails, STOP. Tell the user AutoPilot is unreachable.

## Known Clients (client_id)

1: All Thingz Electric, 2: Adam Levinstein Photography, 3: Dolce Electric,
4: ISS, 5: Saiyan Electric, 6: Cedar Gold, 7: Pelican Coast, 8: ProofPilot,
9: Xsite Belize, 10: Power Route, 11: Alpha Property Management,
12: Trading Academy, 13: Youth Link, 14: LAF Counseling, 15: Judds Plumbing

## CLI Commands (run on VPS via SSH)

All commands require:
```bash
cd /root/Autopilot/backend && export $(grep -v '^#' /root/Autopilot/.env | xargs) && \
export $(grep -v '^#' /root/.hermes/.env | grep -E "OPENROUTER|FIRECRAWL|ANTHROPIC|DATAFORSEO" | xargs)
```

### Generate a single page (reliable)
```bash
PYTHONPATH=/root/Autopilot/backend nohup python3 autopilot_agent.py generate \
  --client-id 15 --page-type service-page \
  --keyword "drain cleaning Mesa" --service "Drain Cleaning" --location "Mesa, AZ" \
  --model "xiaomi/mimo-v2-pro" --output /tmp/output.html \
  > /tmp/autopilot.log 2>&1 &
```

### Best quality: GLM design + Gemini enrich + Gemini 2.5 Pro QA (RECOMMENDED)
```bash
PYTHONPATH=/root/Autopilot/backend nohup python3 autopilot_agent.py generate \
  --client-id 2 --page-type location-page \
  --keyword "San Clemente wedding photographer" --service "Wedding Photography" \
  --location "San Clemente, CA" \
  --model "xiaomi/mimo-v2-pro" \
  --model-map "design:z-ai/glm-5.1,design_enrich:google/gemini-3-flash-preview,qa:google/gemini-2.5-pro-preview" \
  --output /tmp/output.html > /tmp/autopilot.log 2>&1 &
```
Stage names for model-map: research, strategy, copywrite, design, design_enrich, images, qa.

### Content sprint (multiple pages)
```bash
PYTHONPATH=/root/Autopilot/backend python3 autopilot_agent.py sprint \
  --client-id 15 \
  --items '[{"page_type":"service-page","keyword":"drain cleaning","service":"Drain Cleaning","location":"Mesa, AZ"}]'
```

### List clients
```bash
PYTHONPATH=/root/Autopilot/backend python3 autopilot_agent.py clients
```

## Slack Response Behavior (CRITICAL)

When running AutoPilot from Slack, be CONCISE. Do not narrate internal steps.

**DO:**
1. "Kicking off the 6-stage pipeline. This takes 10-15 min."
2. (SILENCE while pipeline runs)
3. "Pipeline complete. Score: 77/100. Preview: https://preview.proofpilotapps.com/client/page.html"

*Always include the preview URL in the final delivery message.* The pipeline auto-deploys and prints the URL. Parse it from the log output and post it to Slack. This is the primary deliverable.

**DON'T:** Narrate env vars, SSH debugging, export issues. Fix silently.

## Execution Notes

- Pipeline takes 10-25 minutes per page (7 stages + up to 3 QA revision rounds). Use nohup + background.
- **Kill stale processes first:** `ps aux | grep autopilot_agent | grep -v grep` and kill orphans.
- **Env var sourcing:** `source .env` does NOT export in non-interactive SSH. Use: `export $(grep -v '^#' /root/Autopilot/.env | xargs)`
- **Paramiko nohup pitfall:** Don't call `stdout.read()` after launching nohup. Fire-and-forget, `time.sleep(5)`, then check with separate `exec_command("ps aux | grep ...")`.
- **Monitoring:** Use `execute_code` polling loop (every 60s). Watch for 5-min timeout — chain multiple blocks for long runs.
- **Code fence stripping:** LLM output sometimes includes ``` ```html ``` wrappers. The pipeline strips them via regex but occasionally misses. Check for `html` text visible at the top of the rendered page. Fix: `head -1 /tmp/output.html` and if it starts with ``` ``` ```, strip with python or redeploy.
- **0-byte output file recovery (CRITICAL):** Sometimes the pipeline completes with a QA score but writes a 0-byte output file (Design stage HTML never extracted properly). ALWAYS verify file size after pipeline: `wc -c /tmp/output.html`. If 0 bytes, the HTML is still in the log. Recover with:
  ```bash
  # Find HTML blocks in the log (there are usually 2: initial + post-revision)
  grep -n "<!DOCTYPE\|</html>" /tmp/autopilot.log
  # Extract the LAST (revised) HTML block — this is the final version
  awk '/<!DOCTYPE/{f=1} f{print} /<\/html>/{f=0}' /tmp/autopilot.log | tail -n +1 > /tmp/output_recovered.html
  # OR with sed using the line numbers from grep:
  sed -n '1889,3491p' /tmp/autopilot.log > /tmp/output_recovered.html
  # VERIFY size on VPS BEFORE pulling locally — sed can fail silently
  wc -c /tmp/output_recovered.html
  ```
  Then deploy via `deploy_preview.py --file /tmp/output_recovered.html`. The original 0-byte file may be cached by the preview server, so always use a NEW filename for the recovered version.
- Stage 6 (Images) frequently fails on OpenRouter credits. Pages ship with placeholder.jpg. This is acceptable — real photos replace placeholders.
- DataForSEO may return 0 results, causing Research to use "simulated" mode.
- **GLM truncation:** GLM 5.1 produces the best design but may truncate if max_tokens is too low. Set to 32K (Apr 8 2026). If truncation persists, QA catches it and the revision loop re-runs design.
- **Gemini enrichment CSS integrity:** Two fallback layers: (1) size check — if <70% of original, merge CSS only. (2) class audit — if 3+ structural classes are missing from CSS despite HTML using them, auto-merge GLM's base CSS under Gemini's polish CSS. The class audit catches the common failure where Gemini rewrites at full size but drops all layout CSS. Always visually verify preview pages after generation — if the page looks unstyled/broken, this is almost certainly a CSS integrity failure in design_enrich.
- **Firecrawl SDK v4.22:** Use `from firecrawl import Firecrawl` (not FirecrawlApp). The `raw_html` attribute is snake_case (`doc.raw_html`), NOT camelCase. CLI v1.12.2 also available on VPS for ad-hoc scraping.

### Rate Limit Strategy

1. Default: `--model "xiaomi/mimo-v2-pro"` — **PREFERRED.** 77/100, best quality.
2. Alternative: `--model "deepseek/deepseek-v3.2"` — 76/100, more concise. Good fallback.
3. Budget: `--model "qwen/qwen3-235b-a22b"` — Cheaper. Decent quality.
4. Avoid: Gemini 3 Flash (truncates), Haiku (wireframe), `qwen/qwen3.6-plus:free` (dead 404).
5. Anthropic models (Sonnet/Opus): Only when gateway is idle. Severe 429 risk.
6. Check OpenRouter credits: `curl -s https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $OPENROUTER_API_KEY"` — look at `limit_remaining`.

**Env for OpenRouter:** Export BOTH .env files:
```bash
export $(grep -v '^#' /root/Autopilot/.env | xargs) && \
export $(grep -v '^#' /root/.hermes/.env | grep -E "OPENROUTER|FIRECRAWL|ANTHROPIC|DATAFORSEO" | xargs)
```

## Preview Server (Persistent, Shareable URLs)

AutoPilot auto-deploys every generated page to the preview server. After pipeline completion, the output HTML is copied to `/var/www/preview/{client}/{page}.html` and a shareable URL is printed.

**Preview URL format:** `https://preview.proofpilotapps.com/{client-slug}/{page-slug}.html`
**Landing page:** `https://preview.proofpilotapps.com/` (lists all previews grouped by client)
**API endpoint:** `https://preview.proofpilotapps.com/api/pages` (JSON listing)
**Direct IP fallback:** `http://187.124.234.21:9090/` (bypasses Cloudflare, no SSL)

This happens automatically in the CLI pipeline (patched into `autopilot_agent.py`). No manual steps needed.

**Manual deploy (for pages generated outside the pipeline):**
```bash
python3 /root/preview/deploy_preview.py --client "dolce-electric" --file /tmp/output.html --name "drain-cleaning-mesa"
# Output: https://preview.proofpilotapps.com/dolce-electric/drain-cleaning-mesa.html
```

**From Pilot (via SSH):**
```python
ssh.exec_command('python3 /root/preview/deploy_preview.py --client "dolce-electric" --file /tmp/output.html --name "drain-cleaning-mesa"')
preview_url = stdout.read().decode().strip()
# Post preview_url to Slack
```

**Service:** `preview-server.service` (systemd, auto-starts on boot, port 9090)
**Deploy script:** `/root/preview/deploy_preview.py`
**Pages stored:** `/var/www/preview/{client-slug}/{page-slug}.html`

Share the URL with Matthew, Marcos, Hammad, or anyone. The URL stays live until the file is deleted or overwritten by a new generation.

**Infrastructure:** `preview.proofpilotapps.com` DNS (Cloudflare proxied) -> Caddy (port 80/443, self-signed cert) -> preview server (port 9090). Caddy and preview server are both systemd services, auto-start on boot.

### Visual Verification After Generation (REQUIRED — Matthew expects this)

After every pipeline run, ALWAYS visually verify the page before reporting to the user.
Matthew explicitly called this out: "You should also be able to tell this by looking, using vision, and then reporting back and fixing this with the agent."

**Verification steps:**
1. Navigate browser to the preview URL
2. Take `browser_vision` screenshots scrolling through hero, middle sections, and footer
3. Check for: broken layouts (unstyled sections), missing images, overlapping text, broken cards
4. Run the CSS class audit programmatically (faster than visual):
```python
import re
html_classes = set()
for cls_str in re.findall(r'class="([^"]*)"', html):
    for cls in cls_str.split():
        html_classes.add(cls)
style_match = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
css = style_match.group(1) if style_match else ""
css_classes = set(re.findall(r'\.([a-zA-Z][\w-]*)', css))
missing = html_classes - css_classes - {'active','open','scrolled','visible'}
print(f"Missing: {len(missing)} classes")  # >10 = broken page
```
5. **If the page looks broken/unstyled**, the most likely cause is design_enrich CSS integrity failure.
6. Only report "done" after visual confirmation looks good. NEVER just say "pipeline scored X, here's the link" without checking.

**Common visual failures to catch:**
- All sections show as plain text with no layout = CSS integrity failure (design_enrich dropped structural CSS)
- Bottom sections unstyled but top looks fine = design model truncated mid-CSS
- No images at all = Stage 5 (Images) failed on credits or images weren't embedded
- FAQ doesn't expand = missing `.faq-answer` CSS or broken JS
- ````html` text visible at top of rendered page = code fence not stripped from LLM output

### Taking Screenshots for Slack

When someone asks to SEE a preview:
1. Navigate browser to `https://preview.proofpilotapps.com/{client}/{page}.html`
2. Take 3-4 `browser_vision` screenshots scrolling down
3. Post screenshots to Slack with section labels

### Legacy: Port 8080 Model Comparison Server
Port 8080 still has an old model comparison index. Port 9090 is the canonical preview server.

## Gateway Restart Recovery

If Hermes gateway restarts during a run, the VPS pipeline keeps running (nohup) but Pilot
loses tracking. Check: `tail -30 /tmp/autopilot.log`, `ls /tmp/*.html`, deliver manually.

## Brand Guidelines (Persistent Style Guides)

Brand guidelines are stored in `/root/Autopilot/brand-guidelines/<domain-slug>/`:
- `style-guide.md` — Human-readable full style guide (colors, typography, buttons, sections, voice)
- `brand-data.json` — Machine-readable brand data (fed into AutoPilot pipeline)
- `variables.css` — CSS custom properties block

Also stored in `client_memory` DB table (design_system, brand_voice, asset_catalog types) for pipeline access.

### Extract/refresh brand guidelines:
```bash
PYTHONPATH=/root/Autopilot/backend python3 /root/Autopilot/extract_brand_guide.py <domain> --client-id <N>
```

### Brand Extraction Pitfalls (CRITICAL — learned Apr 8 2026):
1. **Gemini 2.5 Pro JSON output contains multiline strings.** The raw JSON is valid but only parseable with `json.loads(text, strict=False)`. Never use `json.loads(text)` (strict=True default) or json5 — both fail on Gemini output.
2. **Trailing commas:** Always strip with `re.sub(r',\s*([}\]])', r'\1', text)` before parsing.
3. **Do NOT write a "newline escaper"** that walks character by character — it will corrupt valid strings by double-escaping `\n` sequences that are already properly escaped. The simplest approach (trailing comma fix + `strict=False`) works for all 5 tested clients.
4. **Brand extractor (Haiku) often gets colors wrong.** It picks up text colors (#000000) as "primary" instead of actual brand accent colors from buttons/CTAs. The `extract_brand_guide.py` script using Gemini 2.5 Pro with explicit color extraction rules produces much better results. Always re-extract with Gemini when onboarding a new client.
5. **After extracting, clear stale design_profile cache:** `DELETE FROM client_memory WHERE client_id=N AND memory_type='design_profile'` — otherwise the pipeline reuses old brand data from cache.

### Current clients with brand guidelines (Apr 8 2026):
| Client | Primary Color | Font |
|--------|--------------|------|
| All Thingz Electric | `#0073E6` Bright Blue | Poppins |
| Pelican Coast Electric | `#ffbb00` Electric Yellow | Heebo |
| Power Route Electric | `#E82428` Bright Red | Outfit |
| Saiyan Electric | `#F89D2B` Saiyan Orange | Barlow |
| Adam Levinstein | `#BCAB9A` Dusty Brown | Bigcaslon |

## Adding a New Client

```python
import sqlite3
conn = sqlite3.connect("/root/Autopilot/backend/jobs.db")
cur = conn.cursor()
cur.execute("""INSERT INTO clients (name, domain, service, location, status, notes, strategy_context)
VALUES (?, ?, ?, ?, 'active', ?, ?)""",
("Client Name", "domain.com", "Primary Service", "City, AZ",
 "Owner notes, phone, ROC, etc.", "Service areas: ... Services: ..."))
conn.commit()
conn.close()
```
