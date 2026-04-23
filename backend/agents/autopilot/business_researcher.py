"""
Business Intelligence Researcher — builds a structured business profile per client.

Pulls data from Google Business Profile (via DataForSEO), the client's website,
and Google reviews to synthesize a comprehensive business intelligence profile.

Uses httpx for fetching + Claude Haiku for intelligent extraction from raw data.
Cost: ~$0.01-0.03 per research run (DataForSEO + Haiku). Runs once per client.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import anthropic
import httpx

logger = logging.getLogger(__name__)

# ── HTTP Client Config ────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_TIMEOUT = 15.0
MAX_PAGE_BYTES = 30_000  # 30KB cap per page body


# ── Haiku Synthesis Prompt ───────────────────────────────────────────────

BUSINESS_RESEARCH_PROMPT = """You are an expert business intelligence researcher for a digital marketing agency. Given raw data from a business's website, Google Business Profile, and customer reviews, extract a COMPLETE structured business profile.

Your job is to find SPECIFIC, REAL details — not generic observations. Every field should contain information actually found in the data, not assumptions.

Rules:
- For service_catalog: List every service you find mentioned on the site. Include real pricing if mentioned ANYWHERE (service pages, FAQ, footer, schema data). Note what makes each service different from competitors based on how THEY describe it.
- For service_areas: Extract the ACTUAL cities and neighborhoods mentioned on their website and GBP. Don't guess — only list what's explicitly stated.
- For differentiators: Quote or closely paraphrase what the company SAYS makes them different. Include evidence like "mentioned on homepage hero" or "stated in about page" or "highlighted in 15+ reviews".
- For certifications: Look for license numbers, ROC numbers, contractor licenses, BBB ratings, manufacturer certifications, trade association memberships, insurance mentions, bonding.
- For customer_personas: Analyze review language and website copy to identify 2-3 distinct customer types. What words do THEY use? What are THEY worried about?
- For competitive_position: How does this business position itself? Premium? Budget? Fast? Specialized? What do they emphasize vs what competitors emphasize?
- For guarantees: Look for warranty info, satisfaction guarantees, workmanship guarantees, price-match promises.
- For response_time: Look for "same-day", "24/7", "within 1 hour", scheduling promises, emergency availability.
- For payment_methods: Look for financing, credit card logos, payment plan mentions, accepted payment types.
- For review themes: What do customers praise MOST in their reviews? What specific phrases appear repeatedly?

Return ONLY a JSON object with these fields (use null for anything you genuinely cannot determine from the data):

{
  "service_catalog": [
    {"name": "Service Name", "description": "What they say about it", "price_range": "$X-$Y or null", "differentiator": "What makes their version special or null"}
  ],
  "service_areas": {
    "primary_city": "Main city from GBP/website",
    "surrounding_cities": ["City 1", "City 2"],
    "neighborhoods": ["Neighborhood 1", "Neighborhood 2"]
  },
  "differentiators": ["Specific claim with evidence source"],
  "certifications": ["License/cert with number if found"],
  "customer_personas": [
    {"type": "Persona label", "concerns": "What they worry about", "language": "Words/phrases they use in reviews"}
  ],
  "competitive_position": "How they position themselves in the market",
  "guarantees": ["Specific guarantee or warranty found"],
  "response_time": "Stated response/scheduling speed or null",
  "payment_methods": ["Payment method found"],
  "owner_name": "Owner/founder name or null",
  "year_established": "Year or null",
  "license_number": "Contractor license / ROC # or null",
  "review_themes": ["Top praise theme from reviews"],
  "business_name": "Official business name",
  "phone": "Primary phone number or null",
  "email": "Primary email or null"
}

