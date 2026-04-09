"""
RedditPilot Strategy Engine — self-improving intelligence for multi-client operations.

Adapted from MiloAgent's StrategyEngine for RedditPilot's agency model.
Each client gets independent adaptive weights, community warmth tracking,
and scheduling optimization.

Scoring Dimensions (0-10 composite):
  - Keyword relevance (0-4)   x learned keyword weight
  - Engagement velocity (0-2)
  - Comment velocity / competition (0-2)
  - Recency with exponential decay (0-1.5)
  - Subreddit quality (0-1.5)  x learned subreddit weight
  - Intent signals (0-1.0)

Self-Improvement:
  - Subreddit weights: boost subreddits where comments get engagement
  - Keyword weights: boost keywords that find high-quality opportunities
  - Timing optimization: learn best posting windows per client
  - Community warmth: track account-subreddit trust progression
"""

import random
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

from ..core.database import Database
from ..core.config import Config, ClientProfile

logger = logging.getLogger("redditpilot.strategy")

# ---------------------------------------------------------------------------
# Intent signal patterns (compiled once at module level)
# ---------------------------------------------------------------------------
_QUESTION_SIGNALS = [
    "?", "how do i", "how to", "what is", "which",
    "anyone know", "can someone", "should i",
]

_HELP_SIGNALS = [
    "recommend", "looking for", "suggest", "alternative",
    "advice", "what tool", "what app", "best way",
    "struggling", "stuck", "doesn't work", "help me",
    "need a", "hire", "who do you use",
]

_INTENT_PATTERNS = {
    "direct_ask": [
        re.compile(r"\bwho do you (use|recommend|suggest)\b", re.I),
        re.compile(r"\blooking for (a |an )?(good |reliable )?\w+\b", re.I),
        re.compile(r"\bneed (a |an )?\w+\b", re.I),
        re.compile(r"\bany (recommendations?|suggestions?)\b", re.I),
        re.compile(r"\bbest \w+\b", re.I),
        re.compile(r"\bcan anyone recommend\b", re.I),
    ],
    "problem_post": [
        re.compile(r"\b(broken|not working|stopped|leaking|clogged|tripping)\b", re.I),
        re.compile(r"\bno (hot water|heat|ac|cooling|power)\b", re.I),
        re.compile(r"\bemergency\b", re.I),
    ],
    "diy_question": [
        re.compile(r"\bshould i (call|hire|get) a (pro|professional)\b", re.I),
        re.compile(r"\bdiy or (hire|call|professional)\b", re.I),
        re.compile(r"\bhow (much|hard|difficult|long)\b.*\b(fix|replace|install|repair)\b", re.I),
    ],
    "cost_question": [
        re.compile(r"\bhow much\b.*\b(cost|charge|pay|spend)\b", re.I),
        re.compile(r"\b(fair|reasonable|average|typical) (price|cost|rate|quote)\b", re.I),
        re.compile(r"\bgetting (quoted|charged|billed)\b", re.I),
    ],
}


# ===========================================================================
# Strategy Engine
# ===========================================================================

