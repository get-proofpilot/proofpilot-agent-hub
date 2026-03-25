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
    """Categorize a URL path into: core, service, location, blog, or other.

    Uses heuristics — not perfect, but good enough for initial triage.
    The SEO manager will review and correct.
    """
    path = url_path.strip().lower()

    # Normalize trailing slash for matching
    if not path.endswith('/'):
        path = path + '/'

    # Core pages
    if path in _CORE_PATHS:
        return 'core'

    # Blog detection — check prefix first
    if path.startswith('/blog/') or '/blog/' in path or path == '/blog/':
        return 'blog'
    if path.startswith('/news/') or path.startswith('/articles/') or path.startswith('/resources/'):
        return 'blog'

    # Category/tag pages → other (not real content)
    if path.startswith('/category/') or path.startswith('/tag/') or path.startswith('/author/'):
        return 'other'

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

    # Location detection — look for city + state abbreviation patterns
    # e.g., /electrician-downey-ca/, /panel-upgrades-in-long-beach-ca/
    segments = path.strip('/').replace('/', '-').split('-')

    # Check if any location indicator words are in the path
    for indicator in _LOCATION_INDICATORS:
        if indicator in path:
            return 'location'

    # Check for state abbreviation at or near end of path
    # Pattern: something-city-ST/ where ST is a state abbreviation
    if len(segments) >= 2:
        # Check last segment
        if segments[-1] in _STATE_ABBREVS:
            return 'location'
        # Check second-to-last if last is empty
        if segments[-1] == '' and len(segments) >= 3 and segments[-2] in _STATE_ABBREVS:
            return 'location'

    # Service pages — most remaining paths with descriptive slugs are services
    # Skip very short paths that might be categories
    path_clean = path.strip('/')
    if path_clean and path_clean not in ('sitemap', 'sitemap.xml'):
        # If it has 2+ words (hyphens) and doesn't match other categories, it's likely a service
        if '-' in path_clean:
            return 'service'
        # Single-word paths that aren't core are usually services or categories
        return 'service'

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


async def setup_tracking(client_slug: str, vault_dir: Path) -> dict:
    """Crawl a client's website and generate/update their tracker.yaml.

    Args:
        client_slug: The client folder name (e.g., 'saiyan-electric').
        vault_dir: Path to the vault_data directory.

    Returns:
        Summary dict with total_pages, new_pages, and category counts.
    """
    client_dir = vault_dir / 'clients' / client_slug

    # 1. Read context.md to get website domain
    context_path = client_dir / 'context.md'
    if not context_path.exists():
        raise FileNotFoundError(f"No context.md found for client '{client_slug}' at {context_path}")

    context_text = context_path.read_text(encoding='utf-8')
    frontmatter = _parse_frontmatter(context_text)

    website = frontmatter.get('website', '')
    client_name = frontmatter.get('client', client_slug.replace('-', ' ').title())

    if not website:
        raise ValueError(f"No 'website' field in context.md frontmatter for '{client_slug}'")

    logger.info(f"Setting up tracking for {client_name} ({website})")

    # 2. Crawl the site
    paths = await crawl_site(website)

    # 3. Categorize each URL
    crawled_pages = []
    category_counts: dict[str, int] = {}
    for path in paths:
        cat = categorize_url(path)
        page_name = _url_to_page_name(path)
        crawled_pages.append({
            'page': page_name,
            'url': path,
            'category': cat,
        })
        category_counts[cat] = category_counts.get(cat, 0) + 1

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
            # Update category if it was 'other' before but we have a better guess now
            if existing.get('category') == 'other' and cp['category'] != 'other':
                existing['category'] = cp['category']
            merged_pages.append(existing)
        else:
            # New page found in crawl
            merged_pages.append({
                'page': cp['page'],
                'url': url,
                'category': cp['category'],
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
            merged_pages.append(old_page)
            missing_count += 1

    if missing_count > 0:
        logger.info(f"Marked {missing_count} pages as 'missing' (no longer found in crawl)")

    # Count optimized pages
    pages_optimized = sum(1 for p in merged_pages if p.get('status') == 'done')

    today = date.today().isoformat()

    # 6. Build tracker.yaml
    tracker_data = {
        'client': client_name,
        'website': website,
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
        f.write("# Statuses: planned | in-progress | done | missing\n\n")
        yaml.dump(tracker_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Saved tracker.yaml: {len(merged_pages)} pages ({new_count} new, {missing_count} missing)")

    # 7. Return summary
    return {
        'client': client_name,
        'website': website,
        'total_pages': len(merged_pages),
        'new_pages': new_count,
        'missing_pages': missing_count,
        'pages_optimized': pages_optimized,
        'categories': category_counts,
    }