Return ONLY the JSON object. No markdown fences, no explanation."""


# ── Core Research Function ───────────────────────────────────────────────

async def research_business(
    domain: str,
    location: str,
    anthropic_client: anthropic.AsyncAnthropic,
    service: str = "",
) -> dict:
    """Research a business and build a structured intelligence profile.

    Args:
        domain: Client domain (e.g., "allthingzelectric.com")
        location: City + state (e.g., "Chandler, AZ")
        anthropic_client: AsyncAnthropic client instance
        service: Optional service type (e.g., "electrician") for better GBP lookup

    Returns:
        Structured business intelligence dict with service_catalog,
        service_areas, differentiators, certifications, customer_personas,
        competitive_position, guarantees, response_time, payment_methods,
        owner_name, year_established, license_number, and more.
    """
    url = _normalize_url(domain)
    logger.info("Starting business research for %s in %s", domain, location)

    # Step 1: Fetch website pages (homepage, about, services, FAQ)
    website_data = await _fetch_website_pages(url)
    if not website_data:
        logger.warning("Could not fetch any pages for %s", domain)

    # Step 2: Extract schema.org data from homepage
    schema_data = []
    if website_data.get("homepage"):
        schema_data = _extract_schema_data(website_data["homepage"])

    # Step 3: Try DataForSEO for GBP profile + reviews
    gbp_data = await _fetch_gbp_data(domain, service, location)
    review_data = await _fetch_google_reviews(domain, service, location)

    # Step 4: Send everything to Haiku for structured extraction
    profile = await _haiku_synthesize(
        anthropic_client,
        domain=domain,
        location=location,
        website_data=website_data,
        schema_data=schema_data,
        gbp_data=gbp_data,
        review_data=review_data,
    )

    logger.info(
        "Business research complete for %s: %d services, %d differentiators, %d certs",
        domain,
        len(profile.get("service_catalog", [])),
        len(profile.get("differentiators", [])),
        len(profile.get("certifications", [])),
    )

    return profile


# ── HTTP Fetching ─────────────────────────────────────────────────────────

def _normalize_url(domain: str) -> str:
    """Normalize domain to a full URL."""
    domain = domain.strip().lower()
    if domain.startswith("http"):
        return domain
    return f"https://{domain}"


async def _fetch_page(url: str) -> Optional[str]:
    """Fetch a single page's HTML."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


async def _fetch_website_pages(base_url: str) -> dict[str, str]:
    """Fetch homepage + interior pages relevant to business intelligence.

    Returns dict mapping page type to trimmed body HTML.
    """
    # Pages to try, in order of priority per type
    page_paths = {
        "homepage": ["/"],
        "about": ["/about", "/about-us", "/our-story", "/our-company", "/who-we-are"],
        "services": ["/services", "/our-services", "/what-we-do"],
        "faq": ["/faq", "/faqs", "/frequently-asked-questions"],
        "reviews": ["/reviews", "/testimonials", "/customer-reviews"],
        "contact": ["/contact", "/contact-us", "/get-a-quote", "/schedule"],
        "financing": ["/financing", "/payment-options", "/finance"],
        "service_area": ["/service-area", "/service-areas", "/areas-we-serve", "/locations"],
    }

    results = {}

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
    ) as client:
        for page_type, paths in page_paths.items():
            for path in paths:
                try:
                    resp = await client.get(urljoin(base_url, path))
                    if resp.status_code == 200 and len(resp.text) > 500:
                        if page_type == "homepage":
                            # Keep full HTML for schema extraction, trim body for prompt
                            results["homepage_full"] = resp.text
                            body_match = re.search(
                                r'<body[^>]*>(.*)', resp.text, re.DOTALL | re.IGNORECASE
                            )
                            body = body_match.group(1)[:MAX_PAGE_BYTES] if body_match else resp.text[:MAX_PAGE_BYTES]
                            results["homepage"] = body
                        else:
                            body_match = re.search(
                                r'<body[^>]*>(.*)', resp.text, re.DOTALL | re.IGNORECASE
                            )
                            body = body_match.group(1)[:MAX_PAGE_BYTES] if body_match else resp.text[:MAX_PAGE_BYTES]
                            results[page_type] = body
                        break
                except Exception:
                    continue

    # Also try to discover service sub-pages from the services page or nav
    if results.get("homepage"):
        service_links = _discover_service_links(
            results.get("homepage_full", results["homepage"]), base_url
        )
        # Fetch up to 3 discovered service sub-pages
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
        ) as client:
            for i, link in enumerate(service_links[:3]):
                try:
                    resp = await client.get(link)
                    if resp.status_code == 200 and len(resp.text) > 500:
                        body_match = re.search(
                            r'<body[^>]*>(.*)', resp.text, re.DOTALL | re.IGNORECASE
                        )
                        body = body_match.group(1)[:MAX_PAGE_BYTES] if body_match else resp.text[:MAX_PAGE_BYTES]
                        results[f"service_page_{i+1}"] = body
                except Exception:
                    continue

    # Remove the full homepage HTML (only used for schema + link discovery)
    results.pop("homepage_full", None)

    return results


def _discover_service_links(html: str, base_url: str) -> list[str]:
    """Find links to individual service pages from the homepage nav or services section."""
    # Look for links containing service-related path segments
    service_patterns = [
        r'href=["\']([^"\']*(?:/services?/)[^"\']+)["\']',
        r'href=["\']([^"\']*(?:panel-upgrade|rewir|install|repair|replac|maintenance|inspection|troubleshoot|upgrade|emergency)[^"\']*)["\']',
    ]
    found = set()
    for pattern in service_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            href = match.group(1)
            if not href.startswith(("http", "mailto", "tel", "#", "javascript")):
                href = urljoin(base_url, href)
            if href.startswith("http"):
                found.add(href)

    return list(found)


# ── Schema.org Extraction ────────────────────────────────────────────────

