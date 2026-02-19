"""
Prospect SEO Market Analysis Workflow
A sales-focused report for new clients / proposals.

Unlike the Website & SEO Audit (which is for existing clients), this workflow
produces a market opportunity document designed to show a prospect:
  1. Where they stand today vs. top competitors
  2. What revenue they're leaving on the table
  3. Why NOW is the right time to move
  4. What ProofPilot's 90-day plan looks like

Data sources:
  Search Atlas  — prospect's current organic keywords, backlinks, position distribution
  DataForSEO    — top 5 Google Maps + top 5 organic competitors (with SA profiles)

inputs keys:
    domain          e.g. "steadfastplumbingaz.com"
    service         e.g. "plumber"  — used as the Google search keyword
    location        e.g. "Gilbert, AZ"
    monthly_revenue optional — prospect's claimed monthly revenue (for projections)
    avg_job_value   optional — average ticket size (for revenue projection math)
    notes           optional — sales context, pain points, objections heard
"""

import os
import asyncio
import re
import anthropic
from typing import AsyncGenerator

from utils.searchatlas import sa_call
from utils.dataforseo import (
    research_competitors,
    get_competitor_sa_profiles,
    format_full_competitor_section,
    get_keyword_search_volumes,
    build_service_keyword_seeds,
    format_keyword_volumes,
    get_bulk_keyword_difficulty,
    format_keyword_difficulty,
    get_competitor_gmb_profiles,
    format_competitor_gmb_profiles,
)


# ── State abbreviation → full name ───────────────────────────────────────────

