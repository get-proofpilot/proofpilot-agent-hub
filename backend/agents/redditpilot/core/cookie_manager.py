"""Cookie Manager — Save, load, and manage browser cookies per Reddit account.

Stores cookies as JSON files in ~/.redditpilot/cookies/<account>.json.
Thread-safe file access via a per-file lock.

Features:
  - Save/load cookies per account (JSON format)
  - Cookie expiry checking and pruning
  - Paste cookies from browser (document.cookie string or Netscape format)
  - Thread-safe reads/writes
"""

import json
import logging
import os
import threading
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redditpilot.cookie_manager")

DEFAULT_COOKIE_DIR = Path.home() / ".redditpilot" / "cookies"


class CookieManager:
    """Manage browser cookies per Reddit account.

    Cookies are stored as JSON in ``~/.redditpilot/cookies/<account>.json``.
    Each file contains a list of cookie dicts with keys:
    name, value, domain, path, expires, secure, httpOnly.

    Usage::

        cm = CookieManager()
        cm.save("my_account", cookies)
        cookies = cm.load("my_account")
        if cm.has_valid_cookies("my_account"):
            ...
    """

    def __init__(self, cookie_dir: Optional[str] = None):
        self._cookie_dir = Path(cookie_dir) if cookie_dir else DEFAULT_COOKIE_DIR
        self._cookie_dir.mkdir(parents=True, exist_ok=True)
        # Per-account file locks for thread safety
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    @property
    def cookie_dir(self) -> Path:
        """Return the cookie storage directory."""
        return self._cookie_dir

    def _cookie_path(self, account: str) -> Path:
        """Return the JSON file path for an account."""
        safe_name = account.replace("/", "_").replace("\\", "_")
        return self._cookie_dir / f"{safe_name}.json"

    def _get_lock(self, account: str) -> threading.Lock:
        """Get or create a per-account lock (thread-safe)."""
        with self._global_lock:
            if account not in self._locks:
                self._locks[account] = threading.Lock()
            return self._locks[account]

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def save(
        self,
        account: str,
        cookies: List[Dict[str, Any]],
    ) -> str:
        """Save cookies for an account to disk (JSON).

        Parameters
        ----------
        account : str
            Reddit username (used as filename stem).
        cookies : list of dict
            Each dict should have at minimum ``name`` and ``value``.
            Optional keys: domain, path, expires, secure, httpOnly.

        Returns
        -------
        str
            Path to the saved cookie file.
        """
        filepath = self._cookie_path(account)
        lock = self._get_lock(account)

        # Normalise cookie dicts
        normalised = [self._normalise_cookie(c) for c in cookies]

        with lock:
            self._cookie_dir.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(normalised, f, indent=2)

        logger.info("Saved %d cookies for account '%s' -> %s", len(normalised), account, filepath)
        return str(filepath)

    def save_dict(
        self,
        account: str,
        cookie_dict: Dict[str, str],
        domain: str = ".reddit.com",
    ) -> str:
        """Save a simple {name: value} dict as cookies for an account.

        Convenience wrapper that converts flat dict to the full cookie
        list format before saving.
        """
        cookies = [
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
                "expires": -1,
                "secure": True,
                "httpOnly": False,
            }
            for name, value in cookie_dict.items()
        ]
        return self.save(account, cookies)

    def load(self, account: str) -> Optional[List[Dict[str, Any]]]:
        """Load cookies for an account from disk.

        Returns None if the file doesn't exist or is unreadable.
        """
        filepath = self._cookie_path(account)
        lock = self._get_lock(account)

        with lock:
            if not filepath.exists():
                logger.debug("No cookie file for account '%s'", account)
                return None
            try:
                with open(filepath, "r") as f:
                    cookies = json.load(f)
                if not isinstance(cookies, list):
                    logger.warning(
                        "Cookie file for '%s' has unexpected format, ignoring", account
                    )
                    return None
                logger.debug(
                    "Loaded %d cookies for account '%s'", len(cookies), account
                )
                return cookies
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load cookies for '%s': %s", account, e)
                return None

    def load_as_dict(self, account: str) -> Optional[Dict[str, str]]:
        """Load cookies and return as a simple {name: value} dict.

        Useful for ``requests.Session().cookies.update(...)`` style usage.
        """
        cookies = self.load(account)
        if cookies is None:
            return None
        return {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}

    def delete(self, account: str) -> bool:
        """Delete cookies for an account."""
        filepath = self._cookie_path(account)
        lock = self._get_lock(account)

        with lock:
            if filepath.exists():
                filepath.unlink()
                logger.info("Deleted cookies for account '%s'", account)
                return True
        return False

    def list_accounts(self) -> List[str]:
        """List all accounts with saved cookies."""
        accounts = []
        for fp in self._cookie_dir.glob("*.json"):
            accounts.append(fp.stem)
        return sorted(accounts)

    # ------------------------------------------------------------------
    # Expiry checking
    # ------------------------------------------------------------------

    def has_valid_cookies(self, account: str) -> bool:
        """Check if account has cookies that are not all expired.

        Cookies with expires == -1 or expires == 0 are treated as session
        cookies (valid as long as file exists).
        """
        cookies = self.load(account)
        if not cookies:
            return False

        now = time.time()
        for cookie in cookies:
            expires = cookie.get("expires", -1)
            # Session cookie (no expiry) or not yet expired
            if expires is None or expires <= 0 or expires > now:
                return True

        logger.info("All cookies expired for account '%s'", account)
        return False

    def prune_expired(self, account: str) -> int:
        """Remove expired cookies from an account's file.

        Returns the number of cookies removed.
        """
        cookies = self.load(account)
        if not cookies:
            return 0

        now = time.time()
        valid = []
        removed = 0
        for cookie in cookies:
            expires = cookie.get("expires", -1)
            if expires is None or expires <= 0 or expires > now:
                valid.append(cookie)
            else:
                removed += 1

        if removed > 0:
            self.save(account, valid)
            logger.info(
                "Pruned %d expired cookies for account '%s'", removed, account
            )

        return removed

    def get_cookie_value(
        self, account: str, cookie_name: str
    ) -> Optional[str]:
        """Get a specific cookie value by name."""
        cookies = self.load(account)
        if not cookies:
            return None
        for cookie in cookies:
            if cookie.get("name") == cookie_name:
                return cookie.get("value")
        return None

    # ------------------------------------------------------------------
    # Paste cookies from browser
    # ------------------------------------------------------------------

    def paste_from_browser(
        self,
        account: str,
        raw_text: str,
        domain: str = ".reddit.com",
    ) -> int:
        """Parse and save cookies from pasted browser text.

        Supports two formats:

        1. **document.cookie** style (semicolon-separated ``name=value`` pairs)::

            reddit_session=abc123; loid=xyz; token_v2=eyJ...

        2. **Netscape/Mozilla** format (tab-separated, as exported by browser
           extensions like "cookies.txt")::

            .reddit.com  TRUE  /  TRUE  0  reddit_session  abc123

        Returns the number of cookies saved.
        """
        raw_text = raw_text.strip()
        if not raw_text:
            return 0

        # Detect format: Netscape has tab-separated lines with domain first
        if "\t" in raw_text and self._looks_like_netscape(raw_text):
            cookies = self._parse_netscape(raw_text)
        else:
            cookies = self._parse_document_cookie(raw_text, domain)

        if cookies:
            self.save(account, cookies)
            logger.info(
                "Pasted %d cookies for account '%s'", len(cookies), account
            )
        else:
            logger.warning("Could not parse any cookies from pasted text")

        return len(cookies)

    @staticmethod
    def _looks_like_netscape(text: str) -> bool:
        """Heuristic: check if text looks like Netscape cookie format."""
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                return True
            break
        return False

    @staticmethod
    def _parse_document_cookie(
        text: str, domain: str = ".reddit.com"
    ) -> List[Dict[str, Any]]:
        """Parse ``document.cookie`` style string.

        Format: ``name1=value1; name2=value2; ...``
        """
        cookies = []
        # Handle both semicolon and newline as delimiters
        for pair in text.replace("\n", ";").split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            name = name.strip()
            value = value.strip()
            if name:
                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/",
                        "expires": -1,  # session cookie
                        "secure": True,
                        "httpOnly": False,
                    }
                )
        return cookies

    @staticmethod
    def _parse_netscape(text: str) -> List[Dict[str, Any]]:
        """Parse Netscape/Mozilla cookie file format.

        Tab-separated columns:
        domain  flag  path  secure  expires  name  value
        """
        cookies = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain = parts[0]
            path = parts[2]
            secure = parts[3].upper() == "TRUE"
            try:
                expires = int(parts[4])
            except ValueError:
                expires = -1
            name = parts[5]
            value = parts[6] if len(parts) > 6 else ""

            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "expires": expires,
                    "secure": secure,
                    "httpOnly": False,
                }
            )
        return cookies

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_cookie(cookie: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure a cookie dict has all expected keys with defaults."""
        return {
            "name": cookie.get("name", ""),
            "value": cookie.get("value", ""),
            "domain": cookie.get("domain", ".reddit.com"),
            "path": cookie.get("path", "/"),
            "expires": cookie.get("expires", -1),
            "secure": cookie.get("secure", True),
            "httpOnly": cookie.get("httpOnly", False),
        }
