"""Reddit web-session client — cookie-based, no API app registration needed.

Uses Reddit's public JSON endpoints + old.reddit.com session cookies for
authenticated actions (commenting, posting). This is a drop-in alternative
to the PRAW-based RedditClient in core/reddit_client.py.

Adapted from MiloAgent's RedditWebBot with improvements for RedditPilot.

Usage:
    from redditpilot.platforms.reddit_web import RedditWebClient

    client = RedditWebClient(
        username="mybot",
        password="secret",
        db=database_instance,
    )
    client.login()
    posts = client.get_hot_posts("python", limit=10)
    client.post_comment(post_id, "Great post!", subreddit="python")
"""

import base64
import json
import os
import re
import tempfile
import time
import random
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("redditpilot.web")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REDDIT_BASE = "https://www.reddit.com"
REDDIT_OLD = "https://old.reddit.com"

DEFAULT_COOKIE_DIR = os.path.join(
    os.path.expanduser("~"), ".redditpilot", "data", "cookies"
)

# Shared across ALL web-client instances — avoids hammering blocked subs
_BLOCKED_SUBS: Dict[str, float] = {}
_BLOCKED_SUBS_LOCK = threading.Lock()
_BLOCKED_SUBS_DURATION = 14400  # 4 hours

# ---------------------------------------------------------------------------
# Rotating User-Agents (updated 2025-Q4)
# ---------------------------------------------------------------------------

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.8",
    "en-CA,en;q=0.9",
]


def _random_ua() -> str:
    return random.choice(USER_AGENTS)


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------


