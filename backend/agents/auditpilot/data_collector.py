"""
AuditPilot Data Collector — gathers site crawl, keyword, and competitor data.

Runs sequentially (not parallel) to avoid API rate limits. This is the lesson
learned from the Hermes version where parallel subagents hit 429s and lost data.

Uses existing hub integrations: DataForSEO (utils/dataforseo.py) and
Firecrawl (via httpx since we need rawHtml which MCP doesn't expose).
"""

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import httpx

from utils.dataforseo import (
    get_domain_ranked_keywords,
    get_domain_rank_overview,
    get_keyword_search_volumes,
    get_bulk_keyword_difficulty,
    get_organic_serp,
    get_local_pack,
    research_competitors,
    get_backlink_summary,
    build_service_keyword_seeds,
)

logger = logging.getLogger(__name__)

FIRECRAWL_API_KEY = None  # Set lazily from env

# ── State map (reused from prospect_audit) ──────────────────────────

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


def _parse_location(location_raw: str) -> tuple[str, str]:
    """Return (city, state_abbr) from 'Mesa, AZ' or 'Mesa, Arizona'."""
    parts = re.split(r"[,\s]+", location_raw.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        city = " ".join(parts[:-1]).title()
        state_input = parts[-1].upper()
        if state_input in _STATE_MAP:
            return city, state_input
        # Try reverse lookup
        for abbr, full in _STATE_MAP.items():
            if full.upper() == state_input:
                return city, abbr
        return city, state_input
    return location_raw.strip(), ""


def _build_location_name(city: str, state_abbr: str) -> str:
    """Build DataForSEO location_name."""
    state_full = _STATE_MAP.get(state_abbr, state_abbr)
    return f"{city},{state_full},United States"


def _normalize_domain(domain: str) -> str:
    """Strip protocol, www, trailing slash."""
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.rstrip("/")


# ── Firecrawl helpers ───────────────────────────────────────────────

def _get_firecrawl_key():
    global FIRECRAWL_API_KEY
    if not FIRECRAWL_API_KEY:
        import os
        FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
    return FIRECRAWL_API_KEY


async def firecrawl_map(domain: str) -> list[str]:
    """Get all URLs on a domain via Firecrawl /v1/map."""
    key = _get_firecrawl_key()
    if not key:
        logger.warning("FIRECRAWL_API_KEY not set, skipping site map")
        return []
    # Ensure domain is clean (no protocol) then add https://
    clean = _normalize_domain(domain)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/map",
                headers={"Authorization": f"Bearer {key}"},
                json={"url": f"https://{clean}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("links", [])
        except Exception as e:
            logger.error(f"Firecrawl map failed for {clean}: {e}")
            return []


async def firecrawl_scrape(url: str, formats: list[str] = None) -> dict:
    """Scrape a single page via Firecrawl /v1/scrape."""
    key = _get_firecrawl_key()
    if not key:
        return {}
    if formats is None:
        formats = ["markdown", "rawHtml"]
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {key}"},
                json={"url": url, "formats": formats},
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as e:
            logger.error(f"Firecrawl scrape failed for {url}: {e}")
            return {}


# ── Core keyword builders ───────────────────────────────────────────

def build_audit_keywords(service: str, city: str, state: str) -> list[str]:
    """Build 10 high-intent commercial keywords for ranking reality check."""
    service_lower = service.lower().strip()
    city_lower = city.lower().strip()
    state_lower = state.lower().strip()

    # Base commercial keywords
    keywords = [
        f"{service_lower} {city_lower}",
        f"{service_lower} {city_lower} {state_lower}",
        f"best {service_lower} {city_lower}",
        f"{service_lower} near me",
        f"{service_lower} services {city_lower}",
    ]

    # Industry-specific high-intent keywords
    service_specific = {
        "electrician": ["panel upgrade", "electrical repair", "ev charger installation", "ceiling fan installation", "outlet repair"],
        "plumber": ["drain cleaning", "water heater repair", "sewer line repair", "leak detection", "toilet repair"],
        "hvac": ["ac repair", "furnace repair", "hvac installation", "air conditioning service", "duct cleaning"],
        "roofer": ["roof repair", "roof replacement", "roof inspection", "roofing contractor", "roof leak repair"],
        "pest control": ["exterminator", "termite control", "scorpion control", "rodent control", "bed bug treatment"],
        "painter": ["house painting", "interior painting", "exterior painting", "cabinet painting", "commercial painting"],
        "landscaper": ["landscaping", "lawn care", "hardscape", "sprinkler repair", "tree trimming"],
    }

    # Find matching service type
    for svc_key, specifics in service_specific.items():
        if svc_key in service_lower:
            for s in specifics[:5]:
                keywords.append(f"{s} {city_lower}")
            break
    else:
        # Generic service + city combinations
        keywords.extend([
            f"emergency {service_lower} {city_lower}",
            f"residential {service_lower} {city_lower}",
            f"commercial {service_lower} {city_lower}",
            f"affordable {service_lower} {city_lower}",
            f"licensed {service_lower} {city_lower}",
        ])

    return keywords[:10]


# ── Main data collection orchestrator ───────────────────────────────

async def collect_audit_data(
    domain: str,
    service: str,
    location: str,
    competitor_domains: list[str] = None,
    on_progress: callable = None,
) -> dict:
    """
    Collect all data needed for an AuditPilot audit.

    Returns a dict with keys: site_map, pages, ranking_check,
    competitors, backlinks, keywords.

    on_progress(message) is called with status updates for SSE streaming.
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
        "ranking_check": {},
        "competitors": [],
        "competitor_keywords": {},
        "backlinks": {},
        "keyword_opportunities": [],
    }

    async def progress(msg: str):
        if on_progress:
            await on_progress(msg)

    # ── Step 1: Site crawl (Firecrawl map + key page scrapes) ───────
    await progress("Mapping all pages on the website...")
    urls = await firecrawl_map(domain)
    result["site_map"] = urls
    await progress(f"Found {len(urls)} pages on {domain}")

    # Scrape homepage + up to 8 key pages
    pages_to_scrape = [f"https://{domain}"]
    service_urls = [u for u in urls if "/service" in u.lower() or service.lower().replace(" ", "-") in u.lower()]
    location_urls = [u for u in urls if "/location" in u.lower() or city.lower().replace(" ", "-") in u.lower()]
    about_urls = [u for u in urls if "/about" in u.lower()]

    pages_to_scrape.extend(service_urls[:3])
    pages_to_scrape.extend(location_urls[:2])
    pages_to_scrape.extend(about_urls[:1])
    # Deduplicate while preserving order
    seen = set()
    unique_pages = []
    for p in pages_to_scrape:
        if p not in seen:
            seen.add(p)
            unique_pages.append(p)
    pages_to_scrape = unique_pages[:8]

    await progress(f"Scraping {len(pages_to_scrape)} key pages for content analysis...")
    for url in pages_to_scrape:
        page_data = await firecrawl_scrape(url)
        if page_data:
            result["pages"][url] = {
                "markdown": page_data.get("markdown", ""),
                "html": page_data.get("rawHtml", "")[:15000],  # Cap HTML size
                "title": page_data.get("metadata", {}).get("title", ""),
                "description": page_data.get("metadata", {}).get("description", ""),
            }
        await asyncio.sleep(0.5)  # Rate limit courtesy

    # ── Step 2: Ranking Reality Check (SERP checks on 10 keywords) ──
    await progress("Checking ranking reality across 10 core keywords...")
    audit_keywords = build_audit_keywords(service, city, state)
    ranking_results = []

    for kw in audit_keywords:
        try:
            serp = await asyncio.to_thread(
                get_organic_serp, kw, location_name
            )
            prospect_rank = None
            top_domain = ""
            if serp:
                for i, item in enumerate(serp[:10]):
                    item_domain = _normalize_domain(urlparse(item.get("url", "")).netloc)
                    if i == 0:
                        top_domain = item_domain
                    if domain in item_domain or item_domain in domain:
                        prospect_rank = i + 1
            ranking_results.append({
                "keyword": kw,
                "prospect_rank": prospect_rank,
                "top_domain": top_domain,
            })
        except Exception as e:
            logger.error(f"SERP check failed for '{kw}': {e}")
            ranking_results.append({"keyword": kw, "prospect_rank": None, "top_domain": "error"})
        await asyncio.sleep(0.3)

    # Get keyword volumes for the 10 keywords
    try:
        volumes = await asyncio.to_thread(
            get_keyword_search_volumes, audit_keywords, location_name
        )
        vol_map = {item["keyword"]: item for item in (volumes or [])}
        for r in ranking_results:
            vol_data = vol_map.get(r["keyword"], {})
            r["monthly_volume"] = vol_data.get("search_volume", 0)
            r["cpc"] = vol_data.get("cpc", 0)
    except Exception as e:
        logger.error(f"Keyword volume lookup failed: {e}")

    result["ranking_check"] = {
        "keywords": ranking_results,
        "ranking_count": sum(1 for r in ranking_results if r.get("prospect_rank")),
        "total_checked": len(ranking_results),
    }

    keywords_ranking = result["ranking_check"]["ranking_count"]
    await progress(
        f"Ranking reality: {keywords_ranking}/{len(ranking_results)} core keywords in top 10"
    )

    # ── Step 3: Prospect's ranked keywords (DataForSEO) ─────────────
    await progress("Pulling prospect's full keyword profile...")
    try:
        prospect_keywords = await asyncio.to_thread(
            get_domain_ranked_keywords, domain, location_name
        )
        result["keyword_opportunities"] = prospect_keywords or []
    except Exception as e:
        logger.error(f"Ranked keywords failed for {domain}: {e}")

    # ── Step 4: Competitor discovery + analysis ─────────────────────
    await progress("Discovering and analyzing competitors...")
    competitor_list = list(competitor_domains or [])

    # Auto-discover from SERP results if not enough provided
    if len(competitor_list) < 3:
        serp_domains = set()
        for r in ranking_results:
            d = r.get("top_domain", "")
            if d and d != domain and d != "error" and "." in d:
                serp_domains.add(d)
        for d in sorted(serp_domains):
            if d not in competitor_list:
                competitor_list.append(d)
                if len(competitor_list) >= 5:
                    break

    # Get ranked keywords for each competitor
    for comp_domain in competitor_list[:5]:
        comp_domain = _normalize_domain(comp_domain)
        await progress(f"Analyzing competitor: {comp_domain}...")
        try:
            comp_kws = await asyncio.to_thread(
                get_domain_ranked_keywords, comp_domain, location_name
            )
            comp_overview = await asyncio.to_thread(
                get_domain_rank_overview, comp_domain, location_name
            )
            result["competitors"].append({
                "domain": comp_domain,
                "keywords": comp_kws or [],
                "overview": comp_overview or {},
            })
            result["competitor_keywords"][comp_domain] = comp_kws or []
        except Exception as e:
            logger.error(f"Competitor analysis failed for {comp_domain}: {e}")
        await asyncio.sleep(0.3)

    # ── Step 5: Backlink summary for prospect ───────────────────────
    await progress("Checking backlink profile...")
    try:
        bl = await asyncio.to_thread(get_backlink_summary, domain)
        result["backlinks"] = bl or {}
    except Exception as e:
        logger.error(f"Backlink check failed: {e}")

    await progress("Data collection complete. Running strategic analysis...")
    return result
