"""Subreddit Intelligence Engine — discover high-opportunity communities.

Adapted from MiloAgent's subreddit intelligence module for RedditPilot.

Analyzes subreddit metadata to find under-moderated, high-subscriber communities
where RedditPilot clients can become valued contributors.

Uses Reddit's public JSON endpoints (no auth required for reads):
- r/{sub}/about.json            -> subscribers, active_users, description, rules
- r/{sub}/new.json              -> post frequency calculation
- r/{sub}/about/moderators.json -> mod list (may require auth)
- r/{sub}/about/rules.json      -> posting rules

Data is cached in the subreddit_intel table and re-analyzed when stale.
"""

import json
import math
import time
import random
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from statistics import median
from collections import Counter

import requests

from redditpilot.core.database import Database

logger = logging.getLogger("redditpilot.engines.subreddit_intel")

# ── Constants ──────────────────────────────────────────────────────────

REDDIT_BASE = "https://www.reddit.com"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# Default staleness threshold (days) before re-analyzing a subreddit
DEFAULT_STALE_DAYS = 3

# How many posts to fetch for metric calculations
POST_SAMPLE_SIZE = 50

# Scoring weights — tuned for RedditPilot's agency model
SCORE_WEIGHTS = {
    "subscriber_volume": 0.20,
    "post_frequency": 0.20,
    "engagement_level": 0.20,
    "mod_presence": 0.15,
    "competition_level": 0.25,
}


def _random_ua() -> str:
    """Pick a random User-Agent string."""
    return random.choice(USER_AGENTS)


