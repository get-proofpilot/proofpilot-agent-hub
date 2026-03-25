"""
Site Crawler — discovers all pages on a client website via Firecrawl API
and generates/updates their tracker.yaml for SEO page tracking.

Uses the Firecrawl /v1/map endpoint for fast URL discovery (no content scraping).
"""

import os
import re
import logging
from pathlib import Path
from datetime import date
from urllib.parse import urlparse

import httpx
import yaml

logger = logging.getLogger(__name__)

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"
FIRECRAWL_TIMEOUT = 30.0

# Extensions and patterns to filter out (not real pages)
_SKIP_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.css', '.js', '.json', '.xml', '.txt', '.map',
    '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv',
    '.zip', '.tar', '.gz', '.rar',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
}

# Core pages that are always categorized as 'core'
_CORE_PATHS = {'/', '/about/', '/about-us/', '/contact/', '/contact-us/',
               '/reviews/', '/testimonials/', '/gallery/', '/portfolio/',
               '/privacy-policy/', '/terms/', '/terms-of-service/',
               '/careers/', '/team/', '/our-team/', '/faq/'}

# Common US state abbreviations for location detection
_STATE_ABBREVS = {
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga',
    'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky', 'la', 'ma', 'md',
    'me', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj',
    'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc',
    'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy',
    'dc',
}

# Location indicator words that appear in geo-targeted URLs
_LOCATION_INDICATORS = {
    'near-me', 'in-my-area', 'near', 'serving',
    'electrician-in', 'plumber-in', 'contractor-in',
    'service-area', 'areas-served', 'service-areas',
}

# ---------------------------------------------------------------------------
# Industry-specific service category maps
# ---------------------------------------------------------------------------

ELECTRICAL_CATEGORIES = {
    'panel-upgrades': ['panel', '200-amp', '100-amp', 'sub-panel', 'circuit-breaker',
                       'federal-pacific', 'zinsco', 'challenger', 'pushmatic', 'fuse-box',
                       'breaker', 'electrical-panel'],
    'ev-charger': ['ev-charger', 'ev-charging', 'tesla-wall', 'chargepoint', 'level-2',
                   'charge-ready', 'electric-vehicle', 'charging-station'],
    'rewiring': ['rewir', 'knob-and-tube', 'aluminum-wiring', 'wire-upgrade',
                 'whole-home-rewir', 'whole-house-rewir'],
    'lighting': ['lighting', 'recessed-light', 'landscape-light', 'ceiling-fan',
                 'chandelier', 'led-', 'track-light', 'pendant-light', 'outdoor-light'],
    'generator': ['generator', 'standby', 'backup-power', 'transfer-switch', 'generac',
                  'whole-house-generator', 'backup-generator'],
    'electrical-safety': ['inspection', 'safety-inspection', 'surge-protect',
                          'smoke-detect', 'gfci', 'arc-fault', 'code-compliance',
                          'grounding', 'electrical-safety'],
    'outlets-switches': ['outlet', 'switch', 'receptacle', 'usb-outlet', 'dimmer',
                         'gfci-outlet'],
    'commercial': ['commercial', 'tenant-improvement', 'office-electrical',
                   'warehouse', 'industrial', 'retail-electrical'],
    'emergency': ['emergency', '24-hour', 'urgent', 'same-day'],
    'smart-home': ['smart-home', 'automation', 'home-automation', 'nest', 'ring-doorbell'],
    'hot-tub-spa': ['hot-tub', 'spa-wiring', 'pool-electrical', 'jacuzzi'],
}

PROPERTY_MANAGEMENT_CATEGORIES = {
    'tenant-screening': ['tenant-screen', 'background-check', 'credit-check', 'application'],
    'maintenance': ['maintenance', 'repair', 'plumbing', 'hvac', 'appliance'],
    'leasing': ['leasing', 'rental', 'vacancy', 'listing', 'showing'],
    'accounting': ['accounting', 'rent-collection', 'financial', 'budget', 'invoice'],
    'eviction': ['eviction', 'notice', 'legal', 'compliance'],
    'marketing': ['marketing', 'advertising', 'listing-photos', 'virtual-tour'],
}

