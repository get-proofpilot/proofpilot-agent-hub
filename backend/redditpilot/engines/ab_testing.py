"""A/B Testing Engine for RedditPilot — systematic experimentation for optimal content.

Adapted from MiloAgent's A/B testing framework for RedditPilot's multi-client
architecture and database schema.

Experiments can test 4 variables:
- tone: which conversational tone drives more engagement
- post_type: text vs link vs image post performance
- content_length: short vs long content effectiveness
- promo_ratio: optimal promotional-to-organic content ratio

Lightweight: no extra HTTP requests, just changes content generation params.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from redditpilot.core.database import Database

logger = logging.getLogger(__name__)

# Testable variables and their closeness thresholds for auto-experiment creation
TESTABLE_VARIABLES = {
    "tone": {"threshold": 0.20, "min_samples": 3, "min_experiment_samples": 10},
    "post_type": {"threshold": 0.25, "min_samples": 5, "min_experiment_samples": 8},
    "content_length": {"threshold": 0.30, "min_samples": 5, "min_experiment_samples": 10},
    "promo_ratio": {"threshold": 0.25, "min_samples": 5, "min_experiment_samples": 15},
}

SIGNIFICANCE_THRESHOLD = 0.15  # 15% difference to declare winner
MAX_EXPERIMENT_DAYS = 14       # Cancel experiments older than this
MAX_CONCURRENT_PER_CLIENT = 2  # Max active experiments per client


class ABTestingEngine:
    """Manages A/B experiments and assigns variants for RedditPilot.

    Usage:
        engine = ABTestingEngine(db)
        engine.create_experiment(client_id=1, variable="tone",
                                variant_a="helpful_casual", variant_b="creator_mentor")
        variant, value = engine.get_variant(client_id=1, variable="tone")
        engine.record_result(experiment_id=5, variant="a", score=2.5)
        engine.evaluate_experiments()  # during learning cycle
    """

    def __init__(self, db: Database, significance_threshold: float = SIGNIFICANCE_THRESHOLD):
        self.db = db
        self.significance_threshold = significance_threshold
        self._ensure_results_table()

    # ── Schema helpers ────────────────────────────────────────────────

    def _ensure_results_table(self):
        """Ensure the ab_results table exists for tracking individual outcomes."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS ab_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id),
                    variant TEXT NOT NULL,       -- 'a' or 'b'
                    score REAL DEFAULT 0.0,
                    recorded_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_results_exp
                    ON ab_results(experiment_id, variant)
            """)
            self.db.commit()
        except Exception as e:
            logger.debug(f"ab_results table init: {e}")

    # ── Experiment Creation ───────────────────────────────────────────

    def create_experiment(
        self,
        client_id: int,
        variable: str,
        variant_a: str,
        variant_b: str,
        name: str = "",
        subreddit: str = None,
    ) -> Optional[int]:
        """Create a new A/B experiment if constraints are met.

        Constraints:
        - No duplicate experiment for same client + variable (while active)
        - Max 2 concurrent experiments per client

        Returns experiment ID or None if creation was skipped.
        """
        if variable not in TESTABLE_VARIABLES:
            logger.warning(f"Variable '{variable}' not in testable set: {list(TESTABLE_VARIABLES)}")
            return None

        # Check for existing active experiment on same variable for this client
        running = self._get_active_experiments(client_id)
        for exp in running:
            if exp["dimension"] == variable:
                logger.debug(
                    f"Experiment already running for {variable} on client {client_id}"
                )
                return None

        # Enforce max concurrent experiments per client
        if len(running) >= MAX_CONCURRENT_PER_CLIENT:
            logger.debug(
                f"Client {client_id} already has {len(running)} active experiments (max {MAX_CONCURRENT_PER_CLIENT})"
            )
            return None

        if not name:
            name = f"{variable}_{variant_a}_vs_{variant_b}"

        variants_json = json.dumps({"a": variant_a, "b": variant_b})

        cur = self.db._execute_write(
            """INSERT INTO ab_experiments
               (name, dimension, variants, client_id, subreddit, status, sample_size, significance)
               VALUES (?, ?, ?, ?, ?, 'active', 0, 0.0)""",
            (name, variable, variants_json, client_id, subreddit),
        )
        exp_id = cur.lastrowid
        logger.info(
            f"Created A/B experiment #{exp_id}: {name} ({variant_a} vs {variant_b}) "
            f"for client {client_id}"
        )
        return exp_id

    # ── Variant Assignment ────────────────────────────────────────────

    def get_variant(
        self, client_id: int, variable: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get the variant to use for this client and variable.

        Uses balanced assignment: assigns based on count parity so both
        variants get roughly equal traffic.

        Returns (variant_label, variant_value) e.g. ("a", "helpful_casual")
        Returns (None, None) if no active experiment for this variable.
        """
        experiments = self._get_active_experiments(client_id)
        for exp in experiments:
            if exp["dimension"] == variable:
                variants = self._parse_variants(exp["variants"])
                if not variants:
                    continue

                # Balanced assignment based on count parity
                counts = self._get_variant_counts(exp["id"])
                count_a = counts.get("a", 0)
                count_b = counts.get("b", 0)

                if count_a <= count_b:
                    return ("a", variants.get("a", ""))
                else:
                    return ("b", variants.get("b", ""))

        return (None, None)

    def get_variant_with_id(
        self, client_id: int, variable: str
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Like get_variant but also returns the experiment_id.

        Returns (experiment_id, variant_label, variant_value).
        Returns (None, None, None) if no active experiment.
        """
        experiments = self._get_active_experiments(client_id)
        for exp in experiments:
            if exp["dimension"] == variable:
                variants = self._parse_variants(exp["variants"])
                if not variants:
                    continue

                counts = self._get_variant_counts(exp["id"])
                count_a = counts.get("a", 0)
                count_b = counts.get("b", 0)

                if count_a <= count_b:
                    return (exp["id"], "a", variants.get("a", ""))
                else:
                    return (exp["id"], "b", variants.get("b", ""))

        return (None, None, None)

    # ── Result Recording ──────────────────────────────────────────────

    def record_result(self, experiment_id: int, variant: str, score: float):
        """Record the outcome of an action in an A/B experiment.

        Args:
            experiment_id: The experiment this result belongs to
            variant: 'a' or 'b'
            score: Engagement score (upvotes, replies, composite, etc.)
        """
        if variant not in ("a", "b"):
            logger.warning(f"Invalid variant '{variant}', must be 'a' or 'b'")
            return

        self.db._execute_write(
            "INSERT INTO ab_results (experiment_id, variant, score) VALUES (?, ?, ?)",
            (experiment_id, variant, score),
        )

        # Update sample_size on the experiment
        self.db._execute_write(
            "UPDATE ab_experiments SET sample_size = sample_size + 1 WHERE id = ?",
            (experiment_id,),
        )
        logger.debug(
            f"Recorded A/B result: experiment={experiment_id}, variant={variant}, score={score}"
        )

    # ── Experiment Evaluation ─────────────────────────────────────────

    def evaluate_experiments(self):
        """Evaluate all active experiments across all clients.

        Called during the learning cycle. For each active experiment:
        - If both variants have enough samples, compute significance and declare winner
        - If experiment is older than MAX_EXPERIMENT_DAYS, cancel it
        - Winners are auto-applied to the learned_strategies table
        """
        experiments = self.db.fetchall(
            "SELECT * FROM ab_experiments WHERE status = 'active'"
        )
        for exp in experiments:
            self._evaluate_one(exp)

    def _evaluate_one(self, exp: Dict):
        """Evaluate a single experiment for significance."""
        exp_id = exp["id"]
        variants = self._parse_variants(exp["variants"])
        if not variants:
            return

        # Get per-variant statistics
        stats = self._get_variant_stats(exp_id)
        a_count = stats.get("a", {}).get("count", 0)
        b_count = stats.get("b", {}).get("count", 0)
        a_avg = stats.get("a", {}).get("avg_score", 0.0)
        b_avg = stats.get("b", {}).get("avg_score", 0.0)

        variable = exp["dimension"]
        min_samples = TESTABLE_VARIABLES.get(variable, {}).get("min_experiment_samples", 10)

        # Check if both variants have enough samples
        if a_count >= min_samples and b_count >= min_samples:
            # Calculate relative difference
            if a_avg == 0 and b_avg == 0:
                winner_label = "tie"
                significance = 0.0
            elif a_avg == 0:
                winner_label = "b"
                significance = 1.0
            elif b_avg == 0:
                winner_label = "a"
                significance = 1.0
            else:
                diff = abs(a_avg - b_avg) / max(a_avg, b_avg)
                significance = diff
                if diff > self.significance_threshold:
                    winner_label = "a" if a_avg > b_avg else "b"
                else:
                    winner_label = "tie"

            # Determine winner value and status
            if winner_label == "tie":
                winner_value = None
                status = "no_winner"
            else:
                winner_value = variants.get(winner_label, "")
                status = "evaluated"

            # Update experiment record
            self.db._execute_write(
                """UPDATE ab_experiments
                   SET status = ?, winner = ?, significance = ?,
                       sample_size = ?, concluded_at = datetime('now')
                   WHERE id = ?""",
                (status, winner_value, significance, a_count + b_count, exp_id),
            )

            logger.info(
                f"A/B experiment #{exp_id} '{exp['name']}' concluded: "
                f"winner={winner_label} ({winner_value}), "
                f"A={a_avg:.3f} (n={a_count}), B={b_avg:.3f} (n={b_count}), "
                f"significance={significance:.3f}"
            )

            # Auto-apply winner to learned_strategies
            if winner_label != "tie":
                self._apply_winner(exp, winner_label, winner_value, significance,
                                   a_count + b_count, max(a_avg, b_avg))
        else:
            # Check if experiment is too old → cancel
            self._check_expiry(exp, a_count, b_count)

    def _apply_winner(self, exp: Dict, winner_label: str, winner_value: str,
                      significance: float, total_samples: int, best_score: float):
        """Apply winning variant to learned_strategies and mark as applied."""
        client_id = exp.get("client_id")
        variable = exp["dimension"]

        try:
            self.db.upsert_strategy(
                strategy_type=variable,
                key=winner_value,
                value=best_score,
                confidence=min(0.5 + significance, 1.0),
                sample_count=total_samples,
                client_id=client_id,
                subreddit=exp.get("subreddit"),
            )
            # Mark experiment as fully applied
            self.db._execute_write(
                "UPDATE ab_experiments SET status = 'applied' WHERE id = ?",
                (exp["id"],),
            )
            logger.info(
                f"Applied A/B winner to learned_strategies: "
                f"{variable}={winner_value} (confidence={min(0.5 + significance, 1.0):.2f})"
            )
        except Exception as e:
            logger.warning(f"Failed to apply A/B winner for experiment #{exp['id']}: {e}")

    def _check_expiry(self, exp: Dict, a_count: int, b_count: int):
        """Cancel experiment if it's older than MAX_EXPERIMENT_DAYS."""
        try:
            created = exp.get("created_at", "")
            if not created:
                return
            created_dt = datetime.fromisoformat(created)
            age_days = (datetime.utcnow() - created_dt).days
            if age_days > MAX_EXPERIMENT_DAYS:
                self.db._execute_write(
                    """UPDATE ab_experiments
                       SET status = 'cancelled', concluded_at = datetime('now')
                       WHERE id = ?""",
                    (exp["id"],),
                )
                logger.info(
                    f"A/B experiment #{exp['id']} '{exp['name']}' cancelled "
                    f"(insufficient data after {age_days} days: "
                    f"A n={a_count}, B n={b_count})"
                )
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse experiment date: {e}")

    # ── Auto-Experiment Creation ──────────────────────────────────────

    def auto_create_experiments(self, client_id: int):
        """Smart experiment creation based on learned strategies.

        Checks all 4 testable variables in priority order:
        1. tone — if top 2 tones are within 20%
        2. post_type — if top 2 post types are within 25%
        3. content_length — if short vs long are within 30%
        4. promo_ratio — if current ratio is in uncertain zone

        Respects max 2 concurrent experiments per client.
        """
        running = self._get_active_experiments(client_id)
        if len(running) >= MAX_CONCURRENT_PER_CLIENT:
            return

        running_vars = {exp["dimension"] for exp in running}

        # Priority order: tone > post_type > content_length > promo_ratio
        if "tone" not in running_vars:
            if self._try_create_tone_experiment(client_id):
                running = self._get_active_experiments(client_id)
                if len(running) >= MAX_CONCURRENT_PER_CLIENT:
                    return

        if "post_type" not in running_vars:
            if self._try_create_post_type_experiment(client_id):
                running = self._get_active_experiments(client_id)
                if len(running) >= MAX_CONCURRENT_PER_CLIENT:
                    return

        if "content_length" not in running_vars:
            if self._try_create_length_experiment(client_id):
                running = self._get_active_experiments(client_id)
                if len(running) >= MAX_CONCURRENT_PER_CLIENT:
                    return

        if "promo_ratio" not in running_vars:
            self._try_create_promo_experiment(client_id)

    def _try_create_tone_experiment(self, client_id: int) -> bool:
        """Create tone experiment if top 2 tones have close performance."""
        strategies = self.db.get_strategies("tone", client_id=client_id)
        return self._create_from_strategies(
            client_id=client_id,
            variable="tone",
            strategies=strategies,
        )

    def _try_create_post_type_experiment(self, client_id: int) -> bool:
        """Create post_type experiment if top 2 types are within threshold."""
        strategies = self.db.get_strategies("post_type", client_id=client_id)
        return self._create_from_strategies(
            client_id=client_id,
            variable="post_type",
            strategies=strategies,
        )

    def _try_create_length_experiment(self, client_id: int) -> bool:
        """Create content_length experiment from performance data."""
        # First try learned strategies
        strategies = self.db.get_strategies("content_length", client_id=client_id)
        if self._create_from_strategies(client_id, "content_length", strategies):
            return True

        # Fallback: analyze actual content from performance_log
        try:
            rows = self.db.fetchall(
                """SELECT tone as key, AVG(metric_value) as value,
                          COUNT(*) as sample_count, 0.5 as confidence
                   FROM performance_log
                   WHERE client_id = ? AND metric_type = 'content_length'
                   GROUP BY tone HAVING sample_count >= 5
                   ORDER BY value DESC""",
                (client_id,),
            )
            if len(rows) >= 2:
                return self._create_from_strategies(client_id, "content_length", rows)
        except Exception:
            pass

        # Ultimate fallback: if no data exists, test short vs long
        cfg = TESTABLE_VARIABLES["content_length"]
        existing = self._get_active_experiments(client_id)
        for exp in existing:
            if exp["dimension"] == "content_length":
                return False
        # Only create if we have no data at all — exploratory experiment
        return False

    def _try_create_promo_experiment(self, client_id: int) -> bool:
        """Create promo_ratio experiment if current ratio is in uncertain zone [10-35%]."""
        strategies = self.db.get_strategies("promo_ratio", client_id=client_id)
        if self._create_from_strategies(client_id, "promo_ratio", strategies):
            return True

        # Fallback: check content_type strategies for promotional vs organic split
        ct_strategies = self.db.get_strategies("content_type", client_id=client_id)
        promo_val = 0.0
        organic_val = 0.0
        for s in ct_strategies:
            if s.get("key") == "promotional":
                promo_val = s.get("value", 0.0)
            elif s.get("key") == "organic":
                organic_val = s.get("value", 0.0)

        total = promo_val + organic_val
        if total > 0:
            current_ratio = promo_val / total
            if 0.10 <= current_ratio <= 0.35:
                low = f"{max(0.05, current_ratio - 0.10):.2f}"
                high = f"{min(0.40, current_ratio + 0.10):.2f}"
                exp_id = self.create_experiment(
                    client_id=client_id,
                    variable="promo_ratio",
                    variant_a=low,
                    variant_b=high,
                    name=f"promo_{low}_vs_{high}",
                )
                return exp_id is not None
        return False

    def _create_from_strategies(
        self, client_id: int, variable: str, strategies: List[Dict]
    ) -> bool:
        """Generic helper: create experiment from top 2 strategies if they're close.

        Returns True if experiment was created.
        """
        if len(strategies) < 2:
            return False

        cfg = TESTABLE_VARIABLES.get(variable, {})
        threshold = cfg.get("threshold", 0.20)
        min_samples = cfg.get("min_samples", 3)

        top = strategies[0]
        second = strategies[1]

        top_samples = top.get("sample_count", 0)
        second_samples = second.get("sample_count", 0)

        if top_samples < min_samples or second_samples < min_samples:
            return False

        top_val = top.get("value", 0.0)
        second_val = second.get("value", 0.0)
        max_val = max(top_val, second_val, 0.01)
        diff = abs(top_val - second_val) / max_val

        if diff < threshold:
            exp_id = self.create_experiment(
                client_id=client_id,
                variable=variable,
                variant_a=top.get("key", ""),
                variant_b=second.get("key", ""),
                name=f"{variable}_{top.get('key', 'a')}_vs_{second.get('key', 'b')}",
            )
            return exp_id is not None

        return False

    # ── Query Helpers ─────────────────────────────────────────────────

    def _get_active_experiments(self, client_id: int = None) -> List[Dict]:
        """Get all active experiments, optionally filtered by client."""
        if client_id is not None:
            return self.db.fetchall(
                "SELECT * FROM ab_experiments WHERE status = 'active' AND client_id = ?",
                (client_id,),
            )
        return self.db.fetchall(
            "SELECT * FROM ab_experiments WHERE status = 'active'"
        )

    def _parse_variants(self, variants_raw) -> Optional[Dict]:
        """Parse variants JSON safely. Returns {"a": "...", "b": "..."} or None."""
        if not variants_raw:
            return None
        try:
            if isinstance(variants_raw, str):
                return json.loads(variants_raw)
            elif isinstance(variants_raw, dict):
                return variants_raw
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse variants JSON: {variants_raw}")
        return None

    def _get_variant_counts(self, experiment_id: int) -> Dict[str, int]:
        """Get count of results per variant for balanced assignment."""
        rows = self.db.fetchall(
            "SELECT variant, COUNT(*) as cnt FROM ab_results "
            "WHERE experiment_id = ? GROUP BY variant",
            (experiment_id,),
        )
        return {r["variant"]: r["cnt"] for r in rows}

    def _get_variant_stats(self, experiment_id: int) -> Dict[str, Dict]:
        """Get per-variant statistics (count, avg_score) for evaluation."""
        rows = self.db.fetchall(
            """SELECT variant, COUNT(*) as count, AVG(score) as avg_score
               FROM ab_results
               WHERE experiment_id = ?
               GROUP BY variant""",
            (experiment_id,),
        )
        result = {}
        for r in rows:
            result[r["variant"]] = {
                "count": r["count"],
                "avg_score": r["avg_score"] or 0.0,
            }
        return result

    # ── Reporting ─────────────────────────────────────────────────────

    def get_active_experiments(self, client_id: int = None) -> List[Dict]:
        """Public method: get all active experiments for reporting."""
        return self._get_active_experiments(client_id)

    def get_experiment_summary(self, experiment_id: int) -> Optional[Dict]:
        """Get full summary of an experiment including variant stats."""
        exp = self.db.fetchone(
            "SELECT * FROM ab_experiments WHERE id = ?", (experiment_id,)
        )
        if not exp:
            return None

        variants = self._parse_variants(exp["variants"])
        stats = self._get_variant_stats(experiment_id)

        return {
            "id": exp["id"],
            "name": exp["name"],
            "variable": exp["dimension"],
            "client_id": exp["client_id"],
            "status": exp["status"],
            "winner": exp["winner"],
            "variants": variants,
            "stats": stats,
            "sample_size": exp["sample_size"],
            "significance": exp["significance"],
            "created_at": exp["created_at"],
            "concluded_at": exp.get("concluded_at"),
        }

    def get_all_experiments(self, client_id: int = None, status: str = None) -> List[Dict]:
        """Get experiments with optional filters for dashboard display."""
        sql = "SELECT * FROM ab_experiments WHERE 1=1"
        params: list = []
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        return self.db.fetchall(sql, tuple(params))
