"""
Image generation for the page builder pipeline.

Two-tool strategy based on head-to-head testing (March 2026):

RECRAFT (realistic photography):
- Hero/banner photos (realistic camera-quality output)
- Service action shots (close-ups of work being performed)
- Team/trust portraits (real-looking people, editorial style)
- Before/after photos
- Architectural/property shots
Best for: anything that should look like it came from a real camera

NANO BANANA (text, infographics, composited/edited):
- Infographics & comparison charts (can render accurate readable text)
- Educational visuals, data displays, process diagrams
- Anything with text labels, pricing, specs, or annotations
- Composited/edited-looking images, styled backgrounds
- Marketing collateral style images
Best for: anything that needs readable text or a designed/edited look

Routing: classify each image slot, route to the right tool.
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RECRAFT_API_URL = "https://external.api.recraft.ai/v1/images/generations"
RECRAFT_API_KEY = os.environ.get("RECRAFT_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/images/generations"

# Default model for image generation via OpenRouter
# google/imagen-4 is strong for text-in-image and composited visuals
OPENROUTER_IMAGE_MODEL = os.environ.get("OPENROUTER_IMAGE_MODEL", "google/imagen-4")


# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Token-bucket rate limiter: prevents runaway credit spend on OpenRouter.
# Defaults: 10 requests per 60-second window (safe for pipeline batches of 6-8 images).

class _RateLimiter:
    """Simple token-bucket rate limiter for API calls."""

    def __init__(self, max_calls: int = 10, window_seconds: float = 60.0):
        self._max = max_calls
        self._window = window_seconds
        self._timestamps: list[float] = []

    def _prune(self):
        cutoff = time.monotonic() - self._window
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    async def acquire(self) -> bool:
        """Wait until a slot is available. Returns True when ready."""
        while True:
            self._prune()
            if len(self._timestamps) < self._max:
                self._timestamps.append(time.monotonic())
                return True
            # Wait until oldest token expires
            wait = self._timestamps[0] + self._window - time.monotonic()
            if wait > 0:
                logger.info("OpenRouter rate limiter: waiting %.1fs", wait)
                await asyncio.sleep(min(wait + 0.1, 10.0))


_openrouter_limiter = _RateLimiter(
    max_calls=int(os.environ.get("OPENROUTER_RATE_LIMIT", "10")),
    window_seconds=float(os.environ.get("OPENROUTER_RATE_WINDOW", "60")),
)

# ── Image Type Classification ──────────────────────────────────────────────
#
# RECRAFT realistic — anything that should look like a real camera photo:
#   People (homeowners, families, technicians, consultations)
#   Work scenes (installation, repair, service calls)
#   Architecture (homes, buildings, job sites, neighborhoods)
#   Before/after shots
#   Lifestyle scenes (family in home, homeowner greeting tech)
#
# NANO BANANA — anything that needs readable text, real brands, or designed look:
#   Branded equipment (Generac, Square D, Carrier with visible logos)
#   Infographics, comparison charts, data visuals
#   Truck wraps, branded uniforms, marketing collateral
#   Process diagrams, educational visuals
#
# RECRAFT vector — clean graphic elements:
#   Icons, badges, abstract symbols

# Recraft realistic: people, lifestyle, work scenes, architecture
RECRAFT_PEOPLE_KEYWORDS = [
    "homeowner", "family", "couple", "customer", "client", "person", "people",
    "woman", "man", "child", "kid", "resident", "neighbor",
    "greeting", "handshake", "conversation", "consultation", "meeting",
    "smiling", "happy", "satisfied", "portrait", "headshot",
]
RECRAFT_WORK_KEYWORDS = [
    "installing", "repairing", "working", "servicing", "inspecting",
    "wiring", "connecting", "mounting", "testing", "measuring",
    "technician at", "electrician at", "plumber at", "hvac tech",
    "crawl space", "attic", "utility room", "garage", "job site",
    "before and after", "before after", "completed project",
]
RECRAFT_ARCHITECTURE_KEYWORDS = [
    "home exterior", "house", "building", "property", "neighborhood",
    "driveway", "backyard", "front yard", "curb appeal",
    "modern home", "residential", "commercial building",
    "aerial", "drone shot", "street view",
]
HERO_KEYWORDS = ["hero", "banner", "header", "main", "featured", "background"]

# Nano Banana: text, brands, infographics, designed visuals
INFOGRAPHIC_KEYWORDS = [
    "infographic", "diagram", "chart", "comparison", "process", "flow",
    "data", "stats", "pricing", "cost", "specs", "timeline",
    "step by step", "how it works", "checklist",
]
TEXT_KEYWORDS = [
    "text", "label", "price", "cost", "comparison", "infographic", "chart",
    "specs", "features", "pros", "cons", "vs", "versus",
    "table", "matrix", "scorecard", "rating",
]
BRAND_KEYWORDS = [
    # Generators
    "generac", "kohler generator", "briggs", "cummins", "champion generator",
    # Electrical panels / equipment
    "square d", "siemens panel", "eaton", "cutler-hammer", "leviton",
    # HVAC
    "carrier", "trane", "lennox", "goodman", "rheem", "daikin", "mitsubishi",
    # Plumbing
    "bradford white", "ao smith", "moen", "delta faucet",
    # Branded visuals
    "logo", "branded", "truck wrap", "vehicle wrap", "product shot",
    "company van", "wrapped truck", "fleet", "branded uniform",
]

# Recraft vector
ICON_KEYWORDS = ["icon", "badge", "symbol", "vector", "line art"]


def classify_image_slot(prompt: str, alt: str = "", slot: str = "") -> str:
    """Classify an image placeholder to determine generation tool + style.

    Returns: 'recraft_realistic' | 'recraft_vector' | 'nano_banana'

    Routing priority:
    1. Branded products/logos → Nano Banana (renders real brands accurately)
    2. Text/infographics/data → Nano Banana (can do readable text)
    3. Icons/badges/vectors → Recraft vector
    4. People/lifestyle/work/architecture → Recraft realistic (best at real-looking people)
    5. Default → Recraft realistic
    """
    text = f"{prompt} {alt} {slot}".lower()

    # ── Nano Banana territory ──
    # Real brand names, logos, product shots, truck wraps
    if any(kw in text for kw in BRAND_KEYWORDS):
        return "nano_banana"
    # Anything with text, infographics, comparisons, data visuals
    if any(kw in text for kw in TEXT_KEYWORDS):
        return "nano_banana"
    if any(kw in text for kw in INFOGRAPHIC_KEYWORDS):
        return "nano_banana"

    # ── Recraft vector territory ──
    if any(kw in text for kw in ICON_KEYWORDS):
        return "recraft_vector"

    # ── Recraft realistic territory ──
    # People, lifestyle, human interaction scenes
    # (Recraft excels at realistic human faces, body language, natural poses)
    # This covers: homeowners, families, consultations, handshakes,
    # technicians working, team portraits, before/after
    return "recraft_realistic"


def get_recraft_substyle(style: str, context: str = "") -> Optional[str]:
    """Select the best Recraft substyle based on context."""
    context_lower = context.lower()
    if style == "realistic_image":
        if "evening" in context_lower or "sunset" in context_lower:
            return "evening_light"
        if "portrait" in context_lower or "team" in context_lower:
            return "natural_light"
        return "natural_light"  # Best for home service photos
    if style == "digital_illustration":
        if "infographic" in context_lower:
            return "graphic_intensity"
        return "modern_folk"
    if style == "vector_illustration":
        return "bold_stroke"
    return None


def get_image_size(style: str, slot: str = "") -> str:
    """Select appropriate image size based on usage."""
    slot_lower = slot.lower()
    if any(kw in slot_lower for kw in HERO_KEYWORDS):
        return "1820x1024"  # Wide hero
    if any(kw in slot_lower for kw in ["card", "thumb", "grid"]):
        return "1024x1024"  # Square for cards
    if style == "vector_illustration":
        return "1024x1024"
    return "1365x1024"  # Standard landscape


def _add_trade_realism(prompt: str) -> str:
    """Add trade-specific and scene-specific realism details to image prompts.

    Two goals:
    1. Trade accuracy: real tools, correct equipment, proper technique
    2. Scene authenticity: natural interactions, realistic settings, believable moments
    """
    p = prompt.lower()
    additions = []

    # ── People & lifestyle realism ──
    if any(kw in p for kw in ["homeowner", "family", "couple", "resident"]):
        additions.append("natural candid moment, warm natural lighting, authentic expression")
    if any(kw in p for kw in ["greeting", "handshake", "consultation", "conversation"]):
        additions.append("natural body language, genuine interaction, front door or living room setting")
    if any(kw in p for kw in ["satisfied", "happy", "smiling"]):
        additions.append("genuine smile, relaxed posture, lifestyle photography feel")

    # ── Electrician trade realism ──
    if "electrician" in p or "electrical" in p or "panel" in p or "wiring" in p:
        if "panel" in p:
            additions.append("realistic electrical panel with proper wire routing and labeled breakers")
        if any(kw in p for kw in ["install", "work", "repair", "service"]):
            additions.append("wearing safety glasses, using linesman pliers or wire strippers, realistic work position with hands at correct height")
        if "generator" in p:
            additions.append("on level concrete pad with proper clearance from house, visible disconnect switch, conduit run to panel")
        if "test" in p or "inspect" in p:
            additions.append("holding multimeter or voltage tester, reading display, methodical inspection posture")

    # ── HVAC trade realism ──
    if any(kw in p for kw in ["hvac", "air condition", "furnace", "condenser", "mini-split", "heat pump"]):
        additions.append("on level equipment pad, proper refrigerant line routing with insulation, realistic service environment")
        if any(kw in p for kw in ["service", "repair", "maintain"]):
            additions.append("using manifold gauges or multimeter, access panel removed, wearing work gloves")

    # ── Plumbing trade realism ──
    if any(kw in p for kw in ["plumb", "pipe", "water heater", "drain", "faucet", "sewer"]):
        additions.append("realistic pipe connections with proper fittings, actual plumbing work environment")
        if "water heater" in p:
            additions.append("in utility closet or garage, visible T&P relief valve, proper venting")
        if any(kw in p for kw in ["under sink", "crawl", "repair"]):
            additions.append("realistic under-cabinet view, flashlight visible, pipe wrench in use")

    # ── Roofing trade realism ──
    if any(kw in p for kw in ["roof", "shingle", "gutter"]):
        additions.append("proper safety harness, realistic roof pitch, actual roofing materials visible")

    # ── Home exterior realism ──
    if any(kw in p for kw in ["home exterior", "house", "curb appeal", "property"]):
        additions.append("realistic landscaping, natural street setting, proper architectural details")

    # ── Before/after realism ──
    if "before" in p and "after" in p:
        additions.append("same angle and lighting in both shots, clear visible improvement, realistic transformation")

    if additions:
        return f"{prompt}, {', '.join(additions)}"
    return prompt


def enhance_prompt(
    base_prompt: str,
    business_name: str = "",
    location: str = "",
    service: str = "",
    brand_context: Optional[dict] = None,
) -> str:
    """Enhance an image prompt with trade realism + brand context + quality modifiers.

    1. Add trade-specific realism details
    2. Add brand photography style and color context
    3. Search Nano Banana for a matching prompt template
    4. Add quality modifiers and anti-text directive
    """
    # Add trade-accurate details
    base_prompt = _add_trade_realism(base_prompt)

    # Add brand photography style
    if brand_context:
        photo_style = brand_context.get("photography_style", "")
        if photo_style:
            base_prompt = f"{base_prompt}, {photo_style} photography style"
        palette = brand_context.get("color_palette", {})
        primary = palette.get("primary", "")
        accent = palette.get("accent", "")
        if primary and accent:
            base_prompt = f"{base_prompt}, color scheme complementing {primary} and {accent}"

    # Try Nano Banana prompt library for proven templates
    keywords = base_prompt.lower().split()[:5]
    if service:
        keywords.append(service.lower())
    nb_results = search_nano_banana(keywords, "product-marketing", limit=1)
    if not nb_results:
        nb_results = search_nano_banana(keywords, "social-media-post", limit=1)

    if nb_results:
        # Remix the Nano Banana template with our specific content
        nb_prompt = nb_results[0]["prompt"]
        # Use the NB template structure but inject our specific subject
        enhanced = f"{base_prompt}. Style reference: {nb_prompt[:300]}"
    else:
        enhanced = base_prompt

    # Add context
    parts = [enhanced]
    if business_name:
        parts.append(f"for {business_name}")
    if location:
        parts.append(f"in {location}")

    # Quality modifiers
    quality = "professional photography, high resolution, natural lighting, sharp focus"
    # CRITICAL: prevent Recraft from adding text to images
    anti_text = "no text, no words, no labels, no captions, no watermarks"

    final = f"{' '.join(parts)}, {quality}, {anti_text}"
    return final[:1024]


async def generate_image_nano_banana(
    prompt: str,
    api_key: str = "",
) -> Optional[str]:
    """Generate an image via OpenRouter (Nano Banana / Imagen models).

    Returns the image URL, or None on failure.
    Uses OpenRouter's OpenAI-compatible image generation endpoint.
    Best for: infographics, comparisons, anything with readable text,
    composited/edited looks, styled backgrounds, branded product shots.
    """
    key = api_key or OPENROUTER_API_KEY
    if not key:
        logger.warning("No OPENROUTER_API_KEY — skipping Nano Banana generation")
        return None

    # Rate limit before calling
    await _openrouter_limiter.acquire()

    payload = {
        "model": OPENROUTER_IMAGE_MODEL,
        "prompt": prompt[:4000],
        "n": 1,
        "size": "1024x1024",
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://proofpilot-agents.up.railway.app",
        "X-Title": "ProofPilot Agent Hub",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # OpenRouter returns OpenAI-compatible format: {"data": [{"url": "..."}]}
            images = data.get("data", [])
            if images:
                url = images[0].get("url")
                if url:
                    logger.info("OpenRouter (%s) generated image: %s", OPENROUTER_IMAGE_MODEL, url[:80])
                    return url

                # Some models return base64 instead of URL
                b64 = images[0].get("b64_json")
                if b64:
                    import base64
                    import tempfile
                    raw = base64.b64decode(b64)
                    fd, path = tempfile.mkstemp(suffix=".png", prefix="or_")
                    os.close(fd)
                    with open(path, "wb") as f:
                        f.write(raw)
                    logger.info("OpenRouter (%s) generated: %s (%d KB)",
                                OPENROUTER_IMAGE_MODEL, path, len(raw) // 1024)
                    return f"file://{path}"

            logger.warning("OpenRouter returned no image data: %s", json.dumps(data)[:300])
    except httpx.HTTPStatusError as e:
        logger.error("OpenRouter API error %s: %s", e.response.status_code, e.response.text[:300])
    except Exception as e:
        logger.error("OpenRouter generation failed: %s", e)

    return None


async def generate_image_recraft(
    prompt: str,
    style: str = "realistic_image",
    substyle: Optional[str] = None,
    size: str = "1365x1024",
    api_key: str = "",
) -> Optional[str]:
    """Generate a single image via Recraft API. Returns image URL or None."""
    key = api_key or RECRAFT_API_KEY
    if not key:
        logger.warning("No RECRAFT_API_KEY — skipping image generation")
        return None

    payload = {
        "prompt": prompt[:1024],
        "style": style,
        "model": "recraftv3",
        "size": size,
        "response_format": "url",
    }
    if substyle:
        payload["substyle"] = substyle

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(RECRAFT_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Recraft returns: {"data": [{"url": "https://..."}]}
            images = data.get("data", [])
            if images:
                return images[0].get("url")
    except httpx.HTTPStatusError as e:
        logger.error("Recraft API error %s: %s", e.response.status_code, e.response.text[:200])
    except Exception as e:
        logger.error("Recraft generation failed: %s", e)

    return None


def extract_image_slots(html: str) -> list[dict]:
    """Parse HTML for image placeholders with data-prompt attributes."""
    # Match <img> tags with data-prompt
    pattern = r'<img\s+[^>]*?data-prompt="([^"]*)"[^>]*?(?:alt="([^"]*)")?[^>]*?>'
    slots = []
    for i, match in enumerate(re.finditer(pattern, html, re.IGNORECASE)):
        prompt = match.group(1)
        alt = match.group(2) or ""
        full_tag = match.group(0)

        # Extract existing src if any
        src_match = re.search(r'src="([^"]*)"', full_tag)
        src = src_match.group(1) if src_match else ""

        slots.append({
            "index": i,
            "prompt": prompt,
            "alt": alt,
            "src": src,
            "full_tag": full_tag,
            "style": classify_image_slot(prompt, alt),
        })

    return slots


async def generate_images_for_page(
    html: str,
    business_name: str = "",
    location: str = "",
    service: str = "",
    max_images: int = 6,
    api_key: str = "",
    brand_context: Optional[dict] = None,
) -> tuple[str, list[dict]]:
    """Generate images for all placeholders in an HTML page.

    Uses a multi-tool strategy:
    - Nano Banana templates enhance prompts before generation
    - Recraft for realistic photos and vector illustrations
    - Skips map-type images (should be Google Maps embeds)

    Returns:
        tuple: (updated_html, generation_results)
    """
    slots = extract_image_slots(html)
    if not slots:
        logger.info("No image placeholders found in HTML")
        return html, []

    # Limit to max_images (prioritize hero images first)
    hero_slots = [s for s in slots if any(kw in s["prompt"].lower() for kw in HERO_KEYWORDS)]
    other_slots = [s for s in slots if s not in hero_slots]
    prioritized = (hero_slots + other_slots)[:max_images]

    results = []
    updated_html = html

    MAP_KEYWORDS = ["map", "service area", "coverage area", "locations map"]

    for slot in prioritized:
        prompt_lower = slot["prompt"].lower()

        # Skip map images — these should be Google Maps embeds, not AI-generated
        if any(kw in prompt_lower for kw in MAP_KEYWORDS):
            logger.info("Skipping map image (should be Google Maps embed): %s", slot["prompt"][:60])
            results.append({
                "index": slot["index"],
                "prompt": slot["prompt"],
                "style": "skipped_map",
                "substyle": None,
                "size": None,
                "url": None,
                "success": False,
                "reason": "Map images should use Google Maps iframe embed",
            })
            continue

        tool_type = slot["style"]  # 'recraft_realistic', 'recraft_vector', or 'nano_banana'
        enhanced_prompt = enhance_prompt(slot["prompt"], business_name, location, service, brand_context)
        url = None
        tool_used = tool_type

        if tool_type == "nano_banana":
            # Use OpenRouter for text-heavy / infographic / composited images
            logger.info("Generating image %d via OpenRouter (Nano Banana): %s...", slot["index"], enhanced_prompt[:80])
            result_url = await generate_image_nano_banana(prompt=enhanced_prompt)
            if result_url:
                url = result_url
                tool_used = "nano_banana"

        if tool_type in ("recraft_realistic", "recraft_vector") or (tool_type == "nano_banana" and not url):
            # Use Recraft for realistic photos or vectors (or as fallback)
            recraft_style = "vector_illustration" if tool_type == "recraft_vector" else "realistic_image"
            substyle = get_recraft_substyle(recraft_style, slot["prompt"])
            size = get_image_size(recraft_style, slot["prompt"])

            logger.info("Generating image %d via Recraft (%s): %s...",
                         slot["index"], recraft_style, enhanced_prompt[:80])
            url = await generate_image_recraft(
                prompt=enhanced_prompt,
                style=recraft_style,
                substyle=substyle,
                size=size,
                api_key=api_key,
            )
            if url:
                tool_used = "recraft"

        result = {
            "index": slot["index"],
            "prompt": slot["prompt"],
            "tool": tool_used,
            "url": url,
            "success": url is not None,
        }
        results.append(result)

        if url:
            old_tag = slot["full_tag"]
            new_tag = re.sub(r'src="[^"]*"', f'src="{url}"', old_tag)
            updated_html = updated_html.replace(old_tag, new_tag, 1)

        await asyncio.sleep(0.5)

    return updated_html, results


# ── Nano Banana Integration ─────────────────────────────────────────────────

NANO_BANANA_DIR = Path.home() / ".claude" / "skills" / "nano-banana" / "references"


def search_nano_banana(keywords: list[str], category: str = "product-marketing", limit: int = 3) -> list[dict]:
    """Search the Nano Banana prompt library for matching templates.

    Returns list of {title, prompt, sourceMedia} dicts.
    """
    category_file = NANO_BANANA_DIR / f"{category}.json"
    if not category_file.exists():
        return []

    try:
        with open(category_file) as f:
            prompts = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    # Score prompts by keyword matches
    scored = []
    for p in prompts:
        content = (p.get("content", "") + " " + p.get("title", "") + " " + p.get("description", "")).lower()
        score = sum(1 for kw in keywords if kw.lower() in content)
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "title": p.get("title", ""),
            "prompt": p.get("content", ""),
            "source_media": p.get("sourceMedia", []),
            "needs_reference": p.get("needReferenceImages", False),
        }
        for _, p in scored[:limit]
    ]


def get_nano_banana_categories_for_page(page_type: str) -> list[str]:
    """Map page types to relevant Nano Banana categories."""
    mapping = {
        "service-page": ["product-marketing", "infographic-edu-visual", "social-media-post"],
        "location-page": ["product-marketing", "social-media-post"],
        "blog-post": ["infographic-edu-visual", "social-media-post", "youtube-thumbnail"],
    }
    return mapping.get(page_type, ["product-marketing"])
