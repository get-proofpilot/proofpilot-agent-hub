"""
Brand Extractor — scrapes a client's website to extract their full design system.

Extracts: color palette, typography, logos, section patterns, component styles,
photography style, navigation, footer, social links, schema data, brand voice.

Uses httpx for fetching + Claude Haiku for intelligent extraction from HTML/CSS.
Cost: ~$0.01-0.02 per extraction. Runs once per client, cached in client_memory.
"""

import json
import logging
import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

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
MAX_CSS_BYTES = 200_000  # 200KB cap for external CSS


# ── Haiku Extraction Prompt ───────────────────────────────────────────────

BRAND_EXTRACTION_PROMPT = """You are an expert brand analyst and web designer. Given a website's HTML source and CSS, extract the COMPLETE visual brand identity.

Analyze everything: CSS custom properties, inline styles, <style> blocks, class names, Google Fonts links, color patterns, component structures, section layouts.

Return ONLY a JSON object with ALL of these fields (use null for anything you can't determine):

{
  "color_palette": {
    "primary": "#hex — the main brand color used in header/logo/nav",
    "secondary": "#hex — second most prominent brand color",
    "accent": "#hex — accent color for buttons/CTAs/highlights",
    "background": "#hex — main page background color",
    "background_alt": "#hex — alternating section background",
    "text": "#hex — primary body text color",
    "text_light": "#hex — secondary/lighter text color",
    "dark": "#hex — darkest color (header/footer bg)"
  },
  "css_custom_properties": {
    "PROPERTY_NAME": "VALUE"
  },
  "typography": {
    "heading_font": "Font Family Name",
    "body_font": "Font Family Name",
    "google_fonts_url": "full Google Fonts <link> URL or null",
    "h1_size": "size with unit",
    "h2_size": "size with unit",
    "h3_size": "size with unit",
    "body_size": "size with unit",
    "heading_weight": "weight number",
    "body_weight": "weight number",
    "body_line_height": "unitless number"
  },
  "section_patterns": [
    {"type": "hero|trust_bar|services|features|process|testimonials|cta|faq|footer", "bg": "color or description", "text_color": "color", "notes": "layout description"}
  ],
  "component_styles": {
    "button_primary": {"bg": "#hex", "text": "#hex", "radius": "Xpx", "padding": "values", "font_weight": "weight"},
    "button_secondary": {"bg": "#hex", "text": "#hex", "radius": "Xpx"},
    "card_style": {"bg": "#hex", "shadow": "CSS shadow value", "radius": "Xpx", "border": "CSS border value"},
    "badge_style": {"bg": "#hex", "text": "#hex", "radius": "Xpx"}
  },
  "cta_patterns": {
    "primary_cta_text": "main CTA button text",
    "secondary_cta_text": "secondary CTA text",
    "phone_prominent": true/false,
    "phone_number": "extracted phone number or null",
    "form_present": true/false
  },
  "photography_style": "2-5 word description of the imagery style (e.g., 'warm, bright, editorial' or 'dark, dramatic, industrial')",
  "brand_voice": "2-3 sentence description of the brand's tone from their copy",
  "value_propositions": ["key claim 1", "key claim 2", "key claim 3"],
  "business_info": {
    "name": "extracted business name",
    "phone": "extracted phone number",
    "address": "extracted address or null",
    "hours": "extracted hours or null",
    "license": "extracted license/certification info or null"
  }
}

Rules:
- For colors: Look at CSS custom properties first (--primary, --accent, --brand, etc.), then header/button background colors, then link colors. Ignore standard grays (#000, #fff, #333, #666, #999, #ccc, #f5f5f5).
- For fonts: Check Google Fonts links, @font-face rules, and font-family declarations. Return the actual font name, not the CSS stack.
- For section patterns: Look at the page structure — how does the hero look? What background colors alternate? Where are the dark/light sections?
- For photography: Describe the image style based on alt text, file names, and surrounding context.
- For brand voice: Read the headline copy, about section, and any taglines. Describe their tone.
- Return ONLY the JSON object. No markdown fences, no explanation."""


# ── Core Extraction Function ──────────────────────────────────────────────

