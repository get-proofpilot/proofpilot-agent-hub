"""
RedditPilot Ban Detector
Multi-indicator shadowban and account restriction detection using
Reddit's public JSON API. No authentication required.

Adapted from MiloAgent's ban_detector.py with enhanced confidence
scoring, thread-safety, async support, and structured recommendations.
"""

import logging
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("redditpilot.bandetect")

# Rotating User-Agent pool to avoid fingerprinting on unauthenticated requests.
# Mixed OS/browser combos for realistic diversity.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 "
    "Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 "
    "Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Confidence levels for detection results
CONFIDENCE_NONE = "none"
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

# Indicator keys used in result dicts
INDICATOR_PROFILE_404 = "profile_404"
INDICATOR_LOW_SCORES = "all_low_scores"
INDICATOR_REMOVED_COMMENTS = "removed_comments"
INDICATOR_HIDDEN_PERMALINKS = "hidden_permalinks"

# Recommendations returned with results
RECOMMENDATION_SAFE = "Account appears healthy. No action needed."
RECOMMENDATION_MONITOR = "Possible restrictions detected. Monitor closely and reduce activity."
RECOMMENDATION_STOP = "Likely shadowbanned. Stop posting and switch to a different account."
RECOMMENDATION_SUSPENDED = "Account is suspended or deleted. Remove from rotation immediately."


def _get_headers() -> Dict[str, str]:
    """Return request headers with a randomly selected User-Agent."""
    return {"User-Agent": random.choice(_USER_AGENTS)}


