"""
AuditPilot Engine — multi-stage audit orchestrator with SSE streaming.

Pipeline: COLLECT DATA → ANALYZE SITE → CHECK RANKINGS → STRATEGIC BRAIN → SYNTHESIZE DOCUMENT

Runs sequentially to avoid rate limits. Each stage streams progress tokens
via SSE to the frontend. Final output is a markdown document that gets
converted to branded .docx by the existing docx generator.
"""

import json
import logging
from typing import AsyncGenerator

import anthropic

from agents.auditpilot.data_collector import collect_audit_data
from agents.auditpilot.prompts import (
    SITE_ANALYSIS_SYSTEM,
    RANKING_REALITY_SYSTEM,
    STRATEGIC_BRAIN_SYSTEM,
    SYNTHESIS_SYSTEM,
)

logger = logging.getLogger(__name__)


async def run_audit(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str = "",
    client_name: str = "",
) -> AsyncGenerator[str, None]:
    """
    Run a full AuditPilot audit.

    Yields SSE-ready text tokens that the frontend streams live.
    The final output is a complete markdown audit document.

    inputs:
        domain: str — e.g. "allthingzelectric.com"
        service: str — e.g. "electrician"
        location: str — e.g. "Chandler, AZ"
        prospect_name: str — e.g. "All Thingz Electric"
        competitor_domains: str — comma-separated, optional
        notes: str — optional sales context
    """
    domain = inputs.get("domain", "").strip()
    service = inputs.get("service", "").strip()
    location = inputs.get("location", "").strip()
    prospect_name = inputs.get("prospect_name", client_name or domain)
    competitor_input = inputs.get("competitor_domains", "")
    notes = inputs.get("notes", "")

    if not domain or not service or not location:
        yield "\n\n**Error:** Domain, service, and location are required.\n"
        return

    # Parse competitor domains
    competitor_domains = []
    if competitor_input:
        competitor_domains = [
            d.strip() for d in competitor_input.split(",") if d.strip()
        ]

    # ═══════════════════════════════════════════════════════════════
    # STAGE 1: Data Collection
    # ═══════════════════════════════════════════════════════════════
    yield f"# AuditPilot: {prospect_name}\n\n"
    yield f"**Domain:** {domain}  \n"
    yield f"**Service:** {service}  \n"
    yield f"**Location:** {location}  \n\n"
    yield "---\n\n"
    yield "## Stage 1: Collecting Data\n\n"
    yield "Gathering site inventory, keyword rankings, competitor data, and backlinks. This typically takes 1-2 minutes.\n\n"

    progress_messages = []

    async def on_progress(msg: str):
        progress_messages.append(msg)

    try:
        data = await collect_audit_data(
            domain=domain,
            service=service,
            location=location,
            competitor_domains=competitor_domains,
            on_progress=on_progress,
        )
    except Exception as e:
        yield f"\n**Data collection error:** {e}\n"
        logger.error(f"AuditPilot data collection failed: {e}", exc_info=True)
        return

    # Stream the progress messages that accumulated during collection
    for msg in progress_messages:
        yield f"- {msg}\n"
    yield "\n"

    # Guard: if we got zero pages and zero keywords, the domain may be invalid
    if not data["site_map"] and not data["pages"] and not data.get("keyword_opportunities"):
        yield "**Warning:** Could not retrieve any pages or keyword data for this domain. "
        yield "Check that the domain is correct and the site is publicly accessible.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 2: Site Content Analysis (Claude)
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 2: Analyzing Site Content\n\n"

    # Build page summaries for the prompt (keep under context limits)
    page_summaries = ""
    for url, page_data in list(data["pages"].items())[:8]:
        md_content = page_data.get("markdown", "")[:3000]
        title = page_data.get("title", "")
        page_summaries += f"\n### {url}\nTitle: {title}\n{md_content}\n"

    site_analysis_prompt = f"""Analyze this website for {prospect_name} ({domain}).

Service vertical: {service}
Location: {location}

SITE MAP ({len(data['site_map'])} total pages):
{json.dumps(data['site_map'][:50], indent=2)}

PAGE CONTENT:
{page_summaries}

{f'Additional context: {notes}' if notes else ''}
{f'Client strategy context: {strategy_context}' if strategy_context else ''}

Produce the structured JSON analysis as specified."""

    site_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SITE_ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": site_analysis_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                site_analysis += text
    except Exception as e:
        yield f"\n**Site analysis error:** {e}\n"
        logger.error(f"Site analysis failed: {e}", exc_info=True)
        site_analysis = "{}"

    yield "Site content analysis complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 3: Ranking Reality Analysis (Claude)
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 3: Analyzing Ranking Reality\n\n"

    ranking_prompt = f"""Analyze the ranking reality for {prospect_name} ({domain}).

RANKING CHECK RESULTS:
{json.dumps(data['ranking_check'], indent=2)}

PROSPECT KEYWORD PROFILE ({len(data.get('keyword_opportunities', []))} keywords):
{json.dumps(data.get('keyword_opportunities', [])[:30], indent=2)}

COMPETITOR DATA:
{json.dumps([{
    'domain': c['domain'],
    'overview': c.get('overview', {}),
    'top_keywords': c.get('keywords', [])[:15],
} for c in data['competitors']], indent=2)}

BACKLINKS:
{json.dumps(data.get('backlinks', {}), indent=2)}

Produce the structured JSON analysis as specified."""

    ranking_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=RANKING_REALITY_SYSTEM,
            messages=[{"role": "user", "content": ranking_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                ranking_analysis += text
    except Exception as e:
        yield f"\n**Ranking analysis error:** {e}\n"
        logger.error(f"Ranking analysis failed: {e}", exc_info=True)
        ranking_analysis = "{}"

    yield "Ranking reality analysis complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 4: Strategic Brain Analysis (Claude)
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 4: Strategic Brain Analysis\n\n"

    brain_prompt = f"""Run the 8-dimension strategic analysis for {prospect_name} ({domain}).

SITE ANALYSIS:
{site_analysis[:6000]}

RANKING ANALYSIS:
{ranking_analysis[:6000]}

Service: {service}
Location: {location}

Produce the structured JSON analysis as specified."""

    brain_analysis = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=STRATEGIC_BRAIN_SYSTEM,
            messages=[{"role": "user", "content": brain_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                brain_analysis += text
    except Exception as e:
        yield f"\n**Strategic brain error:** {e}\n"
        logger.error(f"Strategic brain failed: {e}", exc_info=True)
        brain_analysis = "{}"

    yield "Strategic brain analysis complete.\n\n"

    # ═══════════════════════════════════════════════════════════════
    # STAGE 5: Final Document Synthesis (Claude Opus)
    # ═══════════════════════════════════════════════════════════════
    yield "## Stage 5: Generating Audit Document\n\n---\n\n"

    synthesis_prompt = f"""Generate the complete Sales Audit v2 document for {prospect_name}.

PROSPECT INFO:
- Domain: {domain}
- Business Name: {prospect_name}
- Service: {service}
- Location: {location}
- Total pages found: {len(data['site_map'])}
{f'- Sales context: {notes}' if notes else ''}

SITE ANALYSIS:
{site_analysis}

RANKING REALITY:
{ranking_analysis}

STRATEGIC BRAIN:
{brain_analysis}

COMPETITOR DOMAINS ANALYZED: {', '.join(c['domain'] for c in data['competitors'])}

Generate the complete document now. Every section must have specific data and evidence.
Do NOT use placeholder text. Use the actual numbers from the analysis."""

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
        logger.error(f"Synthesis failed: {e}", exc_info=True)