PHOTOGRAPHY_CATEGORIES = {
    'wedding': ['wedding', 'bridal', 'engagement', 'ceremony', 'reception'],
    'portrait': ['portrait', 'headshot', 'family-photo', 'senior-photo'],
    'event': ['event', 'corporate', 'birthday', 'party', 'conference'],
    'commercial': ['commercial', 'product', 'real-estate', 'architecture'],
}

HEALTHCARE_CATEGORIES = {
    'pain-management': ['pain', 'chronic-pain', 'back-pain', 'neck-pain', 'sciatica'],
    'sports-medicine': ['sports', 'athlete', 'injury', 'rehabilitation', 'physical-therapy'],
    'chiropractic': ['chiropractic', 'spinal', 'adjustment', 'alignment'],
    'regenerative': ['regenerative', 'stem-cell', 'prp', 'platelet'],
}

INDUSTRY_CATEGORIES = {
    'electrical': ELECTRICAL_CATEGORIES,
    'property management': PROPERTY_MANAGEMENT_CATEGORIES,
    'photography': PHOTOGRAPHY_CATEGORIES,
    'healthcare': HEALTHCARE_CATEGORIES,
    'healthcare / pain management': HEALTHCARE_CATEGORIES,
}

# Flat set of all service keywords across all industries for enhanced categorize_url
_ALL_SERVICE_KEYWORDS: set[str] = set()
for _cat_map in INDUSTRY_CATEGORIES.values():
    for _kw_list in _cat_map.values():
        _ALL_SERVICE_KEYWORDS.update(_kw_list)


def detect_service_category(url_path: str, industry: str = 'electrical') -> str:
    """Detect the service category from URL slug keywords.

    Checks the URL path against the keyword map for the given industry.
    Falls back to ELECTRICAL_CATEGORIES for unknown industries.

    Args:
        url_path: URL path (e.g., '/panel-upgrades-downey-ca/')
        industry: Industry name (case-insensitive)

    Returns:
        Category slug (e.g., 'panel-upgrades') or 'general' if no match.
    """
    slug = url_path.strip('/').lower()
    categories = INDUSTRY_CATEGORIES.get(industry.lower(), ELECTRICAL_CATEGORIES)
    for category, keywords in categories.items():
        if any(kw in slug for kw in keywords):
            return category
    return 'general'


def extract_city(url_path: str) -> str | None:
    """Extract city name from a URL if it contains a location reference.

    Looks for segments ending with a two-letter US state abbreviation and
    strips common service-keyword prefixes.

    Args:
        url_path: URL path (e.g., '/electrician-in-downey-ca/')

    Returns:
        City-state slug (e.g., 'downey-ca') or None if no city detected.
    """
    slug = url_path.strip('/').lower()
    segments = slug.split('/')

    for segment in segments:
        parts = segment.split('-')
        # Check if ends with state abbreviation (2 letters)
        if len(parts) >= 2 and parts[-1] in _STATE_ABBREVS:
            # City is everything before the state abbrev
            city_parts = parts[:-1]
            # Remove service keywords that might prefix the city
            # e.g., "electrician-in-downey" -> "downey"
            skip_prefixes = ['electrician', 'plumber', 'contractor', 'hvac',
                             'service', 'services', 'in', 'near', 'serving']
            while city_parts and city_parts[0] in skip_prefixes:
                city_parts.pop(0)
            if city_parts:
                return '-'.join(city_parts) + '-' + parts[-1]
    return None


def _get_api_key() -> str | None:
    """Read the Firecrawl API key from environment."""
    return os.environ.get('FIRECRAWL_API_KEY')


def _normalize_url(website: str) -> str:
    """Ensure the website URL has a scheme."""
    website = website.strip()
    if not website.startswith(('http://', 'https://')):
        website = f"https://{website}"
    return website