class BanDetector:
    """Detects Reddit shadowbans and account restrictions.

    Uses Reddit's public JSON API (no authentication required) to check
    multiple ban indicators. Requires 2+ indicators for high-confidence
    detection to avoid false positives.

    Thread-safe: all mutable state is protected by a lock. Results are
    cached per-username with a configurable TTL to avoid hammering the API.

    Usage::

        detector = BanDetector()
        result = detector.check_shadowban("some_username")

        if result["is_shadowbanned"]:
            print(f"Banned! Confidence: {result['confidence']}")
            print(f"Recommendation: {result['recommendation']}")
            for ind in result["indicators"]:
                print(f"  - {ind['name']}: {ind['detail']}")
    """

    def __init__(
        self,
        request_timeout: int = 10,
        permalink_timeout: int = 8,
        max_permalink_checks: int = 3,
        min_comments_for_check: int = 3,
        cache_ttl_seconds: int = 300,
    ):
        """Initialize the ban detector.

        Args:
            request_timeout: Timeout in seconds for profile/comment API calls.
            permalink_timeout: Timeout in seconds for permalink verification.
            max_permalink_checks: Max comment permalinks to verify (rate-limited).
            min_comments_for_check: Minimum comments needed for reliable analysis.
            cache_ttl_seconds: How long to cache results per username (seconds).
        """
        self._request_timeout = request_timeout
        self._permalink_timeout = permalink_timeout
        self._max_permalink_checks = max_permalink_checks
        self._min_comments_for_check = min_comments_for_check
        self._cache_ttl = cache_ttl_seconds

        # Thread-safe cache: username -> (result_dict, timestamp)
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────

    def check_shadowban(self, username: str, force: bool = False) -> Dict:
        """Check a Reddit account for shadowban indicators.

        Runs multiple detection checks and aggregates results into a
        structured dict with confidence scoring.

        Args:
            username: Reddit username to check (without u/ prefix).
            force: If True, bypass the cache and run a fresh check.

        Returns:
            Dict with keys:
                - is_shadowbanned (bool): True if ban is likely.
                - confidence (str): 'none', 'low', 'medium', or 'high'.
                - indicators (list[dict]): Each has 'name' and 'detail'.
                - recommendation (str): Human-readable action to take.
                - checked_at (str): ISO timestamp of when check ran.
                - username (str): The username that was checked.
        """
        # Check cache first (thread-safe)
        if not force:
            cached = self._get_cached(username)
            if cached is not None:
                return cached

        result = self._run_checks(username)

        # Cache the result
        with self._lock:
            self._cache[username] = (result, time.monotonic())

        return result

    def check_multiple(self, usernames: List[str], force: bool = False) -> Dict[str, Dict]:
        """Check multiple usernames and return a mapping of results.

        Args:
            usernames: List of Reddit usernames to check.
            force: If True, bypass cache for all.

        Returns:
            Dict mapping username -> result dict.
        """
        results = {}
        for username in usernames:
            results[username] = self.check_shadowban(username, force=force)
        return results

    def clear_cache(self, username: Optional[str] = None):
        """Clear cached results.

        Args:
            username: If provided, clear only that user's cache.
                      If None, clear all cached results.
        """
        with self._lock:
            if username:
                self._cache.pop(username, None)
            else:
                self._cache.clear()

    # ── Core Detection Logic ─────────────────────────────────────────

    def _run_checks(self, username: str) -> Dict:
        """Execute all shadowban detection checks for a username.

        Returns a fully populated result dict.
        """
        indicators: List[Dict[str, str]] = []

        result = {
            "is_shadowbanned": False,
            "confidence": CONFIDENCE_NONE,
            "indicators": indicators,
            "recommendation": RECOMMENDATION_SAFE,
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "username": username,
        }

        try:
            # ── Check 1: Profile accessibility ───────────────────────
            profile_status = self._check_profile(username)

            if profile_status == 404:
                indicators.append({
                    "name": INDICATOR_PROFILE_404,
                    "detail": "User profile returns 404 (suspended or deleted).",
                })
                # Profile 404 is definitive — skip further checks
                result["is_shadowbanned"] = True
                result["confidence"] = CONFIDENCE_HIGH
                result["recommendation"] = RECOMMENDATION_SUSPENDED
                return result

            if profile_status != 200:
                # API returned unexpected status; can't make a determination
                logger.debug(
                    "u/%s: profile check returned %d, inconclusive",
                    username, profile_status,
                )
                return result

            # ── Check 2–4: Comment-based indicators ──────────────────
            comments = self._fetch_recent_comments(username)

            if comments is None:
                # Failed to fetch comments; return what we have
                logger.debug("u/%s: could not fetch comments", username)
                return result

            if len(comments) < self._min_comments_for_check:
                # Not enough data for reliable detection
                logger.debug(
                    "u/%s: only %d comments, need %d for analysis",
                    username, len(comments), self._min_comments_for_check,
                )
                return result

            # Check 2: All comments have score <= 1
            low_score_count = sum(
                1 for c in comments if c.get("score", 1) <= 1
            )
            if low_score_count == len(comments):
                indicators.append({
                    "name": INDICATOR_LOW_SCORES,
                    "detail": (
                        f"All {len(comments)} recent comments have "
                        f"score <= 1 (no engagement)."
                    ),
                })

            # Check 3: Comments removed or author deleted
            removed_count = sum(
                1 for c in comments
                if c.get("body") in ("[removed]", "[deleted]")
                or c.get("author") == "[deleted]"
            )
            if removed_count >= 2:
                indicators.append({
                    "name": INDICATOR_REMOVED_COMMENTS,
                    "detail": (
                        f"{removed_count}/{len(comments)} comments "
                        f"appear removed or deleted."
                    ),
                })

            # Check 4: Comment permalinks return 404 (hidden from threads)
            hidden_count = self._check_permalink_visibility(comments)
            if hidden_count >= 2:
                indicators.append({
                    "name": INDICATOR_HIDDEN_PERMALINKS,
                    "detail": (
                        f"{hidden_count}/{self._max_permalink_checks} "
                        f"comment permalinks return 404 (hidden)."
                    ),
                })

            # ── Aggregate confidence ─────────────────────────────────
            num_indicators = len(indicators)

            if num_indicators >= 2:
                result["is_shadowbanned"] = True
                result["confidence"] = CONFIDENCE_HIGH
                result["recommendation"] = RECOMMENDATION_STOP
            elif num_indicators == 1:
                result["confidence"] = CONFIDENCE_LOW
                result["recommendation"] = RECOMMENDATION_MONITOR
            else:
                result["confidence"] = CONFIDENCE_NONE
                result["recommendation"] = RECOMMENDATION_SAFE

        except Exception as exc:
            # API errors are NOT indicators — return inconclusive
            logger.error("Shadowban check failed for u/%s: %s", username, exc)

        return result

    # ── Individual Check Methods ─────────────────────────────────────

    def _check_profile(self, username: str) -> int:
        """Check if user profile is accessible via public JSON API.

        Args:
            username: Reddit username.

        Returns:
            HTTP status code (200 = OK, 404 = suspended/deleted).
        """
        resp = requests.get(
            f"https://www.reddit.com/user/{username}/about.json",
            headers=_get_headers(),
            timeout=self._request_timeout,
        )
        return resp.status_code

    def _fetch_recent_comments(
        self, username: str, limit: int = 10
    ) -> Optional[List[Dict]]:
        """Fetch recent comments via Reddit's public JSON API.

        Args:
            username: Reddit username.
            limit: Maximum number of comments to fetch.

        Returns:
            List of comment data dicts, or None if the request failed.
        """
        resp = requests.get(
            f"https://www.reddit.com/user/{username}/comments.json"
            f"?limit={limit}&sort=new",
            headers=_get_headers(),
            timeout=self._request_timeout,
        )

        if resp.status_code != 200:
            logger.debug(
                "u/%s: comments fetch returned %d", username, resp.status_code
            )
            return None

        children = resp.json().get("data", {}).get("children", [])
        return [c["data"] for c in children if c.get("kind") == "t1"]

    def _check_permalink_visibility(self, comments: List[Dict]) -> int:
        """Check if comment permalinks are visible in their threads.

        Shadowbanned users' comments often return 404 when accessed
        directly, even though the user profile still shows them.

        Args:
            comments: List of comment data dicts from the JSON API.

        Returns:
            Number of comments whose permalinks returned 404.
        """
        hidden_count = 0
        checked = 0

        for comment in comments:
            if checked >= self._max_permalink_checks:
                break

            permalink = comment.get("permalink")
            if not permalink:
                continue

            try:
                resp = requests.get(
                    f"https://www.reddit.com{permalink}.json",
                    headers=_get_headers(),
                    timeout=self._permalink_timeout,
                )
                if resp.status_code == 404:
                    hidden_count += 1
                checked += 1
            except requests.RequestException:
                # Network errors are not indicators; skip this permalink
                pass

        return hidden_count

    # ── Cache Management ─────────────────────────────────────────────

    def _get_cached(self, username: str) -> Optional[Dict]:
        """Return a cached result if fresh, otherwise None.

        Thread-safe: acquires the lock for the cache lookup.
        """
        with self._lock:
            entry = self._cache.get(username)
            if entry is None:
                return None

            result, timestamp = entry
            if (time.monotonic() - timestamp) > self._cache_ttl:
                # Expired — remove and return None
                del self._cache[username]
                return None

            return result


