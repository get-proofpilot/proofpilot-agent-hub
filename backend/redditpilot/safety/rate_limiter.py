"""
RedditPilot Rate Limiter
Human-like timing with jitter, daily caps, and circuit breakers.
Adapted from MiloAgent's rate_limiter.py and markmelnic's timeout system.
"""

import time
import random
import logging
from datetime import datetime, timedelta
from ..core.config import Config
from ..core.database import Database

logger = logging.getLogger("redditpilot.ratelimit")


class RateLimiter:
    """Enforces human-like timing and daily action caps."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._circuit_breaker_open = False
        self._circuit_breaker_until = None
        self._consecutive_failures = 0

    def can_act(self, account_id: int, action_type: str = "comment") -> dict:
        """
        Check if an action is allowed right now.
        Returns dict with allowed, reason, and suggested wait time.
        """
        # Check circuit breaker
        if self._circuit_breaker_open:
            if datetime.utcnow() < self._circuit_breaker_until:
                remaining = (self._circuit_breaker_until - datetime.utcnow()).seconds
                return {
                    "allowed": False,
                    "reason": f"Circuit breaker open. Wait {remaining}s",
                    "wait_seconds": remaining,
                }
            else:
                self._circuit_breaker_open = False
                self._consecutive_failures = 0

        # Check daily cap
        account = self.db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return {"allowed": False, "reason": "Account not found", "wait_seconds": 0}

        if account["is_shadowbanned"]:
            return {"allowed": False, "reason": "Account is shadowbanned", "wait_seconds": 0}

        # Reset daily counters if needed
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if account.get("daily_reset_date") != today:
            self.db.execute(
                "UPDATE accounts SET daily_comments_today = 0, daily_posts_today = 0, daily_reset_date = ? WHERE id = ?",
                (today, account_id)
            )
            self.db.commit()
            account = self.db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))

        # Check tier-based caps
        tier_caps = {
            "new": {"comment": 3, "post": 0},
            "growing": {"comment": 7, "post": 2},
            "established": {"comment": 12, "post": 5},
            "veteran": {"comment": 20, "post": 10},
        }
        caps = tier_caps.get(account["karma_tier"], tier_caps["growing"])

        if action_type == "comment" and account["daily_comments_today"] >= caps["comment"]:
            return {
                "allowed": False,
                "reason": f"Daily comment cap reached ({caps['comment']} for {account['karma_tier']})",
                "wait_seconds": self._seconds_until_midnight(),
            }

        if action_type == "post" and account["daily_posts_today"] >= caps["post"]:
            return {
                "allowed": False,
                "reason": f"Daily post cap reached ({caps['post']} for {account['karma_tier']})",
                "wait_seconds": self._seconds_until_midnight(),
            }

        # Check hourly action rate
        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        hourly_count = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM action_log WHERE account_id = ? AND created_at > ?",
            (account_id, one_hour_ago)
        )
        max_per_hour = self.config.safety.max_actions_per_hour
        if hourly_count and hourly_count["cnt"] >= max_per_hour:
            return {
                "allowed": False,
                "reason": f"Hourly action limit reached ({max_per_hour}/hr)",
                "wait_seconds": random.randint(300, 900),
            }

        # Check minimum delay since last action
        if account.get("last_action_at"):
            last_action = datetime.fromisoformat(account["last_action_at"])
            elapsed = (datetime.utcnow() - last_action).total_seconds()
            min_delay = self.config.safety.min_delay_seconds
            if elapsed < min_delay:
                wait = min_delay - elapsed + random.uniform(5, 30)
                return {
                    "allowed": False,
                    "reason": f"Too soon since last action ({elapsed:.0f}s < {min_delay}s minimum)",
                    "wait_seconds": int(wait),
                }

        return {"allowed": True, "reason": "OK", "wait_seconds": 0}

    def get_human_delay(self, action_type: str = "comment") -> float:
        """
        Calculate a human-like delay for the next action.
        Uses Gaussian distribution with jitter for natural timing.
        """
        base_delays = {
            "comment": (
                self.config.safety.min_delay_seconds,
                self.config.safety.max_delay_seconds
            ),
            "post": (60, 300),
            "scan": (5, 15),
        }

        min_d, max_d = base_delays.get(action_type, (30, 120))
        base = random.uniform(min_d, max_d)

        # Add Gaussian jitter (15% standard deviation)
        jitter = random.gauss(0, base * 0.15)
        delay = max(min_d * 0.5, base + jitter)

        # Occasionally add a longer pause (human breaks)
        if random.random() < 0.1:  # 10% chance
            delay += random.uniform(60, 300)  # 1-5 minute break

        return delay

    def record_failure(self):
        """Record a failure for circuit breaker logic."""
        self._consecutive_failures += 1

        if self._consecutive_failures >= 3:
            # Open circuit breaker
            cooldown = min(300 * (2 ** (self._consecutive_failures - 3)), 3600)
            self._circuit_breaker_open = True
            self._circuit_breaker_until = datetime.utcnow() + timedelta(seconds=cooldown)
            logger.warning(f"Circuit breaker OPEN for {cooldown}s after {self._consecutive_failures} failures")

    def record_success(self):
        """Record a success, resetting failure counter."""
        self._consecutive_failures = max(0, self._consecutive_failures - 1)

    def _seconds_until_midnight(self) -> int:
        now = datetime.utcnow()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((midnight - now).total_seconds())
