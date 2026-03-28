"""
Pipeline stage runners — one async generator per stage.

Each stage:
1. Builds its system prompt from skills + previous artifacts + client memory
2. Optionally fetches data from DataForSEO / Search Atlas
3. Calls Claude API with streaming
4. Parses the response into a typed artifact
5. Stores the artifact on the pipeline run

Stage signature:
    async def run_stage(client, run, prev_artifacts, client_memory) -> AsyncGenerator[str, None]
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

import anthropic

from pipeline.artifacts import (
    ResearchArtifact,
    StrategyArtifact,
    ContentArtifact,
    DesignArtifact,
    QAArtifact,
)
from pipeline.skill_loader import build_stage_prompt

logger = logging.getLogger(__name__)


# ── Helper: parse QA revision directives ─────────────────────────────────────

def _parse_revision_directives(review_text: str) -> list[dict]:
    """Parse the ---REVISION_DIRECTIVES--- block from QA review output.

    Returns a list of dicts: [{stage, action, instruction, selector?, property?, value?}]
    """
    directives = []

    # Extract the block between markers
    match = re.search(
        r'---REVISION_DIRECTIVES---\s*\n(.*?)\n---END_DIRECTIVES---',
        review_text, re.DOTALL
    )
    if not match:
        # Fallback: try to parse [COPYWRITE] and [DESIGN] lines anywhere in the text
        lines = review_text.split("\n")
        for line in lines:
            line = line.strip()
            parsed = _parse_directive_line(line)
            if parsed:
                directives.append(parsed)
        return directives

    block = match.group(1)
    for line in block.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_directive_line(line)
        if parsed:
            directives.append(parsed)

    return directives


def _parse_directive_line(line: str) -> dict:
    """Parse a single directive line like '[COPYWRITE] Fix: do something'."""
    # Match [STAGE] Action: instruction
    m = re.match(r'\[(\w+)\]\s*(Fix|Patch):\s*(.+)', line, re.IGNORECASE)
    if not m:
        return {}

    stage = m.group(1).lower()
    action = m.group(2).lower()
    instruction = m.group(3).strip()

    result = {"stage": stage, "action": action, "instruction": instruction}

    # For Patch directives, parse "selector | property | value"
    if action == "patch" and "|" in instruction:
        parts = [p.strip() for p in instruction.split("|")]
        if len(parts) >= 3:
            result["selector"] = parts[0]
            result["property"] = parts[1]
            result["value"] = parts[2]

    return result


# ── Helper: stream Claude and collect full text ─────────────────────────────

async def _stream_claude(
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
    retries: int = 3,
) -> AsyncGenerator[str, None]:
    """Stream Claude response, yielding text chunks. Retries on overloaded."""
    for attempt in range(retries):
        try:
            async with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                thinking={"type": "enabled", "budget_tokens": 5000},
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
            return  # success
        except anthropic.APIStatusError as e:
            if "overloaded" in str(e).lower() and attempt < retries - 1:
                wait = (attempt + 1) * 10
                logger.warning("API overloaded, retrying in %ds (attempt %d/%d)", wait, attempt + 1, retries)
                await asyncio.sleep(wait)
            else:
                raise


# ── RESEARCH Stage ──────────────────────────────────────────────────────────

RESEARCH_BASE_PROMPT = """You are ProofPilot's SEO Research Agent. Your job is to analyze SEO data and produce a comprehensive research report that will guide content creation.

You are the FIRST stage in a multi-agent pipeline. Your output will be consumed by a Strategy Agent (to plan the page structure) and then a Copywriter Agent (to write the content). Be thorough and data-driven.

## Your Output Format
Produce a structured research report with these sections:

### 1. Keyword Analysis
- Primary target keyword with volume, difficulty, and intent
- Secondary keywords (5-10) with volumes
- Long-tail variations
- "People Also Ask" questions

### 2. SERP Analysis
- What currently ranks for the target keyword
- Content formats that dominate (listicles, guides, service pages, etc.)
- Word count ranges of top-ranking pages
- SERP features present (AI Overview, Featured Snippet, Local Pack, PAA)