async def extract_brand(domain: str, anthropic_client: anthropic.AsyncAnthropic) -> dict:
    """Extract a complete brand identity from a client's website.

    Args:
        domain: Client domain (e.g., "owlroofing.com")
        anthropic_client: AsyncAnthropic client instance

    Returns:
        Rich brand data dict with color_palette, typography, section_patterns,
        component_styles, photography_style, assets, etc.
    """
    url = _normalize_url(domain)
    logger.info("Starting brand extraction for %s", url)

    # Step 1: Fetch homepage HTML
    homepage_html = await _fetch_page(url)
    if not homepage_html:
        logger.error("Could not fetch homepage for %s", domain)
        return _empty_brand_data()

    # Step 2: Fetch external CSS files
    external_css = await _fetch_external_css(homepage_html, url)

    # Step 3: Fetch interior pages (About, Services) for brand voice + content
    interior_pages = await _fetch_interior_pages(url)

    # Step 4: Extract assets from HTML (logos, images, social links, schema, nav, footer)
    assets = _extract_all_assets(homepage_html, url)

    # Step 5: Send to Haiku for intelligent extraction
    brand_data = await _haiku_extract(
        anthropic_client, homepage_html, external_css, interior_pages
    )

    # Step 6: Merge Haiku output with regex-extracted assets
    brand_data["assets"] = assets

    logger.info(
        "Brand extraction complete for %s: %d colors, %s heading font, %d images found",
        domain,
        len([v for v in brand_data.get("color_palette", {}).values() if v]),
        brand_data.get("typography", {}).get("heading_font", "unknown"),
        len(assets.get("images", {}).get("all", [])),
    )

    return brand_data


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
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


async def _fetch_external_css(html: str, base_url: str) -> str:
    """Fetch external CSS files linked in <head>. Cap at 3 files, 200KB total."""
    css_links = re.findall(
        r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    # Also catch href before rel
    css_links += re.findall(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']stylesheet["\']',
        html, re.IGNORECASE
    )
    # Deduplicate
    seen = set()
    unique_links = []
    for link in css_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    combined_css = []
    total_bytes = 0

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
    ) as client:
        for link in unique_links[:3]:  # Max 3 CSS files
            abs_url = urljoin(base_url, link)
            try:
                resp = await client.get(abs_url)
                resp.raise_for_status()
                css_text = resp.text
                total_bytes += len(css_text.encode())
                if total_bytes > MAX_CSS_BYTES:
                    css_text = css_text[:MAX_CSS_BYTES - (total_bytes - len(css_text.encode()))]
                    combined_css.append(css_text)
                    break
                combined_css.append(css_text)
            except Exception as e:
                logger.debug("Failed to fetch CSS %s: %s", abs_url, e)

    return "\n\n".join(combined_css)


async def _fetch_interior_pages(base_url: str) -> dict[str, str]:
    """Fetch About and Services pages for brand voice extraction."""
    paths_to_try = {
        "about": ["/about", "/about-us", "/our-story", "/our-company", "/who-we-are"],
        "services": ["/services", "/our-services", "/what-we-do"],
    }

    results = {}
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
    ) as client:
        for page_type, paths in paths_to_try.items():
            for path in paths:
                try:
                    resp = await client.get(urljoin(base_url, path))
                    if resp.status_code == 200 and len(resp.text) > 500:
                        # Trim to first 20KB of body
                        body_match = re.search(r'<body[^>]*>(.*)', resp.text, re.DOTALL | re.IGNORECASE)
                        body = body_match.group(1)[:20000] if body_match else resp.text[:20000]
                        results[page_type] = body
                        break
                except Exception:
                    continue

    return results


# ── Asset Extraction (regex-based) ────────────────────────────────────────

def _extract_all_assets(html: str, base_url: str) -> dict:
    """Extract all assets from HTML using regex."""
    return {
        "images": _extract_images(html, base_url),
        "social_links": _extract_social_links(html),
        "schema_data": _extract_schema_data(html),
        "navigation": _extract_nav_structure(html, base_url),
        "footer": _extract_footer_content(html, base_url),
    }