class RedditWebClient:
    """Cookie-based Reddit client — mirrors the RedditClient (PRAW) interface.

    The user picks which backend to use via config:
        mode: "praw"   -> core.reddit_client.RedditClient
        mode: "web"    -> platforms.reddit_web.RedditWebClient

    Both expose the same public methods:
        - get_hot_posts / get_new_posts / search_posts / get_post_comments
        - post_comment / create_post / delete_comment
        - check_comment_performance / check_shadowban
    """

    # -- construction -------------------------------------------------------

    def __init__(
        self,
        username: str,
        password: str = "",
        db=None,
        cookies_file: str = "",
        proxy: str = "",
    ):
        self.username = username
        self._password = password
        self.db = db
        self._cookies_file = cookies_file or os.path.join(
            DEFAULT_COOKIE_DIR, f"reddit_{username}.json"
        )
        self._proxy = proxy

        # requests session with connection pooling
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"https": proxy, "http": proxy}
        self._rotate_headers()  # set initial UA / accept headers
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Auth state
        self._authenticated = False
        self._modhash = ""  # CSRF token for POST requests

        # Rate-limit / circuit-breaker state
        self._ratelimit_until: float = 0.0
        self._consecutive_failures = 0
        self._max_failures = 5
        self._circuit_open_at: Optional[float] = None

        # Timing
        self._last_action_time: Optional[float] = None

        # Post blacklist (flair required, restricted, etc.)
        self._post_blacklist: set = set()

        # Load saved cookies
        self._load_cookies()

    # -- header rotation ----------------------------------------------------

    def _rotate_headers(self):
        """Set randomized browser-like headers on the session."""
        ua = _random_ua()
        self.session.headers.update({
            "User-Agent": ua,
            "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        })

    # ======================================================================
    # Cookie persistence
    # ======================================================================

    def _load_cookies(self):
        """Load saved session cookies from disk."""
        if not os.path.exists(self._cookies_file):
            return
        try:
            with open(self._cookies_file) as f:
                cookies = json.load(f)
            self.session.cookies.update(cookies)
            self._authenticated = True
            logger.debug("Loaded Reddit cookies from %s", self._cookies_file)
        except Exception as exc:
            logger.warning("Failed to load cookies: %s", exc)

    def _save_cookies(self):
        """Atomically save session cookies to disk."""
        cookie_dir = os.path.dirname(self._cookies_file)
        os.makedirs(cookie_dir, exist_ok=True)
        cookies = dict(self.session.cookies)
        try:
            fd, tmp = tempfile.mkstemp(dir=cookie_dir, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(cookies, f)
            os.replace(tmp, self._cookies_file)
        except Exception as exc:
            logger.warning("Atomic cookie save failed (%s), direct write", exc)
            with open(self._cookies_file, "w") as f:
                json.dump(cookies, f)
        logger.debug("Saved cookies to %s", self._cookies_file)

    def import_cookies(self, cookies_dict: dict):
        """Import cookies from an external source (e.g. browser export).

        Accepts a flat dict of cookie_name -> value.
        Typical keys: reddit_session, token_v2, loid, edgebucket, etc.
        """
        self.session.cookies.update(cookies_dict)
        self._authenticated = True
        self._save_cookies()
        logger.info("Imported %d cookies for u/%s", len(cookies_dict), self.username)

    # ======================================================================
    # Authentication
    # ======================================================================

    def login(self) -> bool:
        """Authenticate via old.reddit.com login form.

        Returns True if session is authenticated (either fresh login or
        valid saved cookies).
        """
        # Fast path: already have valid cookies
        if self._authenticated and self._verify_session():
            return True

        # Try programmatic login via old.reddit.com
        if self._password:
            if self._do_login():
                return True

        # Reload from disk (user may have pasted cookies externally)
        self._load_cookies()
        if self._authenticated and self._verify_session():
            return True

        logger.error(
            "Reddit auth failed for u/%s. Options:\n"
            "  1. Provide password in config for programmatic login\n"
            "  2. Export cookies from browser and call import_cookies()\n"
            "  3. Place cookie JSON at %s",
            self.username, self._cookies_file,
        )
        return False

    def _do_login(self) -> bool:
        """Attempt programmatic login via old.reddit.com/api/login.

        Reddit may block this from server IPs. If it fails, use
        cookie import as a fallback.
        """
        try:
            # Step 1: GET old.reddit.com to get initial cookies
            self._rotate_headers()
            resp = self.session.get(
                f"{REDDIT_OLD}/login",
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("Login page returned %d", resp.status_code)

            # Small delay to appear human
            time.sleep(random.uniform(1.5, 3.0))

            # Step 2: POST login credentials
            login_data = {
                "op": "login-main",
                "user": self.username,
                "passwd": self._password,
                "api_type": "json",
            }
            resp = self.session.post(
                f"{REDDIT_OLD}/api/login/{self.username}",
                data=login_data,
                headers={
                    "Referer": f"{REDDIT_OLD}/login",
                    "Origin": REDDIT_OLD,
                },
                timeout=15,
            )

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    errors = data.get("json", {}).get("errors", [])
                    if not errors:
                        modhash = data.get("json", {}).get("data", {}).get("modhash", "")
                        if modhash:
                            self._modhash = modhash
                        self._authenticated = True
                        self._save_cookies()
                        logger.info("Logged in as u/%s via old.reddit.com", self.username)
                        return True
                    else:
                        logger.warning("Login errors: %s", errors)
                except (ValueError, KeyError):
                    logger.warning("Login returned non-JSON (may be blocked)")

            if resp.status_code == 429:
                logger.warning("Login rate-limited (429)")
            elif resp.status_code == 403:
                logger.warning("Login forbidden (403) — IP may be blocked")

        except Exception as exc:
            logger.error("Login failed: %s", exc)

        return False

    def _verify_session(self) -> bool:
        """Verify current cookies are still valid and fetch modhash."""
        try:
            resp = self.session.get(
                f"{REDDIT_OLD}/api/me.json",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                self._authenticated = False
                return False

            data = resp.json().get("data", {})
            uname = data.get("name")
            if not uname:
                # Maybe token_v2 JWT auth
                token = self.session.cookies.get("token_v2", "")
                if token and self._is_token_v2_logged_in(token):
                    return True
                self._authenticated = False
                return False

            modhash = data.get("modhash", "")
            if modhash:
                self._modhash = modhash
                logger.debug("Got modhash: %s...", modhash[:8])
            return True

        except Exception as exc:
            logger.debug("Session verify failed: %s", exc)
            self._authenticated = False
            return False

    @staticmethod
    def _is_token_v2_logged_in(token: str) -> bool:
        """Check if a token_v2 JWT belongs to a logged-in Reddit user."""
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return False
            payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload))
            return data.get("sub", "").startswith("t2_")
        except Exception:
            return False

    def _ensure_auth(self) -> bool:
        """Ensure authenticated + have modhash for write ops."""
        if self._authenticated and self._modhash:
            return True
        if self._authenticated:
            return self._verify_session()
        return self.login()

    # ======================================================================
    # Human-like delays (Gaussian jitter)
    # ======================================================================

    def _human_delay(self, min_sec: int = 30, max_sec: int = 120):
        """Wait a human-like duration before acting.

        Uses Gaussian jitter for natural variation — not a flat uniform.
        Accounts for time already elapsed since last action.
        """
        base = random.uniform(min_sec, max_sec)
        jitter = random.gauss(0, base * 0.15)
        delay = max(min_sec * 0.5, base + jitter)

        if self._last_action_time:
            elapsed = time.time() - self._last_action_time
            remaining = delay - elapsed
            if remaining > 0:
                logger.debug("Human delay: %.1fs", remaining)
                time.sleep(remaining)
        else:
            logger.debug("Human delay: %.1fs", delay)
            time.sleep(delay)

        self._last_action_time = time.time()

    @staticmethod
    def _human_reading_delay(
        post_title: str, post_body: str, comment_text: str
    ) -> float:
        """Simulate reading the post + thinking + typing a reply."""
        post_words = len(f"{post_title} {post_body}".split())
        reply_words = len(comment_text.split())

        # Reading (250 wpm, 60% skim)
        read_time = (post_words / 250) * 60 * 0.6
        # Thinking
        think_time = random.uniform(5, 30)
        # Typing (~40 wpm with pauses)
        type_time = (reply_words / 40) * 60 * random.uniform(0.7, 1.3)

        base = read_time + think_time + type_time
        delay = base * random.uniform(0.7, 1.3)
        return max(20.0, min(delay, 180.0))

    # ======================================================================
    # Rate-limit detection and backoff
    # ======================================================================

    def _is_rate_limited(self) -> bool:
        """Check if we're still in a rate-limit cooldown."""
        if time.time() < self._ratelimit_until:
            remaining = int((self._ratelimit_until - time.time()) / 60)
            logger.debug("Rate-limited for %d more minutes", remaining)
            return True
        return False

    def _check_circuit_breaker(self) -> bool:
        """Return True if circuit breaker is tripped (too many failures)."""
        if self._consecutive_failures < self._max_failures:
            return False

        if self._circuit_open_at is None:
            self._circuit_open_at = time.time()

        elapsed = time.time() - self._circuit_open_at
        if elapsed < 1800:  # 30 min cooldown
            logger.warning(
                "Circuit breaker open (%d failures), retry in %d min",
                self._consecutive_failures,
                int((1800 - elapsed) / 60),
            )
            return True

        # Auto-reset after 30 min
        logger.info("Circuit breaker auto-reset after %.0f min", elapsed / 60)
        self._consecutive_failures = 0
        self._circuit_open_at = None
        return False

    @staticmethod
    def _parse_ratelimit_wait(error_msg: str) -> int:
        """Parse Reddit RATELIMIT message to minutes.

        Examples: "Take a break for 3 minutes", "Take a break for 45 seconds"
        """
        msg = error_msg.lower()
        m = re.search(r"(\d+)\s*minute", msg)
        if m:
            return int(m.group(1)) + 1
        m = re.search(r"(\d+)\s*second", msg)
        if m:
            return max(1, int(m.group(1)) // 60 + 1)
        m = re.search(r"(\d+)\s*hour", msg)
        if m:
            return int(m.group(1)) * 60
        return 10  # safe fallback

    @staticmethod
    def _parse_ratelimit_message(message: str) -> int:
        """Compatibility alias returning wait time in seconds."""
        msg = message.lower()
        wait = 0
        minutes = re.search(r"(\d+)\s*minute", msg)
        seconds = re.search(r"(\d+)\s*second", msg)
        if minutes:
            wait += int(minutes.group(1)) * 60
        if seconds:
            wait += int(seconds.group(1))
        return max(wait, 30)

    # ======================================================================
    # Blocked-subreddit tracking (shared across instances)
    # ======================================================================

    @staticmethod
    def _is_sub_blocked(subreddit: str) -> bool:
        with _BLOCKED_SUBS_LOCK:
            until = _BLOCKED_SUBS.get(subreddit.lower())
        return bool(until and time.time() < until)

    @staticmethod
    def _block_sub(subreddit: str, duration: int = _BLOCKED_SUBS_DURATION):
        with _BLOCKED_SUBS_LOCK:
            _BLOCKED_SUBS[subreddit.lower()] = time.time() + duration

    # ======================================================================
    # Reading Operations (anonymous JSON endpoints, no auth needed)
    # ======================================================================

    def get_subreddit_info(self, subreddit_name: str) -> dict:
        """Fetch subreddit metadata via JSON endpoint."""
        try:
            resp = self.session.get(
                f"{REDDIT_BASE}/r/{subreddit_name}/about.json",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return {}
            data = resp.json().get("data", {})
            return {
                "name": data.get("display_name", subreddit_name),
                "subscribers": data.get("subscribers", 0),
                "description": data.get("public_description", ""),
                "rules": [],  # rules require separate endpoint
                "over18": data.get("over18", False),
                "created_utc": data.get("created_utc", 0),
            }
        except Exception as exc:
            logger.error("Failed to get subreddit %s: %s", subreddit_name, exc)
            return {}

    def search_subreddits(self, query: str, limit: int = 25) -> list:
        """Search for subreddits by keyword."""
        results = []
        try:
            resp = self.session.get(
                f"{REDDIT_BASE}/subreddits/search.json",
                params={"q": query, "limit": limit},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            for child in resp.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                results.append({
                    "name": d.get("display_name", ""),
                    "subscribers": d.get("subscribers", 0),
                    "description": d.get("public_description", ""),
                    "over18": d.get("over18", False),
                })
        except Exception as exc:
            logger.error("Subreddit search failed for '%s': %s", query, exc)
        return results

    def get_hot_posts(
        self, subreddit_name: str, limit: int = 25, time_filter: str = "day"
    ) -> list:
        """Get hot posts from a subreddit."""
        return self._browse_subreddit(subreddit_name, "hot", limit, time_filter)

    def get_new_posts(self, subreddit_name: str, limit: int = 25) -> list:
        """Get new posts from a subreddit."""
        return self._browse_subreddit(subreddit_name, "new", limit)

    def search_posts(
        self,
        subreddit_name: str,
        query: str,
        sort: str = "new",
        time_filter: str = "week",
        limit: int = 25,
    ) -> list:
        """Search posts within a subreddit."""
        return self._search_subreddit(subreddit_name, query, limit, sort, time_filter)

    def get_post_comments(
        self, post_id: str, limit: int = 10, subreddit: str = ""
    ) -> list:
        """Get top comments on a post.

        Returns list of dicts with id, body, score, author, created_utc.
        """
        try:
            if subreddit:
                url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
            else:
                url = f"{REDDIT_BASE}/comments/{post_id}.json"

            resp = self.session.get(
                url,
                params={"limit": limit, "sort": "best", "depth": 1},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            if not isinstance(data, list) or len(data) < 2:
                return []

            comments = []
            for child in data[1].get("data", {}).get("children", []):
                if child.get("kind") != "t1":
                    continue
                c = child.get("data", {})
                author = c.get("author", "[deleted]")
                body = c.get("body", "")
                if author in ("[deleted]", "AutoModerator") or not body:
                    continue
                comments.append({
                    "id": c.get("id", ""),
                    "body": body[:2000],
                    "score": c.get("score", 0),
                    "author": author,
                    "created_utc": c.get("created_utc", 0),
                })
                if len(comments) >= limit:
                    break
            return comments

        except Exception as exc:
            logger.error("Failed to get comments for %s: %s", post_id, exc)
            return []

    # -- internal browse / search helpers -----------------------------------

    def _browse_subreddit(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        time_filter: str = "day",
    ) -> List[dict]:
        """Browse a subreddit listing (hot/new/rising/top)."""
        if self._is_sub_blocked(subreddit):
            return []

        url = f"{REDDIT_BASE}/r/{subreddit}/{sort}.json"
        params = {"limit": limit, "t": time_filter}

        try:
            resp = self.session.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code in (403, 404):
                self._block_sub(subreddit)
                logger.debug("r/%s returned %d, blocked 4h", subreddit, resp.status_code)
                return []
            if resp.status_code == 429:
                logger.warning("Rate-limited browsing r/%s", subreddit)
                time.sleep(random.uniform(5, 15))
                return []
            if resp.status_code != 200:
                return []

            # Guard against HTML responses (IP-blocked)
            ct = resp.headers.get("Content-Type", "")
            if "json" not in ct and "html" in ct.lower():
                logger.warning("Reddit returned HTML for r/%s (IP blocked?)", subreddit)
                return []

            data = resp.json()
            posts = []
            for child in data.get("data", {}).get("children", []):
                if child.get("kind") == "t3":
                    posts.append(self._raw_post_to_dict(child.get("data", {})))
            return posts

        except requests.Timeout:
            logger.debug("Timeout browsing r/%s/%s", subreddit, sort)
            return []
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Non-JSON from r/%s: %s", subreddit, exc)
            return []
        except Exception as exc:
            logger.debug("Browse error r/%s: %s", subreddit, exc)
            return []

    def _search_subreddit(
        self,
        subreddit: str,
        query: str,
        limit: int = 25,
        sort: str = "new",
        time_filter: str = "week",
    ) -> List[dict]:
        """Search a subreddit via JSON API with retry on 429."""
        if self._is_sub_blocked(subreddit):
            return []

        url = f"{REDDIT_BASE}/r/{subreddit}/search.json"
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": limit,
            "restrict_sr": "true",
        }

        for attempt in range(2):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=10,
                )

                if resp.status_code == 200:
                    ct = resp.headers.get("Content-Type", "")
                    if "json" not in ct and "html" in ct.lower():
                        logger.warning("HTML instead of JSON for r/%s search", subreddit)
                        return []
                    data = resp.json()
                    posts = []
                    for child in data.get("data", {}).get("children", []):
                        if child.get("kind") == "t3":
                            posts.append(self._raw_post_to_dict(child.get("data", {})))
                    return posts

                if resp.status_code == 429:
                    wait = (2 ** attempt) * 5
                    logger.warning("Rate-limited searching r/%s, wait %ds", subreddit, wait)
                    time.sleep(wait)
                    continue

                if resp.status_code in (403, 404):
                    self._block_sub(subreddit)
                    return []

                logger.warning("Search r/%s returned %d", subreddit, resp.status_code)

            except requests.Timeout:
                time.sleep(2 ** attempt)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Non-JSON search result r/%s: %s", subreddit, exc)
                return []
            except Exception as exc:
                logger.debug("Search error r/%s: %s", subreddit, exc)
                break

        return []

    @staticmethod
    def _raw_post_to_dict(post: dict) -> dict:
        """Convert raw Reddit JSON post data to a clean dict.

        Matches the same schema as RedditClient._post_to_dict (PRAW version).
        """
        return {
            "id": post.get("id", ""),
            "title": post.get("title", ""),
            "body": (post.get("selftext") or "")[:2000],
            "author": post.get("author", "[deleted]"),
            "subreddit": post.get("subreddit", ""),
            "url": post.get("url", ""),
            "permalink": f"https://reddit.com{post.get('permalink', '')}",
            "score": post.get("score", 0),
            "upvote_ratio": post.get("upvote_ratio", 0.5),
            "num_comments": post.get("num_comments", 0),
            "created_utc": post.get("created_utc", 0),
            "is_self": post.get("is_self", True),
            "link_flair_text": post.get("link_flair_text"),
            "over_18": post.get("over18", False),
            "locked": post.get("locked", False),
            # Extra fields useful for the web backend
            "fullname": post.get("name", ""),
            "archived": post.get("archived", False),
        }

    # ======================================================================
    # Writing Operations (require authentication + modhash)
    # ======================================================================

    def post_comment(
        self,
        post_id: str,
        comment_text: str,
        client_id: int = None,
        subreddit: str = None,
    ) -> Optional[str]:
        """Post a comment on a submission.

        Returns comment ID on success, None on failure.
        Mirrors RedditClient.post_comment() interface.
        """
        if self._is_rate_limited() or self._check_circuit_breaker():
            return None

        if not self._ensure_auth():
            logger.error("Cannot comment: not authenticated")
            self._consecutive_failures += 1
            return None

        if not self._modhash:
            logger.error("No modhash (CSRF token) — cannot post")
            self._consecutive_failures += 1
            return None

        # Human-like delay
        self._human_delay(min_sec=15, max_sec=60)

        fullname = f"t3_{post_id}" if not post_id.startswith("t3_") else post_id

        post_data = {
            "thing_id": fullname,
            "text": comment_text,
            "uh": self._modhash,
            "api_type": "json",
        }

        post_headers = {
            "Referer": (
                f"{REDDIT_OLD}/r/{subreddit}/comments/{post_id}/"
                if subreddit
                else f"{REDDIT_OLD}/"
            ),
            "Origin": REDDIT_OLD,
        }

        try:
            resp = self.session.post(
                f"{REDDIT_OLD}/api/comment",
                data=post_data,
                headers=post_headers,
                timeout=30,
            )

            # HTTP-level errors
            if resp.status_code == 429:
                logger.warning("Rate-limited on comment POST")
                self._ratelimit_until = time.time() + 600
                self._consecutive_failures += 1
                return None

            if resp.status_code == 403:
                logger.warning(
                    "403 on comment in r/%s — may be banned",
                    subreddit or "unknown",
                )
                self._authenticated = False
                self._modhash = ""
                self._consecutive_failures += 1
                return None

            # Parse JSON response
            try:
                result = resp.json()
            except (ValueError, Exception):
                logger.warning("Non-JSON comment response (status=%d)", resp.status_code)
                self._consecutive_failures += 1
                return None

            errors = result.get("json", {}).get("errors", [])
            if errors:
                return self._handle_post_errors(errors, "comment", subreddit)

            # Success
            self._consecutive_failures = 0
            self._circuit_open_at = None

            things = result.get("json", {}).get("data", {}).get("things", [])
            comment_data = things[0].get("data", {}) if things else {}
            comment_id = comment_data.get("id", "unknown")

            # Log to database if available
            if self.db:
                self._log_action("comment", post_id, comment_text, subreddit, client_id, comment_id)

            logger.info(
                "Posted comment %s on %s in r/%s",
                comment_id, post_id, subreddit or "?",
            )
            return comment_id

        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)
            self._consecutive_failures += 1
            return None

    def create_post(
        self,
        subreddit_name: str,
        title: str,
        body: str = None,
        url: str = None,
        client_id: int = None,
    ) -> Optional[str]:
        """Create a new post in a subreddit.

        Returns post ID on success, None on failure.
        Mirrors RedditClient.create_post() interface.
        """
        if subreddit_name.lower() in self._post_blacklist:
            logger.debug("r/%s blacklisted for posts, skip", subreddit_name)
            return None

        if self._is_rate_limited() or self._check_circuit_breaker():
            return None

        if not self._ensure_auth():
            logger.error("Cannot create post: not authenticated")
            return None

        if not self._modhash:
            logger.error("No modhash — cannot create post")
            return None

        # Longer human delay for post creation
        self._human_delay(min_sec=60, max_sec=300)

        kind = "link" if url else "self"
        submit_data = {
            "sr": subreddit_name,
            "kind": kind,
            "title": title,
            "uh": self._modhash,
            "api_type": "json",
            "resubmit": "true",
        }
        if url:
            submit_data["url"] = url
        else:
            submit_data["text"] = body or ""

        submit_headers = {
            "Referer": f"{REDDIT_OLD}/r/{subreddit_name}/submit",
            "Origin": REDDIT_OLD,
        }

        try:
            resp = self.session.post(
                f"{REDDIT_OLD}/api/submit",
                data=submit_data,
                headers=submit_headers,
                timeout=30,
            )

            if resp.status_code == 429:
                logger.warning("Rate-limited on post creation")
                self._ratelimit_until = time.time() + 600
                return None

            if resp.status_code == 403:
                logger.warning("403 on post in r/%s — banned?", subreddit_name)
                self._consecutive_failures += 1
                return None

            result = resp.json()
            errors = result.get("json", {}).get("errors", [])

            if errors:
                error_codes = [
                    e[0] for e in errors if isinstance(e, list) and e
                ]

                # Permanent blacklist errors
                blacklist_codes = {
                    "SUBMIT_VALIDATION_FLAIR_REQUIRED",
                    "SUBREDDIT_NOTALLOWED",
                    "NOT_WHITELISTED_BY_USER_MESSAGE",
                    "NO_SELFS",
                }
                if blacklist_codes & set(error_codes):
                    logger.warning(
                        "r/%s rejects posts (%s) — blacklisted",
                        subreddit_name, error_codes,
                    )
                    self._post_blacklist.add(subreddit_name.lower())
                    return None

                return self._handle_post_errors(errors, "post", subreddit_name)

            # Success
            self._consecutive_failures = 0
            post_url = result.get("json", {}).get("data", {}).get("url", "")
            post_id_match = re.search(r"/comments/([a-z0-9]+)/", post_url)
            new_post_id = post_id_match.group(1) if post_id_match else "unknown"

            if self.db:
                self._log_action(
                    "post", new_post_id,
                    f"{title}\n\n{body or url or ''}",
                    subreddit_name, client_id, new_post_id,
                )

            logger.info("Created post %s in r/%s", new_post_id, subreddit_name)
            return new_post_id

        except Exception as exc:
            logger.error("Failed to create post: %s", exc)
            self._consecutive_failures += 1
            return None

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment by ID."""
        if not self._ensure_auth() or not self._modhash:
            return False

        try:
            fullname = (
                f"t1_{comment_id}"
                if not comment_id.startswith("t1_")
                else comment_id
            )
            resp = self.session.post(
                f"{REDDIT_OLD}/api/del",
                data={"id": fullname, "uh": self._modhash},
                headers={"Referer": REDDIT_OLD, "Origin": REDDIT_OLD},
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Deleted comment %s", comment_id)
                return True
            logger.warning("Delete returned %d", resp.status_code)
            return False
        except Exception as exc:
            logger.error("Failed to delete comment %s: %s", comment_id, exc)
            return False

    # ======================================================================
    # Monitoring Operations
    # ======================================================================

    def check_comment_performance(self, comment_id: str) -> Optional[dict]:
        """Check how a posted comment is performing."""
        try:
            url = f"{REDDIT_BASE}/api/info.json"
            fullname = (
                f"t1_{comment_id}"
                if not comment_id.startswith("t1_")
                else comment_id
            )
            resp = self.session.get(
                url,
                params={"id": fullname},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            children = resp.json().get("data", {}).get("children", [])
            if not children:
                return None

            c = children[0].get("data", {})
            body = c.get("body", "")
            return {
                "id": c.get("id", comment_id),
                "score": c.get("score", 0),
                "body": body,
                "is_removed": body in ("[removed]", "[deleted]"),
                "replies": c.get("num_reports", 0),  # approximate
            }
        except Exception as exc:
            logger.error("Failed to check comment %s: %s", comment_id, exc)
            return None

    def check_shadowban(self) -> bool:
        """Check if this account is shadowbanned.

        Returns True if shadowbanned, False if OK.
        """
        try:
            resp = self.session.get(
                f"{REDDIT_OLD}/user/{self.username}/about.json",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code == 404:
                logger.warning("u/%s returns 404 — likely shadowbanned", self.username)
                return True
            if resp.status_code == 403:
                logger.warning("u/%s returns 403 — likely suspended", self.username)
                return True
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                if data.get("is_suspended"):
                    return True
                return False
            return False
        except Exception:
            return False

    def check_cookie_validity(self) -> dict:
        """Check if session cookies are still valid.

        Returns dict with 'valid', 'username', 'karma' keys.
        """
        try:
            resp = self.session.get(
                f"{REDDIT_OLD}/api/me.json",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return {"valid": False, "reason": f"HTTP {resp.status_code}"}
            data = resp.json().get("data", {})
            if not data or not data.get("name"):
                return {"valid": False, "reason": "No user data"}
            return {
                "valid": True,
                "username": data.get("name", ""),
                "karma": (data.get("link_karma", 0) or 0) + (data.get("comment_karma", 0) or 0),
                "has_mail": data.get("has_mail", False),
            }
        except Exception as exc:
            return {"valid": False, "reason": str(exc)}

    def verify_comment_posted(self, post_id: str, comment_text: str = "") -> bool:
        """Verify our comment actually appears in the thread (not silently removed)."""
        try:
            time.sleep(3)
            url = f"{REDDIT_BASE}/comments/{post_id}.json"
            resp = self.session.get(
                url,
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return True  # can't verify, assume ok

            data = resp.json()
            if isinstance(data, list) and len(data) >= 2:
                for child in data[1].get("data", {}).get("children", []):
                    c = child.get("data", {})
                    if c.get("author") == self.username:
                        return True

            logger.warning(
                "Comment by u/%s on %s not visible — possible silent removal",
                self.username, post_id,
            )
            return False
        except Exception:
            return True

    # ======================================================================
    # Internal helpers
    # ======================================================================

    def _handle_post_errors(
        self, errors: list, action_type: str, subreddit: str = ""
    ) -> Optional[str]:
        """Handle Reddit API errors from comment/post JSON response.

        Returns None always (action failed).
        """
        error_msg = str(errors)
        error_codes = [e[0] for e in errors if isinstance(e, list) and e]

        # Rate limit
        if "RATELIMIT" in error_codes:
            wait_min = self._parse_ratelimit_wait(error_msg)
            logger.warning(
                "RATELIMIT for u/%s: %d min cooldown", self.username, wait_min
            )
            self._ratelimit_until = time.time() + wait_min * 60
            return None

        # Captcha (shouldn't happen often on aged accounts)
        if "BAD_CAPTCHA" in error_codes:
            logger.warning("CAPTCHA required for u/%s — 2h cooldown", self.username)
            self._ratelimit_until = time.time() + 7200
            return None

        logger.error("Reddit %s error: %s", action_type, error_msg)
        self._consecutive_failures += 1
        return None

    def _log_action(
        self,
        action_type: str,
        target_id: str,
        content: str,
        subreddit: str = None,
        client_id: int = None,
        reddit_id: str = None,
    ):
        """Log action to database if available."""
        if not self.db:
            return
        try:
            # Try the RedditPilot DB interface
            if hasattr(self.db, "record_action"):
                account_row = self.db.fetchone(
                    "SELECT id FROM accounts WHERE username = ?",
                    (self.username,),
                )
                if account_row:
                    self.db.record_action(
                        account_id=account_row["id"],
                        action_type=action_type,
                        subreddit=subreddit or "",
                        client_id=client_id,
                        reddit_id=reddit_id or target_id,
                    )
            elif hasattr(self.db, "log_action"):
                self.db.log_action(
                    platform="reddit",
                    action_type=action_type,
                    account=self.username,
                    project="",
                    target_id=target_id,
                    content=content,
                    metadata={
                        "subreddit": subreddit or "",
                        "method": "web_session",
                        "reddit_id": reddit_id or "",
                    },
                )
        except Exception as exc:
            logger.debug("DB log failed: %s", exc)