class SubredditIntel:
    """Analyzes subreddits for opportunity scoring.

    Thread-safe: uses a lock around the shared request timestamp and session.

    Usage:
        intel = SubredditIntel(db)
        data = intel.analyze_subreddit("NewTubers")
        best = intel.get_best_subreddits(client_id=1)
    """

    def __init__(
        self,
        db: Database,
        session: Optional[requests.Session] = None,
        request_delay: float = 2.0,
        stale_days: int = DEFAULT_STALE_DAYS,
    ):
        self.db = db
        self.stale_days = stale_days

        # HTTP session — one per instance, thread-safe with lock
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", _random_ua())

        # Rate-limiting state (thread-safe)
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._request_delay = request_delay
        self._backoff_until = 0.0  # Epoch time — when 429 backoff expires

    # ══════════════════════════════════════════════════════════════════
    #  HTTP Layer — rate-limited, 429-aware, rotating User-Agent
    # ══════════════════════════════════════════════════════════════════

    def _throttled_get(
        self, url: str, params: dict = None, timeout: int = 15
    ) -> Optional[requests.Response]:
        """Rate-limited GET with automatic 429 retry and UA rotation.

        Returns None on unrecoverable failure; never raises.
        """
        max_retries = 3
        for attempt in range(max_retries):
            with self._lock:
                # Respect 429 backoff
                now = time.time()
                if now < self._backoff_until:
                    wait = self._backoff_until - now
                    logger.debug(f"429 backoff: sleeping {wait:.1f}s")
                    time.sleep(wait)

                # Respect minimum delay between requests
                elapsed = time.time() - self._last_request_time
                if elapsed < self._request_delay:
                    time.sleep(self._request_delay - elapsed)

                self._last_request_time = time.time()

            try:
                resp = self._session.get(
                    url,
                    params=params,
                    headers={
                        "User-Agent": _random_ua(),
                        "Accept": "application/json",
                    },
                    timeout=timeout,
                )

                if resp.status_code == 429:
                    # Reddit rate limit hit — back off exponentially
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    backoff = min(retry_after * (2 ** attempt), 300)
                    logger.warning(
                        f"429 rate-limited on {url} — backing off {backoff}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    with self._lock:
                        self._backoff_until = time.time() + backoff
                    time.sleep(backoff)
                    continue

                if resp.status_code == 403:
                    logger.debug(f"403 Forbidden: {url}")
                    return resp  # Caller handles 403 (e.g. mod list)

                if resp.status_code != 200:
                    logger.debug(f"HTTP {resp.status_code} for {url}")
                    return resp

                return resp

            except requests.exceptions.Timeout:
                logger.debug(f"Timeout fetching {url} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"Connection error for {url}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error fetching {url}: {e}")
                return None

        logger.warning(f"All {max_retries} retries exhausted for {url}")
        return None

    # ══════════════════════════════════════════════════════════════════
    #  Data Fetching — individual endpoints
    # ══════════════════════════════════════════════════════════════════

    def _fetch_about(self, subreddit: str) -> Optional[Dict]:
        """Fetch subreddit about info: subscribers, active_users, description."""
        resp = self._throttled_get(f"{REDDIT_BASE}/r/{subreddit}/about.json")
        if resp is None or resp.status_code != 200:
            return None

        try:
            raw = resp.json().get("data", {})
        except (ValueError, KeyError):
            return None

        return {
            "subscribers": raw.get("subscribers", 0),
            "active_users": raw.get("accounts_active", 0)
            or raw.get("active_user_count", 0),
            "created_utc": raw.get("created_utc", 0),
            "description": (raw.get("public_description", "") or "")[:500],
            "subreddit_type": raw.get("subreddit_type", "public"),
            "over18": 1 if raw.get("over18") else 0,
            "display_name": raw.get("display_name", subreddit),
            "title": (raw.get("title", "") or "")[:200],
        }

    def _fetch_post_metrics(
        self, subreddit: str, limit: int = POST_SAMPLE_SIZE
    ) -> Dict:
        """Calculate post frequency and engagement from recent posts."""
        metrics: Dict = {
            "posts_per_day": 0.0,
            "avg_hours_between_posts": 999.0,
            "avg_score": 0.0,
            "median_post_score": 0.0,
            "avg_comments_per_post": 0.0,
            "top_themes": [],
            "best_posting_hours": [],
        }

        resp = self._throttled_get(
            f"{REDDIT_BASE}/r/{subreddit}/new.json",
            params={"limit": min(limit, 100)},
        )
        if resp is None or resp.status_code != 200:
            return metrics

        try:
            children = resp.json().get("data", {}).get("children", [])
        except (ValueError, KeyError):
            return metrics

        if len(children) < 2:
            return metrics

        timestamps: List[float] = []
        scores: List[int] = []
        comments: List[int] = []
        hour_scores: Dict[int, List[int]] = {}
        word_counter: Counter = Counter()

        for child in children:
            post = child.get("data", {})
            created = post.get("created_utc", 0)
            if created:
                timestamps.append(created)
            score = post.get("score", 0)
            scores.append(score)
            comments.append(post.get("num_comments", 0))

            # Track per-hour scores for best posting hours
            if created:
                hour = int((created % 86400) / 3600)  # UTC hour
                hour_scores.setdefault(hour, []).append(score)

            # Simple word-frequency themes from titles
            title = post.get("title", "")
            for word in title.lower().split():
                clean = word.strip(".,!?()[]\"'")
                if len(clean) > 4:
                    word_counter[clean] += 1

        # Post frequency
        if len(timestamps) >= 2:
            timestamps.sort(reverse=True)
            gaps = [
                (timestamps[i] - timestamps[i + 1]) / 3600
                for i in range(len(timestamps) - 1)
            ]
            avg_gap = sum(gaps) / len(gaps) if gaps else 999.0
            metrics["avg_hours_between_posts"] = round(avg_gap, 2)

            time_span_hours = (timestamps[0] - timestamps[-1]) / 3600
            if time_span_hours > 0:
                metrics["posts_per_day"] = round(
                    len(timestamps) / (time_span_hours / 24), 2
                )

        # Engagement scores
        if scores:
            metrics["avg_score"] = round(sum(scores) / len(scores), 1)
            metrics["median_post_score"] = round(median(scores), 1)
        if comments:
            metrics["avg_comments_per_post"] = round(
                sum(comments) / len(comments), 1
            )

        # Best posting hours (top 5 by average score)
        if hour_scores:
            hour_avgs = [
                {"hour": h, "avg_score": round(sum(s) / len(s), 1)}
                for h, s in hour_scores.items()
                if len(s) >= 2
            ]
            hour_avgs.sort(key=lambda x: x["avg_score"], reverse=True)
            metrics["best_posting_hours"] = hour_avgs[:5]

        # Top themes (most frequent meaningful words)
        # Filter out very common words
        stopwords = {
            "about", "their", "there", "these", "those", "would", "could",
            "should", "which", "where", "after", "before", "being", "other",
            "through", "between", "people", "think", "every", "really",
            "still", "first", "while", "never", "using", "great",
        }
        themes = [
            word
            for word, count in word_counter.most_common(30)
            if word not in stopwords and count >= 2
        ]
        metrics["top_themes"] = themes[:10]

        return metrics

    def _fetch_mod_info(self, subreddit: str) -> Dict:
        """Fetch moderator count. Returns -1 if access denied."""
        info: Dict = {"mod_count": -1}

        resp = self._throttled_get(
            f"{REDDIT_BASE}/r/{subreddit}/about/moderators.json"
        )
        if resp is None or resp.status_code != 200:
            return info

        try:
            children = resp.json().get("data", {}).get("children", [])
            info["mod_count"] = len(children)
        except (ValueError, KeyError):
            pass

        return info

    def _fetch_rules(self, subreddit: str) -> Dict:
        """Fetch subreddit posting rules."""
        info: Dict = {"posting_rules": "[]"}

        resp = self._throttled_get(
            f"{REDDIT_BASE}/r/{subreddit}/about/rules.json"
        )
        if resp is None or resp.status_code != 200:
            return info

        try:
            data = resp.json()
            rules_raw = data.get("rules", [])
            rules = []
            for r in rules_raw:
                rules.append({
                    "short_name": r.get("short_name", ""),
                    "kind": r.get("kind", "all"),
                    "description": (r.get("description", "") or "")[:200],
                })
            info["posting_rules"] = json.dumps(rules)
        except (ValueError, KeyError):
            pass

        return info

    # ══════════════════════════════════════════════════════════════════
    #  Analysis — single subreddit
    # ══════════════════════════════════════════════════════════════════

    def analyze_subreddit(
        self, name: str, force: bool = False
    ) -> Optional[Dict]:
        """Fetch and analyze metadata for one subreddit.

        If a recent (non-stale) analysis exists in the DB and force=False,
        returns the cached version.

        Returns a dict with all intelligence data, or None on failure.
        """
        name = name.strip().lstrip("r/")
        if not name:
            return None

        # Check cache (staleness check)
        if not force:
            cached = self._get_cached(name)
            if cached is not None:
                logger.debug(f"r/{name}: returning cached intel (analyzed {cached.get('last_analyzed')})")
                return cached

        logger.info(f"Analyzing r/{name} ...")

        # 1. About info (subscribers, active users)
        about = self._fetch_about(name)
        if not about:
            logger.warning(f"r/{name}: failed to fetch about info — skipping")
            return None

        # Skip NSFW or restricted subreddits
        if about.get("over18"):
            logger.info(f"r/{name}: NSFW — skipping")
            return None
        if about.get("subreddit_type") not in ("public", "restricted"):
            logger.info(f"r/{name}: type={about.get('subreddit_type')} — skipping")
            return None

        # 2. Post frequency & engagement
        post_metrics = self._fetch_post_metrics(name)

        # 3. Moderator count
        mod_info = self._fetch_mod_info(name)

        # 4. Posting rules
        rules_info = self._fetch_rules(name)

        # Merge all data
        intel_data = {}
        intel_data.update(about)
        intel_data.update(post_metrics)
        intel_data.update(mod_info)
        intel_data.update(rules_info)

        # 5. Compute opportunity score
        opp_score = self._score_opportunity(intel_data)
        intel_data["opportunity_score"] = opp_score

        # 6. Store in database
        self._store_intel(name, intel_data)

        logger.info(
            f"r/{name}: subs={intel_data['subscribers']:,} "
            f"active={intel_data['active_users']:,} "
            f"ppd={intel_data['posts_per_day']} "
            f"mods={intel_data['mod_count']} "
            f"score={opp_score:.1f}/10"
        )

        return intel_data

    def analyze_batch(
        self, names: List[str], force: bool = False
    ) -> Dict[str, Optional[Dict]]:
        """Analyze multiple subreddits sequentially (rate-limited).

        Returns a dict mapping subreddit name -> intel data (or None).
        """
        results: Dict[str, Optional[Dict]] = {}
        total = len(names)
        for i, name in enumerate(names, 1):
            name = name.strip().lstrip("r/")
            if not name:
                continue
            logger.info(f"Batch analysis [{i}/{total}]: r/{name}")
            results[name] = self.analyze_subreddit(name, force=force)
        return results

    # ══════════════════════════════════════════════════════════════════
    #  Opportunity Scoring (0-10)
    # ══════════════════════════════════════════════════════════════════

    def _score_opportunity(self, data: Dict) -> float:
        """Score a subreddit 0-10 for opportunity.

        Components (weights in SCORE_WEIGHTS):
        - subscriber_volume (20%): higher subscriber count = more reach
        - post_frequency   (20%): moderate frequency = healthy community
        - engagement_level (20%): good engagement = posts get seen
        - mod_presence     (15%): fewer mods = more freedom
        - competition_level(25%): less competition = easier to stand out
        """
        scores: Dict[str, float] = {}

        # 1. Subscriber volume (0-10)
        # log10 scale: 1k->3, 10k->4, 100k->5, 1M->6
        subs = data.get("subscribers", 0)
        if subs > 0:
            log_subs = math.log10(max(subs, 1))
            # Normalize: 1k (3) -> 2.5, 10k (4) -> 5.0, 100k (5) -> 7.5, 1M (6) -> 10
            scores["subscriber_volume"] = min(10.0, max(0, (log_subs - 2) * 2.5))
        else:
            scores["subscriber_volume"] = 0.0

        # 2. Post frequency (0-10)
        # Sweet spot: moderate activity (5-50 posts/day) is ideal
        ppd = data.get("posts_per_day", 0)
        if ppd <= 0.5:
            scores["post_frequency"] = 1.0  # Too dead
        elif ppd <= 2:
            scores["post_frequency"] = 4.0  # Low but alive
        elif ppd <= 10:
            scores["post_frequency"] = 8.0  # Sweet spot
        elif ppd <= 50:
            scores["post_frequency"] = 6.0  # Active, still good
        elif ppd <= 200:
            scores["post_frequency"] = 3.0  # Very busy, posts get buried
        else:
            scores["post_frequency"] = 1.0  # Firehose

        # 3. Engagement level (0-10)
        # Based on average score and comments per post
        avg_score = data.get("avg_score", 0)
        avg_comments = data.get("avg_comments_per_post", 0)

        if avg_score >= 50:
            eng = 9.0
        elif avg_score >= 20:
            eng = 7.0
        elif avg_score >= 5:
            eng = 5.0
        elif avg_score >= 1:
            eng = 3.0
        else:
            eng = 1.0

        # Bonus for comment engagement
        if avg_comments >= 10:
            eng = min(10.0, eng + 1.5)
        elif avg_comments >= 5:
            eng = min(10.0, eng + 1.0)
        elif avg_comments >= 2:
            eng = min(10.0, eng + 0.5)

        scores["engagement_level"] = eng

        # 4. Mod presence (0-10) — fewer mods = more opportunity
        mod_count = data.get("mod_count", -1)
        if mod_count == -1:
            scores["mod_presence"] = 5.0  # Unknown — neutral
        elif mod_count <= 1:
            scores["mod_presence"] = 10.0
        elif mod_count <= 3:
            scores["mod_presence"] = 7.0
        elif mod_count <= 5:
            scores["mod_presence"] = 5.0
        elif mod_count <= 10:
            scores["mod_presence"] = 3.0
        else:
            scores["mod_presence"] = 1.5

        # 5. Competition level (0-10)
        # Low active/subscriber ratio = underserved community = opportunity
        active = data.get("active_users", 0)
        if subs > 0 and active > 0:
            ratio = active / subs
            if ratio < 0.001:
                scores["competition_level"] = 10.0  # Very underserved
            elif ratio < 0.003:
                scores["competition_level"] = 8.0
            elif ratio < 0.005:
                scores["competition_level"] = 6.0
            elif ratio < 0.01:
                scores["competition_level"] = 4.0
            elif ratio < 0.05:
                scores["competition_level"] = 2.5
            else:
                scores["competition_level"] = 1.0  # Very competitive
        else:
            scores["competition_level"] = 5.0  # Unknown

        # Weighted sum
        total = sum(
            scores.get(dim, 0) * weight
            for dim, weight in SCORE_WEIGHTS.items()
        )

        return round(min(total, 10.0), 2)

    def _compute_relevance(
        self, intel_data: Dict, keywords: List[str]
    ) -> float:
        """Compute keyword relevance score (0-10) between subreddit and keywords."""
        if not keywords:
            return 5.0  # No keywords to match — neutral

        sub_text = " ".join([
            intel_data.get("description", ""),
            intel_data.get("display_name", ""),
            intel_data.get("title", ""),
            " ".join(intel_data.get("top_themes", [])),
        ]).lower()

        keywords_lower = [kw.lower().strip() for kw in keywords if kw.strip()]
        if not keywords_lower:
            return 5.0

        matches = sum(1 for kw in keywords_lower if kw in sub_text)
        ratio = matches / len(keywords_lower)

        if ratio >= 0.5:
            return 10.0
        elif ratio >= 0.3:
            return 8.0
        elif ratio >= 0.15:
            return 6.0
        elif matches >= 1:
            return 4.0
        return 1.0

    # ══════════════════════════════════════════════════════════════════
    #  Cache / Staleness
    # ══════════════════════════════════════════════════════════════════

    def _get_cached(self, subreddit: str) -> Optional[Dict]:
        """Return cached intel if it exists and is not stale. Otherwise None."""
        row = self.db.get_subreddit_intel(subreddit)
        if row is None:
            return None

        # Check staleness
        last_analyzed = row.get("last_analyzed")
        if not last_analyzed:
            return None

        try:
            analyzed_dt = datetime.fromisoformat(last_analyzed)
            cutoff = datetime.utcnow() - timedelta(days=self.stale_days)
            if analyzed_dt < cutoff:
                logger.debug(f"r/{subreddit}: stale (analyzed {last_analyzed})")
                return None
        except (ValueError, TypeError):
            return None

        # Deserialize JSON fields
        result = dict(row)
        for json_field in ("posting_rules", "top_themes", "best_posting_hours", "metadata"):
            val = result.get(json_field)
            if val and isinstance(val, str):
                try:
                    result[json_field] = json.loads(val)
                except (ValueError, TypeError):
                    pass

        return result

    def _store_intel(self, subreddit: str, data: Dict):
        """Write intelligence data to the subreddit_intel table."""
        # Prepare fields matching the DB schema
        db_fields = {
            "subscribers": data.get("subscribers", 0),
            "active_users": data.get("active_users", 0),
            "posts_per_day": data.get("posts_per_day", 0.0),
            "avg_score": data.get("avg_score", 0.0),
            "avg_comments_per_post": data.get("avg_comments_per_post", 0.0),
            "mod_count": data.get("mod_count", -1),
            "opportunity_score": data.get("opportunity_score", 0.0),
            "relevance_score": data.get("relevance_score", 0.0),
            "posting_rules": (
                data["posting_rules"]
                if isinstance(data.get("posting_rules"), str)
                else json.dumps(data.get("posting_rules", []))
            ),
            "top_themes": json.dumps(data.get("top_themes", [])),
            "best_posting_hours": json.dumps(data.get("best_posting_hours", [])),
            "metadata": json.dumps({
                "description": data.get("description", ""),
                "title": data.get("title", ""),
                "display_name": data.get("display_name", ""),
                "subreddit_type": data.get("subreddit_type", ""),
                "over18": data.get("over18", 0),
                "created_utc": data.get("created_utc", 0),
                "avg_hours_between_posts": data.get("avg_hours_between_posts", 0),
                "median_post_score": data.get("median_post_score", 0),
            }),
        }

        self.db.upsert_subreddit_intel(subreddit, **db_fields)

    # ══════════════════════════════════════════════════════════════════
    #  Staleness Check — find & refresh stale entries
    # ══════════════════════════════════════════════════════════════════

    def refresh_stale(self, limit: int = 10) -> List[str]:
        """Re-analyze subreddits whose intel is older than stale_days.

        Returns list of subreddit names that were refreshed.
        """
        stale_hours = self.stale_days * 24
        stale_rows = self.db.get_stale_subreddit_intel(
            hours=stale_hours, limit=limit
        )
        refreshed = []
        for row in stale_rows:
            name = row.get("subreddit")
            if name:
                result = self.analyze_subreddit(name, force=True)
                if result is not None:
                    refreshed.append(name)

        if refreshed:
            logger.info(f"Refreshed {len(refreshed)} stale subreddits: {refreshed}")
        return refreshed

    # ══════════════════════════════════════════════════════════════════
    #  Client-Aware Best Subreddits
    # ══════════════════════════════════════════════════════════════════

    def get_best_subreddits(
        self,
        client_id: int,
        limit: int = 20,
    ) -> List[Dict]:
        """Get the best subreddits for a specific client.

        Combines opportunity score with keyword relevance to rank subreddits.

        Steps:
        1. Load client profile (keywords, industry, target_subreddits).
        2. Get all analyzed subreddits from DB.
        3. Score each for keyword relevance to this client.
        4. Compute combined_score = 0.6 * opportunity + 0.4 * relevance.
        5. Return top N ranked results.
        """
        # Load client info
        client = self.db.fetchone(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        )
        if not client:
            logger.warning(f"Client id={client_id} not found")
            return []

        # Build keyword list from client profile
        keywords = self._extract_client_keywords(client)

        # Get all analyzed subreddits
        all_intel = self.db.get_top_subreddit_intel(limit=200)
        if not all_intel:
            return []

        # Score each subreddit for relevance to this client
        ranked: List[Tuple[float, Dict]] = []
        for row in all_intel:
            intel_data = dict(row)

            # Deserialize JSON fields for relevance matching
            for json_field in ("top_themes", "best_posting_hours", "metadata", "posting_rules"):
                val = intel_data.get(json_field)
                if val and isinstance(val, str):
                    try:
                        intel_data[json_field] = json.loads(val)
                    except (ValueError, TypeError):
                        pass

            # Extract metadata fields for broader text matching
            meta = intel_data.get("metadata", {})
            if isinstance(meta, dict):
                intel_data.setdefault("description", meta.get("description", ""))
                intel_data.setdefault("title", meta.get("title", ""))
                intel_data.setdefault("display_name", meta.get("display_name", ""))

            relevance = self._compute_relevance(intel_data, keywords)
            opp_score = intel_data.get("opportunity_score", 0)

            # Combined score: weighted blend
            combined = 0.6 * opp_score + 0.4 * relevance
            intel_data["relevance_score"] = round(relevance, 2)
            intel_data["combined_score"] = round(combined, 2)

            ranked.append((combined, intel_data))

        # Sort by combined score descending
        ranked.sort(key=lambda x: x[0], reverse=True)

        # Update relevance_score in DB for the top results
        for _, intel_data in ranked[:limit]:
            sub_name = intel_data.get("subreddit", "")
            if sub_name:
                try:
                    self.db.upsert_subreddit_intel(
                        sub_name,
                        relevance_score=intel_data["relevance_score"],
                    )
                except Exception:
                    pass  # Non-critical

        return [item[1] for item in ranked[:limit]]

    def _extract_client_keywords(self, client: Dict) -> List[str]:
        """Extract all relevant keywords from a client profile."""
        keywords = []

        # Direct keywords (could be JSON string or already a list)
        raw_keywords = client.get("keywords", "")
        if isinstance(raw_keywords, str):
            try:
                parsed = json.loads(raw_keywords)
                if isinstance(parsed, list):
                    keywords.extend(parsed)
            except (ValueError, TypeError):
                # Maybe comma-separated
                if raw_keywords:
                    keywords.extend(
                        kw.strip() for kw in raw_keywords.split(",") if kw.strip()
                    )
        elif isinstance(raw_keywords, list):
            keywords.extend(raw_keywords)

        # Industry as a keyword
        industry = client.get("industry", "")
        if industry:
            keywords.append(industry)

        # Service area
        service_area = client.get("service_area", "")
        if service_area:
            keywords.append(service_area)

        # Client name (might match niche subreddits)
        name = client.get("name", "")
        if name:
            keywords.append(name)

        return [kw for kw in keywords if kw]

    # ══════════════════════════════════════════════════════════════════
    #  Convenience Queries
    # ══════════════════════════════════════════════════════════════════

    def get_top_opportunities(self, limit: int = 20) -> List[Dict]:
        """Get highest-scored subreddits from DB."""
        return self.db.get_top_subreddit_intel(limit=limit)

    def get_intel(self, subreddit: str) -> Optional[Dict]:
        """Get cached intelligence for a single subreddit."""
        return self.db.get_subreddit_intel(subreddit)

    def get_stale_subreddits(self, limit: int = 10) -> List[Dict]:
        """Get subreddits needing re-analysis."""
        stale_hours = self.stale_days * 24
        return self.db.get_stale_subreddit_intel(hours=stale_hours, limit=limit)