def _extract_images(html: str, base_url: str) -> dict:
    """Extract and categorize all images from HTML."""
    img_pattern = re.compile(
        r'<img\s+[^>]*?src=["\']([^"\']+)["\'][^>]*?(?:alt=["\']([^"\']*)["\'])?[^>]*?>',
        re.IGNORECASE
    )
    # Also catch alt before src
    img_pattern2 = re.compile(
        r'<img\s+[^>]*?alt=["\']([^"\']*)["\'][^>]*?src=["\']([^"\']+)["\'][^>]*?>',
        re.IGNORECASE
    )

    all_images = []

    for match in img_pattern.finditer(html):
        src = urljoin(base_url, match.group(1))
        alt = match.group(2) or ""
        context = _get_image_context(html, match.start())
        all_images.append({"src": src, "alt": alt, "context": context})

    for match in img_pattern2.finditer(html):
        src = urljoin(base_url, match.group(2))
        alt = match.group(1) or ""
        context = _get_image_context(html, match.start())
        if not any(img["src"] == src for img in all_images):
            all_images.append({"src": src, "alt": alt, "context": context})

    # Categorize
    logos = [img for img in all_images if _is_logo(img)]
    heroes = [img for img in all_images if _is_hero(img)]
    portfolio = [img for img in all_images if _is_portfolio(img)]
    team = [img for img in all_images if _is_team(img)]

    return {
        "all": all_images,
        "logos": logos,
        "heroes": heroes,
        "portfolio": portfolio,
        "team": team,
    }


def _get_image_context(html: str, pos: int) -> str:
    """Get surrounding context for an image (parent element classes/IDs)."""
    # Look backward for the nearest opening tag with class or id
    start = max(0, pos - 500)
    chunk = html[start:pos]
    # Find class/id attributes in parent elements
    classes = re.findall(r'class=["\']([^"\']+)["\']', chunk)
    ids = re.findall(r'id=["\']([^"\']+)["\']', chunk)
    return f"classes: {', '.join(classes[-3:])}; ids: {', '.join(ids[-2:])}"


def _is_logo(img: dict) -> bool:
    """Check if an image is likely a logo."""
    indicators = ["logo", "brand", "site-logo", "header-logo", "navbar-brand"]
    text = f"{img['src']} {img['alt']} {img['context']}".lower()
    return any(ind in text for ind in indicators)


def _is_hero(img: dict) -> bool:
    """Check if an image is a hero/banner image."""
    indicators = ["hero", "banner", "header-bg", "jumbotron", "slider", "featured"]
    text = f"{img['src']} {img['alt']} {img['context']}".lower()
    return any(ind in text for ind in indicators)


def _is_portfolio(img: dict) -> bool:
    """Check if an image is a portfolio/project image."""
    indicators = ["portfolio", "project", "gallery", "work", "before", "after", "completed"]
    text = f"{img['src']} {img['alt']} {img['context']}".lower()
    return any(ind in text for ind in indicators)


def _is_team(img: dict) -> bool:
    """Check if an image is a team/staff photo."""
    indicators = ["team", "staff", "about", "owner", "founder", "technician", "crew"]
    text = f"{img['src']} {img['alt']} {img['context']}".lower()
    return any(ind in text for ind in indicators)


def _extract_social_links(html: str) -> dict:
    """Extract social media profile URLs."""
    platforms = {
        "facebook": r'href=["\']([^"\']*facebook\.com/[^"\']+)["\']',
        "instagram": r'href=["\']([^"\']*instagram\.com/[^"\']+)["\']',
        "twitter": r'href=["\']([^"\']*(?:twitter|x)\.com/[^"\']+)["\']',
        "youtube": r'href=["\']([^"\']*youtube\.com/[^"\']+)["\']',
        "linkedin": r'href=["\']([^"\']*linkedin\.com/[^"\']+)["\']',
        "yelp": r'href=["\']([^"\']*yelp\.com/[^"\']+)["\']',
        "google_business": r'href=["\']([^"\']*google\.com/maps[^"\']+)["\']',
        "nextdoor": r'href=["\']([^"\']*nextdoor\.com/[^"\']+)["\']',
        "tiktok": r'href=["\']([^"\']*tiktok\.com/[^"\']+)["\']',
    }
    results = {}
    for platform, pattern in platforms.items():
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            results[platform] = matches[0]
    return results


def _extract_schema_data(html: str) -> list[dict]:
    """Extract Schema.org JSON-LD blocks."""
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


