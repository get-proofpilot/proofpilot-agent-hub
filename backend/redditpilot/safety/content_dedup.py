"""
RedditPilot Content Deduplication
Prevents duplicate or too-similar content across all managed accounts/clients.

Adapted from MiloAgent's ContentDeduplicator with enhancements:
- Jaccard word-overlap similarity (configurable threshold)
- N-gram (trigram) overlap as a second similarity check
- Exact target match (already posted on this thread)
- Project-in-subreddit recency (don't mention same client in same sub too often)
- Thread-level dedup (any account already hit this thread)
- Multi-client aware (checks scoped per client_id)
- Fail-safe: blocks on DB errors to prevent spam
- Returns structured result with reason for block/allow
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

logger = logging.getLogger("redditpilot.dedup")


@dataclass
class DedupResult:
    """Structured result from deduplication checks."""
    allowed: bool
    reason: str
    check_name: str = ""           # which check triggered block/allow
    similarity_score: float = 0.0  # highest similarity found (if applicable)
    matched_post_id: str = ""      # reddit ID of the conflicting post (if any)
    details: dict = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def __bool__(self) -> bool:
        """Truthy = allowed, falsy = blocked."""
        return self.allowed


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _ngram_set(text: str, n: int = 3) -> set:
    """Extract character-level n-grams from text."""
    text = text.lower().strip()
    if len(text) < n:
        return {text}
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _ngram_similarity(text_a: str, text_b: str, n: int = 3) -> float:
    """Trigram (character n-gram) Jaccard similarity between two texts."""
    grams_a = _ngram_set(text_a, n)
    grams_b = _ngram_set(text_b, n)
    if not grams_a or not grams_b:
        return 0.0
    intersection = grams_a & grams_b
    union = grams_a | grams_b
    return len(intersection) / len(union) if union else 0.0


def _content_hash(text: str) -> str:
    """Stable hash for exact-match dedup."""
    return hashlib.sha256(text.lower().strip().encode("utf-8")).hexdigest()


class ContentDeduplicator:
    """Prevents duplicate or too-similar content across RedditPilot.

    Checks (in order):
      1. Exact hash match in content_hashes table
      2. Exact target (post_reddit_id) — already commented on this thread
      3. Thread-level dedup — any account already hit this thread recently
      4. Jaccard word-overlap similarity against recent comments
      5. Trigram character-overlap similarity (second layer)
      6. Project-in-subreddit recency — same client promoted in same sub recently

    All checks are scoped to client_id when provided.
    Fail-safe: any DB error → block posting to prevent spam.
    """

    def __init__(
        self,
        db,
        jaccard_threshold: float = 0.6,
        ngram_threshold: float = 0.55,
        recency_hours: int = 24,
        thread_cooldown_hours: int = 6,
        subreddit_client_cooldown_hours: int = 24,
    ):
        self.db = db
        self.jaccard_threshold = jaccard_threshold
        self.ngram_threshold = ngram_threshold
        self.recency_hours = recency_hours
        self.thread_cooldown_hours = thread_cooldown_hours
        self.subreddit_client_cooldown_hours = subreddit_client_cooldown_hours

    # ── Public API ───────────────────────────────────────────────────

    def check(
        self,
        content: str,
        post_reddit_id: str,
        subreddit: str,
        client_id: Optional[int] = None,
        content_type: str = "comment",
    ) -> DedupResult:
        """Run all dedup checks. Returns DedupResult (truthy = allowed).

        This is the main entry point. Call this before posting any content.
        """
        try:
            return self._run_checks(
                content, post_reddit_id, subreddit, client_id, content_type
            )
        except Exception as e:
            # Fail-safe: block on any unexpected error
            logger.error(f"Dedup check failed with unexpected error, blocking as safety: {e}")
            return DedupResult(
                allowed=False,
                reason=f"Dedup system error (fail-safe block): {e}",
                check_name="error_failsafe",
            )

    def record(
        self,
        content: str,
        content_type: str = "comment",
        subreddit: str = None,
    ):
        """Record content hash after successful posting."""
        try:
            h = _content_hash(content)
            self.db.save_content_hash(h, content_type, subreddit)
            logger.debug(f"Recorded content hash {h[:12]}... type={content_type}")
        except Exception as e:
            logger.error(f"Failed to record content hash: {e}")

    # ── Internal checks ──────────────────────────────────────────────

    def _run_checks(
        self,
        content: str,
        post_reddit_id: str,
        subreddit: str,
        client_id: Optional[int],
        content_type: str,
    ) -> DedupResult:
        """Execute all dedup checks in order."""

        # --- Check 1: Exact hash match in content_hashes table ---
        h = _content_hash(content)
        try:
            if self.db.is_duplicate_content(h):
                logger.warning(f"Exact content hash match: {h[:12]}...")
                return DedupResult(
                    allowed=False,
                    reason="Exact duplicate content (hash match)",
                    check_name="exact_hash",
                    similarity_score=1.0,
                    details={"hash": h},
                )
        except Exception as e:
            logger.error(f"Hash check DB error, blocking as safety: {e}")
            return DedupResult(
                allowed=False,
                reason=f"DB error during hash check (fail-safe): {e}",
                check_name="exact_hash_error",
            )

        # --- Check 2: Already commented on this exact post ---
        try:
            result = self._check_target_already_hit(post_reddit_id, client_id)
            if result is not None:
                return result
        except Exception as e:
            logger.error(f"Target check DB error, blocking as safety: {e}")
            return DedupResult(
                allowed=False,
                reason=f"DB error during target check (fail-safe): {e}",
                check_name="target_check_error",
            )

        # --- Check 3: Thread-level dedup (any account recently) ---
        try:
            result = self._check_thread_recently_hit(post_reddit_id)
            if result is not None:
                return result
        except Exception as e:
            logger.error(f"Thread check DB error, blocking as safety: {e}")
            return DedupResult(
                allowed=False,
                reason=f"DB error during thread check (fail-safe): {e}",
                check_name="thread_check_error",
            )

        # --- Check 4 & 5: Jaccard + N-gram similarity ---
        try:
            result = self._check_content_similarity(content, subreddit, client_id)
            if result is not None:
                return result
        except Exception as e:
            logger.error(f"Similarity check DB error, blocking as safety: {e}")
            return DedupResult(
                allowed=False,
                reason=f"DB error during similarity check (fail-safe): {e}",
                check_name="similarity_check_error",
            )

        # --- Check 6: Client-in-subreddit recency ---
        if client_id is not None:
            try:
                result = self._check_client_subreddit_recency(
                    client_id, subreddit
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.error(f"Client/subreddit recency DB error, blocking as safety: {e}")
                return DedupResult(
                    allowed=False,
                    reason=f"DB error during recency check (fail-safe): {e}",
                    check_name="recency_check_error",
                )

        # All checks passed
        return DedupResult(
            allowed=True,
            reason="All dedup checks passed",
            check_name="all_passed",
        )

    def _check_target_already_hit(
        self, post_reddit_id: str, client_id: Optional[int]
    ) -> Optional[DedupResult]:
        """Check if we already commented on this exact post (for this client)."""
        sql = """
            SELECT id, content, client_id, status
            FROM comments
            WHERE post_reddit_id = ?
              AND status IN ('posted', 'approved', 'pending_approval', 'draft')
        """
        params: list = [post_reddit_id]

        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)

        sql += " LIMIT 1"

        existing = self.db.fetchone(sql, tuple(params))
        if existing:
            logger.warning(
                f"Already have a comment on post {post_reddit_id} "
                f"(comment id={existing['id']}, status={existing['status']})"
            )
            return DedupResult(
                allowed=False,
                reason=f"Already commented on this post (status: {existing['status']})",
                check_name="target_already_hit",
                matched_post_id=post_reddit_id,
                details={"existing_comment_id": existing["id"]},
            )
        return None

    def _check_thread_recently_hit(
        self, post_reddit_id: str
    ) -> Optional[DedupResult]:
        """Check if ANY account already hit this thread recently."""
        cutoff = (
            datetime.utcnow() - timedelta(hours=self.thread_cooldown_hours)
        ).strftime("%Y-%m-%d %H:%M:%S")

        sql = """
            SELECT id, client_id, status, created_at
            FROM comments
            WHERE post_reddit_id = ?
              AND status IN ('posted', 'approved')
              AND created_at > ?
            LIMIT 1
        """
        existing = self.db.fetchone(sql, (post_reddit_id, cutoff))
        if existing:
            logger.warning(
                f"Thread {post_reddit_id} already hit within "
                f"{self.thread_cooldown_hours}h (comment id={existing['id']})"
            )
            return DedupResult(
                allowed=False,
                reason=(
                    f"Thread already acted on within {self.thread_cooldown_hours}h "
                    f"(by comment id={existing['id']})"
                ),
                check_name="thread_recently_hit",
                matched_post_id=post_reddit_id,
                details={
                    "existing_comment_id": existing["id"],
                    "cooldown_hours": self.thread_cooldown_hours,
                },
            )
        return None

    def _check_content_similarity(
        self,
        content: str,
        subreddit: str,
        client_id: Optional[int],
    ) -> Optional[DedupResult]:
        """Check Jaccard and trigram similarity against recent comments."""
        cutoff = (
            datetime.utcnow() - timedelta(hours=self.recency_hours)
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Fetch recent comments (same subreddit, or same client across subs)
        sql = """
            SELECT id, post_reddit_id, content, subreddit, client_id
            FROM comments
            WHERE status IN ('posted', 'approved', 'pending_approval', 'draft')
              AND created_at > ?
              AND (subreddit = ?{client_filter})
            ORDER BY created_at DESC
            LIMIT 200
        """
        params: list = [cutoff, subreddit]

        if client_id is not None:
            sql = sql.replace("{client_filter}", " OR client_id = ?")
            params.append(client_id)
        else:
            sql = sql.replace("{client_filter}", "")

        recent_comments = self.db.fetchall(sql, tuple(params))

        best_jaccard = 0.0
        best_ngram = 0.0
        worst_match_id = None
        worst_match_post = ""

        for row in recent_comments:
            prev_content = row.get("content", "")
            if not prev_content:
                continue

            # Jaccard word-overlap
            j_sim = _jaccard_similarity(content, prev_content)
            if j_sim > best_jaccard:
                best_jaccard = j_sim
                worst_match_id = row["id"]
                worst_match_post = row.get("post_reddit_id", "")

            if j_sim >= self.jaccard_threshold:
                logger.warning(
                    f"Content too similar (Jaccard={j_sim:.2f}) to comment "
                    f"id={row['id']} on post {row.get('post_reddit_id', '?')}"
                )
                return DedupResult(
                    allowed=False,
                    reason=(
                        f"Content too similar to recent comment "
                        f"(Jaccard similarity={j_sim:.2f}, threshold={self.jaccard_threshold})"
                    ),
                    check_name="jaccard_similarity",
                    similarity_score=j_sim,
                    matched_post_id=row.get("post_reddit_id", ""),
                    details={
                        "matched_comment_id": row["id"],
                        "threshold": self.jaccard_threshold,
                    },
                )

            # Trigram character-overlap (second layer for near-paraphrases)
            n_sim = _ngram_similarity(content, prev_content)
            if n_sim > best_ngram:
                best_ngram = n_sim

            if n_sim >= self.ngram_threshold:
                logger.warning(
                    f"Content too similar (trigram={n_sim:.2f}) to comment "
                    f"id={row['id']} on post {row.get('post_reddit_id', '?')}"
                )
                return DedupResult(
                    allowed=False,
                    reason=(
                        f"Content too similar to recent comment "
                        f"(trigram similarity={n_sim:.2f}, threshold={self.ngram_threshold})"
                    ),
                    check_name="ngram_similarity",
                    similarity_score=n_sim,
                    matched_post_id=row.get("post_reddit_id", ""),
                    details={
                        "matched_comment_id": row["id"],
                        "threshold": self.ngram_threshold,
                    },
                )

        # No similarity block triggered
        return None

    def _check_client_subreddit_recency(
        self, client_id: int, subreddit: str
    ) -> Optional[DedupResult]:
        """Check if this client was already promoted in this subreddit recently.

        Prevents the same client from appearing too frequently in the same sub,
        which would look suspicious and increase detection risk.
        """
        cutoff = (
            datetime.utcnow()
            - timedelta(hours=self.subreddit_client_cooldown_hours)
        ).strftime("%Y-%m-%d %H:%M:%S")

        sql = """
            SELECT COUNT(*) as cnt
            FROM comments
            WHERE client_id = ?
              AND subreddit = ?
              AND status IN ('posted', 'approved')
              AND created_at > ?
        """
        row = self.db.fetchone(sql, (client_id, subreddit, cutoff))
        count = row["cnt"] if row else 0

        if count > 0:
            logger.info(
                f"Client {client_id} already has {count} comment(s) in "
                f"r/{subreddit} within {self.subreddit_client_cooldown_hours}h"
            )
            return DedupResult(
                allowed=False,
                reason=(
                    f"Client already has {count} comment(s) in r/{subreddit} "
                    f"within {self.subreddit_client_cooldown_hours}h"
                ),
                check_name="client_subreddit_recency",
                details={
                    "client_id": client_id,
                    "subreddit": subreddit,
                    "existing_count": count,
                    "cooldown_hours": self.subreddit_client_cooldown_hours,
                },
            )
        return None