### 3. Competitor Analysis
- Top 3-5 competitors and their approach
- Content gaps (what they cover that the client doesn't)
- Structural patterns (H2s, sections, CTAs)

### 4. Content Gaps & Opportunities
- Keywords the client should target but doesn't
- AI Overview opportunities
- Local intent signals

### 5. Recommendations
- Recommended page angle/hook
- Must-include sections
- Differentiators to emphasize
- Internal linking opportunities

Ground every recommendation in data. Cite volumes, difficulty scores, and SERP positions."""


async def run_research(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """Research stage: gather SEO data and produce analysis."""
    inputs = run.inputs
    domain = inputs.get("domain", "")
    service = inputs.get("service", "")
    location = inputs.get("location", "")
    keyword = inputs.get("keyword", "")
    competitors_str = inputs.get("competitors", "")

    # Import DataForSEO functions
    dfs_context = ""
    try:
        from utils.dataforseo import (
            get_keyword_search_volumes,
            get_domain_ranked_keywords,
            get_bulk_keyword_difficulty,
            get_ai_search_landscape,
            research_competitors,
            get_backlink_summary,
            build_location_name,
            build_service_keyword_seeds,
            format_keyword_volumes,
            format_keyword_difficulty,
            format_domain_ranked_keywords,
            format_ai_search_landscape,
            format_backlink_summary,
            format_full_competitor_section,
        )

        yield "> Gathering keyword and SERP data from DataForSEO...\n\n"

        location_name = build_location_name(location)
        city = location.split(",")[0].strip() if location else ""

        # Build keyword seeds based on page type
        if keyword:
            seeds = [keyword]
        elif service and city:
            seeds = build_service_keyword_seeds(service, city, 10)
        else:
            seeds = [f"{service} {city}".strip()]

        # Run DataForSEO calls in parallel
        tasks = {}
        if seeds:
            tasks["volumes"] = get_keyword_search_volumes(seeds, location_name)
            tasks["difficulty"] = get_bulk_keyword_difficulty(seeds[:10], location_name)
        if domain:
            tasks["ranked"] = get_domain_ranked_keywords(domain, location_name, limit=20)
            tasks["backlinks"] = get_backlink_summary(domain)
        if seeds[:3]:
            tasks["ai_landscape"] = get_ai_search_landscape(seeds[:3], location_name)

        # Competitor research
        competitors = []
        if competitors_str:
            competitors = [d.strip() for d in competitors_str.replace("\n", ",").split(",") if d.strip()]
        if domain and city:
            tasks["competitors"] = research_competitors(domain, service, city, location_name)

        # Await all in parallel
        results = {}
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except Exception as e:
                logger.warning("DataForSEO call '%s' failed: %s", key, e)
                results[key] = None

        # Format data for Claude
        parts = []
        if results.get("volumes"):
            parts.append(f"## Keyword Volumes\n{format_keyword_volumes(results['volumes'])}")
        if results.get("difficulty"):
            parts.append(f"## Keyword Difficulty\n{format_keyword_difficulty(results['difficulty'])}")
        if results.get("ranked"):
            parts.append(f"## Currently Ranked Keywords\n{format_domain_ranked_keywords(results['ranked'])}")
        if results.get("backlinks"):
            parts.append(f"## Backlink Summary\n{format_backlink_summary(results['backlinks'])}")
        if results.get("ai_landscape"):
            parts.append(f"## AI Search Landscape\n{format_ai_search_landscape(results['ai_landscape'])}")
        if results.get("competitors"):
            parts.append(f"## Competitor Analysis\n{format_full_competitor_section(results['competitors'])}")

        dfs_context = "\n\n".join(parts)
        yield f"> Data collected: {len(parts)} data sections from DataForSEO\n\n"

    except ImportError:
        yield "> DataForSEO not available, proceeding with Claude-only research\n\n"
    except Exception as e:
        logger.warning("DataForSEO data collection failed: %s", e)
        yield f"> Some data collection failed, proceeding with available data\n\n"

    # Build system prompt with skills
    system_prompt = build_stage_prompt(
        stage="research",
        base_prompt=RESEARCH_BASE_PROMPT,
        page_type=run.page_type,
        client_memory=client_memory,
        extra_context=dfs_context,
    )

    # Build user prompt
    user_parts = [f"Research for a **{run.page_type}** for **{run.client_name}**"]
    if domain:
        user_parts.append(f"Domain: {domain}")
    if service:
        user_parts.append(f"Service: {service}")
    if location:
        user_parts.append(f"Location: {location}")
    if keyword:
        user_parts.append(f"Target keyword: {keyword}")
    if competitors_str:
        user_parts.append(f"Competitors: {competitors_str}")
    notes = inputs.get("notes", "")
    if notes:
        user_parts.append(f"Notes: {notes}")

    user_prompt = "\n".join(user_parts)

    # Stream Claude analysis
    full_text = []
    async for chunk in _stream_claude(client, system_prompt, user_prompt):
        full_text.append(chunk)
        yield chunk

    # Build and store the artifact
    analysis = "".join(full_text)
    artifact = ResearchArtifact(
        domain=domain,
        service=service,
        location=location,
        analysis_text=analysis,
    )

    # Populate structured fields from DataForSEO results
    if "volumes" in results and results["volumes"]:
        artifact.keyword_volumes = results["volumes"] if isinstance(results["volumes"], list) else []
    if "difficulty" in results and results["difficulty"]:
        artifact.keyword_difficulty = results["difficulty"] if isinstance(results["difficulty"], list) else []
    if "backlinks" in results and results["backlinks"]:
        artifact.backlink_summary = results["backlinks"] if isinstance(results["backlinks"], dict) else {}

    run.artifacts["research"] = artifact.to_json()


# ── STRATEGY Stage ──────────────────────────────────────────────────────────

STRATEGY_BASE_PROMPT = """You are ProofPilot's Content Strategy Agent. You take SEO research data and produce a detailed content brief that a copywriter will follow exactly.

You are the SECOND stage in a multi-agent pipeline. You receive research data from the Research Agent and produce a content brief for the Copywriter Agent.

## Your Output Format
Produce a structured content brief with:

### Page Specifications
- Page type (service page / location page / blog post)
- Target keyword and secondary keywords
- Search intent classification
- Title tag (under 60 chars, keyword-first)
- Meta description (under 155 chars, includes CTA)
- H1 tag

### Content Structure
For each section of the page:
- Heading text (H2 or H3)
- Purpose of this section
- Word count target
- Key points to cover
- Tone guidance

### SEO Requirements
- Internal linking targets (with anchor text suggestions)
- Schema markup types needed
- FAQ questions (5+ from PAA and research)
- Image alt text suggestions

### Differentiation Strategy
- Angle/hook that makes this page unique vs competitors
- Specific differentiators to emphasize
- CTA strategy (what, where, how many)

### Content Rules
- Total word count target
- Tone and voice guidelines
- Topics to avoid (cannibalization)
- Must-include elements

Be specific and actionable. The copywriter should be able to follow this brief without needing to do additional research."""


async def run_strategy(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """Strategy stage: produce content brief from research."""
    research = prev_artifacts.get("research")
    research_context = research.as_prompt_context() if research else "No research data available."

    system_prompt = build_stage_prompt(
        stage="strategy",
        base_prompt=STRATEGY_BASE_PROMPT,
        page_type=run.page_type,
        client_memory=client_memory,
        extra_context=research_context,
    )

    user_prompt = (
        f"Create a content brief for a **{run.page_type}** for **{run.client_name}**.\n"
        f"Domain: {run.inputs.get('domain', '')}\n"
        f"Service: {run.inputs.get('service', '')}\n"
        f"Location: {run.inputs.get('location', '')}\n"
        f"Target keyword: {run.inputs.get('keyword', '')}\n"
    )

    full_text = []
    async for chunk in _stream_claude(client, system_prompt, user_prompt):
        full_text.append(chunk)
        yield chunk

    brief = "".join(full_text)
    artifact = StrategyArtifact(
        page_type=run.page_type,
        target_keyword=run.inputs.get("keyword", ""),
        brief_text=brief,
    )
    run.artifacts["strategy"] = artifact.to_json()


# ── COPYWRITE Stage ─────────────────────────────────────────────────────────

COPYWRITE_BASE_PROMPT = """You are ProofPilot's Conversion Copywriter — a local SEO specialist who writes pages that rank AND convert.

You are the THIRD stage in a multi-agent pipeline. You receive a detailed content brief from the Strategy Agent and must follow it precisely. Your output is the raw page content in clean markdown.

## Critical Rules
- Follow the content brief structure EXACTLY
- Hit the word count targets for each section
- Include all required SEO elements (keywords, internal links, schema-ready FAQs)
- Write in the client's voice if brand voice data is provided
- NEVER use em dashes, semicolons, or banned AI words
- Every sentence earns its place. No filler.

## Internal Linking (from client memory)
If "Previously Generated Content" entries are in the client memory below, link to those pages naturally within your content. Use descriptive anchor text (not "click here"). Aim for 3-5 internal links per 1000 words. This builds the hub-and-spoke content topology that drives rankings.

If the client memory shows past pages on related topics, mention them:
- Link service pages to related service pages ("We also offer [panel upgrades](/panel-upgrade-chandler-az)")
- Link from blog posts to relevant service pages
- Link location pages to the main service page and nearby location pages

## Output Format
Output ONLY the page content in clean markdown:
- # H1 (first line)
- ## H2 for major sections
- ### H3 for subsections
- **bold** for key claims
- Bullet lists for processes, features, FAQs
- No preamble, no meta-commentary, no explanations

After the main content, output these on separate lines:
---
TITLE_TAG: [your title tag]
META_DESCRIPTION: [your meta description]
SCHEMA_TYPE: [LocalBusiness|FAQPage|Service|Article]
FAQ_JSON: [JSON array of {question, answer} objects]"""


async def run_copywrite(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """Copywrite stage: produce page content from brief."""
    strategy = prev_artifacts.get("strategy")
    research = prev_artifacts.get("research")

    context_parts = []
    if strategy:
        context_parts.append(strategy.as_prompt_context())
    if research:
        context_parts.append(research.as_prompt_context())

    system_prompt = build_stage_prompt(
        stage="copywrite",
        base_prompt=COPYWRITE_BASE_PROMPT,
        page_type=run.page_type,
        client_memory=client_memory,
        extra_context="\n\n".join(context_parts),
    )

    # Check if this is a revision pass
    is_revision = run.revision_round > 0 and run.revision_notes
    previous_content = ""
    if is_revision and content_artifact:
        previous_content = content_artifact.as_prompt_context()

    user_prompt = (
        f"Write the full content for a **{run.page_type}** for **{run.client_name}**.\n"
        f"Follow the content brief above precisely.\n"
        f"Domain: {run.inputs.get('domain', '')}\n"
        f"Service: {run.inputs.get('service', '')}\n"
        f"Location: {run.inputs.get('location', '')}\n"
    )
    differentiators = run.inputs.get("differentiators", "")
    if differentiators:
        user_prompt += f"Differentiators: {differentiators}\n"
    price_range = run.inputs.get("price_range", "")
    if price_range:
        user_prompt += f"Price range: {price_range}\n"

    # Inject revision feedback if this is a revision pass
    if is_revision:
        user_prompt += (
            f"\n## REVISION PASS (Round {run.revision_round})\n"
            f"This is a REVISION of previously generated content. The QA agent found these issues:\n\n"
            f"{run.revision_notes}\n\n"
            f"Fix ALL of the issues listed above. Keep everything else the same — "
            f"only change what the QA feedback specifically calls out.\n"
        )
        if previous_content:
            user_prompt += (
                f"\n## Previous Content (revise this, don't start from scratch)\n"
                f"{previous_content}\n"
            )

    full_text = []
    async for chunk in _stream_claude(client, system_prompt, user_prompt, max_tokens=12000):
        full_text.append(chunk)
        yield chunk

    content = "".join(full_text)

    # Parse metadata from end of content
    title_tag = ""
    meta_desc = ""
    schema_type = ""
    faq_json = []
    markdown = content

    # Extract metadata markers if present
    if "TITLE_TAG:" in content:
        parts = content.split("---")
        if len(parts) >= 2:
            markdown = parts[0].strip()
            meta_section = parts[-1]
            for line in meta_section.strip().split("\n"):
                line = line.strip()
                if line.startswith("TITLE_TAG:"):
                    title_tag = line.split(":", 1)[1].strip()
                elif line.startswith("META_DESCRIPTION:"):
                    meta_desc = line.split(":", 1)[1].strip()
                elif line.startswith("SCHEMA_TYPE:"):
                    schema_type = line.split(":", 1)[1].strip()
                elif line.startswith("FAQ_JSON:"):
                    try:
                        faq_json = json.loads(line.split(":", 1)[1].strip())
                    except json.JSONDecodeError:
                        pass

    word_count = len(markdown.split())
    h1_match = re.search(r'^# (.+)$', markdown, re.MULTILINE)
    h1 = h1_match.group(1) if h1_match else ""

    artifact = ContentArtifact(
        markdown=markdown,
        word_count=word_count,
        title_tag=title_tag,
        meta_description=meta_desc,
        h1=h1,
        schema_json=json.dumps({"@type": schema_type}) if schema_type else "",
        faq_data=faq_json,
    )
    run.artifacts["copywrite"] = artifact.to_json()


# ── DESIGN Stage ────────────────────────────────────────────────────────────

DESIGN_BASE_PROMPT = """You are an elite web page designer at a top agency. You take markdown content and transform it into production-ready HTML/CSS pages that match the client's existing website design system exactly. Every page you build looks like it cost $5,000 to design — polished, layered, and intentional.

You are the FOURTH stage in a multi-agent pipeline. You receive written content from the Copywriter Agent and produce a complete, polished HTML page.

## CRITICAL: Use the Client's Brand, NOT a Default Palette

The "CRITICAL BUILD DIRECTIVES" section in the client context below contains the EXACT logo URL, Google Fonts link, phone number, and nav links you MUST use. Copy them into your HTML exactly as provided.

The "Client Design System" section contains CSS custom properties, colors, typography, and component styles extracted from the client's actual website. Use these values — do NOT invent your own color palette or include generic framework variables (no --bs-*, --wp-*, --elementor-* variables).

## MANDATORY PAGE STRUCTURE

Every page MUST include these structural elements in order:

### 1. Sticky Header (REQUIRED)
```
<header> with:
  - Client's LOGO (from the directives — use their actual logo image URL)
  - Navigation links (from the directives)
  - Phone number + primary CTA button (right side)
  - Sticky on scroll (position: sticky; top: 0; z-index: 1000)
  - Mobile: hamburger menu toggle
```

### 2. Hero Section
- Full-width background image with dark gradient overlay
- **Sizing: `min-height: 600px; padding: 100px 0 80px;`** on desktop — do NOT squish it
- Hero H1 should be large: `font-size: 3.5rem` on desktop, `2.5rem` on mobile
- The hero content area should be full container width (not max-width: 600px) for breathing room
- White/light text with H1 + subheading + CTA buttons
- Phone number as a prominent clickable link
- Use an actual image from the client's site (hero_images in assets) or a data-prompt placeholder

### 3. Content Sections — TWO-COLUMN IMAGE+TEXT LAYOUT
**This is the most important design pattern.** Most home service websites use a two-column split as their primary section layout: text/content on one side, a large image on the other, alternating left/right across the page. DO THIS instead of single-column card grids for most sections.

Layout pattern — alternate text/image sides across the page:
```
Section 1: [TEXT LEFT     |  IMAGE RIGHT]    — white bg
Section 2: [IMAGE LEFT    |  TEXT RIGHT ]    — alt bg (use .reversed class)
Section 3: [TEXT LEFT     |  IMAGE RIGHT]    — white bg
```

**Implementation (match real home service sites):**
```css
.container { max-width: 1350px; margin: 0 auto; padding: 0 2rem; }
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3rem;
  align-items: center;
}
.two-col.reversed { direction: rtl; }
.two-col.reversed > * { direction: ltr; }
.two-col__image {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 30px rgba(0,0,0,0.12);
}
.two-col__image img {
  width: 100%;
  height: auto;
  object-fit: cover;
  aspect-ratio: 4/3;
  display: block;
}
@media (max-width: 768px) {
  .two-col { grid-template-columns: 1fr; }
  .two-col.reversed { direction: ltr; }
}
```

**Section header labels (`.micro` pattern):**
Above every H2, add a small uppercase label in the heading font:
```css
.micro {
  font-family: var(--font-heading);
  font-size: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent);
  margin-bottom: 0.5rem;
  display: block;
  /* IMPORTANT: inherit text-align from parent — don't hardcode left or center */
}
```
**Alignment rule:** The `.micro` label and its H2 must have the SAME alignment. If the section header is centered, the micro is centered. If it's left-aligned (e.g., in a two-col text block), the micro is left-aligned. Never mix alignments within the same header group.

Example: `<span class="micro">Our Process</span><h2>How We Work</h2>`

**Button styling:**
Buttons should use the heading font, uppercase, with the client's exact button styles:
```css
.btn {
  font-family: var(--font-heading);
  text-transform: uppercase;
  font-size: 0.875rem;
  font-weight: 700;
  padding: 14px 24px;
  border-radius: 5px;
  text-decoration: none;
  display: inline-block;
  transition: all 0.3s ease;
  letter-spacing: 0.02em;
}
.btn-primary { background: var(--primary); color: #fff; border: 2px solid var(--primary); }
.btn-primary:hover { background: var(--accent); border-color: var(--accent); color: var(--text); }
.btn-secondary { background: transparent; color: var(--text); border: 2px solid var(--primary); }
.btn-secondary:hover { background: var(--primary); color: #fff; }
```

**When to use card grids vs two-column:**
- **Two-column** (default): narrative sections — "why choose us", "about our process", "our expertise", "about [location]", any section with 1-3 paragraphs of text
- **Card grid**: ONLY for 4+ equal items — trust badges, service types, material comparisons
- **Process steps**: large decorative numbers (4-5rem, 0.3-0.5 opacity) + step title + description, with optional background image on one side
- **Service areas**: pill-style location tags in a flex-wrap grid, NOT long lists:
```css
.location-tags { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.location-tag {
  background: var(--primary); color: #fff;
  padding: 8px 16px; border-radius: 20px;
  font-size: 0.875rem; text-decoration: none;
  transition: background 0.2s;
}
.location-tag:hover { background: var(--accent); }
```

### 4. IMAGE REQUIREMENTS (CRITICAL)
Every content section MUST have imagery. The page should feel photo-heavy like a real agency site.

For each section, add an image using `data-prompt` for AI generation:
```html
<img src="placeholder.jpg"
     data-prompt="Professional photo of [specific scene], natural lighting, no text, no words, no labels, no watermark"
     alt="[descriptive alt text]"
     loading="lazy">
```

Image prompt guidelines:
- Be SPECIFIC: "licensed electrician installing a Generac generator on a concrete pad next to a beige stucco home" not "person working"
- Include the trade: roofer, electrician, plumber in proper gear
- Include the setting: residential home exterior, attic, crawlspace, rooftop
- Include the materials: shingles, tiles, copper pipe, electrical panel
- ALWAYS end with: "no text, no words, no labels, no watermark"
- Use the client's photography style from the brand data

**Minimum images per page: 4** (hero background + at least 3 content images in two-col sections)

### 5. Footer
- Client's darkest brand color background
- Multi-column: Services | Service Areas | Contact | Hours
- Social media icon links (from assets)
- Phone, email, address from business info
- White logo variant if available (check assets for alt/white logo)
- Copyright line

## VISUAL POLISH — What Separates 8/10 from 10/10

This is where most AI-generated pages fail. They get the structure right but look flat and generic. Apply these treatments to EVERY section:

### Card Containers (REQUIRED on all grid items)
Every grid item (trust badges, features, process steps, benefits, materials) MUST be in a styled card:
```css
.card {
  background: var(--background);
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  border: 1px solid rgba(0,0,0,0.06);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
```
On dark backgrounds, use `background: rgba(255,255,255,0.08)` with `border: 1px solid rgba(255,255,255,0.12)`.

### Background Treatments (alternate across sections)
Don't just swap between white and gray. Use these patterns:
- **Subtle gradient**: `background: linear-gradient(180deg, var(--background) 0%, var(--background-alt) 100%)`
- **Accent strip**: A 4px accent-colored border-top on the section
- **Dark feature section**: Use the client's darkest brand color as background with white/light text
- **Accent-tinted section**: The client's accent color at 8-12% opacity as background
- **Textured pattern**: Use a CSS repeating subtle dot or line pattern on at least one section

### Section Heading Accents (REQUIRED)
Every H2 section heading should have a visual accent — pick one per section:
- Colored underline bar: `border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; display: inline-block;`
- Small label above: `<span class="section-label">OUR PROCESS</span>` in accent color, uppercase, letter-spacing: 0.15em, font-size: 0.75rem
- Icon beside heading: relevant Lucide icon inline with the H2

### Visual Rhythm Between Sections
Add at least 2 of these across the page:
- Diagonal divider: `clip-path: polygon(0 0, 100% 4%, 100% 100%, 0 100%)` on a section
- Accent-colored strip: `<div style="height: 4px; background: var(--accent);"></div>` between sections
- Overlapping element: A trust stat bar that overlaps the hero bottom by 40px using negative margin

### Icon Integration (REQUIRED — never use emoji)
Include Lucide icons via CDN:
```html
<script src="https://unpkg.com/lucide@latest"></script>
```
Use: `<i data-lucide="shield-check"></i>` and call `lucide.createIcons()` at page end.

Size icons: 20-24px inline, 32-40px for cards, 48-64px for hero badges.
On dark backgrounds: white icons. On light backgrounds: accent color icons.
Wrap card icons in a tinted circle: `background: rgba(accent, 0.1); border-radius: 50%; padding: 12px;`

### Process/Timeline Steps
Use large decorative numbers (like real agency sites — not small circles):
```css
.process-step { position: relative; padding-left: 100px; margin-bottom: 2.5rem; }
.process-number {
  position: absolute; left: 0; top: -10px;
  font-family: var(--font-heading);
  font-size: 4.5rem; font-weight: 600;
  color: var(--primary); opacity: 0.15;
  line-height: 1;
}
.process-step .micro { color: var(--accent); margin-bottom: 0.25rem; }
.process-step h3 { font-size: 1.25rem; margin-bottom: 0.5rem; }
```
Layout: steps on the LEFT column, large background image on the RIGHT column (two-col pattern).
This matches how real roofing/home service sites display their process.

### CTA Sections
- Use the client's accent color as background
- Large heading, short paragraph, 2 buttons (primary + phone)
- Add a subtle background pattern or radial gradient for depth

### FAQ Accordion (two-column layout)
Use a two-column layout: FAQ questions on the LEFT, section header + "See All FAQs" link on the RIGHT (or header on top if only a few questions).
```css
.faq-item {
  background: var(--background);
  border-radius: 8px;
  margin-bottom: 1rem;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.faq-question {
  width: 100%; padding: 1.25rem 1.5rem;
  background: none; border: none; cursor: pointer;
  display: flex; justify-content: space-between; align-items: center;
  font-family: var(--font-body); font-weight: 600; font-size: 1rem;
  text-align: left; color: var(--text);
}
.faq-answer {
  max-height: 0; overflow: hidden; padding: 0 1.5rem;
  transition: max-height 0.3s ease, padding 0.3s ease;
}
.faq-item.active .faq-answer { max-height: 500px; padding: 0 1.5rem 1.5rem; }
.faq-item.active { border-left: 3px solid var(--accent); }
.faq-icon { transition: transform 0.3s ease; color: var(--accent); }
.faq-item.active .faq-icon { transform: rotate(180deg); }
```
Use Lucide chevron-down icon for the toggle, NOT +/- text.

## ANTI-PATTERNS — DO NOT:
- Include Bootstrap, Tailwind, or any framework CSS variables in your :root
- Use emoji as icons anywhere
- Leave grid items without card containers (no floating text on backgrounds)
- Use the same flat background color on 3+ consecutive sections
- Generate maps as images (use Google Maps iframe)
- Output markdown code fences — output raw HTML only
- Skip the <header> with logo and navigation
- Use display:none for FAQ answers (use max-height transition)
- Include placeholder text like "Lorem ipsum" or "[Your text here]"

## OUTPUT FORMAT
Output ONLY the complete HTML document. Start with `<!DOCTYPE html>`, end with `</html>`.

Include in <head>:
- Google Fonts <link> (from the CRITICAL DIRECTIVES above)
- Lucide icons script
- Schema.org JSON-LD (LocalBusiness + Service + FAQPage)
- Open Graph meta tags
- Canonical URL
- All CSS in a single <style> block — no external stylesheets

At the end of <body>:
```html
<script>
  lucide.createIcons();
  // FAQ accordion
  document.querySelectorAll('.faq-question').forEach(q => {
    q.addEventListener('click', () => {
      const item = q.closest('.faq-item');
      item.classList.toggle('active');
    });
  });
  // Mobile menu toggle
  const menuBtn = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.nav-links');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', () => nav.classList.toggle('open'));
  }
</script>
```

Image placeholders: `<img src="placeholder.jpg" data-prompt="[detailed AI image prompt, include 'no text, no words']" alt="[descriptive]" loading="lazy">`
For service area maps: use Google Maps iframe embed, NOT a generated image."""


async def run_design(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """Design stage: produce HTML/CSS from content."""
    content_artifact = prev_artifacts.get("copywrite")
    strategy = prev_artifacts.get("strategy")

    context_parts = []
    if content_artifact:
        context_parts.append(content_artifact.as_prompt_context())
    if strategy:
        # Pass section guidance from strategy, but let designer choose layouts
        context_parts.append(
            f"## Strategy Brief\n"
            f"Target keyword: {strategy.target_keyword}\n"
            f"Page type: {strategy.page_type}\n\n"
            f"The strategy stage determined WHAT sections this page needs. "
            f"Your job is to decide HOW to lay out each section. Choose the "
            f"best visual format per section based on the content:\n"
            f"- 8+ items → card grid (2x4, 3x3) NOT a vertical list\n"
            f"- 3-4 items → icon cards in a row\n"
            f"- Process/steps → numbered timeline or step cards\n"
            f"- Comparison → side-by-side columns or table\n"
            f"- Long text → two-column with image\n"
            f"- FAQ → accordion\n"
            f"- Testimonials → quote cards\n\n"
            f"Do NOT follow a rigid template. Design each section to best "
            f"serve its specific content."
        )

    # Use brand-formatted memory for the design stage (richer than raw snapshot)
    design_memory = client_memory
    try:
        from pipeline.brand_memory import format_brand_for_design_prompt
        from utils.db import _connect as db_connect
        from memory.store import ClientMemoryStore
        _store = ClientMemoryStore(db_connect)
        brand_block = format_brand_for_design_prompt(_store, run.client_id)
        if brand_block:
            # Prepend brand data to memory so it's prominent in the prompt
            design_memory = brand_block + "\n\n" + client_memory
    except Exception as e:
        logger.warning("Failed to format brand for design prompt: %s", e)

    system_prompt = build_stage_prompt(
        stage="design",
        base_prompt=DESIGN_BASE_PROMPT,
        page_type=run.page_type,
        client_memory=design_memory,
        extra_context="\n\n".join(context_parts),
    )

    # Check if this is a revision pass
    is_revision = run.revision_round > 0 and run.revision_notes
    design_revision_notes = ""
    if is_revision:
        # Extract design-specific directives from revision notes
        design_lines = []
        for line in (run.revision_notes or "").split("\n"):
            line = line.strip()
            if line.startswith("[DESIGN]") or line.startswith("[design]"):
                design_lines.append(line)
        if design_lines:
            design_revision_notes = "\n".join(design_lines)

    user_prompt = (
        f"Design a complete HTML/CSS page for this **{run.page_type}** for **{run.client_name}**.\n"
        f"Transform the markdown content above into a production-ready HTML page.\n"
        f"MUST INCLUDE: sticky header with the client's logo + nav, polished card containers on all grid items, "
        f"varied background treatments across sections, heading accent elements, and a full footer.\n"
        f"Use the EXACT logo URL, Google Fonts link, and phone number from the CRITICAL BUILD DIRECTIVES.\n"
    )

    if design_revision_notes:
        user_prompt += (
            f"\n## DESIGN REVISION (Round {run.revision_round})\n"
            f"The QA agent found these design issues to fix:\n\n"
            f"{design_revision_notes}\n\n"
            f"Address ALL of these issues in your output.\n"
        )

    full_text = []
    async for chunk in _stream_claude(client, system_prompt, user_prompt, max_tokens=16000):
        full_text.append(chunk)
        yield chunk

    html_output = "".join(full_text)

    # Extract HTML from code blocks if Claude wrapped it
    html_match = re.search(r'```html\s*\n(.*?)\n```', html_output, re.DOTALL)
    if html_match:
        html_output = html_match.group(1)

    artifact = DesignArtifact(
        full_page=html_output,
    )
    run.artifacts["design"] = artifact.to_json()


# ── QA Stage ────────────────────────────────────────────────────────────────

QA_BASE_PROMPT = """You are ProofPilot's QA Review Agent. You evaluate the complete page output (content + design + SEO) and produce a quality score with actionable feedback.

You are the FINAL stage in a multi-agent pipeline. You review everything produced by previous agents. Your output will be used by a REVISION LOOP that automatically fixes issues — so your feedback must be specific and actionable.

## Scoring System (100 points total)
Score each category 0-20:

1. **Content Quality (20)**: Writing quality, specificity, no AI tells, brand voice match, word count target met
2. **SEO Optimization (20)**: Keyword usage, heading hierarchy, title/meta, internal links, keyword density
3. **E-E-A-T Signals (20)**: Expertise, experience, authoritativeness, trustworthiness markers
4. **Technical Quality (20)**: HTML validity, schema markup, responsive design, page speed considerations, accessibility
5. **AEO Readiness (20)**: AI citability, FAQ structure, passage-level answers, entity clarity

## Output Format

### Part 1: Human-Readable Review
```
## Quality Score: [TOTAL]/100

### Content Quality: [X]/20
[Findings and issues]

### SEO Optimization: [X]/20
[Findings and issues]

### E-E-A-T Signals: [X]/20
[Findings and issues]

### Technical Quality: [X]/20
[Findings and issues]

### AEO Readiness: [X]/20
[Findings and issues]

## Issues Found
[List each issue with severity: CRITICAL / HIGH / MEDIUM / LOW]

## Verdict
[APPROVED / NEEDS_REVISION]
[Reason for verdict]

## Recommendations
[Ordered list of improvements, most impactful first]
```

### Part 2: Machine-Readable Revision Directives (REQUIRED)

After the human-readable review, output a `REVISION_DIRECTIVES` block. This tells the automated revision system EXACTLY what to fix and which stage should fix it.

```
---REVISION_DIRECTIVES---
[COPYWRITE] Fix: <specific instruction for the copywriter to fix>
[COPYWRITE] Fix: <another copywrite fix>
[DESIGN] Fix: <specific instruction for the designer to fix>
[DESIGN] Patch: <CSS selector> | <property> | <new value>
---END_DIRECTIVES---
```

Rules for directives:
- Prefix each line with `[COPYWRITE]` or `[DESIGN]` to route to the right stage
- `[COPYWRITE] Fix:` — a content/SEO/E-E-A-T/AEO issue the copywriter should address
- `[DESIGN] Fix:` — a structural/layout issue requiring design regeneration
- `[DESIGN] Patch:` — a targeted CSS/HTML fix: `selector | property | value` (for simple fixes like colors, spacing, font-size)
- List CRITICAL issues first, then HIGH, then MEDIUM
- Maximum 10 directives (focus on highest impact)
- Be specific: "Add Schema.org FAQPage JSON-LD with all 5 FAQ questions" not "improve schema"
- For geographic errors: specify exactly what text to replace and with what

Score honestly. Pages scoring below 70 should be marked NEEDS_REVISION."""


async def run_qa(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """QA stage: review and score the complete output."""
    context_parts = []
    for stage_name in ["research", "strategy", "copywrite", "design"]:
        artifact = prev_artifacts.get(stage_name)
        if artifact:
            if hasattr(artifact, "as_prompt_context"):
                context_parts.append(f"## {stage_name.title()} Stage Output\n{artifact.as_prompt_context()}")
            elif hasattr(artifact, "full_page"):
                context_parts.append(f"## Design Output\n```html\n{artifact.full_page[:8000]}\n```")

    system_prompt = build_stage_prompt(
        stage="qa",
        base_prompt=QA_BASE_PROMPT,
        page_type=run.page_type,
        client_memory=client_memory,
        extra_context="\n\n".join(context_parts),
    )

    user_prompt = (
        f"Review and score the complete **{run.page_type}** built for **{run.client_name}**.\n"
        f"Evaluate all previous stage outputs above. Be thorough and honest.\n"
    )

    full_text = []
    async for chunk in _stream_claude(client, system_prompt, user_prompt):
        full_text.append(chunk)
        yield chunk

    review = "".join(full_text)

    # Parse score from review
    score = 0
    score_match = re.search(r'Quality Score:\s*(\d+)/100', review)
    if score_match:
        score = int(score_match.group(1))

    approved = "APPROVED" in review and "NEEDS_REVISION" not in review
    if not score_match:
        approved = False

    # Parse category scores
    cat_scores = {}
    for cat_name, field_name in [
        ("Content Quality", "content_quality_score"),
        ("SEO Optimization", "seo_score"),
        ("E-E-A-T Signals", "eeat_score"),
        ("Technical Quality", "technical_score"),
        ("AEO Readiness", "aeo_score"),
    ]:
        cat_match = re.search(rf'{cat_name}:\s*(\d+)/20', review)
        if cat_match:
            cat_scores[field_name] = int(cat_match.group(1))

    # Parse revision directives
    directives = _parse_revision_directives(review)

    artifact = QAArtifact(
        overall_score=score,
        approved=approved,
        review_text=review,
        revision_directives=directives,
        **cat_scores,
    )
    run.artifacts["qa"] = artifact.to_json()


# ── IMAGE GENERATION Stage ──────────────────────────────────────────────────

async def run_images(
    client: anthropic.AsyncAnthropic,
    run,
    prev_artifacts: dict,
    client_memory: str,
) -> AsyncGenerator[str, None]:
    """Image generation stage: replace placeholders with real Recraft images."""
    from pipeline.image_gen import (
        generate_images_for_page,
        extract_image_slots,
    )

    design = prev_artifacts.get("design")
    if not design or not hasattr(design, "full_page") or not design.full_page:
        yield "> No design artifact found, skipping image generation\n"
        return

    html = design.full_page
    slots = extract_image_slots(html)
    yield f"> Found {len(slots)} image placeholders in HTML\n"

    if not slots:
        yield "> No image placeholders to generate\n"
        run.artifacts["images"] = json.dumps({"html": html, "images": []})
        return

    # Show what we're generating
    for i, slot in enumerate(slots[:8]):
        style_label = slot["style"].replace("_", " ").title()
        yield f">   [{i+1}] {style_label}: {slot['prompt'][:80]}...\n"

    yield f"\n> Generating {min(len(slots), 6)} images via Recraft + OpenRouter...\n\n"

    # Load brand context for image generation
    brand_context = None
    try:
        from pipeline.brand_memory import get_brand_context_for_images
        from utils.db import _connect as db_connect
        from memory.store import ClientMemoryStore
        _store = ClientMemoryStore(db_connect)
        brand_context = get_brand_context_for_images(_store, run.client_id)
        if brand_context and brand_context.get("photography_style"):
            yield f"> Brand photography style: {brand_context['photography_style']}\n"
    except Exception as e:
        logger.warning("Failed to load brand context for images: %s", e)

    # Generate images
    business_name = run.client_name
    location = run.inputs.get("location", "")
    service = run.inputs.get("service", "")

    updated_html, results = await generate_images_for_page(
        html=html,
        business_name=business_name,
        location=location,
        service=service,
        max_images=6,
        brand_context=brand_context,
    )

    # Report results
    success = sum(1 for r in results if r["success"])
    failed = len(results) - success
    yield f"> Image generation complete: {success} generated, {failed} failed\n"

    for r in results:
        status = "done" if r["success"] else "FAILED"
        tool = r.get("tool", r.get("style", "unknown"))
        yield f">   [{status}] {tool}: {r['prompt'][:60]}...\n"
        if r.get("url"):
            yield f">     URL: {r['url'][:80]}...\n"

    # Store updated HTML as the images artifact
    run.artifacts["images"] = json.dumps({
        "html": updated_html,
        "images": results,
    })

    # Also update the design artifact with the image-enriched HTML
    design_data = json.loads(run.artifacts.get("design", "{}"))
    design_data["full_page"] = updated_html
    run.artifacts["design"] = json.dumps(design_data)

    yield f"\n> HTML updated with {success} generated images\n"


# ── Stage Runner Registry ──────────────────────────────────────────────────

STAGE_RUNNERS = {
    "research": run_research,
    "strategy": run_strategy,
    "copywrite": run_copywrite,
    "design": run_design,
    "images": run_images,
    "qa": run_qa,
}
