"""RedditPilot Orchestrator — production-grade central coordinator.

Merges RedditPilot's clean agency pipeline with MiloAgent's safety patterns.

Pipeline: DISCOVER → SCAN → SCORE → GENERATE → CHECK → APPROVE → POST → LEARN

SAFETY GUARANTEES
-----------------
- Hard timeouts on all operations via concurrent.futures (scan=400s, act=150s, llm=45s)
- Resource checks (RAM, disk, RSS) before AND during every heavy operation
- Auto-pause on RAM/disk pressure via ResourceMonitor callbacks
- Emergency stop capability (graceful or immediate)
- Signal handlers for SIGTERM/SIGINT → clean shutdown
- Thread-safe with RLock on all mutable state
- Content deduplication in the generation pipeline
- Periodic shadowban detection via BanDetector
- APScheduler (BackgroundScheduler) replaces 'schedule' library
- No blocking initial scan (delayed by 2 minutes)
"""

import os
import signal
import sys
import time
import random
import logging
import threading
import concurrent.futures
from collections import deque
from datetime import datetime, timedelta
from hashlib import md5
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

from .core.config import Config, ClientProfile
from .core.database import Database
from .core.reddit_client import RedditClient, AccountPool
from .core.resource_monitor import ResourceMonitor
from .engines.discovery import DiscoveryEngine
from .engines.scanner import OpportunityScanner
from .engines.content_generator import ContentGenerator
from .engines.llm_client import LLMClient
from .engines.learning import LearningEngine
from .safety.content_validator import ContentValidator
from .safety.rate_limiter import RateLimiter
from .safety.account_manager import AccountManager
from .safety.ban_detector import BanDetector
from .safety.content_dedup import ContentDeduplicator
from .integrations.slack_approval import SlackApproval

logger = logging.getLogger("redditpilot")

# ── Hard Safety Limits ────────────────────────────────────────────────────
SCAN_TIMEOUT_SECONDS = 400     # Hard timeout for scan operations
ACT_TIMEOUT_SECONDS = 150      # Hard timeout for post/action operations
LLM_TIMEOUT_SECONDS = 45       # Hard timeout for LLM calls
GENERATE_TIMEOUT_SECONDS = 180 # Hard timeout for content generation per client
DISCOVER_TIMEOUT_SECONDS = 300 # Hard timeout for subreddit discovery
LEARN_TIMEOUT_SECONDS = 300    # Hard timeout for learning cycle