def _extract_schema_data(html: str) -> list[dict]:
    """Extract Schema.org JSON-LD blocks from HTML."""
    pattern = re.compile(
        r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE
    )
    schemas = []
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
            schemas.append(data)
        except json.JSONDecodeError:
            continue
    return schemas


# ── DataForSEO Integration ───────────────────────────────────────────────

async def _fetch_gbp_data(domain: str, service: str, location: str) -> Optional[dict]:
    """Fetch Google Business Profile data via DataForSEO.

    Falls back gracefully if DataForSEO is unavailable or the business isn't found.
    """
    try:
        from utils.dataforseo import get_competitor_gmb_profiles
    except ImportError:
        logger.debug("DataForSEO not available, skipping GBP lookup")
        return None

    # Build a search query from domain or service + location
    business_name = _domain_to_business_name(domain)
    location_name = _format_location_name(location)

    if not location_name:
        logger.debug("Could not format location '%s' for DataForSEO", location)
        return None

    try:
        # Search by business name
        profiles = await get_competitor_gmb_profiles(
            [business_name], location_name
        )
        if profiles:
            return profiles[0]

        # Fallback: search by service + business name
        if service:
            profiles = await get_competitor_gmb_profiles(
                [f"{service} {business_name}"], location_name
            )
            if profiles:
                return profiles[0]

        return None

    except Exception as e:
        logger.warning("DataForSEO GBP lookup failed for %s: %s", domain, e)
        return None


async def _fetch_google_reviews(
    domain: str, service: str, location: str
) -> list[dict]:
    """Fetch Google reviews via DataForSEO business_data/google/reviews endpoint.

    Falls back gracefully if DataForSEO is unavailable or no reviews found.
    """
    try:
        from utils.dataforseo import _dfs_post
    except ImportError:
        logger.debug("DataForSEO not available, skipping reviews lookup")
        return []

    business_name = _domain_to_business_name(domain)
    location_name = _format_location_name(location)

    if not location_name:
        return []

    # First, get the place_id from a GMB search (needed for reviews endpoint)
    try:
        from utils.dataforseo import get_competitor_gmb_profiles

        # We need the place_id or the keyword to search reviews
        # Use business_data/google/reviews/search/live with keyword
        search_keyword = f"{business_name} {service}".strip() if service else business_name

        data = await _dfs_post("business_data/google/reviews/search/live", [{
            "keyword": search_keyword,
            "location_name": location_name,
            "language_name": "English",
            "depth": 20,  # up to 20 reviews
        }])

        tasks = data.get("tasks") or []
        reviews = []

        for task in tasks:
            try:
                items = task["result"][0]["items"] or []
            except (KeyError, IndexError, TypeError):
                continue

            for item in items:
                review_text = item.get("review_text") or item.get("snippet") or ""
                rating = None
                rating_obj = item.get("rating") or {}
                if isinstance(rating_obj, dict):
                    rating = rating_obj.get("value")
                elif isinstance(rating_obj, (int, float)):
                    rating = rating_obj

                if review_text:
                    reviews.append({
                        "text": review_text[:500],  # Cap individual review length
                        "rating": rating,
                        "author": item.get("profile_name") or item.get("author") or "",
                        "time": item.get("time_ago") or item.get("timestamp") or "",
                    })

        return reviews[:20]  # Cap at 20 reviews

    except Exception as e:
        logger.debug("DataForSEO reviews lookup failed for %s: %s", domain, e)
        return []


def _domain_to_business_name(domain: str) -> str:
    """Convert domain to a rough business name for GBP search.

    e.g., "allthingzelectric.com" -> "allthingz electric"
         "owlroofing.com" -> "owl roofing"
    """
    # Strip protocol and www
    name = domain.lower().strip()
    if name.startswith("http"):
        from urllib.parse import urlparse
        name = urlparse(name).netloc
    name = name.replace("www.", "").split(".")[0]

    # Insert spaces before common business suffixes
    suffixes = [
        "electric", "plumbing", "roofing", "hvac", "painting", "landscaping",
        "construction", "restoration", "remodeling", "mechanical", "services",
        "solutions", "pros", "experts", "group", "company", "co",
    ]
    for suffix in suffixes:
        if name.endswith(suffix) and name != suffix:
            prefix = name[:-len(suffix)]
            if prefix:
                name = f"{prefix} {suffix}"
                break

    return name


