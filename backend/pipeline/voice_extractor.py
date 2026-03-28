"""
Voice Extractor — scrapes a client's website copy and Google reviews to
produce a structured writing voice profile.

Extracts: voice profile summary, tone attributes (formality/technical/warmth/urgency),
vocabulary patterns (use/avoid), sentence structure, sample passages, customer language
from reviews, and primary tagline.

Uses httpx for fetching + Claude Haiku for intelligent voice analysis.
Cost: ~$0.02-0.04 per extraction (Haiku, <4096 output tokens).
Runs once per client, cached in client_memory under brand_voice type.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# ── HTTP Client Config ────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_TIMEOUT = 15.0
MAX_BODY_CHARS = 20_000  # Cap per page to stay within Haiku context


# ── Haiku Voice Analysis Prompt ──────────────────────────────────────────

VOICE_ANALYSIS_PROMPT = """You are an expert copywriter and brand voice analyst. You specialize in deconstructing HOW a company communicates — not just what they say, but their specific linguistic fingerprint.

Given website copy from multiple pages (and optionally Google reviews from their customers), produce a detailed, actionable writing voice profile.

DO NOT return generic observations like "professional and approachable" or "friendly tone." Every company says that. Instead, extract what makes THIS company's voice distinctive:

- Do they use contractions (we're, you'll) or formal full forms (we are, you will)?
- Do they address the reader directly (you, your) or talk about themselves (we, our team)?
- Are sentences short and punchy (<12 words avg) or complex and detailed (20+ words)?
- Do they use industry jargon, or do they explain things in plain language?
- Do they use action verbs and commands ("Call now", "Get your free quote") or softer invitations ("Feel free to reach out")?
- Do they lead with benefits ("Save $500") or credentials ("25 years of experience")?
- Do they use numbers and specifics or vague claims?
- Do they use rhetorical questions?
- What emotional register do they operate in — urgency, reassurance, excitement, authority?
- Do paragraphs tend to be short (1-2 sentences) or long (4+ sentences)?

For customer reviews (if provided), analyze separately:
- What words/phrases do customers repeatedly use to describe this business?
- What emotions do customers express?
- What specific outcomes or experiences do customers highlight?
- What language could be woven back into the company's marketing?