def _extract_nav_structure(html: str, base_url: str) -> list[dict]:
    """Extract navigation menu items."""
    # Try <nav> first
    nav_match = re.search(r'<nav[^>]*>(.*?)</nav>', html, re.DOTALL | re.IGNORECASE)
    nav_html = nav_match.group(1) if nav_match else ""

    # Fallback: look in <header>
    if not nav_html:
        header_match = re.search(r'<header[^>]*>(.*?)</header>', html, re.DOTALL | re.IGNORECASE)
        nav_html = header_match.group(1) if header_match else ""

    if not nav_html:
        return []

    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', nav_html, re.DOTALL | re.IGNORECASE)
    items = []
    for href, text in links:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        if clean_text and len(clean_text) < 50:
            items.append({
                "text": clean_text,
                "href": urljoin(base_url, href),
            })
    return items


def _extract_footer_content(html: str, base_url: str) -> dict:
    """Extract footer content: phone, address, hours, links."""
    footer_match = re.search(r'<footer[^>]*>(.*?)</footer>', html, re.DOTALL | re.IGNORECASE)
    footer_html = footer_match.group(1) if footer_match else ""

    if not footer_html:
        return {}

    # Phone numbers
    phones = re.findall(r'[\(]?\d{3}[\)]?[\s.-]?\d{3}[\s.-]?\d{4}', footer_html)
    # Email
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', footer_html)
    # Links
    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', footer_html, re.DOTALL | re.IGNORECASE)
    footer_links = []
    for href, text in links:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        if clean_text and len(clean_text) < 60:
            footer_links.append({"text": clean_text, "href": urljoin(base_url, href)})

    # Copyright
    copyright_match = re.search(r'(?:©|&copy;|copyright)\s*(\d{4})?[^<]*', footer_html, re.IGNORECASE)
    copyright_text = copyright_match.group(0).strip() if copyright_match else ""

    return {
        "phones": phones[:3],
        "emails": emails[:2],
        "links": footer_links[:20],
        "copyright": copyright_text,
    }


# ── Haiku Extraction ─────────────────────────────────────────────────────

async def _haiku_extract(
    anthropic_client: anthropic.AsyncAnthropic,
    homepage_html: str,
    external_css: str,
    interior_pages: dict[str, str],
) -> dict:
    """Send HTML + CSS to Claude Haiku for intelligent brand extraction."""

    # Build the content to analyze
    # Keep <head> fully + first 30KB of body (same pattern as page_design.py)
    head_match = re.search(r'<head[^>]*>(.*?)</head>', homepage_html, re.DOTALL | re.IGNORECASE)
    head_html = head_match.group(1) if head_match else ""
    body_match = re.search(r'<body[^>]*>(.*)', homepage_html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1)[:30000] if body_match else ""

    content_parts = [
        "## Homepage HTML",
        f"<head>{head_html}</head>",
        f"<body>{body_html}</body>",
    ]

    if external_css:
        content_parts.append(f"\n## External CSS\n{external_css[:100000]}")

    for page_type, page_html in interior_pages.items():
        content_parts.append(f"\n## {page_type.title()} Page (partial)\n{page_html[:15000]}")

    full_content = "\n".join(content_parts)
    # Cap total at 90KB for Haiku context
    if len(full_content) > 90000:
        full_content = full_content[:90000]

    try:
        msg = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": f"Extract the complete brand identity from this website:\n\n{full_content}"
            }],
            system=BRAND_EXTRACTION_PROMPT,
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Haiku returned invalid JSON: %s", e)
        return _empty_brand_data()
    except Exception as e:
        logger.error("Haiku brand extraction failed: %s", e)
        return _empty_brand_data()


def _empty_brand_data() -> dict:
    """Return a minimal brand data structure when extraction fails."""
    return {
        "color_palette": {},
        "css_custom_properties": {},
        "typography": {},
        "section_patterns": [],
        "component_styles": {},
        "cta_patterns": {},
        "photography_style": "",
        "brand_voice": "",
        "value_propositions": [],
        "business_info": {},
        "assets": {
            "images": {"all": [], "logos": [], "heroes": [], "portfolio": [], "team": []},
            "social_links": {},
            "schema_data": [],
            "navigation": [],
            "footer": {},
        },
    }