def _is_page_url(path: str) -> bool:
    """Return True if the path looks like a real page (not an asset or query)."""
    if not path:
        return False
    # Skip URLs with query params or fragments
    if '?' in path or '#' in path:
        return False
    # Skip asset files
    lower = path.lower()
    for ext in _SKIP_EXTENSIONS:
        if lower.endswith(ext):
            return False
    # Skip common non-page paths
    skip_prefixes = ('/wp-content/', '/wp-admin/', '/wp-includes/',
                     '/wp-json/', '/feed/', '/cdn-cgi/', '/.well-known/',
                     '/assets/', '/static/', '/images/', '/img/',
                     '/fonts/', '/css/', '/js/')
    for prefix in skip_prefixes:
        if lower.startswith(prefix):
            return False
    return True


async def crawl_site(website: str) -> list[str]:
    """Call the Firecrawl map endpoint and return a sorted list of URL paths.

    Args:
        website: The client's website domain or full URL.

    Returns:
        Sorted, deduplicated list of URL paths (e.g., ['/about/', '/panel-upgrades/']).
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("FIRECRAWL_API_KEY not set — cannot crawl site")
        return []

    url = _normalize_url(website)
    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.lower()

    logger.info(f"Crawling {url} via Firecrawl map endpoint...")

    try:
        async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT) as client:
            resp = await client.post(
                f"{FIRECRAWL_BASE}/map",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "limit": 500},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.error(f"Firecrawl timed out after {FIRECRAWL_TIMEOUT}s for {url}")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"Firecrawl HTTP error {e.response.status_code}: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"Firecrawl request failed: {e}")
        return []

    if not data.get('success'):
        logger.warning(f"Firecrawl returned success=false for {url}")
        return []

    links = data.get('links', [])
    logger.info(f"Firecrawl returned {len(links)} raw links")

    # Extract paths, filter, deduplicate
    paths: set[str] = set()
    for link in links:
        try:
            parsed = urlparse(link)
        except Exception:
            continue
        # Only include links from the same domain
        link_domain = parsed.netloc.lower()
        if link_domain and link_domain != base_domain and link_domain != f"www.{base_domain}" and f"www.{link_domain}" != base_domain:
            continue
        path = parsed.path or '/'
        # Normalize: ensure trailing slash for non-file paths
        if not path.endswith('/') and '.' not in path.split('/')[-1]:
            path = path + '/'
        if _is_page_url(path):
            paths.add(path)

    # If we found a /blog/ index but very few blog posts, do a second
    # crawl specifically on the blog section to discover sub-pages
    blog_paths = [p for p in paths if p.startswith('/blog/') and p != '/blog/']
    has_blog_index = '/blog/' in paths
    if has_blog_index and len(blog_paths) < 3:
        logger.info("Blog index found but few posts — crawling /blog/ section...")
        try:
            async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT) as client:
                resp = await client.post(
                    f"{FIRECRAWL_BASE}/map",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"url": f"{url}/blog/", "limit": 200},
                )
                resp.raise_for_status()
                blog_data = resp.json()
                blog_links = blog_data.get('links', [])
                logger.info(f"Blog crawl returned {len(blog_links)} links")
                for link in blog_links:
                    try:
                        parsed = urlparse(link)
                        link_domain = parsed.netloc.lower()
                        if link_domain and link_domain != base_domain and link_domain != f"www.{base_domain}" and f"www.{link_domain}" != base_domain:
                            continue
                        path = parsed.path or '/'
                        if not path.endswith('/') and '.' not in path.split('/')[-1]:
                            path = path + '/'
                        if _is_page_url(path):
                            paths.add(path)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Blog sub-crawl failed: {e}")

    result = sorted(paths)
    logger.info(f"Found {len(result)} unique page paths after filtering")
    return result


def categorize_url(url_path: str) -> str:
    """Categorize a URL path into an enhanced type taxonomy.

    Returns one of: core, service, sub-service, service-location, location,
    blog, or other.

    Uses heuristics — not perfect, but good enough for initial triage.
    The SEO manager will review and correct.

    Enhanced type logic (checked in order):
        1. Core pages -> 'core'
        2. Category/tag/author -> 'other'
        3. Blog patterns -> 'blog'
        4. Has city AND service keywords -> 'service-location'
        5. Has city pattern -> 'location'
        6. Has service keywords -> 'service' or 'sub-service'
        7. Default -> 'other'
    """
    path = url_path.strip().lower()

    # Normalize trailing slash for matching
    if not path.endswith('/'):
        path = path + '/'

    # 1. Core pages
    if path in _CORE_PATHS:
        return 'core'

    # 2. Category/tag pages -> other (not real content)
    if path.startswith('/category/') or path.startswith('/tag/') or path.startswith('/author/'):
        return 'other'

    # 3. Blog detection — check prefix first
    if path.startswith('/blog/') or '/blog/' in path or path == '/blog/':
        return 'blog'
    if path.startswith('/news/') or path.startswith('/articles/') or path.startswith('/resources/'):
        return 'blog'

    # Blog detection — informational content patterns (guides, how-to, lists)
    slug = path.strip('/')
    blog_indicators = [
        'how-to-', 'what-is-', 'why-', 'when-to-', 'guide', 'tips',
        'cost-of-', 'signs-', 'best-', 'top-', 'common-', 'benefits-of-',
        '-vs-', 'checklist', 'mistakes', 'questions', 'explained',
        'things-to-know', 'homeowner', 'complete-guide',
    ]
    if any(indicator in slug for indicator in blog_indicators):
        return 'blog'

    # --- Detect city presence and service-keyword presence ---
    has_city = False
    has_service_kw = False

    # City detection: state abbreviation at or near end of path
    segments = path.strip('/').replace('/', '-').split('-')
    if len(segments) >= 2:
        if segments[-1] in _STATE_ABBREVS:
            has_city = True
        elif segments[-1] == '' and len(segments) >= 3 and segments[-2] in _STATE_ABBREVS:
            has_city = True

    # Also check location indicator words
    if not has_city:
        for indicator in _LOCATION_INDICATORS:
            if indicator in path:
                has_city = True
                break

    # Service keyword detection: check against all industry keyword maps
    for kw in _ALL_SERVICE_KEYWORDS:
        if kw in slug:
            has_service_kw = True
            break

    # 4. Has city AND service keywords -> 'service-location'
    if has_city and has_service_kw:
        return 'service-location'

    # 5. Has city pattern -> 'location'
    if has_city:
        return 'location'

    # 6. Service pages — check for service keywords or descriptive slugs
    path_clean = path.strip('/')
    if path_clean and path_clean not in ('sitemap', 'sitemap.xml'):
        if has_service_kw:
            # Sub-service detection: longer slugs with 3+ hyphenated segments
            # that contain a service keyword suggest a specialization page
            # e.g., /federal-pacific-panel-replacement/ is a sub-service of panel-upgrades
            hyphen_count = path_clean.count('-')
            if hyphen_count >= 3:
                return 'sub-service'
            return 'service'
        # If it has 2+ words (hyphens) and doesn't match other categories, it's likely a service
        if '-' in path_clean:
            return 'service'
        # Single-word paths that aren't core are usually services or categories
        return 'service'

    # 7. Default
    return 'other'


def _url_to_page_name(url_path: str) -> str:
    """Convert a URL path to a human-readable page name.

    Examples:
        /panel-upgrades/           -> Panel Upgrades
        /ev-charger-installation/  -> EV Charger Installation
        /electrician-downey-ca/    -> Electrician Downey CA
        /                          -> Homepage
    """
    path = url_path.strip('/')
    if not path:
        return 'Homepage'
    # Replace hyphens and underscores with spaces, title case
    name = path.replace('-', ' ').replace('_', ' ')
    # Handle nested paths: use just the last segment
    if '/' in name:
        name = name.split('/')[-1]
    return name.title()


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Expects the file to start with --- and have a closing ---.
    Returns the parsed YAML dict, or empty dict if no frontmatter found.
    """
    if not text.startswith('---'):
        return {}
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