Return ONLY a JSON object with ALL of these fields (use null or empty arrays for anything you can't determine):

{
  "voice_profile": "3-5 sentence description of how this company communicates. Be specific and actionable — a copywriter should be able to read this and write in the client's voice. Include specific examples from the copy.",
  "tone_attributes": {
    "formality": 3,
    "technical_depth": 2,
    "warmth": 4,
    "urgency": 3
  },
  "vocabulary_use": ["exact words and phrases the client actually uses on their site — pull 10-20 of the most distinctive ones, not generic words"],
  "vocabulary_avoid": ["generic AI-sounding words/phrases that would clash with this client's voice — e.g., 'leverage', 'utilize', 'comprehensive solutions', 'cutting-edge', 'delve' — tailor this list to what would feel wrong for THIS brand"],
  "sentence_patterns": {
    "avg_sentence_length": "short (5-10 words) | medium (10-18 words) | long (18+ words)",
    "avg_paragraph_length": "short (1-2 sentences) | medium (3-4 sentences) | long (5+ sentences)",
    "uses_questions": true,
    "uses_second_person": true
  },
  "sample_passages": ["3-5 best excerpts from the website copy that most clearly demonstrate the brand's voice — pull actual text, do not rewrite it"],
  "customer_language": ["recurring phrases, themes, and emotions from Google reviews — pull actual words customers use, not paraphrases"],
  "tagline": "primary tagline or slogan if found on the site, otherwise null"
}

Rules:
- tone_attributes: each is an integer 1-5. 1=very low, 5=very high. For formality: 1=casual/slang, 5=corporate/formal. For technical_depth: 1=plain language, 5=heavy jargon. For warmth: 1=cold/transactional, 5=very warm/personal. For urgency: 1=relaxed/no pressure, 5=high urgency/scarcity.
- vocabulary_use: Pull ACTUAL words and short phrases from the website copy. These should be distinctive to this brand, not generic industry terms everyone uses.
- vocabulary_avoid: Think about what would sound WRONG for this brand. If they're casual, avoid corporate jargon. If they're technical, avoid oversimplified language.
- sample_passages: Copy exact text from the website. Choose passages that best represent the voice. 2-4 sentences each.
- customer_language: If no reviews are provided, return an empty array.
- Return ONLY the JSON object. No markdown fences, no explanation."""


# ── Core Extraction Function ─────────────────────────────────────────────

async def extract_voice(
    domain: str,
    anthropic_client,
    reviews: list[str] | None = None,
) -> dict:
    """Extract a writing voice profile from a client's website and reviews.

    Args:
        domain: Client domain (e.g., "owlroofing.com")
        anthropic_client: AsyncAnthropic client instance
        reviews: Optional list of Google review text strings

    Returns:
        Voice profile dict with voice_profile, tone_attributes,
        vocabulary_use, vocabulary_avoid, sentence_patterns,
        sample_passages, customer_language, tagline.
    """
    url = _normalize_url(domain)
    logger.info("Starting voice extraction for %s", url)

    # Step 1: Fetch homepage HTML
    homepage_html = await _fetch_page(url)
    if not homepage_html:
        logger.error("Could not fetch homepage for %s", domain)
        return _empty_voice_data()

    # Step 2: Discover internal links from homepage for service pages
    internal_links = _discover_internal_links(homepage_html, url)

    # Step 3: Fetch interior pages (about + 2-3 service pages)
    page_texts = await _fetch_content_pages(url, internal_links)

    # Step 4: Extract text content from homepage
    homepage_text = _extract_text_content(homepage_html, url)
    if homepage_text:
        page_texts["homepage"] = homepage_text

    if not page_texts:
        logger.error("No page text extracted for %s", domain)
        return _empty_voice_data()

    # Step 5: Send to Haiku for voice analysis
    voice_data = await _haiku_analyze_voice(
        anthropic_client, page_texts, reviews or []
    )

    logger.info(
        "Voice extraction complete for %s: %d tone attributes, %d vocab words, %d sample passages",
        domain,
        len(voice_data.get("tone_attributes", {})),
        len(voice_data.get("vocabulary_use", [])),
        len(voice_data.get("sample_passages", [])),
    )

    return voice_data


# ── HTTP Fetching ────────────────────────────────────────────────────────

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


def _discover_internal_links(html: str, base_url: str) -> list[str]:
    """Find internal links from the homepage to discover service/content pages.

    Returns up to 10 unique internal URLs, prioritizing service and about pages.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    # Extract all href values from anchor tags
    hrefs = re.findall(r'<a\s+[^>]*href=["\']([^"\'#]+)["\']', html, re.IGNORECASE)

    # Prioritized path fragments for service/about pages
    priority_fragments = [
        "service", "about", "why", "our-", "how-we", "what-we",
        "residential", "commercial", "repair", "install", "maintenance",
    ]

    internal_urls = []
    seen = set()

    for href in hrefs:
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)

        # Must be same domain, not an anchor or asset
        if parsed.netloc != base_domain:
            continue
        if parsed.path in seen or parsed.path == "/" or parsed.path == "":
            continue
        if any(parsed.path.endswith(ext) for ext in [".jpg", ".png", ".pdf", ".css", ".js", ".svg"]):
            continue

        seen.add(parsed.path)
        internal_urls.append(abs_url)

    # Sort: priority pages first, then alphabetical
    def sort_key(url: str) -> tuple:
        path = urlparse(url).path.lower()
        is_priority = any(frag in path for frag in priority_fragments)
        return (0 if is_priority else 1, path)

    internal_urls.sort(key=sort_key)
    return internal_urls[:10]


async def _fetch_content_pages(
    base_url: str,
    discovered_links: list[str],
) -> dict[str, str]:
    """Fetch about page + 2-3 service pages for voice analysis.

    Tries known about paths first, then picks service pages from discovered links.
    Returns a dict of {page_label: extracted_text}.
    """
    about_paths = ["/about", "/about-us", "/our-story", "/our-company", "/who-we-are"]
    results = {}

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=FETCH_TIMEOUT, headers=HEADERS
    ) as client:
        # Try to find an about page
        for path in about_paths:
            try:
                resp = await client.get(urljoin(base_url, path))
                if resp.status_code == 200 and len(resp.text) > 500:
                    text = _extract_text_content(resp.text, urljoin(base_url, path))
                    if text and len(text) > 100:
                        results["about"] = text
                        break
            except Exception:
                continue

        # Fetch 2-3 service/interior pages from discovered links
        service_count = 0
        for link_url in discovered_links:
            if service_count >= 3:
                break
            # Skip if it looks like the about page we already fetched
            path = urlparse(link_url).path.lower()
            if any(ap.lstrip("/") in path for ap in about_paths):
                continue
            # Skip common non-content pages
            if any(skip in path for skip in [
                "contact", "privacy", "terms", "sitemap", "blog",
                "careers", "login", "cart", "checkout", "faq",
            ]):
                continue

            try:
                resp = await client.get(link_url)
                if resp.status_code == 200 and len(resp.text) > 500:
                    text = _extract_text_content(resp.text, link_url)
                    if text and len(text) > 100:
                        label = f"service_page_{service_count + 1}"
                        results[label] = text
                        service_count += 1
            except Exception:
                continue

    return results


