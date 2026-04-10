"""
StrategyPilot Engine — multi-stage strategy document orchestrator.

Pipeline: RESEARCH → FOOTPRINT ANALYSIS → COMPETITIVE ANALYSIS →
          PAGE SYSTEM DESIGN → ROI MODEL → DOCUMENT SYNTHESIS

Uses Sonnet for analysis stages, Opus for final document synthesis.
"""

import json
import logging
from typing import AsyncGenerator

import anthropic

from agents.strategypilot.research import collect_strategy_data
from agents.strategypilot.prompts import (
    FOOTPRINT_SYSTEM,
    COMPETITIVE_SYSTEM,
    PAGE_SYSTEMS_SYSTEM,
    ROI_SYSTEM,
    SYNTHESIS_SYSTEM,
)

logger = logging.getLogger(__name__)


async def run_strategy(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str = "",
    client_name: str = "",
) -> AsyncGenerator[str, None]:
    """
    Run a full StrategyPilot strategy document generation.

    inputs:
        domain: str
        service: str
        location: str
        business_name: str — optional
        competitor_domains: str — comma-separated, optional
        priorities: str — optional known priorities
        notes: str — optional context
    """
    domain = inputs.get("domain", "").strip()
    service = inputs.get("service", "").strip()
    location = inputs.get("location", "").strip()
    business_name = inputs.get("business_name", client_name or domain)
    competitor_input = inputs.get("competitor_domains", "")
    priorities = inputs.get("priorities", "")
    notes = inputs.get("notes", "")

    if not domain or not service or not location:
        yield "\n\n**Error:** Domain, service, and location are required.\n"
        return

    competitor_domains = [
        d.strip() for d in competitor_input.split(",") if d.strip()
    ] if competitor_input else []

    # ═══════════════════════════════════════════════════════════════
    # STAGE 1: Data Collection
    # ═══════════════════════════════════════════════════════════════
    yield f"# StrategyPilot: {business_name}\n\n"
    yield f"**Domain:** {domain}  \n"
    yield f"**Service:** {service}  \n"
    yield f"**Location:** {location}  \n\n"
    yield "---\n\n"
    yield "## Stage 1: Research & Data Collection\n\n"
    yield "Gathering site inventory, competitor page systems, keyword data, and SERP patterns. This typically takes 1-2 minutes.\n\n"

    progress_messages = []

    async def on_progress(msg: str):
        progress_messages.append(msg)

    try:
        data = await collect_strategy_data(
            domain=domain,
            service=service,
            location=location,
            competitor_domains=competitor_domains,
            on_progress=on_progress,
        )
    except Exception as e:
        yield f"\n**Research error:** {e}\n"
        logger.error(f"StrategyPilot research failed: {e}", exc_info=True)
        return

    for msg in progress_messages:
        yield f"- {msg}\n"
    yield "\n"

    if not data["site_map"] and not data["pages"]:
        yield "**Warning:** Could not retrieve any pages for this domain. "
        yield "Check that the domain is correct and the site is publicly accessible.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 2: Site Footprint Analysis
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 2: Analyzing Site Footprint\n\n"

    page_summaries = ""
    for url, pg in list(data["pages"].items())[:10]:
        page_summaries += f"\n### {url}\nTitle: {pg.get('title','')}\n{pg.get('markdown','')[:2500]}\n"

    footprint_prompt = f"""Analyze the site footprint for {business_name} ({domain}).

Service: {service}
Location: {location}

SITE MAP ({len(data['site_map'])} pages):
{json.dumps(data['site_map'][:60], indent=2)}

PAGE CONTENT:
{page_summaries}

{f'Known priorities: {priorities}' if priorities else ''}
{f'Context: {notes}' if notes else ''}"""

    footprint_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=FOOTPRINT_SYSTEM,
            messages=[{"role": "user", "content": footprint_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                footprint_analysis += text
    except Exception as e:
        yield f"\n**Footprint analysis error:** {e}\n"
        footprint_analysis = "{}"

    yield "Site footprint analysis complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 3: Competitive & SERP Analysis
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 3: Competitive & SERP Analysis\n\n"

    competitive_prompt = f"""Analyze the competitive landscape for {business_name} ({domain}).

PROSPECT KEYWORDS ({len(data.get('prospect_keywords', []))} ranked):
{json.dumps(data.get('prospect_keywords', [])[:25], indent=2)}

PROSPECT OVERVIEW:
{json.dumps(data.get('prospect_overview', {}), indent=2)}

SERP SNAPSHOTS:
{json.dumps(data.get('serp_snapshots', [])[:8], indent=2)}

KEYWORD VOLUMES:
{json.dumps(data.get('keyword_volumes', [])[:20], indent=2)}

COMPETITORS:
{json.dumps([{
    'domain': c['domain'],
    'page_count': c.get('page_count', 0),
    'overview': c.get('overview', {}),
    'top_keywords': c.get('keywords', [])[:15],
    'page_families': _classify_urls(c.get('pages', [])),
} for c in data['competitors']], indent=2)}

Service: {service}
Location: {location}"""

    competitive_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=COMPETITIVE_SYSTEM,
            messages=[{"role": "user", "content": competitive_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                competitive_analysis += text
    except Exception as e:
        yield f"\n**Competitive analysis error:** {e}\n"
        competitive_analysis = "{}"

    yield "Competitive analysis complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 4: Page System Recommendations
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 4: Designing Page Systems\n\n"

    systems_prompt = f"""Design page system recommendations for {business_name} ({domain}).

FOOTPRINT ANALYSIS:
{footprint_analysis[:5000]}

COMPETITIVE ANALYSIS:
{competitive_analysis[:5000]}

KEYWORD DATA:
{json.dumps(data.get('keyword_volumes', [])[:20], indent=2)}

Service: {service}
Location: {location}
{f'Known priorities: {priorities}' if priorities else ''}"""

    systems_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=5000,
            system=PAGE_SYSTEMS_SYSTEM,
            messages=[{"role": "user", "content": systems_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                systems_analysis += text
    except Exception as e:
        yield f"\n**Page systems error:** {e}\n"
        systems_analysis = "{}"

    yield "Page system design complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 5: ROI Model
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 5: Building ROI Model\n\n"

    roi_prompt = f"""Build the revenue and ROI model for {business_name}.

Service: {service}
Location: {location}

KEYWORD VOLUMES:
{json.dumps(data.get('keyword_volumes', [])[:20], indent=2)}

PAGE SYSTEMS RECOMMENDED:
{systems_analysis[:4000]}

COMPETITOR VISIBILITY:
{json.dumps([{
    'domain': c['domain'],
    'overview': c.get('overview', {}),
} for c in data['competitors'][:3]], indent=2)}

{f'Notes: {notes}' if notes else ''}"""

    roi_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=ROI_SYSTEM,
            messages=[{"role": "user", "content": roi_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                roi_analysis += text
    except Exception as e:
        yield f"\n**ROI model error:** {e}\n"
        roi_analysis = "{}"

    yield "ROI model complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 6: Final Document Synthesis (Opus)
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 6: Generating Strategy Document\n\n---\n\n"

    synthesis_prompt = f"""Generate the complete SEO strategy document for {business_name}.

BUSINESS INFO:
- Domain: {domain}
- Business Name: {business_name}
- Service: {service}
- Location: {location}
- Total pages: {len(data['site_map'])}
{f'- Known priorities: {priorities}' if priorities else ''}
{f'- Notes: {notes}' if notes else ''}

SITE FOOTPRINT ANALYSIS:
{footprint_analysis}

COMPETITIVE & SERP ANALYSIS:
{competitive_analysis}

PAGE SYSTEM RECOMMENDATIONS:
{systems_analysis}

ROI MODEL:
{roi_analysis}

COMPETITOR DOMAINS: {', '.join(c['domain'] for c in data['competitors'])}

Generate the complete document now. Every section must use specific data and evidence.
Use clean tables for page maps and recommendations.
Do NOT use placeholder text."""

    try:
        async with client.messages.stream(
            model="claude-opus-4-20250514",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": synthesis_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\n\n**Document generation error:** {e}\n"
        logger.error(f"Strategy synthesis failed: {e}", exc_info=True)


def _classify_urls(urls: list[str]) -> dict:
    """Quick classification of URL list into page families."""
    families = {
        "service": 0, "location": 0, "blog": 0, "about": 0,
        "contact": 0, "gallery": 0, "reviews": 0, "other": 0,
    }
    for url in urls:
        lower = url.lower()
        if "/service" in lower or "/repair" in lower or "/install" in lower:
            families["service"] += 1
        elif "/location" in lower or "/areas" in lower or "/city" in lower:
            families["location"] += 1
        elif "/blog" in lower or "/post" in lower or "/article" in lower:
            families["blog"] += 1
        elif "/about" in lower or "/team" in lower:
            families["about"] += 1
        elif "/contact" in lower:
            families["contact"] += 1
        elif "/gallery" in lower or "/project" in lower or "/portfolio" in lower:
            families["gallery"] += 1
        elif "/review" in lower or "/testimonial" in lower:
            families["reviews"] += 1
        else:
            families["other"] += 1
    return families