def _format_location_name(location: str) -> str:
    """Convert user-friendly location to DataForSEO format.

    "Chandler, AZ" -> "Chandler,Arizona,United States"
    "Phoenix, Arizona" -> "Phoenix,Arizona,United States"
    """
    STATE_MAP = {
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
        "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    }
    # Reverse map: full name -> full name (for cases where they pass "Arizona")
    STATE_FULL = {v: v for v in STATE_MAP.values()}

    if not location:
        return ""

    parts = [p.strip() for p in location.split(",")]
    if len(parts) < 2:
        # Try splitting on space for "Chandler AZ"
        parts = location.rsplit(" ", 1)
        if len(parts) < 2:
            return ""

    city = parts[0].strip()
    state_raw = parts[1].strip()

    state = STATE_MAP.get(state_raw.upper()) or STATE_FULL.get(state_raw) or ""
    if not state:
        # Maybe they passed the full state name with different casing
        for full_name in STATE_MAP.values():
            if state_raw.lower() == full_name.lower():
                state = full_name
                break

    if not state:
        return ""

    return f"{city},{state},United States"


# ── Haiku Synthesis ──────────────────────────────────────────────────────

async def _haiku_synthesize(
    anthropic_client: anthropic.AsyncAnthropic,
    domain: str,
    location: str,
    website_data: dict[str, str],
    schema_data: list[dict],
    gbp_data: Optional[dict],
    review_data: list[dict],
) -> dict:
    """Send all collected data to Claude Haiku for structured business intelligence extraction."""

    content_parts = [f"## Business: {domain} | Location: {location}\n"]

    # Add website pages
    for page_type, page_html in website_data.items():
        # Strip most HTML tags but keep text content readable
        clean = _strip_html_tags(page_html)
        if clean.strip():
            label = page_type.replace("_", " ").title()
            content_parts.append(f"\n## Website — {label}\n{clean[:15000]}")

    # Add schema.org data
    if schema_data:
        schema_str = json.dumps(schema_data, indent=2, default=str)[:8000]
        content_parts.append(f"\n## Schema.org Structured Data\n{schema_str}")

    # Add GBP data
    if gbp_data:
        content_parts.append("\n## Google Business Profile Data")
        content_parts.append(f"  Name: {gbp_data.get('name', 'N/A')}")
        content_parts.append(f"  Rating: {gbp_data.get('rating', 'N/A')}")
        content_parts.append(f"  Reviews: {gbp_data.get('reviews_count', 'N/A')}")
        content_parts.append(f"  Categories: {gbp_data.get('categories', 'N/A')}")
        content_parts.append(f"  Address: {gbp_data.get('address', 'N/A')}")
        content_parts.append(f"  Phone: {gbp_data.get('phone', 'N/A')}")
        content_parts.append(f"  Website: {gbp_data.get('website', 'N/A')}")
        work_hours = gbp_data.get("work_hours")
        if work_hours:
            content_parts.append(f"  Hours: {json.dumps(work_hours, default=str)[:1000]}")
        attributes = gbp_data.get("attributes")
        if attributes:
            content_parts.append(f"  Attributes: {json.dumps(attributes, default=str)[:500]}")

    # Add review data
    if review_data:
        content_parts.append(f"\n## Google Reviews ({len(review_data)} reviews)")
        for review in review_data:
            rating_str = f"[{review['rating']}*]" if review.get("rating") else ""
            content_parts.append(f"  {rating_str} {review['text'][:300]}")

    full_content = "\n".join(content_parts)
    # Cap total at 90KB for Haiku context
    if len(full_content) > 90000:
        full_content = full_content[:90000]

    try:
        msg = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"Extract the complete business intelligence profile from this data:\n\n{full_content}"
            }],
            system=BUSINESS_RESEARCH_PROMPT,
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw)
        return _normalize_result(result)
    except json.JSONDecodeError as e:
        logger.error("Haiku returned invalid JSON: %s", e)
        return _empty_profile()
    except Exception as e:
        logger.error("Haiku business research failed: %s", e)
        return _empty_profile()


def _strip_html_tags(html: str) -> str:
    """Strip HTML tags but keep readable text content."""
    # Remove script and style blocks entirely
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
    # Replace block-level tags with newlines for readability
    text = re.sub(r'<(?:br|hr|/p|/div|/li|/h[1-6]|/tr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


def _normalize_result(data: dict) -> dict:
    """Ensure all expected keys exist in the result, filling missing ones with defaults."""
    defaults = _empty_profile()
    for key, default_value in defaults.items():
        if key not in data or data[key] is None:
            data[key] = default_value
    return data


def _empty_profile() -> dict:
    """Return a minimal business profile structure when extraction fails."""
    return {
        "service_catalog": [],
        "service_areas": {
            "primary_city": "",
            "surrounding_cities": [],
            "neighborhoods": [],
        },
        "differentiators": [],
        "certifications": [],
        "customer_personas": [],
        "competitive_position": "",
        "guarantees": [],
        "response_time": "",
        "payment_methods": [],
        "owner_name": "",
        "year_established": "",
        "license_number": "",
        "review_themes": [],
        "business_name": "",
        "phone": "",
        "email": "",
    }