_STATE_MAP = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def _build_location_name(location_raw: str) -> str:
    parts = re.split(r"[,\s]+", location_raw.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        city = " ".join(parts[:-1]).title()
        state_input = parts[-1].upper()
        state_full = _STATE_MAP.get(state_input, state_input.title())
        return f"{city},{state_full},United States"
    return location_raw.strip()


# ── Search Atlas data gathering ───────────────────────────────────────────────

async def _gather_sa_data(domain: str) -> dict[str, str]:
    """Fetch Search Atlas data for the prospect's domain."""

    async def safe_call(tool: str, op: str, params: dict, label: str) -> tuple[str, str]:
        try:
            result = await sa_call(tool, op, params)
            return label, result
        except Exception as e:
            return label, f"Data unavailable: {e}"

    tasks = [
        safe_call(
            "Site_Explorer_Organic_Tool", "get_organic_keywords",
            {"project_identifier": domain, "page_size": 20, "ordering": "-traffic"},
            "organic_keywords",
        ),
        safe_call(
            "Site_Explorer_Organic_Tool", "get_organic_competitors",
            {"project_identifier": domain, "page_size": 6},
            "sa_competitors",
        ),
        safe_call(
            "Site_Explorer_Backlinks_Tool", "get_site_referring_domains",
            {"project_identifier": domain, "page_size": 10, "ordering": "-domain_rating"},
            "referring_domains",
        ),
        safe_call(
            "Site_Explorer_Analysis_Tool", "get_position_distribution",
            {"identifier": domain},
            "position_distribution",
        ),
        safe_call(
            "Site_Explorer_Holistic_Audit_Tool", "get_holistic_seo_pillar_scores",
            {"domain": domain},
            "pillar_scores",
        ),
    ]

    results = await asyncio.gather(*tasks)
    return dict(results)


# ── DataForSEO competitor research ───────────────────────────────────────────

async def _gather_competitor_data(service: str, location_name: str) -> dict | None:
    dfs_login = os.environ.get("DATAFORSEO_LOGIN", "")
    dfs_pass = os.environ.get("DATAFORSEO_PASSWORD", "")
    if not dfs_login or not dfs_pass:
        return None

    try:
        keyword = f"{service} {location_name.split(',')[0]}"
        competitors = await research_competitors(
            keyword=keyword,
            location_name=location_name,
            maps_count=5,
            organic_count=5,
        )
        top_domains = competitors.get("all_domains", [])[:5]
        sa_profiles = await get_competitor_sa_profiles(top_domains) if top_domains else []
        competitors["sa_profiles"] = sa_profiles
        return competitors
    except Exception as e:
        return {"error": str(e), "maps": [], "organic": [], "sa_profiles": [], "all_domains": []}


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior SEO strategist at ProofPilot, a results-driven digital marketing agency.

Your job is to write a compelling SEO Market Analysis for a prospective client. This is a SALES document — not a report card. It should make the prospect feel the urgency of acting now, excited about the opportunity, and confident that ProofPilot is the right partner.

## Core objectives
- Show the prospect exactly how much organic search revenue they're missing
- Name their top competitors specifically — make it feel personal and local
- Make the opportunity feel real, urgent, and winnable
- End with a clear 90-day roadmap that feels achievable

## What makes this different from a regular audit
- Frame everything as opportunity, not problems — they're leaving money on the table, not failing
- Revenue language throughout — clicks = calls = revenue, not just rankings
- Competitor names front and center — they know these businesses, make it land
- The close — Section 7 should make them want to sign today

## Tone
- Confident and direct — you know what you're talking about
- Specific — real numbers, real competitor names, real keywords
- Optimistic but honest — show the gap, then show the path
- No agency jargon — talk like a business advisor, not a marketer

## Format (strict markdown)
- # H1 — report title
- ## H2 — section headers
- ### H3 — sub-sections
- **bold** for key metrics, competitor names, dollar figures, action items
- Bullet lists for findings
- Use --- for section dividers
- No tables (clean for .docx conversion)

Do NOT write any preamble or meta-commentary. Start the report immediately with the H1 title."""


# ── Main workflow ─────────────────────────────────────────────────────────────

async def run_prospect_audit(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str,
    client_name: str,
) -> AsyncGenerator[str, None]:
    """
    Yields tokens forming a complete SEO Market Analysis for a prospect.

    inputs keys:
        domain          — prospect's website domain
        service         — primary service type (e.g. "plumber")
        location        — city, state (e.g. "Gilbert, AZ")
        monthly_revenue — optional, claimed monthly revenue
        avg_job_value   — optional, average job/ticket value
        notes           — optional, sales context / pain points heard
    """
    domain = inputs.get("domain", "").strip().lower()
    if not domain:
        yield "Error: No domain provided."
        return

    service         = inputs.get("service", "").strip()
    location        = inputs.get("location", "").strip()
    monthly_revenue = inputs.get("monthly_revenue", "").strip()
    avg_job_value   = inputs.get("avg_job_value", "").strip()
    notes           = inputs.get("notes", "").strip()

    location_name  = _build_location_name(location) if location else ""
    search_keyword = f"{service} {location.split(',')[0].strip()}" if service and location else service

    # ── Phase 1: Status ────────────────────────────────────────────────────
    yield f"> Pulling current SEO data for **{domain}**...\n\n"
    if service and location:
        yield f"> Researching top competitors ranking for **\"{search_keyword}\"**...\n\n"

    # ── Phase 2: Gather all data in parallel ──────────────────────────────
    async def _no_competitor_data():
        return None

    async def _gather_keyword_volumes():
        dfs_login = os.environ.get("DATAFORSEO_LOGIN", "")
        if not dfs_login or not service or not location_name:
            return []
        try:
            city  = location.split(",")[0].strip()
            seeds = build_service_keyword_seeds(service, city, count=10)
            return await get_keyword_search_volumes(seeds, location_name)
        except Exception:
            return []

    sa_task  = _gather_sa_data(domain)
    dfs_task = _gather_competitor_data(service, location_name) if (service and location_name) else _no_competitor_data()
    vol_task = _gather_keyword_volumes()

    sa_data, competitor_data, keyword_volumes = await asyncio.gather(sa_task, dfs_task, vol_task)

    # ── Phase 2b: Secondary enrichment (depends on Phase 2 results) ───────
    yield f"> Fetching keyword difficulty scores...\n\n"
    yield f"> Fetching GBP profiles...\n\n"

    async def _gather_keyword_difficulty():
        dfs_login = os.environ.get("DATAFORSEO_LOGIN", "")
        if not dfs_login or not os.environ.get("DATAFORSEO_PASSWORD") or not location_name:
            return []
        if not keyword_volumes:
            return []
        try:
            # Extract top 8 keywords by search volume
            top_keywords = [kw["keyword"] for kw in keyword_volumes[:8] if kw.get("keyword")]
            if not top_keywords:
                return []
            return await get_bulk_keyword_difficulty(top_keywords, location_name)
        except Exception:
            return []

    async def _gather_gmb_profiles():
        dfs_login = os.environ.get("DATAFORSEO_LOGIN", "")
        if not dfs_login or not os.environ.get("DATAFORSEO_PASSWORD") or not location_name:
            return []
        if not competitor_data or competitor_data.get("error"):
            return []
        try:
            maps_competitors = competitor_data.get("maps", [])
            competitor_names = [c["name"] for c in maps_competitors if c.get("name")]
            if not competitor_names:
                return []
            return await get_competitor_gmb_profiles(competitor_names[:3], location_name)
        except Exception:
            return []

    keyword_difficulty, gmb_profiles = await asyncio.gather(
        _gather_keyword_difficulty(),
        _gather_gmb_profiles(),
    )

    yield f"> Data collected — generating market analysis with Claude Opus...\n\n"
    yield "---\n\n"

    # ── Phase 3: Build context document ───────────────────────────────────
    today = __import__("datetime").date.today().isoformat()

    context_sections = [
        f"## Prospect: {client_name}",
        f"## Domain: {domain}",
        f"## Primary Service: {service or 'Not specified'}",
        f"## Service Area: {location or 'Not specified'}",
        f"## Analysis Date: {today}",
    ]

    if monthly_revenue:
        context_sections.append(f"## Prospect's Claimed Monthly Revenue: {monthly_revenue}")
    if avg_job_value:
        context_sections.append(f"## Average Job Value: {avg_job_value}")

    context_sections += [
        "",
        "---",
        "",
        "## CURRENT ORGANIC KEYWORD RANKINGS (Search Atlas)",
        sa_data["organic_keywords"],
        "",
        "## ORGANIC COMPETITOR OVERLAP — SEARCH ATLAS",
        sa_data["sa_competitors"],
        "",
        "## CURRENT BACKLINK PROFILE (Search Atlas)",
        sa_data["referring_domains"],
    ]

    pos_dist = sa_data.get("position_distribution", "")
    if pos_dist and "Data unavailable" not in pos_dist:
        context_sections += ["", "## POSITION DISTRIBUTION", pos_dist]

    pillar = sa_data.get("pillar_scores", "")
    if pillar and "Data unavailable" not in pillar:
        context_sections += ["", "## SEO PILLAR SCORES (overall health)", pillar]

    # Keyword search volume data (DataForSEO Keywords Data API)
    if keyword_volumes:
        context_sections += [
            "", "## TARGET KEYWORD SEARCH VOLUMES (Google Ads data — use for revenue math)",
            format_keyword_volumes(keyword_volumes),
        ]

    # Keyword difficulty scores (DataForSEO Labs)
    if keyword_difficulty:
        context_sections += [
            "", "## KEYWORD DIFFICULTY SCORES (DataForSEO Labs — 0-100, higher = harder to rank)",
            format_keyword_difficulty(keyword_difficulty),
        ]

    # DataForSEO competitor section
    if competitor_data and not competitor_data.get("error"):
        maps_results    = competitor_data.get("maps", [])
        organic_results = competitor_data.get("organic", [])
        sa_profiles     = competitor_data.get("sa_profiles", [])

        competitor_section = format_full_competitor_section(
            keyword=search_keyword,
            maps=maps_results,
            organic=organic_results,
            sa_profiles=sa_profiles,
        )
        context_sections += ["", "---", "", competitor_section]
    elif competitor_data and competitor_data.get("error"):
        context_sections += [
            "", "## COMPETITOR RESEARCH",
            f"SERP lookup failed: {competitor_data['error']}",
        ]
    else:
        context_sections += [
            "", "## COMPETITOR RESEARCH",
            "DataForSEO not configured — SERP competitor data unavailable.",
        ]

    # GBP competitor profiles (Business Data API)
    if gmb_profiles:
        context_sections += [
            "", "## COMPETITOR GBP PROFILES (Google Business Profile data)",
            format_competitor_gmb_profiles(gmb_profiles),
        ]

    context_doc = "\n".join(context_sections)

    # ── Phase 4: Build Claude prompt ──────────────────────────────────────
    has_competitor_data = bool(
        competitor_data and not competitor_data.get("error") and
        (competitor_data.get("maps") or competitor_data.get("organic"))
    )

    prompt_lines = [
        f"Write a compelling SEO Market Analysis for **{client_name}** ({domain}).",
        f"They are a **{service}** serving **{location}**.",
        "",
        "Here is the live SEO data collected for this prospect and their market:",
        "",
        context_doc,
    ]

    if notes:
        prompt_lines += ["", "**Sales context from the ProofPilot team:**", notes]

    if strategy_context and strategy_context.strip():
        prompt_lines += [
            "", "**Agency strategy direction:**",
            strategy_context.strip(),
        ]

    # Revenue projection guidance
    if avg_job_value:
        prompt_lines += [
            "",
            f"**For revenue projections:** Use an average job value of {avg_job_value}. "
            "Calculate how many additional calls/leads top 3 Google Maps rankings "
            "would generate vs. their current position, and translate to monthly revenue gain.",
        ]
    elif monthly_revenue:
        prompt_lines += [
            "",
            f"**For revenue projections:** The prospect claims {monthly_revenue}/month in revenue. "
            "Show what percentage increase capturing top keyword rankings could produce "
            "based on estimated traffic and conversion rates for their service type.",
        ]

    # Report structure
    report_sections = [
        "1. Executive Summary (3-4 sentences — where they stand today and the size of the opportunity)",
        "2. Your Market: Who's Winning Right Now (name the top Maps and organic competitors explicitly — "
        "rating, review count, estimated traffic, what they're doing right)",
        "3. Where You Stand Today (their current keyword rankings, backlink profile, position distribution — "
        "be honest but frame as gap/opportunity, not failure)",
    ]

    if has_competitor_data:
        report_sections.append(
            "4. The Revenue Gap (specific keywords they should be ranking for but aren't — "
            "translate search volume to estimated calls using local conversion rates, "
            "multiply by job value to get monthly revenue left on the table)"
        )
    else:
        report_sections.append(
            "4. The Revenue Opportunity (keywords they should target based on SA overlap data — "
            "estimate traffic and revenue potential for their service type and location)"
        )

    report_sections += [
        "5. Why This Is Winnable (the market isn't locked up — show specific evidence that "
        "the top competitors have weaknesses or that the prospect has a foundation to build from)",
        "6. ProofPilot's 90-Day Plan (Month 1: quick wins + foundation; "
        "Month 2: authority building; Month 3: ranking push — specific, named actions)",
        "7. What Happens If You Wait (3-4 sentences — frame the cost of inaction in real numbers, "
        "then end with a clear call to action for next steps with ProofPilot)",
    ]

    prompt_lines += [
        "",
        "Write the full market analysis now. Structure it as:",
        *[f"   {s}" for s in report_sections],
        "",
        "Be specific — use the actual competitor names, keyword data, and numbers from the data above. "
        "This document goes directly to the prospect. Make it feel personal, local, and urgent. "
        "Start immediately with the H1 title.",
    ]

    user_prompt = "\n".join(prompt_lines)

    # ── Phase 5: Stream Claude's analysis ────────────────────────────────
    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