# ---------------------------------------------------------------------------
# Deep taxonomy helpers
# ---------------------------------------------------------------------------

def categorize_url_deep(url_path: str, industry: str = 'electrical') -> dict:
    """Return full taxonomy for a URL: type, service_category, and city.

    Combines the enhanced categorize_url(), detect_service_category(), and
    extract_city() into a single dict.

    Args:
        url_path: URL path (e.g., '/panel-upgrades-downey-ca/')
        industry: Industry name for service category detection.

    Returns:
        Dict with keys 'type', 'service_category', 'city'.
    """
    return {
        'type': categorize_url(url_path),
        'service_category': detect_service_category(url_path, industry),
        'city': extract_city(url_path),
    }


def build_content_inventory(pages: list[dict], industry: str = 'electrical') -> dict:
    """Build a structured content inventory from categorized pages.

    Args:
        pages: List of page dicts with 'url', 'type', 'service_category', 'city' keys.
        industry: Industry name (used in gap labels).

    Returns:
        Inventory dict with 'by_service_category', 'by_city', and 'gap_analysis'.
    """
    if not pages:
        return {
            'by_service_category': {},
            'by_city': {},
            'gap_analysis': {
                'categories_without_blog': [],
                'thin_categories': [],
                'categories_without_location_pages': [],
                'thin_cities': [],
            },
        }

    # --- Group by service_category, then by type within each ---
    by_category: dict[str, dict[str, list[dict]]] = {}
    for page in pages:
        cat = page.get('service_category', 'general')
        ptype = page.get('type', 'other')
        by_category.setdefault(cat, {}).setdefault(ptype, []).append(page)

    # --- Group by city ---
    by_city: dict[str, list[dict]] = {}
    for page in pages:
        city = page.get('city')
        if city:
            by_city.setdefault(city, []).append(page)

    # --- Gap analysis ---
    categories_without_blog: list[str] = []
    thin_categories: list[str] = []
    categories_without_location_pages: list[str] = []
    thin_cities: list[str] = []

    for cat, type_map in by_category.items():
        if cat == 'general':
            continue  # skip the catch-all bucket
        total = sum(len(v) for v in type_map.values())
        blog_count = len(type_map.get('blog', []))
        location_count = len(type_map.get('service-location', []))
        has_service = bool(type_map.get('service') or type_map.get('sub-service'))

        if blog_count == 0:
            categories_without_blog.append(cat)
        if total < 2:
            thin_categories.append(cat)
        if has_service and location_count == 0:
            categories_without_location_pages.append(cat)

    for city, city_pages in by_city.items():
        if len(city_pages) <= 1:
            thin_cities.append(city)

    return {
        'by_service_category': by_category,
        'by_city': by_city,
        'gap_analysis': {
            'categories_without_blog': sorted(categories_without_blog),
            'thin_categories': sorted(thin_categories),
            'categories_without_location_pages': sorted(categories_without_location_pages),
            'thin_cities': sorted(thin_cities),
        },
    }