# ── Async Support ────────────────────────────────────────────────────

class AsyncBanDetector:
    """Async variant of BanDetector using aiohttp for non-blocking checks.

    Drop-in replacement for async codepaths. Same result format as
    BanDetector.

    Usage::

        detector = AsyncBanDetector()
        result = await detector.check_shadowban("some_username")
    """

    def __init__(
        self,
        request_timeout: int = 10,
        permalink_timeout: int = 8,
        max_permalink_checks: int = 3,
        min_comments_for_check: int = 3,
        cache_ttl_seconds: int = 300,
    ):
        """Initialize the async ban detector.

        Args:
            request_timeout: Timeout in seconds for profile/comment API calls.
            permalink_timeout: Timeout in seconds for permalink verification.
            max_permalink_checks: Max comment permalinks to verify.
            min_comments_for_check: Minimum comments needed for analysis.
            cache_ttl_seconds: How long to cache results per username.
        """
        self._request_timeout = request_timeout
        self._permalink_timeout = permalink_timeout
        self._max_permalink_checks = max_permalink_checks
        self._min_comments_for_check = min_comments_for_check
        self._cache_ttl = cache_ttl_seconds

        # asyncio.Lock is created lazily to avoid binding to a loop at init
        self._lock: Optional[object] = None
        self._cache: Dict[str, tuple] = {}

    async def _get_lock(self):
        """Lazily create an asyncio.Lock bound to the current event loop."""
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()
        return self._lock

    async def check_shadowban(self, username: str, force: bool = False) -> Dict:
        """Async shadowban check with the same result format as BanDetector.

        Args:
            username: Reddit username to check.
            force: If True, bypass the cache.

        Returns:
            Structured result dict (same format as BanDetector.check_shadowban).
        """
        if not force:
            cached = await self._get_cached(username)
            if cached is not None:
                return cached

        result = await self._run_checks(username)

        lock = await self._get_lock()
        async with lock:
            self._cache[username] = (result, time.monotonic())

        return result

    async def _run_checks(self, username: str) -> Dict:
        """Execute all detection checks asynchronously."""
        import aiohttp

        indicators: List[Dict[str, str]] = []
        result = {
            "is_shadowbanned": False,
            "confidence": CONFIDENCE_NONE,
            "indicators": indicators,
            "recommendation": RECOMMENDATION_SAFE,
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "username": username,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self._request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:

                # Check 1: Profile accessibility
                async with session.get(
                    f"https://www.reddit.com/user/{username}/about.json",
                    headers=_get_headers(),
                ) as resp:
                    profile_status = resp.status

                if profile_status == 404:
                    indicators.append({
                        "name": INDICATOR_PROFILE_404,
                        "detail": "User profile returns 404 (suspended or deleted).",
                    })
                    result["is_shadowbanned"] = True
                    result["confidence"] = CONFIDENCE_HIGH
                    result["recommendation"] = RECOMMENDATION_SUSPENDED
                    return result

                if profile_status != 200:
                    return result

                # Check 2–4: Comment-based indicators
                comment_timeout = aiohttp.ClientTimeout(total=self._request_timeout)
                async with aiohttp.ClientSession(timeout=comment_timeout) as csession:
                    async with csession.get(
                        f"https://www.reddit.com/user/{username}/comments.json"
                        f"?limit=10&sort=new",
                        headers=_get_headers(),
                    ) as cresp:
                        if cresp.status != 200:
                            return result
                        data = await cresp.json()

                children = data.get("data", {}).get("children", [])
                comments = [c["data"] for c in children if c.get("kind") == "t1"]

                if len(comments) < self._min_comments_for_check:
                    return result

                # Low scores
                low_score_count = sum(
                    1 for c in comments if c.get("score", 1) <= 1
                )
                if low_score_count == len(comments):
                    indicators.append({
                        "name": INDICATOR_LOW_SCORES,
                        "detail": (
                            f"All {len(comments)} recent comments have "
                            f"score <= 1 (no engagement)."
                        ),
                    })

                # Removed comments
                removed_count = sum(
                    1 for c in comments
                    if c.get("body") in ("[removed]", "[deleted]")
                    or c.get("author") == "[deleted]"
                )
                if removed_count >= 2:
                    indicators.append({
                        "name": INDICATOR_REMOVED_COMMENTS,
                        "detail": (
                            f"{removed_count}/{len(comments)} comments "
                            f"appear removed or deleted."
                        ),
                    })

                # Hidden permalinks
                hidden_count = 0
                checked = 0
                pl_timeout = aiohttp.ClientTimeout(total=self._permalink_timeout)
                async with aiohttp.ClientSession(timeout=pl_timeout) as psession:
                    for comment in comments:
                        if checked >= self._max_permalink_checks:
                            break
                        permalink = comment.get("permalink")
                        if not permalink:
                            continue
                        try:
                            async with psession.get(
                                f"https://www.reddit.com{permalink}.json",
                                headers=_get_headers(),
                            ) as presp:
                                if presp.status == 404:
                                    hidden_count += 1
                                checked += 1
                        except Exception:
                            pass

                if hidden_count >= 2:
                    indicators.append({
                        "name": INDICATOR_HIDDEN_PERMALINKS,
                        "detail": (
                            f"{hidden_count}/{self._max_permalink_checks} "
                            f"comment permalinks return 404 (hidden)."
                        ),
                    })

                # Aggregate
                num_indicators = len(indicators)
                if num_indicators >= 2:
                    result["is_shadowbanned"] = True
                    result["confidence"] = CONFIDENCE_HIGH
                    result["recommendation"] = RECOMMENDATION_STOP
                elif num_indicators == 1:
                    result["confidence"] = CONFIDENCE_LOW
                    result["recommendation"] = RECOMMENDATION_MONITOR

        except Exception as exc:
            logger.error("Async shadowban check failed for u/%s: %s", username, exc)

        return result

    async def _get_cached(self, username: str) -> Optional[Dict]:
        """Return a cached result if fresh, otherwise None."""
        lock = await self._get_lock()
        async with lock:
            entry = self._cache.get(username)
            if entry is None:
                return None
            result, timestamp = entry
            if (time.monotonic() - timestamp) > self._cache_ttl:
                del self._cache[username]
                return None
            return result

    async def clear_cache(self, username: Optional[str] = None):
        """Clear cached results (async version)."""
        lock = await self._get_lock()
        async with lock:
            if username:
                self._cache.pop(username, None)
            else:
                self._cache.clear()