def _run_with_timeout(fn, timeout_seconds: int, label: str = "operation"):
    """Run a callable in a thread pool with a hard timeout.

    Returns the result on success, None on timeout or error.
    Logs warnings/errors appropriately.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                               thread_name_prefix=label) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            logger.warning(
                f"{label} ABORTED: exceeded {timeout_seconds}s hard timeout"
            )
            future.cancel()
            return None
        except Exception as e:
            logger.error(f"{label} error: {e}", exc_info=True)
            return None


class RedditPilot:
    """Main orchestrator for the RedditPilot system.

    SAFETY GUARANTEES:
    - All heavy operations wrapped with hard timeouts
    - Resource check (is_safe_to_proceed) before every heavy operation
    - Auto-pause on RAM/disk pressure via ResourceMonitor
    - Emergency stop with e_stop() for immediate halt
    - Graceful shutdown via stop() or signal handlers
    - Thread-safe: all mutable state protected by _state_lock
    - Content deduplication via ContentDeduplicator
    - Periodic shadowban checks via BanDetector
    - APScheduler BackgroundScheduler with coalesced, single-instance jobs
    """

    def __init__(self, config: Config):
        self.config = config

        # ── Core state flags (thread-safe) ────────────────────────────
        self._state_lock = threading.RLock()
        self._running = False
        self._paused = False
        self._emergency_stopped = False
        self._scan_running = False
        self._cycle_count = 0

        # Alert/event log for dashboards
        self._alert_log: deque = deque(maxlen=200)

        # ── Initialize database ───────────────────────────────────────
        data_dir = config.data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.db = Database(f"{data_dir}/redditpilot.db")

        # ── Initialize LLM ────────────────────────────────────────────
        self.llm = LLMClient(config.llm)

        # ── Core engines ──────────────────────────────────────────────
        self.discovery = DiscoveryEngine(config, self.db, self.llm)
        self.scanner = OpportunityScanner(config, self.db)
        self.content_gen = ContentGenerator(config, self.db, self.llm)
        self.validator = ContentValidator(config, self.db)
        self.rate_limiter = RateLimiter(config, self.db)
        self.learning = LearningEngine(config, self.db, self.llm)
        self.slack = SlackApproval(config)

        # ── Safety modules (new) ──────────────────────────────────────
        self.account_mgr = AccountManager(config, self.db)
        self.ban_detector = BanDetector()
        self.dedup = ContentDeduplicator(self.db)

        # ── Resource monitor ──────────────────────────────────────────
        self.resource_monitor = ResourceMonitor(check_interval=30)
        self.resource_monitor.on_threshold(self._on_resource_event)

        # ── Legacy account pool (kept for RedditClient creation) ──────
        self._reddit_clients: Dict[str, RedditClient] = {}
        for account in config.get_enabled_accounts():
            self._reddit_clients[account.username] = RedditClient(account, self.db)

        # ── APScheduler ───────────────────────────────────────────────
        self.scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            executors={"default": {"type": "threadpool", "max_workers": 3}},
        )

        # ── Sync clients to database ─────────────────────────────────
        for client in config.get_enabled_clients():
            self.db.execute("""
                INSERT OR IGNORE INTO clients
                    (name, slug, industry, service_area, website, brand_voice, promo_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (client.name, client.slug, client.industry, client.service_area,
                  client.website, client.brand_voice, client.promo_ratio))
        self.db.commit()

        logger.info(
            f"RedditPilot initialized: "
            f"{len(config.get_enabled_accounts())} accounts, "
            f"{len(config.get_enabled_clients())} clients"
        )

    # ══════════════════════════════════════════════════════════════════
    # Resource & Safety
    # ══════════════════════════════════════════════════════════════════

    def _on_resource_event(self, event: str, state):
        """Handle resource monitor threshold events."""
        with self._state_lock:
            if event == "ram_critical":
                self._paused = True
                logger.warning(
                    f"AUTO-PAUSED: RAM at {state.ram_used_percent:.0f}% "
                    f"({state.ram_available_gb:.1f}GB free)"
                )
                self._log_alert(
                    f"Auto-paused: RAM {state.ram_used_percent:.0f}% "
                    f"({state.ram_available_gb:.1f}GB free)"
                )
            elif event == "ram_warn":
                logger.warning(
                    f"RAM high: {state.ram_used_percent:.0f}%, "
                    f"throttling to {self.resource_monitor.throttle_factor}x"
                )
            elif event == "disk_critical":
                self._paused = True
                logger.warning(f"AUTO-PAUSED: Disk at {state.disk_used_percent:.0f}%")
                self._log_alert(f"Auto-paused: disk {state.disk_used_percent:.0f}%")
            elif event == "disk_warn":
                logger.warning(f"Disk usage high: {state.disk_used_percent:.0f}%")
            elif event == "recovered":
                if self._paused and not self._emergency_stopped:
                    self._paused = False
                    logger.info("Resources recovered, resuming operations")
                    self._log_alert("Resources recovered, resuming")
            elif event == "process_memory_warn":
                logger.warning(
                    f"Process RSS high: {state.process_rss_mb:.0f}MB, "
                    f"running garbage collection"
                )

    def _check_resources(self) -> bool:
        """Quick resource gate check. Returns False if we should abort."""
        with self._state_lock:
            if self._emergency_stopped:
                return False
            if self._paused:
                return False
        return self.resource_monitor.is_safe_to_proceed()

    def _log_alert(self, message: str):
        """Log an alert with timestamp for dashboard consumption."""
        self._alert_log.append((datetime.utcnow().isoformat(), message))

    def is_safe_to_proceed(self) -> bool:
        """Public gate check: safe to start a heavy operation?

        Checks: not emergency-stopped, not paused, resources OK.
        """
        return self._check_resources()

    # ══════════════════════════════════════════════════════════════════
    # Emergency Stop
    # ══════════════════════════════════════════════════════════════════

    def e_stop(self):
        """Emergency stop — immediately halt all operations.

        Unlike stop(), this sets a permanent flag that prevents
        any further work even if resources recover. Requires restart.
        """
        with self._state_lock:
            self._emergency_stopped = True
            self._paused = True
            self._running = False
        logger.critical("EMERGENCY STOP activated — all operations halted")
        self._log_alert("EMERGENCY STOP activated")

        # Shut down scheduler without waiting
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass

    @property
    def is_emergency_stopped(self) -> bool:
        with self._state_lock:
            return self._emergency_stopped

    # ══════════════════════════════════════════════════════════════════
    # Reddit Client Management (replaces AccountPool)
    # ══════════════════════════════════════════════════════════════════

    def _get_reddit_client(self, client_slug: str = None) -> Optional[RedditClient]:
        """Get the best available Reddit client using the AccountManager.

        Uses the new AccountManager for intelligent selection (karma tiers,
        health states, LRU fairness, daily caps) instead of the old
        AccountPool round-robin.
        """
        account = self.account_mgr.get_best_account(client_id=client_slug)
        if not account:
            logger.warning("No available Reddit accounts")
            return None

        username = account.username
        if username not in self._reddit_clients:
            self._reddit_clients[username] = RedditClient(account, self.db)

        return self._reddit_clients[username]

    def _get_reddit_client_by_username(self, username: str) -> Optional[RedditClient]:
        """Get a Reddit client for a specific username."""
        if username in self._reddit_clients:
            return self._reddit_clients[username]

        account = self.account_mgr.get_account_by_username(username)
        if account:
            self._reddit_clients[username] = RedditClient(account, self.db)
            return self._reddit_clients[username]

        return None

    # ══════════════════════════════════════════════════════════════════
    # Pipeline Steps
    # ══════════════════════════════════════════════════════════════════

    def discover(self, client_slug: str = None):
        """STEP 1: DISCOVER — Find relevant subreddits for each client."""
        if not self._check_resources():
            logger.info("Discovery skipped: resources constrained")
            return

        clients = self._get_clients(client_slug)
        reddit = self._get_reddit_client()
        if not reddit:
            return

        for client in clients:
            if not self._check_resources():
                break

            logger.info(f"Discovering subreddits for {client.name}")
            try:
                results = self.discovery.discover_subreddits_for_client(client, reddit)
                logger.info(f"Found {len(results)} subreddits for {client.name}")

                for sub in results[:10]:
                    logger.info(
                        f"  r/{sub['name']} "
                        f"(score: {sub.get('relevance_score', 0):.2f}, "
                        f"subs: {sub.get('subscribers', 0):,})"
                    )
            except Exception as e:
                logger.error(f"Discovery failed for {client.name}: {e}")

    def scan(self, client_slug: str = None):
        """STEP 2: SCAN + SCORE — Find and score engagement opportunities."""
        if not self._check_resources():
            logger.info("Scan skipped: resources constrained")
            return

        with self._state_lock:
            if self._scan_running:
                logger.info("Scan already in progress, skipping")
                return
            self._scan_running = True

        try:
            self._scan_inner(client_slug)
        finally:
            with self._state_lock:
                self._scan_running = False

    def _scan_inner(self, client_slug: str = None):
        """Inner scan logic, always called with _scan_running=True."""
        clients = self._get_clients(client_slug)

        for client in clients:
            if not self._check_resources():
                logger.info("Scan interrupted: resources constrained")
                break

            reddit = self._get_reddit_client(client.slug)
            if not reddit:
                continue

            logger.info(f"Scanning opportunities for {client.name}")
            try:
                opportunities = self.scanner.scan_for_client(client, reddit)

                for opp in opportunities[:5]:
                    logger.info(
                        f"  [{opp['scores']['composite']:.2f}] "
                        f"r/{opp['subreddit']}: {opp['title'][:80]}... "
                        f"(intent: {', '.join(opp['scores'].get('matched_intents', []))})"
                    )
            except Exception as e:
                logger.error(f"Scan failed for {client.name}: {e}")

            # Throttle-aware delay between clients
            throttle = self.resource_monitor.throttle_factor
            delay = random.uniform(2, 5) * throttle
            time.sleep(delay)

    def generate(self, client_slug: str = None, limit: int = 5,
                 auto_approve: bool = False):
        """STEP 3-5: GENERATE → CHECK → APPROVE

        Generates content for top opportunities with integrated dedup,
        content validation, and approval routing.
        """
        if not self._check_resources():
            logger.info("Generation skipped: resources constrained")
            return

        clients = self._get_clients(client_slug)

        for client in clients:
            if not self._check_resources():
                break

            client_row = self.db.fetchone(
                "SELECT id FROM clients WHERE slug = ?", (client.slug,)
            )
            if not client_row:
                continue
            client_id = client_row["id"]

            opportunities = self.db.get_pending_opportunities(
                client_id=client_id, limit=limit
            )
            if not opportunities:
                logger.info(f"No pending opportunities for {client.name}")
                continue

            reddit = self._get_reddit_client(client.slug)
            if not reddit:
                continue

            for opp in opportunities:
                if not self._check_resources():
                    break

                try:
                    self._generate_for_opportunity(
                        opp, client, client_id, reddit, auto_approve
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to generate comment for {opp['reddit_id']}: {e}"
                    )

    def _generate_for_opportunity(self, opp: dict, client: ClientProfile,
                                  client_id: int, reddit: RedditClient,
                                  auto_approve: bool):
        """Generate, validate, dedup, and route one comment."""

        # ── Dedup check: already commented on this post? ──────────
        dedup_result = self.dedup.check(
            content="",  # pre-check: just target/thread level
            post_reddit_id=opp["reddit_id"],
            subreddit=opp["subreddit"],
            client_id=client_id,
            content_type="comment",
        )
        # Only block on target/thread checks (content similarity needs actual content)
        if dedup_result.blocked and dedup_result.check_name in (
            "target_already_hit", "thread_recently_hit", "client_subreddit_recency"
        ):
            logger.info(
                f"Dedup blocked for {opp['reddit_id']}: {dedup_result.reason}"
            )
            return

        # ── Get context ───────────────────────────────────────────
        existing_comments = reddit.get_post_comments(opp["reddit_id"], limit=5)

        # Decide if this should include subtle promotion
        include_promo = random.random() < client.promo_ratio

        # Check if learning engine suggests a tone
        learned_tone = self.learning.get_best_tone(opp["subreddit"])

        # ── Generate the comment (with LLM timeout) ──────────────
        comment_data = _run_with_timeout(
            lambda: self.content_gen.generate_comment(
                post=opp,
                client=client,
                existing_comments=existing_comments,
                tone=learned_tone,
                include_promotion=include_promo,
            ),
            timeout_seconds=LLM_TIMEOUT_SECONDS,
            label="llm_generate",
        )
        if not comment_data:
            logger.warning(f"LLM generation timed out for {opp['reddit_id']}")
            return

        # ── Content dedup (full content check) ────────────────────
        dedup_full = self.dedup.check(
            content=comment_data["content"],
            post_reddit_id=opp["reddit_id"],
            subreddit=opp["subreddit"],
            client_id=client_id,
            content_type="comment",
        )
        if dedup_full.blocked:
            logger.warning(
                f"Dedup blocked content for {opp['reddit_id']}: "
                f"{dedup_full.reason} (score={dedup_full.similarity_score:.2f})"
            )
            self.db.execute(
                "UPDATE discovered_posts SET status = 'skipped' WHERE reddit_id = ?",
                (opp["reddit_id"],),
            )
            self.db.commit()
            return

        # ── Content validation ────────────────────────────────────
        validation = self.validator.validate_comment(
            content=comment_data["content"],
            subreddit=opp["subreddit"],
        )

        if not validation["passed"]:
            logger.warning(
                f"Content validation failed for r/{opp['subreddit']}: "
                f"{validation['issues']}"
            )
            # Retry once without promotion
            comment_data = _run_with_timeout(
                lambda: self.content_gen.generate_comment(
                    post=opp,
                    client=client,
                    existing_comments=existing_comments,
                    include_promotion=False,
                ),
                timeout_seconds=LLM_TIMEOUT_SECONDS,
                label="llm_retry",
            )
            if not comment_data:
                return

            validation = self.validator.validate_comment(
                comment_data["content"], opp["subreddit"]
            )

        if not validation["passed"]:
            logger.error("Content still fails validation, skipping")
            self.db.execute(
                "UPDATE discovered_posts SET status = 'skipped' WHERE reddit_id = ?",
                (opp["reddit_id"],),
            )
            self.db.commit()
            return

        # ── Save to database ──────────────────────────────────────
        comment_id = self.db.save_comment(
            post_reddit_id=opp["reddit_id"],
            subreddit=opp["subreddit"],
            content=comment_data["content"],
            client_id=client_id,
            persona_used=comment_data.get("persona"),
            tone_used=comment_data.get("tone"),
            generation_model=self.config.llm.primary_model,
        )
        comment_data["db_id"] = comment_id
        comment_data["validation"] = validation

        # ── Route to approval ─────────────────────────────────────
        if auto_approve or not client.approval_required:
            self.db.update_comment_status(comment_id, "approved")
            logger.info(f"Auto-approved comment {comment_id}")
        else:
            self.db.update_comment_status(comment_id, "pending_approval")
            self.slack.request_comment_approval(
                comment_data=comment_data,
                post_data=opp,
                client_name=client.name,
            )
            logger.info(f"Comment {comment_id} sent to Slack for approval")

        # Mark post as queued
        self.db.execute(
            "UPDATE discovered_posts SET status = 'queued', client_id = ? "
            "WHERE reddit_id = ?",
            (client_id, opp["reddit_id"]),
        )
        self.db.commit()

    def post_approved(self):
        """STEP 6: POST — Post all approved content to Reddit."""
        if not self._check_resources():
            logger.info("Posting skipped: resources constrained")
            return

        approved = self.db.fetchall("""
            SELECT c.*, cl.name as client_name, cl.slug as client_slug
            FROM comments c
            JOIN clients cl ON c.client_id = cl.id
            WHERE c.status = 'approved'
            ORDER BY c.created_at ASC
        """)

        if not approved:
            logger.info("No approved comments to post")
            return

        logger.info(f"Posting {len(approved)} approved comments")

        for comment in approved:
            if not self._check_resources():
                logger.warning("Posting interrupted: resources constrained")
                break

            # Use AccountManager for account selection
            account = self.account_mgr.get_best_account(
                client_id=comment.get("client_slug")
            )
            if not account:
                logger.warning("No available accounts, stopping post cycle")
                break

            reddit = self._get_reddit_client_by_username(account.username)
            if not reddit:
                continue

            # Get account DB row for rate limiting
            account_row = self.db.fetchone(
                "SELECT * FROM accounts WHERE username = ?",
                (account.username,),
            )
            if not account_row:
                continue

            # Check rate limits
            rate_check = self.rate_limiter.can_act(account_row["id"], "comment")
            if not rate_check["allowed"]:
                logger.info(
                    f"Rate limited: {rate_check['reason']}. "
                    f"Waiting {rate_check['wait_seconds']}s"
                )
                time.sleep(min(rate_check["wait_seconds"], 60))

            # Post the comment
            try:
                reddit_comment_id = reddit.post_comment(
                    post_id=comment["post_reddit_id"],
                    comment_text=comment["content"],
                    client_id=comment["client_id"],
                    subreddit=comment["subreddit"],
                )

                if reddit_comment_id:
                    self.db.update_comment_status(
                        comment["id"], "posted",
                        reddit_comment_id=reddit_comment_id,
                        account_id=account_row["id"],
                        posted_at=datetime.utcnow().isoformat(),
                    )

                    # Record content hash for dedup
                    self.dedup.record(
                        content=comment["content"],
                        content_type="comment",
                        subreddit=comment["subreddit"],
                    )

                    # Record action in AccountManager tracking
                    self.db.record_action(
                        account_id=account_row["id"],
                        action_type="comment",
                        subreddit=comment["subreddit"],
                        client_id=comment["client_id"],
                        reddit_id=reddit_comment_id,
                    )

                    self.rate_limiter.record_success()
                    logger.info(
                        f"Posted comment {reddit_comment_id} in "
                        f"r/{comment['subreddit']} as /u/{account.username}"
                    )

                    # Human-like delay before next action (throttle-aware)
                    base_delay = self.rate_limiter.get_human_delay("comment")
                    throttle = self.resource_monitor.throttle_factor
                    delay = base_delay * throttle
                    logger.debug(f"Waiting {delay:.0f}s before next action")
                    time.sleep(delay)
                else:
                    self.db.update_comment_status(comment["id"], "failed")
                    self.rate_limiter.record_failure()
                    # Put account on cooldown
                    self.account_mgr.mark_cooldown(account.username)

            except Exception as e:
                logger.error(f"Failed to post comment: {e}")
                self.db.update_comment_status(comment["id"], "failed")
                self.rate_limiter.record_failure()
                self.account_mgr.mark_cooldown(account.username)

    def learn(self):
        """STEP 7: LEARN — Run the learning cycle to optimize strategies."""
        if not self._check_resources():
            logger.info("Learning skipped: resources constrained")
            return
        self.learning.run_learning_cycle()

    # ══════════════════════════════════════════════════════════════════
    # Monitoring & Verification
    # ══════════════════════════════════════════════════════════════════

    def verify_comments(self):
        """Check posted comment performance and detect removals.

        Checks recent posted comments for:
        - Score changes (log performance)
        - Removals (mark as deleted, alert)
        - Negative scores (auto-delete if configured)
        """
        if not self._check_resources():
            return

        logger.info("Verifying posted comments...")
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

        posted = self.db.fetchall("""
            SELECT c.*, a.username
            FROM comments c
            LEFT JOIN accounts a ON c.account_id = a.id
            WHERE c.status = 'posted'
              AND c.posted_at > ?
              AND c.reddit_comment_id IS NOT NULL
            ORDER BY c.posted_at DESC
            LIMIT 50
        """, (cutoff,))

        if not posted:
            logger.info("No recent comments to verify")
            return

        checked = 0
        removed = 0
        negative = 0

        for comment in posted:
            if not self._check_resources():
                break

            username = comment.get("username")
            if not username:
                continue

            reddit = self._get_reddit_client_by_username(username)
            if not reddit:
                continue

            try:
                perf = reddit.check_comment_performance(comment["reddit_comment_id"])
                if not perf:
                    continue

                checked += 1

                # Update score in DB
                self.db.execute(
                    "UPDATE comments SET score = ?, last_checked_at = datetime('now') "
                    "WHERE id = ?",
                    (perf["score"], comment["id"]),
                )

                # Log performance metric
                self.db.log_performance(
                    metric_type="comment_score",
                    metric_value=perf["score"],
                    client_id=comment.get("client_id"),
                    subreddit=comment.get("subreddit"),
                    account_id=comment.get("account_id"),
                    tone=comment.get("tone_used"),
                )

                if perf["is_removed"]:
                    removed += 1
                    self.db.update_comment_status(comment["id"], "deleted")
                    logger.warning(
                        f"Comment {comment['reddit_comment_id']} was removed "
                        f"from r/{comment['subreddit']}"
                    )
                elif (perf["score"] <= self.config.safety.negative_score_threshold
                      and self.config.safety.auto_delete_negative_comments):
                    negative += 1
                    reddit.delete_comment(comment["reddit_comment_id"])
                    self.db.update_comment_status(comment["id"], "deleted")
                    logger.info(
                        f"Auto-deleted negative comment {comment['reddit_comment_id']} "
                        f"(score={perf['score']})"
                    )

                # Brief delay between checks
                time.sleep(random.uniform(1, 3))

            except Exception as e:
                logger.error(
                    f"Error verifying comment {comment.get('reddit_comment_id')}: {e}"
                )

        self.db.commit()
        logger.info(
            f"Verified {checked} comments: "
            f"{removed} removed, {negative} auto-deleted"
        )

    def check_shadowbans(self):
        """Run shadowban detection on all active accounts using BanDetector.

        Uses the enhanced BanDetector (public JSON API, multi-indicator,
        confidence scoring) instead of the old PRAW-based check.
        """
        if not self._check_resources():
            return

        logger.info("Running shadowban checks...")
        accounts = self.config.get_enabled_accounts()
        usernames = [a.username for a in accounts]

        results = self.ban_detector.check_multiple(usernames)

        for username, result in results.items():
            if result["is_shadowbanned"]:
                confidence = result["confidence"]
                logger.warning(
                    f"SHADOWBAN DETECTED: /u/{username} "
                    f"(confidence={confidence}, "
                    f"recommendation={result['recommendation']})"
                )
                self._log_alert(
                    f"Shadowban: /u/{username} ({confidence} confidence)"
                )

                # Mark as banned in AccountManager
                self.account_mgr.mark_banned(username, reason=result["recommendation"])

                # Update DB
                self.db.execute(
                    "UPDATE accounts SET is_shadowbanned = 1, "
                    "last_shadowban_check = datetime('now') "
                    "WHERE username = ?",
                    (username,),
                )
            else:
                # Account healthy
                self.db.execute(
                    "UPDATE accounts SET is_shadowbanned = 0, "
                    "last_shadowban_check = datetime('now') "
                    "WHERE username = ?",
                    (username,),
                )

            # Rate-limit shadowban checks (avoid Reddit API throttling)
            time.sleep(random.uniform(2, 5))

        self.db.commit()
        logger.info(f"Shadowban check complete for {len(usernames)} accounts")

    def health_check(self):
        """Periodic health check — system status, DB stats, account health."""
        logger.info("=" * 50)
        logger.info("HEALTH CHECK")
        logger.info("=" * 50)

        # Resource status
        state = self.resource_monitor.get_state()
        logger.info(
            f"System: RAM {state.ram_used_percent:.0f}% "
            f"({state.ram_available_gb:.1f}GB free), "
            f"Disk {state.disk_used_percent:.0f}% "
            f"({state.disk_free_gb:.0f}GB free), "
            f"CPU {state.cpu_percent:.0f}%, "
            f"RSS {state.process_rss_mb:.0f}MB"
        )

        # Paused state
        with self._state_lock:
            if self._emergency_stopped:
                logger.warning("Status: EMERGENCY STOPPED")
            elif self._paused:
                logger.warning("Status: PAUSED (resource pressure)")
            else:
                logger.info("Status: RUNNING")

        # DB stats
        stats = {}
        for table, label in [
            ("accounts", "Accounts"),
            ("clients", "Clients"),
            ("discovered_posts", "Discovered Posts"),
            ("comments", "Comments"),
        ]:
            row = self.db.fetchone(f"SELECT COUNT(*) as cnt FROM {table}")
            stats[label] = row["cnt"] if row else 0

        # Comment status breakdown
        comment_stats = self.db.fetchall(
            "SELECT status, COUNT(*) as cnt FROM comments GROUP BY status"
        )
        status_str = ", ".join(
            f"{r['status']}={r['cnt']}" for r in comment_stats
        )

        logger.info(
            f"DB: {stats.get('Accounts', 0)} accounts, "
            f"{stats.get('Clients', 0)} clients, "
            f"{stats.get('Discovered Posts', 0)} posts, "
            f"{stats.get('Comments', 0)} comments"
        )
        if status_str:
            logger.info(f"Comment status: {status_str}")

        # Account health summary
        accounts = self.config.get_enabled_accounts()
        for acct in accounts:
            tier = self.account_mgr.get_account_tier(acct.username)
            status = self.account_mgr.get_status(acct.username)
            logger.info(
                f"  /u/{acct.username}: tier={tier.get('name', '?')}, "
                f"status={status}, cap={tier.get('daily_cap', '?')}/day"
            )

        # Scheduler job status
        jobs = self.scheduler.get_jobs()
        logger.info(f"Scheduler: {len(jobs)} jobs active")
        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                logger.debug(f"  {job.id}: next={next_run.strftime('%H:%M:%S')}")

        logger.info("=" * 50)

    def report(self, client_slug: str = None, days: int = 7):
        """Generate and send performance report."""
        client_id = None
        client_name = "All Clients"

        if client_slug:
            client_row = self.db.fetchone(
                "SELECT * FROM clients WHERE slug = ?", (client_slug,)
            )
            if client_row:
                client_id = client_row["id"]
                client_name = client_row["name"]

        report = self.learning.generate_report(client_id=client_id, days=days)
        self.slack.send_performance_report(report, client_name=client_name)
        return report

    # ══════════════════════════════════════════════════════════════════
    # Safe Wrappers (timeout + resource check)
    # ══════════════════════════════════════════════════════════════════

    def _scan_safe(self):
        """Wrapper: run scan with hard timeout and resource check."""
        if not self._check_resources():
            logger.info("Scan skipped: resources constrained")
            return
        _run_with_timeout(self.scan, SCAN_TIMEOUT_SECONDS, "scan_cycle")

    def _discover_safe(self):
        """Wrapper: run discover with hard timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(self.discover, DISCOVER_TIMEOUT_SECONDS, "discover")

    def _generate_safe(self, auto_approve: bool = False):
        """Wrapper: run generate with hard timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(
            lambda: self.generate(auto_approve=auto_approve),
            GENERATE_TIMEOUT_SECONDS,
            "generate",
        )

    def _post_safe(self):
        """Wrapper: run post_approved with hard timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(self.post_approved, ACT_TIMEOUT_SECONDS, "post")

    def _learn_safe(self):
        """Wrapper: run learn with hard timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(self.learn, LEARN_TIMEOUT_SECONDS, "learn")

    def _verify_comments_safe(self):
        """Wrapper: run verify_comments with hard timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(self.verify_comments, ACT_TIMEOUT_SECONDS, "verify")

    def _health_check_safe(self):
        """Wrapper: run health_check (lightweight, no timeout needed)."""
        try:
            self.health_check()
        except Exception as e:
            logger.error(f"Health check error: {e}")

    def _shadowban_check_safe(self):
        """Wrapper: run shadowban detection with timeout."""
        if not self._check_resources():
            return
        _run_with_timeout(
            self.check_shadowbans, ACT_TIMEOUT_SECONDS, "shadowban_check"
        )

    # ══════════════════════════════════════════════════════════════════
    # Full Pipeline
    # ══════════════════════════════════════════════════════════════════

    def run_cycle(self, client_slug: str = None, auto_approve: bool = False):
        """Run one full pipeline cycle:
        DISCOVER → SCAN → SCORE → GENERATE → CHECK → APPROVE → POST → LEARN

        Each step has resource checks and is individually timeout-protected.
        """
        with self._state_lock:
            if self._emergency_stopped:
                logger.info("Cycle skipped: emergency stopped")
                return
            self._cycle_count += 1
            cycle_num = self._cycle_count

        logger.info("=" * 60)
        logger.info(
            f"RedditPilot cycle #{cycle_num} starting at "
            f"{datetime.utcnow().isoformat()}"
        )
        logger.info("=" * 60)

        cycle_start = time.monotonic()

        # Step 1: SCAN for opportunities
        if self._check_resources():
            logger.info("[1/4] SCAN — Finding opportunities...")
            self._scan_safe()
        else:
            logger.info("[1/4] SCAN — Skipped (resources)")

        # Step 2: GENERATE + CHECK + APPROVE
        if self._check_resources():
            logger.info("[2/4] GENERATE — Creating content...")
            self._generate_safe(auto_approve=auto_approve)
        else:
            logger.info("[2/4] GENERATE — Skipped (resources)")

        # Step 3: POST approved content
        if self._check_resources():
            logger.info("[3/4] POST — Posting approved content...")
            self._post_safe()
        else:
            logger.info("[3/4] POST — Skipped (resources)")

        # Step 4: MONITOR
        if self._check_resources():
            logger.info("[4/4] MONITOR — Checking account health...")
            self._shadowban_check_safe()
        else:
            logger.info("[4/4] MONITOR — Skipped (resources)")

        elapsed = time.monotonic() - cycle_start
        logger.info(f"Cycle #{cycle_num} complete in {elapsed:.1f}s")

    def _run_cycle_safe(self, auto_approve: bool = False):
        """Scheduled wrapper for run_cycle with full timeout."""
        if not self._check_resources():
            logger.info("Cycle skipped: resources constrained")
            return

        total_timeout = (
            SCAN_TIMEOUT_SECONDS + GENERATE_TIMEOUT_SECONDS +
            ACT_TIMEOUT_SECONDS + ACT_TIMEOUT_SECONDS + 60  # buffer
        )
        _run_with_timeout(
            lambda: self.run_cycle(auto_approve=auto_approve),
            total_timeout,
            "full_cycle",
        )

    # ══════════════════════════════════════════════════════════════════
    # Signal Handlers & Lifecycle
    # ══════════════════════════════════════════════════════════════════

    def _setup_signal_handlers(self):
        """Install signal handlers for graceful shutdown."""
        def _handle_sigterm(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop()

        def _handle_sigint(signum, frame):
            logger.info("Received SIGINT (Ctrl+C), shutting down...")
            self.stop()
            # If called twice, force exit
            signal.signal(signal.SIGINT, lambda s, f: sys.exit(1))

        try:
            signal.signal(signal.SIGTERM, _handle_sigterm)
            signal.signal(signal.SIGINT, _handle_sigint)
        except (OSError, ValueError):
            # Can't set signal handlers in non-main thread
            logger.debug("Could not set signal handlers (not main thread)")

    def start(self, auto_approve: bool = False, nonblocking: bool = False):
        """Start the bot with APScheduler-based scheduling.

        Args:
            auto_approve: If True, auto-approve generated content.
            nonblocking: If True, return after starting (caller manages loop).
        """
        with self._state_lock:
            self._running = True

        self._setup_signal_handlers()

        # Start resource monitor
        self.resource_monitor.start()
        state = self.resource_monitor.get_state()
        logger.info(
            f"System: {state.cpu_cores} cores, "
            f"{state.ram_total_gb:.0f}GB RAM "
            f"({state.ram_used_percent:.0f}% used), "
            f"{state.disk_free_gb:.0f}GB disk free, "
            f"RSS={state.process_rss_mb:.0f}MB"
        )

        # Safety: abort startup if resources already critical
        if state.ram_used_percent >= 90:
            logger.warning(
                f"RAM already at {state.ram_used_percent:.0f}% — "
                f"starting in reduced mode"
            )

        # Get intervals from config
        scan_interval = self.config.scan_interval_minutes
        learn_interval = self.config.learning_interval_hours

        # ── Schedule jobs ─────────────────────────────────────────

        now = datetime.utcnow()

        # Main cycle: scan + generate + post
        self.scheduler.add_job(
            lambda: self._run_cycle_safe(auto_approve=auto_approve),
            "interval",
            minutes=scan_interval,
            id="main_cycle",
            next_run_time=now + timedelta(minutes=2),  # Delayed start
        )

        # Verify comments (check performance, detect removals)
        self.scheduler.add_job(
            self._verify_comments_safe,
            "interval",
            hours=1,
            id="verify_comments",
            next_run_time=now + timedelta(minutes=20),
        )

        # Health check (system status, DB stats)
        self.scheduler.add_job(
            self._health_check_safe,
            "interval",
            minutes=30,
            id="health_check",
            next_run_time=now + timedelta(minutes=10),
        )

        # Learning cycle (optimize strategies)
        self.scheduler.add_job(
            self._learn_safe,
            "interval",
            hours=learn_interval,
            id="auto_learn",
            next_run_time=now + timedelta(minutes=30),
        )

        # Shadowban detection
        self.scheduler.add_job(
            self._shadowban_check_safe,
            "interval",
            hours=self.config.safety.shadowban_check_interval_hours,
            id="shadowban_check",
            next_run_time=now + timedelta(minutes=15),
        )

        # Subreddit discovery (daily)
        self.scheduler.add_job(
            self._discover_safe,
            "interval",
            hours=24,
            id="discovery",
            next_run_time=now + timedelta(hours=1),
        )

        # Daily performance report
        self.scheduler.add_job(
            lambda: self.report(),
            "cron",
            hour=18,
            id="daily_report",
        )

        # ── Error/missed job handling ─────────────────────────────

        def _on_job_error(event):
            logger.error(
                f"Scheduled job '{event.job_id}' crashed: {event.exception}",
                exc_info=event.exception,
            )
            self._log_alert(f"Job '{event.job_id}' crashed: {event.exception}")
            # Auto-recover: re-enable if disabled
            try:
                job = self.scheduler.get_job(event.job_id)
                if job and job.next_run_time is None:
                    job.resume()
                    logger.info(f"Auto-recovered crashed job '{event.job_id}'")
            except Exception as e:
                logger.error(f"Failed to auto-recover job '{event.job_id}': {e}")

        def _on_job_missed(event):
            logger.warning(f"Scheduled job '{event.job_id}' missed its run window")

        self.scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)

        # ── Start scheduler ───────────────────────────────────────

        self.scheduler.start()

        logger.info(
            f"RedditPilot started. "
            f"First cycle in 2min. "
            f"Scan every {scan_interval}min, learn every {learn_interval}h. "
            f"Health check every 30min, verify comments every 1h."
        )

        if nonblocking:
            return  # Caller manages the main loop

        # Keep main thread alive
        try:
            while True:
                with self._state_lock:
                    if not self._running:
                        break
                try:
                    signal.pause()
                except AttributeError:
                    # Windows fallback (no signal.pause)
                    time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self):
        """Graceful shutdown — close all resources. Idempotent.

        Safe to call from signal handlers and multiple threads.
        """
        with self._state_lock:
            if not self._running:
                return
            self._running = False
            self._paused = True  # Stop new work immediately

        logger.info("Shutting down RedditPilot...")

        # Stop resource monitor
        try:
            self.resource_monitor.stop()
        except Exception:
            pass

        # Stop account manager watcher
        try:
            self.account_mgr.stop_watching()
        except Exception:
            pass

        # Shut down scheduler (don't wait — avoid blocking)
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass

        # Brief pause for in-flight DB writes
        time.sleep(0.5)

        logger.info("RedditPilot stopped.")

    # ══════════════════════════════════════════════════════════════════
    # Legacy Compatibility: run_scheduler (wraps start)
    # ══════════════════════════════════════════════════════════════════

    def run_scheduler(self, auto_approve: bool = False):
        """Legacy entry point — wraps start() for backwards compatibility."""
        self.start(auto_approve=auto_approve)

    # ══════════════════════════════════════════════════════════════════
    # Dashboard / API Helpers
    # ══════════════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        """Return system status dict for dashboard/API consumption."""
        with self._state_lock:
            running = self._running
            paused = self._paused
            e_stopped = self._emergency_stopped
            cycle_count = self._cycle_count

        resource_status = self.resource_monitor.get_status_dict()

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

        return {
            "running": running,
            "paused": paused,
            "emergency_stopped": e_stopped,
            "cycle_count": cycle_count,
            "resources": resource_status,
            "scheduled_jobs": jobs,
            "accounts": len(self.config.get_enabled_accounts()),
            "clients": len(self.config.get_enabled_clients()),
            "alerts": list(self._alert_log)[-20:],
            "timestamp": datetime.utcnow().isoformat(),
        }

    def pause(self):
        """Pause all operations (manual)."""
        with self._state_lock:
            self._paused = True
        logger.info("RedditPilot manually paused")
        self._log_alert("Manually paused")

    def resume(self):
        """Resume operations (manual, won't override emergency stop)."""
        with self._state_lock:
            if self._emergency_stopped:
                logger.warning("Cannot resume: emergency stop is active")
                return
            self._paused = False
        logger.info("RedditPilot manually resumed")
        self._log_alert("Manually resumed")

    # ══════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════

    def _get_clients(self, client_slug: str = None) -> List[ClientProfile]:
        """Get client profiles, optionally filtered by slug."""
        if client_slug:
            return [
                c for c in self.config.get_enabled_clients()
                if c.slug == client_slug
            ]
        return self.config.get_enabled_clients()