def format_inventory_text(inventory: dict) -> str:
    """Format the content inventory as readable text for prompt injection.

    Args:
        inventory: Output from build_content_inventory().

    Returns:
        Multi-line string suitable for embedding in an LLM prompt.
    """
    lines: list[str] = ['## Content Inventory', '']

    by_cat = inventory.get('by_service_category', {})
    by_city = inventory.get('by_city', {})
    gaps = inventory.get('gap_analysis', {})

    # --- By Service Category ---
    lines.append('### By Service Category')
    if not by_cat:
        lines.append('(no pages)')
    else:
        for cat in sorted(by_cat.keys()):
            type_map = by_cat[cat]
            total = sum(len(v) for v in type_map.values())
            service_ct = len(type_map.get('service', []))
            sub_ct = len(type_map.get('sub-service', []))
            loc_ct = len(type_map.get('service-location', []))
            blog_ct = len(type_map.get('blog', []))

            label = cat.replace('-', ' ').title()
            detail = f"{total} pages ({service_ct} service, {sub_ct} sub-service, {loc_ct} service-location, {blog_ct} blog)"

            # Annotate thin / needs-depth
            warnings: list[str] = []
            if total < 2:
                warnings.append('NEEDS DEPTH')
            elif total <= 3 and (loc_ct == 0 or blog_ct == 0):
                warnings.append('THIN')
            if blog_ct == 0 and total >= 2:
                warnings.append('needs blog content')

            suffix = ''
            if warnings:
                suffix = ' <- ' + ', '.join(warnings)

            lines.append(f'{label}: {detail}{suffix}')
    lines.append('')

    # --- Location Coverage ---
    lines.append('### Location Coverage')
    if not by_city:
        lines.append('(no location pages detected)')
    else:
        deep_cities = sorted(
            [(c, len(p)) for c, p in by_city.items() if len(p) >= 3],
            key=lambda x: -x[1],
        )
        thin_cities_list = sorted(
            [(c, len(p)) for c, p in by_city.items() if len(p) < 3],
            key=lambda x: -x[1],
        )

        if deep_cities:
            deep_str = ', '.join(f'{c.replace("-", " ").title()} ({n})' for c, n in deep_cities)
            lines.append(f'Cities with deep coverage (3+ pages): {deep_str}')
        if thin_cities_list:
            thin_str = ', '.join(f'{c.replace("-", " ").title()} ({n})' for c, n in thin_cities_list)
            lines.append(f'Cities with thin coverage (1-2 pages): {thin_str}')
        if not deep_cities and not thin_cities_list:
            lines.append('(no city data)')
    lines.append('')

    # --- Content Gaps ---
    lines.append('### Content Gaps')
    gap_lines: list[str] = []

    cats_no_loc = gaps.get('categories_without_location_pages', [])
    cats_no_blog = gaps.get('categories_without_blog', [])
    thin_cats = gaps.get('thin_categories', [])

    # Build per-category gap summary
    all_gap_cats = sorted(set(cats_no_loc + cats_no_blog + thin_cats))
    for cat in all_gap_cats:
        label = cat.replace('-', ' ').title()
        missing: list[str] = []
        type_map = by_cat.get(cat, {})
        if cat in thin_cats:
            missing.append('needs more pages overall')
        if not type_map.get('sub-service'):
            missing.append('0 sub-service pages')
        if cat in cats_no_loc:
            missing.append('0 location pages')
        if cat in cats_no_blog:
            missing.append('0 blog posts')
        if missing:
            gap_lines.append(f'- {label}: {", ".join(missing)}')

    if gap_lines:
        lines.extend(gap_lines)
    else:
        lines.append('(no significant gaps detected)')

    return '\n'.join(lines)


