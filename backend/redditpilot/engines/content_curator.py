"""Content Curator — finds, curates, and annotates shareable web content.

Capabilities:
- Web article discovery via Google News RSS
- Subreddit hot-post scraping for content ideas
- LLM-generated value-add commentary for curated items
- Per-client storage of ready-to-share items in learned_strategies

Adapted from MiloAgent's ContentCurator for RedditPilot's multi-client
architecture.  No YouTube integration — focused on web articles and
resources.
"""

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from ..core.database import Database
from ..core.config import ClientProfile

logger = logging.getLogger("redditpilot.curator")

# ── Constants ────────────────────────────────────────────────────────
_HTTP_TIMEOUT = 15
_CURATED_TTL_HOURS = 168  # 7 days

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


class ContentCurator:
    """Finds and curates shareable web content relevant to a client's
    industry, generates value-add commentary, and stores items for
    future posting.

    Curated items are stored in ``learned_strategies`` with
    ``strategy_type='curated_content'``.  The composite ``key`` column
    encodes the article title, URL, source, and LLM commentary.

    Usage::

        curator = ContentCurator(db, llm)
        curator.curate_content(client_id)           # periodic scan
        items = curator.get_curated_content(client_id)  # ready-to-share
    """

    def __init__(self, db: Database, llm=None, config=None):
        self.db = db
        self.llm = llm
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
        })

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_client_profile(self, client_id: int) -> Optional[ClientProfile]:
        """Resolve a DB client_id to a ClientProfile from config."""
        if not self.config:
            return None
        row = self.db.fetchone("SELECT slug FROM clients WHERE id = ?", (client_id,))
        if not row:
            return None
        for c in self.config.clients:
            if c.slug == row["slug"]:
                return c
        return None

    def _encode_curated_key(self, title: str, url: str, source: str,
                            commentary: str) -> str:
        """Encode curated item data into a composite key string."""
        payload = {
            "title": title[:200],
            "url": url[:500],
            "source": source[:100],
            "commentary": commentary[:500],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _decode_curated_key(self, key: str) -> Dict:
        """Decode a composite key back into item fields."""
        try:
            return json.loads(key)
        except (json.JSONDecodeError, TypeError):
            return {"title": key, "url": "", "source": "", "commentary": ""}

    def _store_curated_item(self, client_id: int, title: str, url: str,
                            source: str, commentary: str,
                            confidence: float = 0.7, subreddit: str = None):
        """Persist a curated content item in learned_strategies."""
        key = self._encode_curated_key(title, url, source, commentary)
        self.db.upsert_strategy(
            strategy_type="curated_content",
            key=key,
            value=confidence,
            confidence=confidence,
            sample_count=1,
            client_id=client_id,
            subreddit=subreddit,
        )

    def _get_existing_urls(self, client_id: int) -> set:
        """Return set of URLs already curated for this client."""
        rows = self.db.get_strategies("curated_content", client_id=client_id)
        urls = set()
        for r in rows:
            decoded = self._decode_curated_key(r.get("key", ""))
            u = decoded.get("url", "")
            if u:
                urls.add(u)
        return urls

    # ── Web Scraping ─────────────────────────────────────────────────

    def scrape_news_headlines(self, topics: List[str],
                              max_results: int = 10) -> List[Dict]:
        """Scrape recent news/blog headlines from Google News RSS.

        Returns list of dicts: title, url, source, topic
        """
        all_articles: List[Dict] = []
        for topic in topics[:4]:
            try:
                rss_url = (
                    f"https://news.google.com/rss/search?"
                    f"q={quote_plus(topic)}&hl=en"
                )
                resp = self._session.get(rss_url, timeout=_HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.find_all("item")[:max_results]:
                    title_tag = item.find("title")
                    link_tag = item.find("link")
                    source_tag = item.find("source")
                    if title_tag and link_tag:
                        title_text = title_tag.get_text(strip=True)
                        link_text = (
                            link_tag.get_text(strip=True)
                            if link_tag.string
                            else str(link_tag.next_sibling).strip()
                        )
                        all_articles.append({
                            "title": title_text,
                            "url": link_text,
                            "source": (
                                source_tag.get_text(strip=True) if source_tag else ""
                            ),
                            "topic": topic,
                        })
                time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                logger.debug(f"News scrape failed for '{topic}': {e}")

        return all_articles

    def scrape_subreddit_hot(self, subreddit: str,
                             limit: int = 15) -> List[Dict]:
        """Scrape hot posts from a subreddit (public JSON API)."""
        try:
            url = f"https://old.reddit.com/r/{subreddit}/hot.json?limit={limit}"
            resp = self._session.get(url, timeout=_HTTP_TIMEOUT)
            if resp.status_code != 200:
                return []

            data = resp.json()
            posts = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                posts.append({
                    "title": post.get("title", ""),
                    "url": (
                        f"https://reddit.com{post.get('permalink', '')}"
                    ),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "author": post.get("author", ""),
                    "is_self": post.get("is_self", True),
                    "external_url": (
                        post.get("url", "") if not post.get("is_self") else ""
                    ),
                })
            return posts
        except Exception as e:
            logger.debug(f"Subreddit scrape failed for r/{subreddit}: {e}")
            return []

    def scrape_page_content(self, url: str,
                            max_chars: int = 2000) -> Optional[str]:
        """Extract main text from a web page for LLM summarisation."""
        try:
            resp = self._session.get(url, timeout=_HTTP_TIMEOUT)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()

            content = (
                soup.find("article") or soup.find("main") or soup.find("body")
            )
            if not content:
                return None

            text = content.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:max_chars]
        except Exception as e:
            logger.debug(f"Page scrape failed for {url}: {e}")
            return None

    # ── Public API ───────────────────────────────────────────────────

    def curate_content(self, client_id: int):
        """Run a curation cycle: discover articles, generate commentary,
        and store ready-to-share items.

        Idempotent — already-stored URLs are skipped.
        """
        client = self._get_client_profile(client_id)
        if not client:
            logger.warning(f"curate_content: client_id={client_id} not found")
            return

        logger.info(
            f"Content curation starting for '{client.name}' (id={client_id})"
        )

        existing_urls = self._get_existing_urls(client_id)

        # Build search topics from client keywords / industry
        keywords = list(client.keywords or [])
        topics = keywords[:4] if keywords else [client.industry]

        # Step 1: Discover articles
        articles = self.scrape_news_headlines(topics, max_results=8)

        # Also check link-posts in target subreddits for external articles
        for sub in list(client.target_subreddits or [])[:3]:
            try:
                posts = self.scrape_subreddit_hot(sub, limit=20)
                for p in posts:
                    ext_url = p.get("external_url", "")
                    if ext_url and not ext_url.startswith("https://reddit.com"):
                        articles.append({
                            "title": p.get("title", ""),
                            "url": ext_url,
                            "source": f"r/{sub}",
                            "topic": client.industry,
                        })
                time.sleep(random.uniform(1, 2))
            except Exception:
                pass

        # Deduplicate & filter already-curated
        seen: set = set()
        fresh: List[Dict] = []
        for a in articles:
            url = a.get("url", "")
            title = a.get("title", "")
            if not url or not title:
                continue
            if url in existing_urls or url in seen:
                continue
            seen.add(url)
            fresh.append(a)

        if not fresh:
            logger.info(f"No new articles found for '{client.name}'")
            return

        # Step 2: Generate commentary for top articles
        curated_count = 0
        for article in fresh[:8]:
            try:
                commentary = self._generate_commentary(
                    client, article
                )
                if commentary:
                    self._store_curated_item(
                        client_id=client_id,
                        title=article["title"],
                        url=article["url"],
                        source=article.get("source", ""),
                        commentary=commentary,
                        confidence=0.7,
                    )
                    curated_count += 1
                time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                logger.debug(f"Commentary generation failed: {e}")

        logger.info(
            f"Curated {curated_count} items for '{client.name}'"
        )

        # Step 3: Expire stale items
        self._expire_old_items(client_id)

    def get_curated_content(self, client_id: int,
                            limit: int = 10) -> List[Dict]:
        """Return ready-to-share curated items with commentary.

        Each item is a dict with: title, url, source, commentary, confidence.
        """
        rows = self.db.get_strategies("curated_content", client_id=client_id)

        # Filter by age
        cutoff = (
            datetime.utcnow() - timedelta(hours=_CURATED_TTL_HOURS)
        ).isoformat()

        items: List[Dict] = []
        for r in rows:
            updated = r.get("updated_at", "")
            if updated and updated < cutoff:
                continue
            decoded = self._decode_curated_key(r.get("key", ""))
            if not decoded.get("url"):
                continue
            items.append({
                "id": r.get("id"),
                "title": decoded.get("title", ""),
                "url": decoded.get("url", ""),
                "source": decoded.get("source", ""),
                "commentary": decoded.get("commentary", ""),
                "confidence": r.get("confidence", 0.5),
                "updated_at": updated,
            })

        # Sort by confidence descending
        items.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return items[:limit]

    def mark_shared(self, item_id: int):
        """Lower confidence of a shared item so it's deprioritised."""
        try:
            self.db._execute_write(
                "UPDATE learned_strategies SET confidence = confidence * 0.3, "
                "updated_at = datetime('now') WHERE id = ?",
                (item_id,),
            )
        except Exception:
            pass

    # ── Commentary Generation ────────────────────────────────────────

    def _generate_commentary(self, client: ClientProfile,
                             article: Dict) -> Optional[str]:
        """Use LLM to generate value-add commentary for an article."""
        if not self.llm:
            return None

        title = article.get("title", "")
        url = article.get("url", "")
        source = article.get("source", "")

        # Optionally scrape article text for richer context
        snippet = ""
        try:
            page_text = self.scrape_page_content(url, max_chars=1000)
            if page_text:
                snippet = page_text[:500]
        except Exception:
            pass

        context = f"Title: {title}\nSource: {source}\n"
        if snippet:
            context += f"Excerpt: {snippet}\n"

        prompt = (
            f"You are a knowledgeable person in the {client.industry} industry "
            f"in {client.service_area}.  Here's a recent article:\n\n"
            f"{context}\n"
            "Write a brief, casual 2-3 sentence commentary that:\n"
            "1. Adds genuine value or personal perspective\n"
            "2. Sounds like a real Reddit user sharing something interesting\n"
            "3. Is NOT promotional — just sharing useful info\n"
            "4. Could work as a Reddit post body or comment\n\n"
            "Just the commentary, nothing else."
        )

        try:
            result = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "You write casual, genuine Reddit-style commentary. "
                    "No marketing speak.  Sound like a helpful community member."
                ),
                max_tokens=200,
            )
            # Basic cleanup
            result = result.strip().strip('"')
            if len(result) < 20:
                return None
            return result
        except Exception as e:
            logger.debug(f"Commentary generation LLM error: {e}")
            return None

    # ── Content Ideas ────────────────────────────────────────────────

    def get_content_ideas(self, client_id: int,
                          max_ideas: int = 5) -> List[Dict]:
        """Return a mix of content ideas combining curated articles with
        trending subreddit topics.

        Each idea dict has: type, title, url (opt), commentary (opt).
        """
        client = self._get_client_profile(client_id)
        if not client:
            return []

        ideas: List[Dict] = []

        # Curated articles
        curated = self.get_curated_content(client_id, limit=3)
        for item in curated:
            ideas.append({
                "type": "article_share",
                "title": item["title"],
                "url": item["url"],
                "commentary": item["commentary"],
                "source": item["source"],
            })

        # Trending topics from subreddits (scrape a couple of subs)
        subs = list(client.target_subreddits or [])[:2]
        for sub in subs:
            try:
                posts = self.scrape_subreddit_hot(sub, limit=10)
                # Pick high-engagement posts as discussion seeds
                hot_posts = sorted(
                    posts, key=lambda p: p.get("score", 0), reverse=True
                )[:2]
                for p in hot_posts:
                    ideas.append({
                        "type": "trending_topic",
                        "title": p.get("title", ""),
                        "url": p.get("url", ""),
                        "subreddit": sub,
                    })
            except Exception:
                pass

        random.shuffle(ideas)
        return ideas[:max_ideas]

    # ── Expiry ───────────────────────────────────────────────────────

    def _expire_old_items(self, client_id: int):
        """Remove curated items older than the TTL."""
        cutoff = (
            datetime.utcnow() - timedelta(hours=_CURATED_TTL_HOURS)
        ).isoformat()
        try:
            self.db._execute_write(
                "DELETE FROM learned_strategies "
                "WHERE strategy_type = 'curated_content' "
                "AND client_id = ? AND updated_at < ?",
                (client_id, cutoff),
            )
        except Exception:
            pass
