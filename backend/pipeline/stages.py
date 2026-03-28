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

DESIGN_BASE_PROMPT = """You are an elite web page designer. You take markdown content and transform it into production-ready HTML/CSS pages that match the client's existing website design system exactly.

You are the FOURTH stage in a multi-agent pipeline. You receive written content from the Copywriter Agent and produce a complete, polished HTML page.

## CRITICAL: Use the Client's Brand, NOT a Default Palette

The client's design system is provided in the "Client Context (from memory)" section below. You MUST use their exact colors, fonts, spacing, and component patterns. If no client design system is provided, use a clean, professional default.

Look for these memory entries:
- `design_system_css` — CSS custom properties with exact hex colors
- `typography` — font families, sizes, weights for each heading level
- `section_patterns` — how sections alternate (dark/light/gold backgrounds)
- `component_styles` — button styles, card styles, icon treatments
- `page_layout` — the order and structure of page sections

## Design Excellence Requirements

### Layout & Spacing
- Generous section padding (60-80px vertical on desktop, 40-60px mobile)
- Container max-width matching client site
- Clear visual hierarchy with ample whitespace between sections
- Alternating section backgrounds that create visual rhythm
- 2-column layouts for content+image sections on desktop, stacking on mobile

### Visual Treatments
- Full-width hero with background image overlay (dark gradient) and white text
- Trust badge bar spanning full width in the client's accent color
- Service/feature cards with consistent shadows or borders
- Icon treatments: use SVG icons from a CDN (Lucide, Heroicons, or FontAwesome) — NOT emoji
- Process steps with numbered circles or timeline connectors
- FAQ accordion with clean borders and +/- indicators
- CTA sections with strong contrast (client's accent color)

### Icon Integration (REQUIRED — never use emoji)
Include one of these icon CDNs in <head>:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/lucide-static@latest/font/lucide.min.css">
```
Or use inline SVGs from Lucide/Heroicons. Every feature card, trust badge, and bullet point should have a relevant icon.

### Typography
- Load the client's Google Fonts via <link> tag
- Proper heading hierarchy (H1 > H2 > H3) with distinct sizes
- Body text: comfortable line-height (1.6-1.7), readable font-size (16-18px)
- Bold strategic elements, not entire paragraphs

### Mobile Responsiveness
- At least 2 breakpoints: tablet (768px) and mobile (480px)
- Touch-friendly tap targets (min 44px)
- Readable font sizes on mobile (min 16px body)
- Cards stack to single column
- Hero text scales down appropriately

## Output Format
Output a COMPLETE HTML document — no markdown wrappers, no code fences:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>...</title>
    <meta name="description" content="...">
    <meta property="og:title" content="...">
    <meta property="og:description" content="...">
    <meta property="og:type" content="website">
    <link rel="canonical" href="...">
    <!-- Google Fonts -->
    <!-- Icon CDN -->
    <!-- Schema JSON-LD -->
    <style>/* ALL CSS HERE — no external stylesheets */</style>
</head>
<body>...</body>
</html>
```

### Required in every page:
- Schema.org JSON-LD (LocalBusiness + Service + FAQPage)
- Open Graph meta tags
- Canonical URL
- All CSS inline in <style> (no external sheets except fonts/icons)
- Image placeholders: `<img src="placeholder.jpg" data-prompt="[AI image generation prompt]" alt="[descriptive alt]" loading="lazy">`
- Vanilla JS only for FAQ accordion and mobile menu toggle

Do NOT use emoji as icons. Do NOT output markdown — output raw HTML only."""


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

    user_prompt = (
        f"Design a complete HTML/CSS page for this **{run.page_type}** for **{run.client_name}**.\n"
        f"Transform the markdown content above into a production-ready HTML page.\n"
        f"Include all Schema.org JSON-LD, Open Graph tags, and responsive design.\n"
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

You are the FINAL stage in a multi-agent pipeline. You review everything produced by previous agents.

## Scoring System (100 points total)
Score each category 0-20:

1. **Content Quality (20)**: Writing quality, specificity, no AI tells, brand voice match, word count target met
2. **SEO Optimization (20)**: Keyword usage, heading hierarchy, title/meta, internal links, keyword density
3. **E-E-A-T Signals (20)**: Expertise, experience, authoritativeness, trustworthiness markers
4. **Technical Quality (20)**: HTML validity, schema markup, responsive design, page speed considerations, accessibility
5. **AEO Readiness (20)**: AI citability, FAQ structure, passage-level answers, entity clarity

## Output Format
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

    artifact = QAArtifact(
        overall_score=score,
        approved=approved,
        review_text=review,
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

    yield f"\n> Generating {min(len(slots), 6)} images via Recraft API...\n\n"

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