# ── Text Extraction ──────────────────────────────────────────────────────

def _extract_text_content(html: str, url: str) -> Optional[str]:
    """Extract meaningful text content from HTML, stripping tags and scripts.

    Returns cleaned text capped at MAX_BODY_CHARS.
    """
    if not html:
        return None

    # Get body content
    body_match = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else html

    # Remove script and style blocks
    body = re.sub(r'<script[^>]*>.*?</script>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<style[^>]*>.*?</style>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', body, flags=re.DOTALL | re.IGNORECASE)

    # Remove nav and footer (we want main content copy, not boilerplate)
    body = re.sub(r'<nav[^>]*>.*?</nav>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<footer[^>]*>.*?</footer>', ' ', body, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', body)

    # Decode HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) < 50:
        return None

    return text[:MAX_BODY_CHARS]


# ── Tagline Extraction (regex pre-pass) ──────────────────────────────────

def _extract_tagline_hint(html: str) -> Optional[str]:
    """Try to extract a tagline from meta tags or hero area.

    This gives Haiku a hint — the model will confirm or override.
    """
    # Check og:title or og:description
    og_match = re.search(
        r'<meta\s+[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not og_match:
        og_match = re.search(
            r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:description["\']',
            html, re.IGNORECASE,
        )

    # Check meta description
    if not og_match:
        og_match = re.search(
            r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if not og_match:
            og_match = re.search(
                r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']',
                html, re.IGNORECASE,
            )

    if og_match:
        candidate = og_match.group(1).strip()
        # Taglines are typically short
        if len(candidate) < 120:
            return candidate

    return None


# ── Haiku Voice Analysis ─────────────────────────────────────────────────

async def _haiku_analyze_voice(
    anthropic_client,
    page_texts: dict[str, str],
    reviews: list[str],
) -> dict:
    """Send website copy + reviews to Claude Haiku for voice analysis."""

    content_parts = []

    for page_label, text in page_texts.items():
        label = page_label.replace("_", " ").title()
        content_parts.append(f"## {label}\n{text}")

    if reviews:
        review_block = "\n\n".join(
            f"Review {i+1}: {r.strip()}" for i, r in enumerate(reviews[:20])
        )
        content_parts.append(f"## Google Reviews ({len(reviews)} total, showing up to 20)\n{review_block}")

    full_content = "\n\n---\n\n".join(content_parts)

    # Cap total at 80KB for Haiku context
    if len(full_content) > 80_000:
        full_content = full_content[:80_000]

    try:
        msg = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": (
                    "Analyze the writing voice of this company based on their website copy"
                    f"{' and customer reviews' if reviews else ''}."
                    " Extract a detailed, actionable voice profile.\n\n"
                    f"{full_content}"
                ),
            }],
            system=VOICE_ANALYSIS_PROMPT,
        )
        raw = msg.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Haiku returned invalid JSON for voice analysis: %s", e)
        return _empty_voice_data()
    except Exception as e:
        logger.error("Haiku voice analysis failed: %s", e)
        return _empty_voice_data()


# ── Fallback Data ────────────────────────────────────────────────────────

def _empty_voice_data() -> dict:
    """Return a minimal voice data structure when extraction fails."""
    return {
        "voice_profile": "",
        "tone_attributes": {
            "formality": None,
            "technical_depth": None,
            "warmth": None,
            "urgency": None,
        },
        "vocabulary_use": [],
        "vocabulary_avoid": [],
        "sentence_patterns": {
            "avg_sentence_length": "",
            "avg_paragraph_length": "",
            "uses_questions": None,
            "uses_second_person": None,
        },
        "sample_passages": [],
        "customer_language": [],
        "tagline": None,
    }