async def setup_tracking(client_slug: str, vault_dir: Path) -> dict:
    """Crawl a client's website and generate/update their tracker.yaml.

    Uses deep categorization (type, service_category, city) for each page
    and builds a content inventory with gap analysis.

    Args:
        client_slug: The client folder name (e.g., 'saiyan-electric').
        vault_dir: Path to the vault_data directory.

    Returns:
        Summary dict with total_pages, new_pages, category counts,
        content_inventory, and inventory_text.
    """
    client_dir = vault_dir / 'clients' / client_slug

    # 1. Read context.md to get website domain and industry
    context_path = client_dir / 'context.md'
    if not context_path.exists():
        raise FileNotFoundError(f"No context.md found for client '{client_slug}' at {context_path}")

    context_text = context_path.read_text(encoding='utf-8')
    frontmatter = _parse_frontmatter(context_text)

    website = frontmatter.get('website', '')
    client_name = frontmatter.get('client', client_slug.replace('-', ' ').title())
    industry = frontmatter.get('industry', 'electrical')

    if not website:
        raise ValueError(f"No 'website' field in context.md frontmatter for '{client_slug}'")

    logger.info(f"Setting up tracking for {client_name} ({website}), industry={industry}")

    # 2. Crawl the site
    paths = await crawl_site(website)

    # 3. Deep-categorize each URL
    crawled_pages = []
    category_counts: dict[str, int] = {}
    for path in paths:
        taxonomy = categorize_url_deep(path, industry)
        page_name = _url_to_page_name(path)
        crawled_pages.append({
            'page': page_name,
            'url': path,
            'type': taxonomy['type'],
            'service_category': taxonomy['service_category'],
            'city': taxonomy['city'],
        })
        ptype = taxonomy['type']
        category_counts[ptype] = category_counts.get(ptype, 0) + 1

    # 4. Load existing tracker if present
    tracker_path = client_dir / 'tracker.yaml'
    existing_pages: dict[str, dict] = {}  # keyed by url
    if tracker_path.exists():
        try:
            existing_data = yaml.safe_load(tracker_path.read_text(encoding='utf-8'))
            if existing_data and 'pages' in existing_data:
                for p in existing_data['pages']:
                    existing_pages[p.get('url', '')] = p
        except yaml.YAMLError as e:
            logger.warning(f"Could not parse existing tracker.yaml: {e}")

    # 5. Merge — keep existing statuses, add new pages, mark missing ones
    crawled_urls = {p['url'] for p in crawled_pages}
    merged_pages = []
    new_count = 0

    for cp in crawled_pages:
        url = cp['url']
        if url in existing_pages:
            # Keep existing entry (preserves status, history, last_updated)
            existing = existing_pages[url]
            # Upgrade taxonomy fields — always overwrite with fresh deep categorization
            # but preserve 'category' for backward compat if present
            if existing.get('type', existing.get('category', 'other')) == 'other' and cp['type'] != 'other':
                existing['type'] = cp['type']
            elif 'type' not in existing:
                existing['type'] = cp['type']
            # Always update service_category and city from fresh crawl
            existing['service_category'] = cp['service_category']
            existing['city'] = cp['city']
            # Migrate legacy 'category' field to 'type'
            if 'category' in existing and 'type' not in existing:
                existing['type'] = existing.pop('category')
            merged_pages.append(existing)
        else:
            # New page found in crawl
            merged_pages.append({
                'page': cp['page'],
                'url': url,
                'type': cp['type'],
                'service_category': cp['service_category'],
                'city': cp['city'],
                'status': 'planned',
                'last_updated': None,
                'history': [],
            })
            new_count += 1

    # Pages in old tracker but NOT in crawl — mark as missing
    missing_count = 0
    for url, old_page in existing_pages.items():
        if url not in crawled_urls:
            old_page['status'] = 'missing'
            # Ensure deep taxonomy fields exist on legacy entries
            if 'type' not in old_page:
                old_page['type'] = old_page.get('category', 'other')
            if 'service_category' not in old_page:
                old_page['service_category'] = detect_service_category(url, industry)
            if 'city' not in old_page:
                old_page['city'] = extract_city(url)
            merged_pages.append(old_page)
            missing_count += 1

    if missing_count > 0:
        logger.info(f"Marked {missing_count} pages as 'missing' (no longer found in crawl)")

    # Count optimized pages
    pages_optimized = sum(1 for p in merged_pages if p.get('status') == 'done')

    today = date.today().isoformat()

    # 6. Build content inventory from merged pages
    inventory = build_content_inventory(merged_pages, industry)
    inventory_text = format_inventory_text(inventory)

    # 7. Build tracker.yaml
    tracker_data = {
        'client': client_name,
        'website': website,
        'industry': industry,
        'total_pages': len(merged_pages),
        'pages_optimized': pages_optimized,
        'last_updated': today,
        'generated': today,
        'pages': merged_pages,
    }

    # Write the file
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tracker_path, 'w', encoding='utf-8') as f:
        # Add header comment
        f.write(f"# {client_name} — Page Tracker\n")
        f.write(f"# Generated by /setup-tracking on {today}\n")
        f.write("# Statuses: planned | in-progress | done | missing\n")
        f.write(f"# Industry: {industry}\n\n")
        yaml.dump(tracker_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Saved tracker.yaml: {len(merged_pages)} pages ({new_count} new, {missing_count} missing)")

    # 8. Return summary with inventory
    return {
        'client': client_name,
        'website': website,
        'industry': industry,
        'total_pages': len(merged_pages),
        'new_pages': new_count,
        'missing_pages': missing_count,
        'pages_optimized': pages_optimized,
        'categories': category_counts,
        'content_inventory': inventory,
        'inventory_text': inventory_text,
    }
