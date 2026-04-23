"""Research & Intelligence Engine — builds per-client knowledge bases.

Periodic research cycles:
1. Subreddit trend analysis (top posts, recurring themes, hot questions)
2. Industry news scanning via web scraping
3. LLM synthesis of raw data into actionable talking points
4. Knowledge base management via learned_strategies table

Adapted from MiloAgent's ResearchEngine for RedditPilot's multi-client
architecture.  All findings are persisted as learned_strategies rows with
strategy_type='research_finding'.
"""

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from ..core.database import Database
from ..core.config import ClientProfile

logger = logging.getLogger("redditpilot.research")

# ── Constants ────────────────────────────────────────────────────────
# TTLs in hours — findings older than this are considered stale
_TTL_HOURS = {
    "trend": 48,
    "question": 48,
    "news": 72,
    "talking_point": 168,
    "competitor": 168,
}

MAX_SUBREDDITS_PER_CYCLE = 6
_HTTP_TIMEOUT = 15

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


class ResearchEngine:
    """Builds and maintains a per-client knowledge base of industry trends,
    competitor mentions, and common questions.

    All findings are stored in ``learned_strategies`` with
    ``strategy_type='research_finding'``.  The ``key`` column encodes the
    finding category (trend / question / news / talking_point / competitor)
    and the ``value`` column stores a confidence/relevance weight.

    Usage::

        engine = ResearchEngine(db, llm)
        engine.discover_trends(client_id)          # periodic (every ~12 h)
        ctx = engine.get_relevant_knowledge(client_id, "plumbing")
    """

    def __init__(self, db: Database, llm=None, config=None):
        self.db = db
        self.llm = llm
        self.config = config  # master Config object (has .clients list)
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

    def _resolve_client_id(self, client: ClientProfile) -> Optional[int]:
        row = self.db.fetchone("SELECT id FROM clients WHERE slug = ?", (client.slug,))
        return row["id"] if row else None

    def _store_finding(self, client_id: int, category: str, key_text: str,
                       detail: str, subreddit: str = None,
                       confidence: float = 0.7):
        """Persist a research finding into learned_strategies.

        The ``key`` column is formatted as ``<category>::<key_text>`` to allow
        easy filtering.  ``detail`` goes into a JSON-encoded value stored as
        the strategy's ``value`` (we borrow the numeric column for confidence
        and keep the actual text in ``key``).
        """
        # Encode: strategy_type = 'research_finding'
        # key = '<category>::<short label>::<detail snippet>'
        # value = confidence (float)
        composed_key = f"{category}::{key_text[:80]}::{detail[:200]}"
        self.db.upsert_strategy(
            strategy_type="research_finding",
            key=composed_key,
            value=confidence,
            confidence=confidence,
            sample_count=1,
            client_id=client_id,
            subreddit=subreddit,
        )

    def _get_findings(self, client_id: int, category: str = None,
                      subreddit: str = None, limit: int = 20,
                      max_age_hours: int = None) -> List[Dict]:
        """Retrieve research findings from learned_strategies."""
        sql = "SELECT * FROM learned_strategies WHERE strategy_type = 'research_finding'"
        params: list = []

        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        if category:
            sql += " AND key LIKE ?"
            params.append(f"{category}::%")
        if subreddit:
            sql += " AND subreddit = ?"
            params.append(subreddit)
        if max_age_hours:
            cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()
            sql += " AND updated_at > ?"
            params.append(cutoff)

        sql += " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetchall(sql, tuple(params))
        # Parse the composite key back into parts
        results = []
        for r in rows:
            parts = r["key"].split("::", 2)
            results.append({
                "id": r["id"],
                "category": parts[0] if len(parts) > 0 else "unknown",
                "topic": parts[1] if len(parts) > 1 else "",
                "detail": parts[2] if len(parts) > 2 else "",
                "confidence": r["confidence"],
                "subreddit": r.get("subreddit"),
                "updated_at": r.get("updated_at"),
            })
        return results

    # ── Public API ───────────────────────────────────────────────────

    def discover_trends(self, client_id: int):
        """Run a full research cycle for a single client.

        1. Analyse subreddit trends (hot posts → LLM themes & questions)
        2. Scan industry news headlines
        3. Track competitor mentions
        4. Synthesise talking points from collected data
        """
        client = self._get_client_profile(client_id)
        if not client:
            logger.warning(f"discover_trends: client_id={client_id} not found")
            return

        logger.info(f"Research cycle starting for client '{client.name}' (id={client_id})")

        try:
            self._analyze_subreddit_trends(client_id, client)
        except Exception as e:
            logger.debug(f"Trend analysis failed for {client.name}: {e}")

        try:
            self._scan_industry_news(client_id, client)
        except Exception as e:
            logger.debug(f"News scan failed for {client.name}: {e}")

        try:
            self._track_competitors(client_id, client)
        except Exception as e:
            logger.debug(f"Competitor tracking failed for {client.name}: {e}")

        try:
            self._synthesize_talking_points(client_id, client)
        except Exception as e:
            logger.debug(f"Synthesis failed for {client.name}: {e}")

        # Expire old findings
        try:
            self._expire_old_findings(client_id)
        except Exception:
            pass

        logger.info(f"Research cycle complete for client '{client.name}'")

    def get_relevant_knowledge(self, client_id: int, subreddit: str = None) -> str:
        """Return a formatted context block for injection into content
        generation prompts.

        Pulls recent trends, news, and talking points for the client
        (optionally filtered by subreddit).
        """
        entries: List[str] = []

        # Recent trends (sub-specific if available, then global)
        trends = self._get_findings(
            client_id, category="trend",
            subreddit=subreddit,
            limit=3, max_age_hours=_TTL_HOURS["trend"],
        )
        if len(trends) < 2 and subreddit:
            # Fall back to client-wide trends
            trends += self._get_findings(
                client_id, category="trend",
                limit=3, max_age_hours=_TTL_HOURS["trend"],
            )
        for t in trends[:3]:
            entries.append(f"- Trend: {t['detail']}")

        # Common questions
        questions = self._get_findings(
            client_id, category="question",
            subreddit=subreddit,
            limit=2, max_age_hours=_TTL_HOURS["question"],
        )
        for q in questions[:2]:
            entries.append(f"- Common Q: {q['detail']}")

        # News
        news = self._get_findings(
            client_id, category="news",
            limit=2, max_age_hours=_TTL_HOURS["news"],
        )
        for n in news[:2]:
            entries.append(f"- News: {n['detail']}")

        # Talking points
        points = self._get_findings(
            client_id, category="talking_point",
            limit=2, max_age_hours=_TTL_HOURS["talking_point"],
        )
        for p in points[:2]:
            entries.append(f"- Insight: {p['detail']}")

        if not entries:
            return ""

        # Cap at 6 entries to keep prompts compact
        entries = entries[:6]
        return (
            "CURRENT CONTEXT (reference naturally if relevant, don't force it):\n"
            + "\n".join(entries)
        )

    def get_trending_topics(self, client_id: int) -> List[str]:
        """Return a list of short trending-topic labels for the client."""
        trends = self._get_findings(
            client_id, category="trend",
            limit=10, max_age_hours=_TTL_HOURS["trend"],
        )
        return [t["topic"] for t in trends if t.get("topic")]

    # ── Subreddit Trend Analysis ─────────────────────────────────────

    def _scrape_subreddit_hot(self, subreddit: str, limit: int = 25) -> List[Dict]:
        """Fetch hot posts from a subreddit using Reddit's public JSON API."""
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
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "author": post.get("author", ""),
                    "is_self": post.get("is_self", True),
                    "selftext": (post.get("selftext") or "")[:300],
                    "url": post.get("url", ""),
                })
            return posts
        except Exception as e:
            logger.debug(f"Subreddit scrape failed for r/{subreddit}: {e}")
            return []

    def _analyze_subreddit_trends(self, client_id: int, client: ClientProfile):
        """Fetch hot posts from target subs, extract themes via LLM."""
        if not self.llm:
            return

        subs = list(client.target_subreddits or [])
        if not subs:
            return

        sample = random.sample(subs, min(MAX_SUBREDDITS_PER_CYCLE, len(subs)))

        for sub in sample:
            try:
                posts = self._scrape_subreddit_hot(sub, limit=25)
                if not posts:
                    continue

                # Build summary for LLM
                post_summaries = []
                for p in posts[:15]:
                    title = p.get("title", "")[:120]
                    score = p.get("score", 0)
                    comments = p.get("num_comments", 0)
                    post_summaries.append(
                        f"- [{score} pts, {comments} comments] {title}"
                    )

                if not post_summaries:
                    continue

                prompt = (
                    f"Analyze these top posts from r/{sub} "
                    f"(industry context: {client.industry}):\n"
                    + "\n".join(post_summaries)
                    + "\n\nIdentify:\n"
                    "1. Top 3-5 recurring themes (short labels)\n"
                    "2. Top 3 common questions or pain points\n\n"
                    "Format:\n"
                    "THEMES: theme1, theme2, theme3\n"
                    "QUESTIONS: question1 | question2 | question3"
                )

                result = self.llm.generate(
                    prompt=prompt,
                    system_prompt=(
                        "You analyze Reddit trends. Output only the requested "
                        "format, nothing else."
                    ),
                    max_tokens=250,
                )

                themes, questions = self._parse_trends(result)

                for theme in themes[:5]:
                    self._store_finding(
                        client_id, "trend", theme,
                        f"Trending in r/{sub}: {theme}",
                        subreddit=sub, confidence=0.7,
                    )

                for q in questions[:3]:
                    self._store_finding(
                        client_id, "question", q[:50],
                        f"Common question in r/{sub}: {q}",
                        subreddit=sub, confidence=0.65,
                    )

                time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.debug(f"Trend analysis for r/{sub} failed: {e}")

    @staticmethod
    def _parse_trends(text: str) -> Tuple[List[str], List[str]]:
        """Parse LLM trend output into (themes, questions)."""
        themes: List[str] = []
        questions: List[str] = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("THEMES:"):
                items = line.split(":", 1)[1].strip().split(",")
                themes = [t.strip() for t in items if t.strip()]
            elif line.upper().startswith("QUESTIONS:"):
                items = line.split(":", 1)[1].strip().split("|")
                questions = [q.strip() for q in items if q.strip()]
        return themes, questions

    # ── Industry News Scanning ───────────────────────────────────────

    def _scan_industry_news(self, client_id: int, client: ClientProfile):
        """Scrape Google News RSS for headlines relevant to client keywords."""
        if not self.llm:
            return

        keywords = list(client.keywords or [])
        topics = keywords[:3] if keywords else [client.industry]

        articles: List[Dict] = []
        for topic in topics:
            try:
                rss_url = (
                    f"https://news.google.com/rss/search?"
                    f"q={quote_plus(topic)}&hl=en"
                )
                resp = self._session.get(rss_url, timeout=_HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.find_all("item")[:5]:
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
                        articles.append({
                            "title": title_text,
                            "url": link_text,
                            "source": source_tag.get_text(strip=True) if source_tag else "",
                            "topic": topic,
                        })
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.debug(f"News scrape failed for '{topic}': {e}")

        if not articles:
            return

        # Deduplicate
        seen = set()
        unique = []
        for a in articles:
            t = a.get("title", "")
            if t not in seen:
                seen.add(t)
                unique.append(a)

        # Summarise via LLM
        article_text = "\n".join(
            f"- {a['title']} (from {a.get('source', 'unknown')})"
            for a in unique[:6]
        )

        prompt = (
            f"These are recent news articles relevant to '{client.industry}':\n"
            f"{article_text}\n\n"
            "For each article, give a one-sentence casual takeaway someone "
            "could reference in a Reddit conversation.\n"
            "Format: one takeaway per line, no numbering."
        )

        try:
            result = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "You summarize industry news into casual talking points. "
                    "Be brief and conversational."
                ),
                max_tokens=300,
            )

            for line in result.strip().split("\n"):
                line = line.strip().lstrip("- •")
                if line and len(line) > 20:
                    self._store_finding(
                        client_id, "news", line[:50], line,
                        confidence=0.6,
                    )
        except Exception as e:
            logger.debug(f"News synthesis failed: {e}")

    # ── Competitor Tracking ──────────────────────────────────────────

    def _track_competitors(self, client_id: int, client: ClientProfile):
        """Search target subreddits for mentions of known competitors."""
        competitors = list(client.competitors or [])
        if not competitors:
            return

        subs = list(client.target_subreddits or [])[:3]
        for sub in subs:
            try:
                posts = self._scrape_subreddit_hot(sub, limit=50)
                for comp in competitors:
                    comp_lower = comp.lower()
                    mentions = []
                    for p in posts:
                        text = (
                            f"{p.get('title', '')} {p.get('selftext', '')}"
                        ).lower()
                        if comp_lower in text:
                            mentions.append(p.get("title", "")[:100])

                    if mentions:
                        detail = (
                            f"Competitor '{comp}' mentioned {len(mentions)}x "
                            f"in r/{sub}: {mentions[0]}"
                        )
                        self._store_finding(
                            client_id, "competitor", f"{comp}@{sub}",
                            detail, subreddit=sub, confidence=0.6,
                        )
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.debug(f"Competitor tracking in r/{sub} failed: {e}")

    # ── Insight Synthesis ────────────────────────────────────────────

    def _synthesize_talking_points(self, client_id: int, client: ClientProfile):
        """Use LLM to distil collected research into casual talking points."""
        if not self.llm:
            return

        trends = self._get_findings(client_id, category="trend", limit=6)
        news = self._get_findings(client_id, category="news", limit=4)
        questions = self._get_findings(client_id, category="question", limit=4)

        if not trends and not news and not questions:
            return

        context_items: List[str] = []
        for t in trends[:4]:
            context_items.append(f"Trend: {t['detail']}")
        for n in news[:3]:
            context_items.append(f"News: {n['detail']}")
        for q in questions[:3]:
            context_items.append(f"Question: {q['detail']}")

        prompt = (
            f"Based on this recent research for a {client.industry} business "
            f"in {client.service_area}:\n"
            + "\n".join(context_items)
            + "\n\nGenerate 3-5 casual talking points the business can "
            "reference naturally in Reddit conversations.  Each should be a "
            "natural factoid or observation — NOT promotional.\n"
            "Format: one per line, no numbering."
        )

        try:
            result = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "You create natural conversation topics from research "
                    "data.  Be casual and conversational."
                ),
                max_tokens=300,
            )

            for line in result.strip().split("\n"):
                line = line.strip().lstrip("- •")
                if line and len(line) > 15:
                    self._store_finding(
                        client_id, "talking_point", line[:50], line,
                        confidence=0.75,
                    )
        except Exception as e:
            logger.debug(f"Talking-point synthesis failed: {e}")

    # ── Expiry ───────────────────────────────────────────────────────

    def _expire_old_findings(self, client_id: int):
        """Delete research findings that are past their TTL."""
        for category, ttl_h in _TTL_HOURS.items():
            cutoff = (datetime.utcnow() - timedelta(hours=ttl_h)).isoformat()
            try:
                self.db._execute_write(
                    "DELETE FROM learned_strategies "
                    "WHERE strategy_type = 'research_finding' "
                    "AND key LIKE ? AND client_id = ? AND updated_at < ?",
                    (f"{category}::%", client_id, cutoff),
                )
            except Exception:
                pass