class StrategyEngine:
    """Self-improving intelligence layer for multi-client Reddit operations.

    All scoring weights adapt per-client based on performance data stored in
    the ``learned_strategies`` table.  Community warmth is tracked per
    account-subreddit pair so the system can decide when promotional content
    is safe.
    """

    # ── Default scoring weights (overridden by learned per-client values) ──
    DEFAULT_WEIGHTS: Dict[str, float] = {
        "keyword_relevance": 0.30,
        "engagement_velocity": 0.15,
        "comment_velocity": 0.15,
        "recency": 0.10,
        "subreddit_quality": 0.10,
        "intent": 0.20,
    }

    # Community warmth stage thresholds
    WARMTH_STAGES = ("new", "warming", "established", "trusted")

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        # Weighted round-robin state per client slug
        self._last_client_index: int = -1
        # Cache for learned boosts (cleared each cycle)
        self._boost_cache: Dict[str, float] = {}

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC API: score_opportunity
    # ──────────────────────────────────────────────────────────────────────

    def score_opportunity(self, post: Dict, client: ClientProfile) -> Dict:
        """Score a Reddit post opportunity on 6 adaptive dimensions.

        Returns a dict with per-dimension scores (each 0-1 normalised),
        a ``composite`` score (0-10), and auxiliary info.
        """
        text = f"{post.get('title', '')} {post.get('body', '')}".lower()
        client_db_id = self._resolve_client_id(client)

        # Per-dimension scores (raw 0-N, will be normalised to 0-1 for weighting)
        raw = {}

        # 1) Keyword relevance (raw 0-4)
        raw["keyword_relevance"] = self._score_keyword_relevance(
            text, post, client, client_db_id,
        )

        # 2) Engagement velocity (raw 0-2)
        raw["engagement_velocity"] = self._score_engagement_velocity(post)

        # 3) Comment velocity / competition (raw 0-2)
        raw["comment_velocity"] = self._score_comment_velocity(post)

        # 4) Recency (raw 0-1.5)
        raw["recency"] = self._score_recency(post)

        # 5) Subreddit quality (raw 0-1.5)
        raw["subreddit_quality"] = self._score_subreddit_quality(
            post, client, client_db_id,
        )

        # 6) Intent signals (raw 0-1.0)
        raw["intent"] = self._score_intent(text)

        # ── Normalise each raw score to 0-1 ────────────────────────────
        max_raw = {
            "keyword_relevance": 4.0,
            "engagement_velocity": 2.0,
            "comment_velocity": 2.0,
            "recency": 1.5,
            "subreddit_quality": 1.5,
            "intent": 1.0,
        }
        normed = {
            dim: min(raw[dim] / max_raw[dim], 1.0)
            for dim in raw
        }

        # ── Load per-client learned weights ────────────────────────────
        weights = dict(self.DEFAULT_WEIGHTS)
        learned = self.db.get_strategies("scoring_weight", client_id=client_db_id)
        for strat in learned:
            if strat["key"] in weights:
                weights[strat["key"]] = strat["value"]

        # ── Composite (0-10) ───────────────────────────────────────────
        weighted_sum = sum(
            normed[dim] * weights.get(dim, 0.1)
            for dim in normed
        )
        # Scale from weighted-average-in-[0,1] to [0,10]
        composite = min(max(weighted_sum * 10.0, 0.0), 10.0)

        # Bonus: upvote ratio
        if post.get("upvote_ratio", 0.5) >= 0.9:
            composite = min(composite + 0.3, 10.0)

        return {
            **normed,
            "raw": raw,
            "composite": composite,
            "matched_intents": self._get_matched_intents(text),
            "matched_keywords": self._get_matched_keywords(
                f"{post.get('title', '')} {post.get('body', '')}",
                client,
            ),
        }

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC API: select_client (weighted round-robin with catch-up)
    # ──────────────────────────────────────────────────────────────────────

    def select_client(
        self,
        exclude: Optional[set] = None,
    ) -> Optional[ClientProfile]:
        """Select which client to serve next using weighted round-robin
        with catch-up fairness.

        ``exclude`` is a set of client slugs already served this cycle.
        """
        clients = [c for c in self.config.get_enabled_clients()
                    if not exclude or c.slug not in exclude]
        if not clients:
            return None
        if len(clients) == 1:
            return clients[0]

        # Fetch recent action counts per client (last 24h)
        recent_rows = self.db.fetchall(
            "SELECT client_id, COUNT(*) as cnt FROM action_log "
            "WHERE created_at > datetime('now', '-24 hours') "
            "GROUP BY client_id",
        )
        action_counts: Dict[int, int] = {
            r["client_id"]: r["cnt"] for r in recent_rows
        }
        total_actions = sum(action_counts.values()) or 1

        # Build weighted list
        weighted: List[Tuple[ClientProfile, float]] = []
        total_base = max(len(clients), 1)  # equal weight when none specified
        for cl in clients:
            base_weight = 1.0  # equal by default
            cid = self._resolve_client_id(cl)
            actual = action_counts.get(cid, 0)
            expected_share = base_weight / total_base
            actual_share = actual / total_actions
            catch_up = max(0.5, expected_share / max(actual_share, 0.01))
            weight = base_weight * min(catch_up, 3.0)
            weighted.append((cl, weight))

        # Weighted random selection
        total_w = sum(w for _, w in weighted)
        r = random.uniform(0, total_w)
        cumulative = 0.0
        for cl, w in weighted:
            cumulative += w
            if r <= cumulative:
                return cl
        return weighted[-1][0]

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC API: get_best_subreddits
    # ──────────────────────────────────────────────────────────────────────

    def get_best_subreddits(
        self,
        client_id: int,
        limit: int = 20,
    ) -> List[Dict]:
        """Return subreddits ranked by combined strategy + intel score.

        Each item: ``{name, combined_score, opportunity_score, learned_boost}``
        """
        client = self._client_by_db_id(client_id)
        base_subs = self._get_expanded_subreddits(client, client_id)

        scored: List[Dict] = []
        for sub in base_subs:
            intel = self.db.get_subreddit_intel(sub)
            opp_score = intel.get("opportunity_score", 5.0) if intel else 5.0
            boost = self._get_learned_boost("subreddit", sub, client_id)
            combined = opp_score * boost
            scored.append({
                "name": sub,
                "combined_score": round(combined, 3),
                "opportunity_score": round(opp_score, 3),
                "learned_boost": round(boost, 3),
            })

        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        return scored[:limit]

    # ──────────────────────────────────────────────────────────────────────
    #  Keyword / subreddit expansion
    # ──────────────────────────────────────────────────────────────────────

    def get_expanded_keywords(
        self,
        client: ClientProfile,
        client_db_id: Optional[int] = None,
    ) -> List[str]:
        """Original keywords + approved discovered keywords from learning data."""
        cid = client_db_id or self._resolve_client_id(client)
        base = list(client.keywords)
        discovered = self.db.get_strategies(
            "discovered_keyword", client_id=cid,
        )
        for d in discovered:
            if d["confidence"] >= 0.5 and d["key"] not in base:
                base.append(d["key"])
        return base

    def _get_expanded_subreddits(
        self,
        client: Optional[ClientProfile],
        client_db_id: int,
    ) -> List[str]:
        """Original target_subreddits + DB-stored + discovered subreddits."""
        base: List[str] = []
        if client and client.target_subreddits:
            base = list(client.target_subreddits)

        # DB-stored subreddits for this client
        db_subs = self.db.fetchall(
            "SELECT s.name FROM subreddits s "
            "JOIN client_subreddits cs ON s.id = cs.subreddit_id "
            "WHERE cs.client_id = ? AND s.enabled = 1 "
            "ORDER BY cs.relevance_score DESC LIMIT 50",
            (client_db_id,),
        )
        base.extend(s["name"] for s in db_subs)

        # Discovered subreddits (from learning engine)
        discovered = self.db.get_strategies(
            "discovered_subreddit", client_id=client_db_id,
        )
        for d in discovered:
            if d["confidence"] >= 0.5:
                base.append(d["key"])

        # Deduplicate preserving order
        seen: set = set()
        unique: List[str] = []
        for s in base:
            sl = s.lower()
            if sl not in seen:
                seen.add(sl)
                unique.append(s)
        return unique

    # ──────────────────────────────────────────────────────────────────────
    #  Community Warmth
    # ──────────────────────────────────────────────────────────────────────

    def compute_warmth_score(self, presence: Dict) -> float:
        """Compute community warmth score (0-10) from presence data.

        Presence dict keys:
            total_comments, total_posts, comments_surviving, comments_removed,
            days_active, avg_comment_score
        """
        score = 0.0

        # Interaction volume (0-3)
        total = presence.get("total_comments", 0) + presence.get("total_posts", 0)
        if total >= 20:
            score += 3.0
        elif total >= 10:
            score += 2.0
        elif total >= 5:
            score += 1.5
        elif total >= 2:
            score += 0.5

        # Reputation / survival rate (0-3)
        surviving = presence.get("comments_surviving", 0)
        removed = presence.get("comments_removed", 0)
        total_c = surviving + removed
        if total_c > 0:
            survival_rate = surviving / total_c
            score += min(3.0, survival_rate * 3.0)

        # Time invested (0-2)
        days = presence.get("days_active", 0)
        if days >= 30:
            score += 2.0
        elif days >= 14:
            score += 1.5
        elif days >= 7:
            score += 1.0
        elif days >= 3:
            score += 0.5

        # Engagement quality (0-2)
        avg_score = presence.get("avg_comment_score", 0)
        if avg_score >= 5:
            score += 2.0
        elif avg_score >= 3:
            score += 1.5
        elif avg_score >= 1:
            score += 1.0

        return min(score, 10.0)

    def determine_warmth_stage(self, presence: Dict) -> str:
        """Determine engagement stage from presence data.

        Stages: new -> warming -> established -> trusted
        """
        total = presence.get("total_comments", 0) + presence.get("total_posts", 0)
        days = presence.get("days_active", 0)
        surviving = presence.get("comments_surviving", 0)
        removed = presence.get("comments_removed", 0)
        total_c = surviving + removed
        removal_rate = removed / total_c if total_c > 0 else 0
        avg_score = presence.get("avg_comment_score", 0)

        if total >= 20 and days >= 30 and removal_rate < 0.1 and avg_score > 2:
            return "trusted"
        if total >= 10 and days >= 14 and removal_rate < 0.2:
            return "established"
        if total >= 3 and days >= 3 and removal_rate < 0.5:
            return "warming"
        return "new"

    def get_warmth_for_subreddit(
        self,
        subreddit: str,
        account_username: str,
        client_db_id: int,
    ) -> Dict:
        """Build a presence dict from DB data for a specific account-subreddit pair.

        Returns ``{stage, warmth_score, total_comments, ...}`` or defaults for 'new'.
        """
        # Count comments by this account in this subreddit for this client
        comments_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt, "
            "  SUM(CASE WHEN is_removed = 0 THEN 1 ELSE 0 END) as surviving, "
            "  SUM(CASE WHEN is_removed = 1 THEN 1 ELSE 0 END) as removed, "
            "  AVG(CASE WHEN score IS NOT NULL THEN score ELSE 0 END) as avg_score "
            "FROM comments c "
            "JOIN accounts a ON c.account_id = a.id "
            "WHERE a.username = ? AND c.subreddit = ? AND c.client_id = ? "
            "  AND c.status = 'posted'",
            (account_username, subreddit, client_db_id),
        )

        posts_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM posts p "
            "JOIN accounts a ON p.account_id = a.id "
            "WHERE a.username = ? AND p.subreddit = ? AND p.client_id = ? "
            "  AND p.status = 'posted'",
            (account_username, subreddit, client_db_id),
        )

        # Calculate days active
        first_action = self.db.fetchone(
            "SELECT MIN(c.created_at) as first_at FROM comments c "
            "JOIN accounts a ON c.account_id = a.id "
            "WHERE a.username = ? AND c.subreddit = ? AND c.client_id = ?",
            (account_username, subreddit, client_db_id),
        )
        days_active = 0
        if first_action and first_action.get("first_at"):
            try:
                first_dt = datetime.fromisoformat(first_action["first_at"])
                days_active = (datetime.utcnow() - first_dt).days
            except (ValueError, TypeError):
                pass

        total_comments = (comments_row["cnt"] if comments_row else 0) or 0
        total_posts = (posts_row["cnt"] if posts_row else 0) or 0
        surviving = (comments_row["surviving"] if comments_row else 0) or 0
        removed = (comments_row["removed"] if comments_row else 0) or 0
        avg_score = (comments_row["avg_score"] if comments_row else 0) or 0

        presence = {
            "total_comments": total_comments,
            "total_posts": total_posts,
            "comments_surviving": surviving,
            "comments_removed": removed,
            "days_active": days_active,
            "avg_comment_score": avg_score,
        }
        stage = self.determine_warmth_stage(presence)
        warmth = self.compute_warmth_score(presence)

        return {
            "stage": stage,
            "warmth_score": round(warmth, 2),
            **presence,
        }

    def can_promote_in_subreddit(
        self,
        subreddit: str,
        account_username: str,
        client_db_id: int,
    ) -> bool:
        """True only if the account has 'trusted' status in this subreddit."""
        info = self.get_warmth_for_subreddit(subreddit, account_username, client_db_id)
        return info["stage"] == "trusted"

    # ──────────────────────────────────────────────────────────────────────
    #  Smart Scheduling
    # ──────────────────────────────────────────────────────────────────────

    def get_best_posting_times(
        self,
        client_db_id: int,
        limit: int = 5,
    ) -> List[Dict]:
        """Analyse performance_log to find best (day_of_week, hour_of_day) slots.

        Returns list of ``{day_of_week, hour_of_day, avg_score, sample_count}``
        ordered by avg_score descending.
        """
        rows = self.db.fetchall(
            "SELECT day_of_week, hour_of_day, "
            "  AVG(metric_value) as avg_score, COUNT(*) as sample_count "
            "FROM performance_log "
            "WHERE metric_type IN ('comment_score', 'post_score') "
            "  AND client_id = ? AND recorded_at > datetime('now', '-30 days') "
            "GROUP BY day_of_week, hour_of_day "
            "HAVING sample_count >= 2 "
            "ORDER BY avg_score DESC LIMIT ?",
            (client_db_id, limit),
        )
        return [dict(r) for r in rows]

    def should_delay_action(self, client_db_id: int) -> Optional[int]:
        """Check if we should delay posting for a better time slot.

        Returns minutes to delay (0 = post now), None if no data.
        Max delay: 2 hours.
        """
        best = self.get_best_posting_times(client_db_id, limit=3)
        if not best:
            return None

        now = datetime.utcnow()
        current_hour = now.hour
        current_day = now.weekday()

        # Already in a good window?
        for slot in best:
            if (slot["hour_of_day"] == current_hour
                    and slot["day_of_week"] == current_day):
                return 0

        # Find the nearest top slot within 2 hours
        best_hour = best[0]["hour_of_day"]
        hours_until = (best_hour - current_hour) % 24
        if hours_until <= 2:
            return hours_until * 60

        return 0  # Too far away, post now

    def get_schedule_recommendation(self, client_db_id: int) -> Dict:
        """Return a human-friendly scheduling recommendation."""
        times = self.get_best_posting_times(client_db_id, limit=5)
        delay = self.should_delay_action(client_db_id)
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        slots = []
        for t in times:
            d = day_names[t["day_of_week"]] if 0 <= t["day_of_week"] <= 6 else "?"
            slots.append(f"{d} {t['hour_of_day']:02d}:00 (avg={t['avg_score']:.1f}, n={t['sample_count']})")
        return {
            "best_slots": slots,
            "delay_minutes": delay,
            "has_data": len(times) > 0,
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Strategy Insights / Analytics
    # ──────────────────────────────────────────────────────────────────────

    def get_client_strategy_summary(self, client_db_id: int) -> Dict:
        """Return a summary of all learned strategy data for a client."""
        weights = self.db.get_strategies("scoring_weight", client_id=client_db_id)
        kw_boosts = self.db.get_strategies("keyword_boost", client_id=client_db_id)
        sub_boosts = self.db.get_strategies("subreddit_boost", client_id=client_db_id)
        perf = self.db.get_performance_summary("comment_score", days=7, client_id=client_db_id)

        return {
            "scoring_weights": {s["key"]: round(s["value"], 3) for s in weights},
            "top_keyword_boosts": {
                s["key"]: round(s["value"], 2) for s in kw_boosts[:10]
            },
            "top_subreddit_boosts": {
                s["key"]: round(s["value"], 2) for s in sub_boosts[:10]
            },
            "performance_7d": dict(perf) if perf else {},
            "best_times": self.get_best_posting_times(client_db_id, limit=3),
        }

    # ──────────────────────────────────────────────────────────────────────
    #  PRIVATE: Scoring sub-functions
    # ──────────────────────────────────────────────────────────────────────

    def _score_keyword_relevance(
        self,
        text: str,
        post: Dict,
        client: ClientProfile,
        client_db_id: Optional[int],
    ) -> float:
        """Keyword relevance score (0-4) with title bonus + learned boosts."""
        keywords = self.get_expanded_keywords(client, client_db_id)
        title = post.get("title", "").lower()
        body = post.get("body", "").lower()

        kw_score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            boost = self._get_learned_boost("keyword", kw, client_db_id)
            if kw_lower in title:
                kw_score += 1.5 * boost  # Title match = strong signal
            elif kw_lower in body:
                kw_score += 0.8 * boost

        # Industry term bonus
        industry_terms = {
            "plumbing": ["plumb", "pipe", "drain", "faucet", "toilet",
                         "water heater", "sewer", "leak"],
            "hvac": ["hvac", "air condition", "furnace", "heat pump",
                     "thermostat", "duct", "ac ", "a/c"],
            "electrical": ["electric", "wiring", "outlet", "circuit",
                           "breaker", "panel", "switch", "volt"],
        }
        terms = industry_terms.get(client.industry, [])
        matches = sum(1 for t in terms if t in text)
        kw_score += min(matches * 0.15, 0.5)

        # Service area mention
        if client.service_area:
            city = client.service_area.split(",")[0].strip().lower()
            if city and city in text:
                kw_score += 0.5

        return min(kw_score, 4.0)

    def _score_engagement_velocity(self, post: Dict) -> float:
        """Engagement velocity score (0-2) — upvotes per hour."""
        post_score = post.get("score", post.get("post_score", 0))
        created = post.get("created_utc")
        if not created or not isinstance(post_score, (int, float)):
            if isinstance(post_score, (int, float)) and post_score >= 5:
                return 0.5
            return 0.0

        age_hours = max(0.1, (
            datetime.now(timezone.utc).timestamp() - created
        ) / 3600)
        velocity = post_score / age_hours

        if velocity >= 50:
            return 2.0
        if velocity >= 20:
            return 1.5
        if velocity >= 5:
            return 1.0
        if velocity >= 1:
            return 0.5
        return 0.0

    def _score_comment_velocity(self, post: Dict) -> float:
        """Comment velocity score (0-2) — lower = less competition."""
        num_comments = post.get("num_comments", 0)
        created = post.get("created_utc")
        if not created or not isinstance(num_comments, int):
            return 1.0  # neutral

        age_hours = max(0.1, (
            datetime.now(timezone.utc).timestamp() - created
        ) / 3600)
        vel = num_comments / age_hours

        if vel <= 1:
            return 2.0
        if vel <= 3:
            return 1.5
        if vel <= 8:
            return 1.0
        if vel <= 15:
            return 0.5
        return 0.0

    def _score_recency(self, post: Dict) -> float:
        """Recency with exponential decay (0-1.5)."""
        created = post.get("created_utc")
        if not created:
            return 0.3  # unknown age — slight penalty

        age_hours = (
            datetime.now(timezone.utc).timestamp() - created
        ) / 3600
        # Half-life of 4 hours
        recency = 1.5 * (0.5 ** (age_hours / 4))
        return max(0.0, min(recency, 1.5))

    def _score_subreddit_quality(
        self,
        post: Dict,
        client: ClientProfile,
        client_db_id: Optional[int],
    ) -> float:
        """Subreddit quality score (0-1.5) with learned boost + intel data."""
        subreddit = post.get("subreddit", "")
        primary = client.target_subreddits or []
        boost = self._get_learned_boost("subreddit", subreddit, client_db_id)

        if subreddit.lower() in [p.lower() for p in primary]:
            base = 1.2
        else:
            base = 0.5

        # Intel boost for high-opportunity subreddits
        try:
            intel = self.db.get_subreddit_intel(subreddit)
            if intel and intel.get("opportunity_score", 0) > 6.0:
                base += 0.3
        except Exception:
            pass

        return min(base * boost, 1.5)

    def _score_intent(self, text: str) -> float:
        """Intent signal score (0-1.0)."""
        score = 0.0

        # Simple signal matching
        if any(sig in text for sig in _QUESTION_SIGNALS):
            score += 0.3

        if any(sig in text for sig in _HELP_SIGNALS):
            score += 0.3

        # Regex pattern matching for stronger signals
        intent_weights = {
            "direct_ask": 0.4,
            "problem_post": 0.3,
            "cost_question": 0.3,
            "diy_question": 0.2,
        }
        for category, patterns in _INTENT_PATTERNS.items():
            for pat in patterns:
                if pat.search(text):
                    score += intent_weights.get(category, 0.2)
                    break  # one match per category

        return min(score, 1.0)

    # ──────────────────────────────────────────────────────────────────────
    #  PRIVATE: Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _get_learned_boost(
        self,
        boost_type: str,
        key: str,
        client_db_id: Optional[int],
    ) -> float:
        """Get a learned scoring boost multiplier (default 1.0).

        Caches results in ``_boost_cache`` for the current cycle.
        """
        cache_key = f"{boost_type}:{key}:{client_db_id}"
        if cache_key in self._boost_cache:
            return self._boost_cache[cache_key]

        strategy_type = f"{boost_type}_boost"
        rows = self.db.get_strategies(strategy_type, client_id=client_db_id)
        boost = 1.0
        for r in rows:
            if r["key"].lower() == key.lower() and r["confidence"] >= 0.3:
                boost = max(0.5, min(r["value"], 3.0))
                break

        self._boost_cache[cache_key] = boost
        return boost

    def clear_boost_cache(self):
        """Clear the per-cycle boost cache (call at start of each scan cycle)."""
        self._boost_cache.clear()

    def _resolve_client_id(self, client: ClientProfile) -> Optional[int]:
        """Look up the DB id for a ClientProfile by slug."""
        row = self.db.fetchone(
            "SELECT id FROM clients WHERE slug = ?", (client.slug,)
        )
        return row["id"] if row else None

    def _client_by_db_id(self, client_db_id: int) -> Optional[ClientProfile]:
        """Find the ClientProfile from config that matches a DB id."""
        row = self.db.fetchone(
            "SELECT slug FROM clients WHERE id = ?", (client_db_id,)
        )
        if not row:
            return None
        for c in self.config.clients:
            if c.slug == row["slug"]:
                return c
        return None

    def _get_matched_intents(self, text: str) -> List[str]:
        """Return list of matched intent category names."""
        matched = []
        for category, patterns in _INTENT_PATTERNS.items():
            for pat in patterns:
                if pat.search(text):
                    matched.append(category)
                    break
        return matched

    def _get_matched_keywords(self, text: str, client: ClientProfile) -> List[str]:
        """Return list of client keywords found in text."""
        text_lower = text.lower()
        return [k for k in client.keywords if k.lower() in text_lower]

    # ──────────────────────────────────────────────────────────────────────
    #  Learning: record and update strategy weights
    # ──────────────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        client_db_id: int,
        subreddit: str,
        keyword_hits: List[str],
        comment_score: int,
        was_removed: bool,
        tone: str = None,
        hour_of_day: int = None,
        day_of_week: int = None,
    ):
        """Record the outcome of an action and update learned weights.

        Call this after checking comment performance (score, removal status).
        """
        # Log raw metric
        now = datetime.utcnow()
        self.db.log_performance(
            metric_type="comment_score",
            metric_value=float(comment_score),
            client_id=client_db_id,
            subreddit=subreddit,
            tone=tone,
        )

        # Update subreddit boost
        current_boost = self._get_learned_boost("subreddit", subreddit, client_db_id)
        if was_removed:
            new_boost = max(0.3, current_boost * 0.85)  # penalise removals
        elif comment_score >= 3:
            new_boost = min(3.0, current_boost * 1.1)
        elif comment_score >= 1:
            new_boost = current_boost  # neutral
        else:
            new_boost = max(0.5, current_boost * 0.95)

        self.db.upsert_strategy(
            strategy_type="subreddit_boost",
            key=subreddit,
            value=round(new_boost, 3),
            confidence=min(0.9, 0.5 + 0.01 * comment_score),
            sample_count=1,
            client_id=client_db_id,
            subreddit=subreddit,
        )

        # Update keyword boosts
        for kw in keyword_hits:
            kw_boost = self._get_learned_boost("keyword", kw, client_db_id)
            if comment_score >= 3:
                kw_boost = min(3.0, kw_boost * 1.1)
            elif was_removed:
                kw_boost = max(0.5, kw_boost * 0.9)
            self.db.upsert_strategy(
                strategy_type="keyword_boost",
                key=kw,
                value=round(kw_boost, 3),
                confidence=min(0.9, 0.5 + 0.01 * comment_score),
                sample_count=1,
                client_id=client_db_id,
            )

        # Clear cache so new values take effect
        self.clear_boost_cache()
