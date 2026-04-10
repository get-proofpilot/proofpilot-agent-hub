"""
StrategyPilot Research — gathers site footprint, competitor data, and SERP patterns.

Reuses AuditPilot's data collection patterns but focuses on strategic inputs:
site inventory, competitor page systems, keyword clusters, and SERP features.
"""

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from agents.auditpilot.data_collector import (
    firecrawl_map,
    firecrawl_scrape,
    _normalize_domain,
    _parse_location,
    _build_location_name,
)
from utils.dataforseo import (
    get_domain_ranked_keywords,
    get_domain_rank_overview,
    get_keyword_search_volumes,
    get_bulk_keyword_difficulty,
    get_organic_serp,
    research_competitors,
    build_service_keyword_seeds,
)

logger = logging.getLogger(__name__)


def _build_strategy_keywords(service: str, city: str, state: str) -> list[str]:
    """Build a broader set of keywords for strategy research (20+)."""
    s = service.lower().strip()
    c = city.lower().strip()

    keywords = [
        f"{s} {c}",
        f"{s} {c} {state.lower()}",
        f"best {s} {c}",
        f"{s} near me",
        f"{s} services {c}",
        f"affordable {s} {c}",
        f"emergency {s} {c}",
        f"residential {s} {c}",
        f"commercial {s} {c}",
        f"licensed {s} {c}",
        f"how much does {s} cost {c}",
        f"best {s} in {c}",
        f"{s} reviews {c}",
        f"{s} vs",  # comparison intent
        f"diy vs professional {s}",
        f"how to choose a {s}",
        f"questions to ask a {s}",
        f"{s} cost guide",
        f"signs you need a {s}",
        f"when to call a {s}",
    ]

    return keywords[:20]


async def collect_strategy_data(
    domain: str,
    service: str,
    location: str,
    competitor_domains: list[str] = None,
    on_progress: callable = None,
) -> dict:
    """
    Collect all data needed for a StrategyPilot strategy document.

    Returns structured research data for the engine to feed through
    analysis stages.
    """
    domain = _normalize_domain(domain)
    city, state = _parse_location(location)
    location_name = _build_location_name(city, state)

    result = {
        "domain": domain,
        "service": service,
        "city": city,
        "state": state,
        "location_name": location_name,
        "site_map": [],
        "pages": {},
        "prospect_keywords": [],
        "prospect_overview": {},
        "competitors": [],
        "serp_snapshots": [],
        "keyword_volumes": [],
    }

    async def progress(msg: str):
        if on_progress:
            await on_progress(msg)

    # ── Step 1: Site inventory ──────────────────────────────────────
    await progress("Mapping site pages...")
    urls = await firecrawl_map(domain)
    result["site_map"] = urls
    await progress(f"Found {len(urls)} pages on {domain}")

    # Scrape homepage + key pages for content quality assessment
    pages_to_scrape = [f"https://{domain}"]
    service_urls = [u for u in urls if "/service" in u.lower() or service.lower().replace(" ", "-") in u.lower()]
    location_urls = [u for u in urls if "/location" in u.lower() or city.lower().replace(" ", "-") in u.lower()]
    about_urls = [u for u in urls if "/about" in u.lower()]
    blog_urls = [u for u in urls if "/blog" in u.lower()]

    pages_to_scrape.extend(service_urls[:4])
    pages_to_scrape.extend(location_urls[:3])
    pages_to_scrape.extend(about_urls[:1])
    pages_to_scrape.extend(blog_urls[:2])

    seen = set()
    unique_pages = []
    for p in pages_to_scrape:
        if p not in seen:
            seen.add(p)
            unique_pages.append(p)
    pages_to_scrape = unique_pages[:12]

    await progress(f"Scraping {len(pages_to_scrape)} key pages...")
    for url in pages_to_scrape:
        page_data = await firecrawl_scrape(url, formats=["markdown"])
        if page_data:
            result["pages"][url] = {
                "markdown": page_data.get("markdown", "")[:4000],
                "title": page_data.get("metadata", {}).get("title", ""),
                "description": page_data.get("metadata", {}).get("description", ""),
            }
        await asyncio.sleep(0.5)

    # ── Step 2: Prospect keyword profile ────────────────────────────
    await progress("Pulling keyword profile...")
    try:
        kws = await asyncio.to_thread(
            get_domain_ranked_keywords, domain, location_name
        )
        result["prospect_keywords"] = kws or []
    except Exception as e:
        logger.error(f"Ranked keywords failed: {e}")

    try:
        overview = await asyncio.to_thread(
            get_domain_rank_overview, domain, location_name
        )
        result["prospect_overview"] = overview or {}
    except Exception as e:
        logger.error(f"Domain overview failed: {e}")

    await progress(f"Prospect has {len(result['prospect_keywords'])} ranked keywords")

    # ── Step 3: SERP snapshots for key themes ───────────────────────
    await progress("Checking SERP patterns for key themes...")
    strategy_keywords = _build_strategy_keywords(service, city, state)

    # Get volumes for strategy keywords
    try:
        volumes = await asyncio.to_thread(
            get_keyword_search_volumes, strategy_keywords, location_name
        )
        result["keyword_volumes"] = volumes or []
    except Exception as e:
        logger.error(f"Keyword volumes failed: {e}")

    # SERP snapshots on top 8 keywords
    for kw in strategy_keywords[:8]:
        try:
            serp = await asyncio.to_thread(get_organic_serp, kw, location_name)
            if serp:
                result["serp_snapshots"].append({
                    "keyword": kw,
                    "results": [
                        {
                            "position": i + 1,
                            "domain": _normalize_domain(urlparse(r.get("url", "")).netloc),
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                        }
                        for i, r in enumerate(serp[:10])
                    ]
                })
        except Exception as e:
            logger.error(f"SERP check failed for '{kw}': {e}")
        await asyncio.sleep(0.3)

    # ── Step 4: Competitor analysis ─────────────────────────────────
    await progress("Analyzing competitors...")
    competitor_list = list(competitor_domains or [])

    # Auto-discover from SERP if not enough provided
    if len(competitor_list) < 3:
        serp_domains = set()
        for snap in result["serp_snapshots"]:
            for r in snap.get("results", [])[:5]:
                d = r.get("domain", "")
                if d and d != domain and "." in d:
                    serp_domains.add(d)
        for d in sorted(serp_domains, key=lambda x: sum(
            1 for s in result["serp_snapshots"]
            for r in s.get("results", [])[:5] if r.get("domain") == x
        ), reverse=True):
            if d not in competitor_list:
                competitor_list.append(d)
                if len(competitor_list) >= 5:
                    break

    for comp in competitor_list[:5]:
        comp = _normalize_domain(comp)
        await progress(f"Analyzing competitor: {comp}...")
        try:
            comp_kws = await asyncio.to_thread(
                get_domain_ranked_keywords, comp, location_name
            )
            comp_overview = await asyncio.to_thread(
                get_domain_rank_overview, comp, location_name
            )
            # Also map their pages to understand their page systems
            comp_urls = await firecrawl_map(comp)
            result["competitors"].append({
                "domain": comp,
                "keywords": (comp_kws or [])[:30],
                "overview": comp_overview or {},
                "pages": comp_urls[:50],
                "page_count": len(comp_urls),
            })
        except Exception as e:
            logger.error(f"Competitor analysis failed for {comp}: {e}")
        await asyncio.sleep(0.3)

    await progress("Research complete. Building strategy...")
    return result
