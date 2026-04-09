"""
RedditPilot Account Manager
Multi-client account rotation with karma tiers, health tracking, and LRU fairness.

Adapted from MiloAgent's safety/account_manager.py for RedditPilot's
multi-client agency model using dataclass config (RedditAccount, Config).
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from redditpilot.core.config import Config, RedditAccount
from redditpilot.core.database import Database

logger = logging.getLogger("redditpilot.account_manager")


class AccountHealthState:
    """Enum-like constants for account health states."""
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    WARNED = "warned"
    BANNED = "banned"

    ALL = (HEALTHY, COOLDOWN, WARNED, BANNED)


class AccountManager:
    """Manages Reddit account rotation and health for multi-client operations.

    Features:
    - Karma tier system with daily action caps
    - Round-robin rotation with LRU fairness correction
    - Account health states: healthy, cooldown, warned, banned
    - Per-client account assignment (accounts can be dedicated to specific clients)
    - Hot-reload support for config changes
    - Thread-safe with RLock-based locking
    - Database-backed persistence for state recovery across restarts

    Karma Tiers:
        new       (<10 karma):  3 actions/day, comment-only
        growing   (10-50):      7 actions/day
        established (50-200):  12 actions/day
        veteran   (200+):     20 actions/day
    """

    # Account health states (re-export for convenience)
    HEALTHY = AccountHealthState.HEALTHY
    COOLDOWN = AccountHealthState.COOLDOWN
    WARNED = AccountHealthState.WARNED
    BANNED = AccountHealthState.BANNED

    # Karma tier definitions: (min_karma, tier_name, daily_cap, can_post)
    # Ordered highest-first so first match wins
    KARMA_TIERS = [
        (200, "veteran",      20, True),
        ( 50, "established",  12, True),
        ( 10, "growing",       7, True),
        (  0, "new",           3, False),
    ]
    MIN_KARMA_WRITE = -5      # Below this karma: skip entirely (shadowban risk)
    KARMA_CACHE_TTL = 43200   # 12 hours in seconds

    # Default cooldown duration for Reddit accounts (minutes)
    DEFAULT_COOLDOWN_MINUTES = 15

    def __init__(self, config: Config, db: Database):
        """Initialize the account manager.

        Args:
            config: RedditPilot Config dataclass with accounts and clients.
            db: Database instance for persistence.
        """
        self.config = config
        self.db = db
        self._lock = threading.RLock()

        # In-memory state
        self._cooldowns: Dict[str, datetime] = {}      # username -> cooldown_expires_at
        self._statuses: Dict[str, str] = {}             # username -> health state
        self._last_used: Dict[str, datetime] = {}       # username -> last used timestamp
        self._rotation_index: int = 0                   # Global round-robin index
        self._client_rotation: Dict[str, int] = {}      # client_slug -> rotation index

        # Karma cache: username -> (total_karma, fetched_at_timestamp)
        self._karma_cache: Dict[str, tuple] = {}

        # Hot-reload support
        self._config_path: Optional[str] = None
        self._config_mtime: Optional[float] = None
        self._on_reload_callbacks: List[Callable] = []
        self._watching = False
        self._watcher_thread: Optional[threading.Thread] = None

        # Sync accounts to DB and restore state
        self._sync_accounts_to_db()
        self._restore_state_from_db()

    # ── Initialization & State Recovery ─────────────────────────────

    def _sync_accounts_to_db(self):
        """Ensure all config accounts exist in the database."""
        for account in self.config.get_enabled_accounts():
            self.db.upsert_account(
                username=account.username,
                karma_tier=account.karma_tier,
            )
            logger.debug(f"Synced account {account.username} to DB (tier={account.karma_tier})")

    def _restore_state_from_db(self):
        """Restore account health/cooldown state from database on startup."""
        try:
            for account in self.config.get_enabled_accounts():
                username = account.username
                row = self.db.fetchone(
                    "SELECT * FROM accounts WHERE username = ?",
                    (username,),
                )
                if not row:
                    continue

                # Restore karma cache from DB
                total_karma = (row.get("comment_karma", 0) or 0) + (row.get("post_karma", 0) or 0)
                if total_karma != 0:
                    self._karma_cache[username] = (total_karma, time.time())

                # Restore health state from is_shadowbanned flag
                if row.get("is_shadowbanned"):
                    self._statuses[username] = self.BANNED
                elif not row.get("enabled"):
                    self._statuses[username] = self.BANNED
                else:
                    self._statuses[username] = self.HEALTHY

                # Restore last-used timestamp for LRU
                if row.get("last_action_at"):
                    try:
                        self._last_used[username] = datetime.fromisoformat(
                            row["last_action_at"]
                        )
                    except (ValueError, TypeError):
                        pass

            logger.debug(f"Restored state for {len(self._statuses)} accounts")
        except Exception as e:
            logger.warning(f"Could not restore account state from DB: {e}")

    # ── Hot-Reload Support ──────────────────────────────────────────

    def set_config_path(self, path: str):
        """Set the config file path for hot-reload monitoring."""
        self._config_path = path
        try:
            self._config_mtime = os.path.getmtime(path)
        except FileNotFoundError:
            self._config_mtime = None

    def reload(self, new_config: Optional[Config] = None):
        """Re-read config and update internal state.

        Args:
            new_config: If provided, use this config directly.
                        Otherwise, reload from the config file path.
        """
        with self._lock:
            if new_config:
                self.config = new_config
            elif self._config_path:
                try:
                    self.config = Config.load(self._config_path)
                except Exception as e:
                    logger.error(f"Failed to reload config: {e}")
                    return

            self._sync_accounts_to_db()
            self._cleanup_expired_cooldowns()

            if self._config_path:
                try:
                    self._config_mtime = os.path.getmtime(self._config_path)
                except FileNotFoundError:
                    pass

        logger.info("Account manager config reloaded")
        for cb in self._on_reload_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Reload callback error: {e}")

    def start_watching(self, interval: float = 10.0):
        """Start a background thread that polls config for changes."""
        if self._watching or not self._config_path:
            return
        self._watching = True
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            args=(interval,),
            daemon=True,
        )
        self._watcher_thread.start()
        logger.debug(f"Config watcher started (interval={interval}s)")

    def stop_watching(self):
        """Stop the config file watcher thread."""
        self._watching = False

    def _watch_loop(self, interval: float):
        """Poll config file for mtime changes."""
        while self._watching:
            time.sleep(interval)
            if not self._config_path:
                continue
            try:
                current_mtime = os.path.getmtime(self._config_path)
                if self._config_mtime and current_mtime != self._config_mtime:
                    logger.info(f"Config file changed, reloading: {self._config_path}")
                    self.reload()
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.error(f"Config watcher error: {e}")

    def on_reload(self, callback: Callable):
        """Register a callback to be called when config is reloaded."""
        self._on_reload_callbacks.append(callback)

    # ── Account Selection ───────────────────────────────────────────

    def get_best_account(self, client_id: Optional[str] = None) -> Optional[RedditAccount]:
        """Get the best available Reddit account for a given client.

        Selection algorithm:
        1. Get all enabled accounts from config
        2. Filter out banned, shadowbanned, and accounts on cooldown
        3. If client_id given, prefer accounts assigned to that client
        4. Filter by daily cap (karma tier limits)
        5. Round-robin with LRU fairness correction

        Args:
            client_id: Client slug to find assigned accounts for.
                       Falls back to all accounts if none are assigned.

        Returns:
            RedditAccount dataclass, or None if no accounts available.
        """
        with self._lock:
            self._cleanup_expired_cooldowns()

            accounts = self.config.get_enabled_accounts()
            if not accounts:
                logger.warning("No enabled accounts configured")
                return None

            # Step 1: Filter by health state
            available = []
            for acct in accounts:
                status = self._statuses.get(acct.username, self.HEALTHY)
                if status == self.BANNED:
                    continue
                if acct.username in self._cooldowns:
                    if datetime.utcnow() < self._cooldowns[acct.username]:
                        continue
                    else:
                        # Cooldown expired, mark healthy
                        del self._cooldowns[acct.username]
                        self._statuses[acct.username] = self.HEALTHY
                available.append(acct)

            if not available:
                logger.warning("No healthy accounts available (all banned/cooldown)")
                return None

            # Step 2: If client_id specified, prefer assigned accounts
            if client_id:
                client_assigned = [
                    a for a in available
                    if self._is_account_assigned_to_client(a, client_id)
                ]
                if client_assigned:
                    available = client_assigned
                # else: fall back to all available (unassigned pool)

            # Step 3: Filter by daily cap (respect karma tier limits)
            under_cap = []
            for acct in available:
                if self._is_under_daily_cap(acct):
                    under_cap.append(acct)
            if under_cap:
                available = under_cap
            else:
                logger.warning("All available accounts have reached daily caps")
                return None

            # Step 4: Karma gate -- prefer accounts with sufficient karma
            karma_ok = [a for a in available if self.is_karma_sufficient(a.username)]
            if karma_ok:
                available = karma_ok

            # Step 5: Round-robin rotation with LRU fairness
            rotation_key = client_id or "__global__"
            best = self._select_with_rotation(available, rotation_key)

            if best:
                self._last_used[best.username] = datetime.utcnow()
                logger.debug(
                    f"Account selected: {best.username} "
                    f"(tier={best.karma_tier}, client={client_id or 'any'})"
                )

            return best

    def get_account_by_username(self, username: str) -> Optional[RedditAccount]:
        """Get a specific account by username if it's healthy and available.

        Args:
            username: Reddit username to look up.

        Returns:
            RedditAccount or None if not found/unavailable.
        """
        with self._lock:
            for acct in self.config.get_enabled_accounts():
                if acct.username.lower() == username.lower():
                    status = self._statuses.get(acct.username, self.HEALTHY)
                    if status == self.BANNED:
                        logger.warning(f"Account {username} is banned")
                        return None
                    if acct.username in self._cooldowns:
                        if datetime.utcnow() < self._cooldowns[acct.username]:
                            logger.warning(f"Account {username} is on cooldown")
                            return None
                    return acct
        return None

    def _is_account_assigned_to_client(
        self, account: RedditAccount, client_id: str
    ) -> bool:
        """Check if an account is assigned to a specific client.

        Accounts with no assigned_subreddits or no client-specific assignments
        are considered available to all clients (unassigned pool).

        We check if the client's target subreddits overlap with the account's
        assigned subreddits. If the account has no assigned subreddits, it's
        available to everyone.
        """
        # Check if account has assigned_subreddits that match client's targets
        if not account.assigned_subreddits:
            return False  # Not specifically assigned -- part of general pool

        # Find the client config
        client = None
        for c in self.config.get_enabled_clients():
            if c.slug == client_id:
                client = c
                break

        if not client:
            return False

        # Check if any of the account's assigned subreddits match the client's targets
        acct_subs = {s.lower() for s in account.assigned_subreddits}
        client_subs = {s.lower() for s in (client.target_subreddits or [])}

        return bool(acct_subs & client_subs)

    def _is_under_daily_cap(self, account: RedditAccount) -> bool:
        """Check if an account is under its daily action cap."""
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Reset daily counters if needed
        self.db.execute(
            """UPDATE accounts SET daily_comments_today = 0, daily_posts_today = 0,
               daily_reset_date = ?
               WHERE username = ? AND (daily_reset_date IS NULL OR daily_reset_date < ?)""",
            (today, account.username, today),
        )
        self.db.commit()

        row = self.db.fetchone(
            "SELECT daily_comments_today, daily_posts_today, karma_tier FROM accounts WHERE username = ?",
            (account.username,),
        )
        if not row:
            return True  # Unknown account, allow

        actions_today = (row.get("daily_comments_today", 0) or 0) + (row.get("daily_posts_today", 0) or 0)
        tier_info = self.get_account_tier(account.username)
        daily_cap = tier_info["daily_cap"]

        return actions_today < daily_cap

    def _select_with_rotation(
        self, available: List[RedditAccount], rotation_key: str
    ) -> Optional[RedditAccount]:
        """Select an account using round-robin with LRU fairness correction.

        Args:
            available: List of candidate accounts.
            rotation_key: Key for tracking rotation index (client_id or global).

        Returns:
            Selected RedditAccount.
        """
        if not available:
            return None

        if len(available) == 1:
            return available[0]

        # Step 1: Round-robin -- advance rotation index
        idx = self._client_rotation.get(rotation_key, -1) + 1
        if idx >= len(available):
            idx = 0
        self._client_rotation[rotation_key] = idx

        best = available[idx]

        # Step 2: LRU fairness correction
        # If the selected account was used much more recently than the
        # least-recently-used account, switch to the LRU one.
        best_last_used = self._last_used.get(best.username)
        lru_account = min(
            available,
            key=lambda a: self._last_used.get(a.username, datetime.min),
        )
        lru_last_used = self._last_used.get(lru_account.username)

        if best_last_used and lru_last_used:
            # If best was used more than 5 minutes after the LRU account, switch
            if (best_last_used - lru_last_used).total_seconds() > 300:
                best = lru_account
                # Update rotation index to match
                for i, acct in enumerate(available):
                    if acct.username == best.username:
                        self._client_rotation[rotation_key] = i
                        break
        elif best_last_used and not lru_last_used:
            # LRU account was never used, prefer it
            best = lru_account
            for i, acct in enumerate(available):
                if acct.username == best.username:
                    self._client_rotation[rotation_key] = i
                    break

        return best

    # ── Karma Tier System ───────────────────────────────────────────

    def update_karma_cache(self, username: str, karma: int):
        """Store a fresh karma value for an account.

        Args:
            username: Reddit username.
            karma: Total karma value.
        """
        with self._lock:
            self._karma_cache[username] = (karma, time.time())

        # Also persist to DB
        self.db.upsert_account(username, comment_karma=karma)
        logger.debug(f"Karma cache updated: {username} = {karma}")

    def get_cached_karma(self, username: str) -> Optional[int]:
        """Return cached karma if fresh (< 12h), else None."""
        entry = self._karma_cache.get(username)
        if entry and (time.time() - entry[1]) < self.KARMA_CACHE_TTL:
            return entry[0]
        return None

    def is_karma_sufficient(self, username: str) -> bool:
        """Check if account has enough karma for write operations.

        Returns True if karma is sufficient OR if karma is unknown (cache miss).
        """
        karma = self.get_cached_karma(username)
        if karma is None:
            return True  # Unknown karma: don't block
        return karma >= self.MIN_KARMA_WRITE

    def get_account_tier(self, username: str) -> dict:
        """Return tier info for an account based on cached karma.

        Returns:
            dict with keys: tier (int 0-3), name, daily_cap, can_post, karma.
            Defaults to most conservative tier when karma is unknown.
        """
        # First check if the account has a configured tier
        for acct in self.config.accounts:
            if acct.username == username:
                # Use configured tier as baseline
                for min_k, tier_name, daily_cap, can_post in self.KARMA_TIERS:
                    if tier_name == acct.karma_tier:
                        return {
                            "tier": len(self.KARMA_TIERS) - 1 - self.KARMA_TIERS.index(
                                (min_k, tier_name, daily_cap, can_post)
                            ),
                            "name": tier_name,
                            "daily_cap": daily_cap,
                            "can_post": can_post,
                            "karma": self.get_cached_karma(username),
                        }

        # Fall back to karma-based tier
        karma = self.get_cached_karma(username)
        if karma is None:
            return {"tier": 0, "name": "new", "daily_cap": 3, "can_post": False, "karma": None}

        for min_k, tier_name, daily_cap, can_post in self.KARMA_TIERS:
            if karma >= min_k:
                tier_idx = self.KARMA_TIERS.index((min_k, tier_name, daily_cap, can_post))
                return {
                    "tier": len(self.KARMA_TIERS) - 1 - tier_idx,
                    "name": tier_name,
                    "daily_cap": daily_cap,
                    "can_post": can_post,
                    "karma": karma,
                }

        return {"tier": 0, "name": "new", "daily_cap": 3, "can_post": False, "karma": karma}

    def get_daily_cap(self, username: str) -> int:
        """Return the daily action cap for this account based on karma tier."""
        return self.get_account_tier(username)["daily_cap"]

    def can_post(self, username: str) -> bool:
        """Return True if account's karma tier allows posting (not just commenting)."""
        return self.get_account_tier(username)["can_post"]

    # ── Health State Management ─────────────────────────────────────

    def mark_cooldown(self, username: str, minutes: int = None):
        """Put an account on cooldown.

        Args:
            username: Reddit username.
            minutes: Cooldown duration. Defaults to DEFAULT_COOLDOWN_MINUTES.
        """
        if minutes is None:
            minutes = self.DEFAULT_COOLDOWN_MINUTES

        with self._lock:
            self._cooldowns[username] = datetime.utcnow() + timedelta(minutes=minutes)
            self._statuses[username] = self.COOLDOWN

        # Persist to DB via action_log
        account_row = self.db.fetchone(
            "SELECT id FROM accounts WHERE username = ?", (username,)
        )
        if account_row:
            self.db.record_action(
                account_id=account_row["id"],
                action_type="cooldown",
                success=True,
                error_message=f"Cooldown for {minutes}min",
            )

        logger.info(f"Account {username}: cooldown for {minutes}min")

    def mark_warned(self, username: str, reason: str):
        """Mark an account as warned (suspicious activity detected).

        Args:
            username: Reddit username.
            reason: Reason for the warning.
        """
        with self._lock:
            self._statuses[username] = self.WARNED

        account_row = self.db.fetchone(
            "SELECT id FROM accounts WHERE username = ?", (username,)
        )
        if account_row:
            self.db.record_action(
                account_id=account_row["id"],
                action_type="warning",
                success=False,
                error_message=reason,
            )

        logger.warning(f"Account {username}: WARNED -- {reason}")

    def mark_banned(self, username: str, reason: str):
        """Mark an account as banned (permanently unavailable).

        Args:
            username: Reddit username.
            reason: Reason for the ban.
        """
        with self._lock:
            self._statuses[username] = self.BANNED

        # Persist ban to DB
        self.db.execute(
            "UPDATE accounts SET is_shadowbanned = 1, enabled = 0, updated_at = datetime('now') "
            "WHERE username = ?",
            (username,),
        )
        self.db.commit()

        account_row = self.db.fetchone(
            "SELECT id FROM accounts WHERE username = ?", (username,)
        )
        if account_row:
            self.db.record_action(
                account_id=account_row["id"],
                action_type="banned",
                success=False,
                error_message=reason,
            )

        logger.error(f"Account {username}: BANNED -- {reason}")

    def mark_healthy(self, username: str):
        """Mark an account as healthy (clear cooldown/warning).

        Args:
            username: Reddit username.
        """
        with self._lock:
            self._statuses[username] = self.HEALTHY
            if username in self._cooldowns:
                del self._cooldowns[username]

        self.db.execute(
            "UPDATE accounts SET is_shadowbanned = 0, enabled = 1, updated_at = datetime('now') "
            "WHERE username = ?",
            (username,),
        )
        self.db.commit()
        logger.info(f"Account {username}: marked healthy")

    def get_status(self, username: str) -> str:
        """Get the current health status of an account.

        Args:
            username: Reddit username.

        Returns:
            One of: healthy, cooldown, warned, banned.
        """
        with self._lock:
            status = self._statuses.get(username, self.HEALTHY)
            # Check if cooldown has expired
            if status == self.COOLDOWN and username in self._cooldowns:
                if datetime.utcnow() >= self._cooldowns[username]:
                    del self._cooldowns[username]
                    self._statuses[username] = self.HEALTHY
                    return self.HEALTHY
            return status

    # ── Cleanup & Utility ───────────────────────────────────────────

    def _cleanup_expired_cooldowns(self):
        """Remove expired cooldown entries."""
        now = datetime.utcnow()
        expired = [k for k, v in self._cooldowns.items() if now >= v]
        for username in expired:
            del self._cooldowns[username]
            if self._statuses.get(username) == self.COOLDOWN:
                self._statuses[username] = self.HEALTHY
                logger.debug(f"Cooldown expired for {username}")

    def get_all_health(self) -> List[Dict]:
        """Get health status summary for all configured accounts.

        Returns:
            List of dicts with username, status, tier, actions_today, cooldown_until.
        """
        results = []
        with self._lock:
            for account in self.config.get_enabled_accounts():
                username = account.username
                status = self.get_status(username)
                tier = self.get_account_tier(username)

                # Get today's action count from DB
                row = self.db.fetchone(
                    "SELECT daily_comments_today, daily_posts_today FROM accounts WHERE username = ?",
                    (username,),
                )
                actions_today = 0
                if row:
                    actions_today = (row.get("daily_comments_today", 0) or 0) + \
                                    (row.get("daily_posts_today", 0) or 0)

                results.append({
                    "username": username,
                    "status": status,
                    "tier_name": tier["name"],
                    "tier_num": tier["tier"],
                    "daily_cap": tier["daily_cap"],
                    "actions_today": actions_today,
                    "can_post": tier["can_post"],
                    "karma": tier.get("karma"),
                    "cooldown_until": (
                        self._cooldowns[username].isoformat()
                        if username in self._cooldowns
                        else None
                    ),
                    "last_used": (
                        self._last_used[username].isoformat()
                        if username in self._last_used
                        else None
                    ),
                    "assigned_subreddits": account.assigned_subreddits,
                })

        return results

    def get_accounts_for_client(self, client_id: str) -> List[RedditAccount]:
        """Get all available accounts that can serve a specific client.

        Returns accounts assigned to the client, plus any unassigned accounts.

        Args:
            client_id: Client slug.

        Returns:
            List of available RedditAccount instances.
        """
        with self._lock:
            self._cleanup_expired_cooldowns()
            available = []

            for acct in self.config.get_enabled_accounts():
                status = self._statuses.get(acct.username, self.HEALTHY)
                if status in (self.BANNED,):
                    continue
                if acct.username in self._cooldowns:
                    if datetime.utcnow() < self._cooldowns[acct.username]:
                        continue

                # Include if: assigned to this client OR not assigned to anyone
                if self._is_account_assigned_to_client(acct, client_id):
                    available.append(acct)
                elif not acct.assigned_subreddits:
                    available.append(acct)

            return available

    def record_action(self, username: str, action_type: str,
                      subreddit: str = None, client_id: int = None,
                      reddit_id: str = None, success: bool = True,
                      error_message: str = None):
        """Record an action taken by an account and update counters.

        Wraps Database.record_action and also updates last-used timestamp.

        Args:
            username: Reddit username that performed the action.
            action_type: Type of action (comment, post, etc).
            subreddit: Subreddit the action was in.
            client_id: Numeric client ID from the database.
            reddit_id: Reddit thing ID (comment/post ID).
            success: Whether the action succeeded.
            error_message: Error details if failed.
        """
        account_row = self.db.fetchone(
            "SELECT id FROM accounts WHERE username = ?", (username,)
        )
        if not account_row:
            logger.warning(f"Cannot record action: account {username} not in DB")
            return

        self.db.record_action(
            account_id=account_row["id"],
            action_type=action_type,
            subreddit=subreddit,
            client_id=client_id,
            reddit_id=reddit_id,
            success=success,
            error_message=error_message,
        )

        with self._lock:
            self._last_used[username] = datetime.utcnow()

    def __repr__(self) -> str:
        total = len(self.config.accounts)
        enabled = len(self.config.get_enabled_accounts())
        healthy = sum(
            1 for a in self.config.get_enabled_accounts()
            if self._statuses.get(a.username, self.HEALTHY) == self.HEALTHY
        )
        return (
            f"AccountManager(total={total}, enabled={enabled}, healthy={healthy})"
        )
