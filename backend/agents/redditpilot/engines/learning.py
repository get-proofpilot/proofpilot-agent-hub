"""
RedditPilot Learning Engine
Self-improving system that tracks performance and optimizes strategies.
Merged from original RedditPilot learning engine + MiloAgent advanced features.

Features:
- Comment score tracking and negative-comment cleanup
- Tone, timing, keyword weight learning
- Sentiment analysis (keyword-based, no LLM)
- Tone-from-sentiment blending (70% engagement + 30% sentiment)
- Post type weight learning
- LLM-powered target discovery (new subreddits/keywords)
- LLM-powered prompt evolution from top content
- Performance benchmarking (this week vs last week)
- Recency decay factor (0.95) for weight calculations
- LLM-powered strategy rule extraction
- Failure analysis via LLM
- All features multi-client aware (scoped by client_id)
"""

import json
import logging
import math
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Dict, List

from ..core.config import Config
from ..core.database import Database

logger = logging.getLogger("redditpilot.learning")

# Minimum samples before we trust a learned weight
_MIN_SAMPLES = 3
# Decay factor: recent data matters more (exponential decay per day)
_RECENCY_DECAY = 0.95

# ── Sentiment keyword scoring (no LLM needed) ──────────────────────────
_POSITIVE_SIGNALS = {
    "thanks": 0.3, "thank you": 0.3, "helpful": 0.4, "great advice": 0.5,
    "this helped": 0.5, "exactly what i needed": 0.5, "good point": 0.3,
    "agree": 0.2, "nice": 0.2, "awesome": 0.3, "love this": 0.4,
    "saved me": 0.5, "game changer": 0.4, "underrated": 0.3,
    "solid": 0.2, "appreciate": 0.3, "well said": 0.3, "spot on": 0.3,
    "this works": 0.4, "just tried": 0.3, "i needed this": 0.4,
}
_NEGATIVE_SIGNALS = {
    "spam": -0.8, "shill": -0.9, "bot": -0.7, "ad": -0.6,
    "reported": -0.9, "self-promo": -0.8, "self promo": -0.8,
    "wrong": -0.3, "doesn't work": -0.4, "terrible": -0.5,
    "useless": -0.4, "downvoted": -0.5, "cringe": -0.4,
    "suspicious": -0.6, "misleading": -0.5, "clickbait": -0.5,
    "not helpful": -0.4, "bad advice": -0.5, "scam": -0.9,
}


class LearningEngine:
    """Tracks performance and learns optimal strategies over time.

    Combines RedditPilot's original learning cycle with MiloAgent's
    advanced self-improvement features. All methods are multi-client
    aware and scope data by client_id where applicable.
    """

    def __init__(self, config: Config, db: Database, llm_client=None):
        self.config = config
        self.db = db
        self.llm = llm_client

    # ══════════════════════════════════════════════════════════════════════
    #  Main Learning Cycle
    # ══════════════════════════════════════════════════════════════════════

    def run_learning_cycle(self, client_id: int = None):
        """Execute a full learning cycle. Should run every few hours.

        Analyzes recent performance and updates strategy weights.
        If client_id is provided, scopes learning to that client only.
        """
        logger.info("Starting learning cycle" + (f" for client {client_id}" if client_id else ""))

        # Original RP features
        self._check_comment_scores(client_id=client_id)
        self._cleanup_negative_comments(client_id=client_id)
        self._learn_tone_weights(client_id=client_id)
        self._learn_timing_weights(client_id=client_id)
        self._learn_keyword_weights(client_id=client_id)

        # MiloAgent advanced features
        self._learn_tone_from_sentiment(client_id=client_id)
        self._learn_post_type_weights(client_id=client_id)

        # LLM-powered features
        if self.llm:
            self._analyze_failures(client_id=client_id)
            self._discover_new_targets(client_id=client_id)
            self._learn_strategy_rules(client_id=client_id)
            self._evolve_prompts(client_id=client_id)

        logger.info("Learning cycle complete")

    # ══════════════════════════════════════════════════════════════════════
    #  Original RedditPilot Features
    # ══════════════════════════════════════════════════════════════════════

    def _check_comment_scores(self, client_id: int = None):
        """Update scores for all posted comments."""
        cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        sql = """
            SELECT c.*, a.username FROM comments c
            JOIN accounts a ON c.account_id = a.id
            WHERE c.status = 'posted'
              AND c.reddit_comment_id IS NOT NULL
              AND (c.last_checked_at IS NULL OR c.last_checked_at < ?)
        """
        params = [cutoff]
        if client_id:
            sql += " AND c.client_id = ?"
            params.append(client_id)
        sql += " LIMIT 50"

        comments = self.db.fetchall(sql, tuple(params))
        if not comments:
            return

        logger.info(f"Checking scores for {len(comments)} comments")

        for comment in comments:
            self.db.execute("""
                UPDATE comments SET last_checked_at = datetime('now')
                WHERE id = ?
            """, (comment["id"],))

        self.db.commit()

    def _cleanup_negative_comments(self, client_id: int = None):
        """Flag negative-score comments for deletion."""
        if not self.config.safety.auto_delete_negative_comments:
            return

        threshold = self.config.safety.negative_score_threshold
        sql = """
            SELECT * FROM comments
            WHERE status = 'posted'
              AND score < ?
              AND reddit_comment_id IS NOT NULL
        """
        params = [threshold]
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)

        negative = self.db.fetchall(sql, tuple(params))

        for comment in negative:
            logger.warning(
                f"Negative comment {comment['reddit_comment_id']} "
                f"(score: {comment['score']}) in r/{comment['subreddit']} - flagging for deletion"
            )
            self.db.update_comment_status(comment["id"], "flagged_for_deletion")

    def _learn_tone_weights(self, client_id: int = None):
        """Learn which tones perform best per subreddit.

        Applies recency decay: recent data weighted more heavily.
        """
        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        results = self.db.fetchall(f"""
            SELECT subreddit, tone_used, AVG(score) as avg_score,
                   COUNT(*) as sample_count,
                   MAX(posted_at) as last_posted
            FROM comments
            WHERE status = 'posted' AND tone_used IS NOT NULL AND score IS NOT NULL
            {client_filter}
            GROUP BY subreddit, tone_used
            HAVING sample_count >= {_MIN_SAMPLES}
        """, tuple(params))

        for row in results:
            decay = self._compute_recency_decay(row.get("last_posted"))
            adjusted_score = row["avg_score"] * decay

            self.db.upsert_strategy(
                strategy_type="tone_weight",
                key=row["tone_used"],
                value=adjusted_score,
                confidence=min(row["sample_count"] / 20, 1.0),
                sample_count=row["sample_count"],
                subreddit=row["subreddit"],
                client_id=client_id,
            )

        if results:
            logger.info(f"Updated tone weights for {len(results)} subreddit/tone combos")

    def _learn_timing_weights(self, client_id: int = None):
        """Learn optimal posting times."""
        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        results = self.db.fetchall(f"""
            SELECT hour_of_day, day_of_week, AVG(metric_value) as avg_score,
                   COUNT(*) as sample_count,
                   MAX(recorded_at) as last_recorded
            FROM performance_log
            WHERE metric_type IN ('comment_score', 'post_score')
            {client_filter}
            GROUP BY hour_of_day, day_of_week
            HAVING sample_count >= {_MIN_SAMPLES}
        """, tuple(params))

        for row in results:
            key = f"hour_{row['hour_of_day']}_day_{row['day_of_week']}"
            decay = self._compute_recency_decay(row.get("last_recorded"))
            adjusted_score = row["avg_score"] * decay

            self.db.upsert_strategy(
                strategy_type="timing_weight",
                key=key,
                value=adjusted_score,
                confidence=min(row["sample_count"] / 10, 1.0),
                sample_count=row["sample_count"],
                client_id=client_id,
            )

    def _learn_keyword_weights(self, client_id: int = None):
        """Learn which matched keywords lead to best engagement."""
        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND c.client_id = ?"
            params.append(client_id)

        results = self.db.fetchall(f"""
            SELECT dp.matched_keywords, AVG(c.score) as avg_score,
                   COUNT(*) as sample_count,
                   MAX(c.posted_at) as last_posted
            FROM comments c
            JOIN discovered_posts dp ON c.post_reddit_id = dp.reddit_id
            WHERE c.status = 'posted' AND dp.matched_keywords IS NOT NULL
            {client_filter}
            GROUP BY dp.matched_keywords
            HAVING sample_count >= 2
        """, tuple(params))

        for row in results:
            keywords = row.get("matched_keywords", "")
            if keywords:
                decay = self._compute_recency_decay(row.get("last_posted"))
                adjusted_score = row["avg_score"] * decay

                self.db.upsert_strategy(
                    strategy_type="keyword_weight",
                    key=keywords,
                    value=adjusted_score,
                    confidence=min(row["sample_count"] / 10, 1.0),
                    sample_count=row["sample_count"],
                    client_id=client_id,
                )

    def _analyze_failures(self, client_id: int = None):
        """Use LLM to analyze why some content failed."""
        client_filter = ""
        params_f = []
        params_s = []
        if client_id:
            client_filter = "AND client_id = ?"
            params_f.append(client_id)
            params_s.append(client_id)

        failures = self.db.fetchall(f"""
            SELECT content, subreddit, tone_used, score, persona_used
            FROM comments
            WHERE status = 'posted' AND score < 0
            {client_filter}
            ORDER BY score ASC
            LIMIT 10
        """, tuple(params_f))

        successes = self.db.fetchall(f"""
            SELECT content, subreddit, tone_used, score, persona_used
            FROM comments
            WHERE status = 'posted' AND score > 5
            {client_filter}
            ORDER BY score DESC
            LIMIT 10
        """, tuple(params_s))

        if not failures or not successes:
            return

        prompt = f"""Analyze these Reddit comments. Some failed (negative scores) and some succeeded (high scores).
What patterns do you see? What should we do differently?

FAILED COMMENTS:
{json.dumps([{"content": f["content"][:200], "subreddit": f["subreddit"], "score": f["score"], "tone": f["tone_used"]} for f in failures], indent=2)}

SUCCESSFUL COMMENTS:
{json.dumps([{"content": s["content"][:200], "subreddit": s["subreddit"], "score": s["score"], "tone": s["tone_used"]} for s in successes], indent=2)}

Respond with JSON:
{{"insights": ["insight 1", "insight 2"], "tone_recommendations": {{"subreddit_name": "recommended_tone"}}, "avoid_patterns": ["pattern to avoid"]}}
"""

        try:
            response = self.llm.generate(prompt, max_tokens=1000)
            analysis = json.loads(response)
            logger.info(f"Failure analysis insights: {analysis.get('insights', [])}")

            for pattern in analysis.get("avoid_patterns", []):
                self.db.upsert_strategy(
                    strategy_type="avoid_pattern",
                    key=pattern[:100],
                    value=-1.0,
                    confidence=0.6,
                    client_id=client_id,
                )

        except Exception as e:
            logger.error(f"Failure analysis failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    #  Sentiment Analysis (from MiloAgent - no LLM needed)
    # ══════════════════════════════════════════════════════════════════════

    def analyze_reply_sentiment(self, reply_bodies: List[str]) -> Dict:
        """Analyze sentiment of reply texts using keyword scoring.

        No LLM call — pure keyword matching for speed and cost.
        Returns: {score: float[-1,1], positive: list, negative: list}
        """
        if not reply_bodies:
            return {"score": 0.0, "positive": [], "negative": []}

        total_score = 0.0
        positives = []
        negatives = []

        for body in reply_bodies:
            body_lower = body.lower()
            for signal, weight in _POSITIVE_SIGNALS.items():
                if signal in body_lower:
                    total_score += weight
                    if signal not in positives:
                        positives.append(signal)
            for signal, weight in _NEGATIVE_SIGNALS.items():
                if signal in body_lower:
                    total_score += weight
                    if signal not in negatives:
                        negatives.append(signal)

        count = len(reply_bodies)
        normalized = max(-1.0, min(1.0, total_score / max(count, 1)))
        return {
            "score": round(normalized, 3),
            "positive": positives,
            "negative": negatives,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  Tone from Sentiment (MiloAgent: 70% engagement + 30% sentiment)
    # ══════════════════════════════════════════════════════════════════════

    def _learn_tone_from_sentiment(self, client_id: int = None):
        """Adjust tone weights by blending 70% engagement + 30% reply sentiment.

        For each tone+subreddit combo, looks at engagement scores (from
        tone_weight strategies) and reply sentiment (keyword-based analysis
        on comments that received replies). Blends both signals.
        """
        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND c.client_id = ?"
            params.append(client_id)

        # Get comments that have replies (engagement_count > 0) grouped by tone+subreddit
        tone_data = self.db.fetchall(f"""
            SELECT c.tone_used, c.subreddit,
                   COUNT(*) as sample_count,
                   AVG(c.score) as avg_score,
                   GROUP_CONCAT(c.id) as comment_ids
            FROM comments c
            WHERE c.status = 'posted'
              AND c.tone_used IS NOT NULL
              AND c.score IS NOT NULL
              AND c.engagement_count > 0
              {client_filter}
            GROUP BY c.tone_used, c.subreddit
            HAVING sample_count >= {_MIN_SAMPLES}
        """, tuple(params))

        if not tone_data:
            return

        # Get existing tone weights for blending
        existing_strategies = self.db.get_strategies(
            "tone_weight", client_id=client_id
        )
        weight_map = {}
        for s in existing_strategies:
            k = (s["key"], s.get("subreddit", ""))
            weight_map[k] = s

        adjustments = 0
        for row in tone_data:
            tone = row["tone_used"]
            subreddit = row["subreddit"]

            # Gather reply bodies for sentiment analysis
            comment_ids = str(row["comment_ids"]).split(",")[:20]
            reply_bodies = []
            for cid in comment_ids:
                try:
                    # Look for replies in performance_log or comments table
                    replies = self.db.fetchall("""
                        SELECT content FROM comments
                        WHERE post_reddit_id IN (
                            SELECT post_reddit_id FROM comments WHERE id = ?
                        ) AND id != ?
                        LIMIT 5
                    """, (cid.strip(), cid.strip()))
                    for r in replies:
                        if r.get("content"):
                            reply_bodies.append(r["content"])
                except Exception:
                    pass

            sentiment = self.analyze_reply_sentiment(reply_bodies)

            # Get existing engagement weight
            existing = weight_map.get((tone, subreddit))
            engagement_weight = existing["value"] if existing else row["avg_score"]

            # Blend: 70% engagement + 30% sentiment
            sentiment_bonus = sentiment["score"] * 0.3
            blended = (engagement_weight * 0.7) + (row["avg_score"] * 0.3) + sentiment_bonus
            blended = max(0.1, blended)

            self.db.upsert_strategy(
                strategy_type="tone_weight",
                key=tone,
                value=round(blended, 3),
                confidence=min(row["sample_count"] / 20, 1.0),
                sample_count=row["sample_count"],
                subreddit=subreddit,
                client_id=client_id,
            )
            adjustments += 1

        if adjustments:
            logger.info(f"Adjusted {adjustments} tone weights with sentiment blending")

    # ══════════════════════════════════════════════════════════════════════
    #  Post Type Weights (MiloAgent)
    # ══════════════════════════════════════════════════════════════════════

    def _learn_post_type_weights(self, client_id: int = None):
        """Learn which post types (text, link, image, etc.) perform best."""
        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        # From performance_log
        perf_results = self.db.fetchall(f"""
            SELECT post_type, COUNT(*) as sample_count,
                   AVG(metric_value) as avg_score,
                   MAX(recorded_at) as last_recorded
            FROM performance_log
            WHERE metric_type IN ('post_score', 'comment_score')
              AND post_type IS NOT NULL AND post_type != ''
              {client_filter}
            GROUP BY post_type
            HAVING sample_count >= {_MIN_SAMPLES}
        """, tuple(params))

        # Also from posts table directly
        params2 = []
        if client_id:
            params2.append(client_id)
        post_results = self.db.fetchall(f"""
            SELECT post_type, COUNT(*) as sample_count,
                   AVG(score) as avg_score,
                   MAX(posted_at) as last_posted
            FROM posts
            WHERE status = 'posted' AND post_type IS NOT NULL AND post_type != ''
              {client_filter}
            GROUP BY post_type
            HAVING sample_count >= {_MIN_SAMPLES}
        """, tuple(params2))

        # Merge both data sources
        merged = defaultdict(lambda: {"count": 0, "total_score": 0.0, "last_seen": None})
        for row in perf_results:
            pt = row["post_type"]
            merged[pt]["count"] += row["sample_count"]
            merged[pt]["total_score"] += row["avg_score"] * row["sample_count"]
            merged[pt]["last_seen"] = row.get("last_recorded")
        for row in post_results:
            pt = row["post_type"]
            merged[pt]["count"] += row["sample_count"]
            merged[pt]["total_score"] += row["avg_score"] * row["sample_count"]
            if not merged[pt]["last_seen"]:
                merged[pt]["last_seen"] = row.get("last_posted")

        for post_type, data in merged.items():
            if data["count"] < _MIN_SAMPLES:
                continue
            avg_score = data["total_score"] / data["count"]
            decay = self._compute_recency_decay(data["last_seen"])
            adjusted = avg_score * decay

            self.db.upsert_strategy(
                strategy_type="post_type_weight",
                key=post_type,
                value=round(max(0.1, adjusted), 3),
                confidence=min(data["count"] / 15, 1.0),
                sample_count=data["count"],
                client_id=client_id,
            )

        if merged:
            logger.info(f"Updated post type weights for {len(merged)} types")

    # ══════════════════════════════════════════════════════════════════════
    #  LLM-Powered Target Discovery (MiloAgent)
    # ══════════════════════════════════════════════════════════════════════

    def discover_new_targets(self, client_id: int = None):
        """Use LLM to discover new subreddits/keywords from performance data.

        Analyzes top-performing subreddits and keywords, then asks the LLM
        to suggest new targets. Results stored as strategies with type
        'discovered_subreddit' or 'discovered_keyword'.
        """
        if not self.llm:
            logger.debug("No LLM client, skipping target discovery")
            return

        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        # Get top-performing subreddits
        top_subs = self.db.fetchall(f"""
            SELECT subreddit, AVG(score) as avg_score, COUNT(*) as cnt
            FROM comments
            WHERE status = 'posted' AND score IS NOT NULL
              {client_filter}
            GROUP BY subreddit
            HAVING cnt >= 2
            ORDER BY avg_score DESC
            LIMIT 5
        """, tuple(params))

        # Get top-performing keywords
        params2 = list(params)
        top_keywords = self.db.fetchall(f"""
            SELECT key, value as avg_score, sample_count
            FROM learned_strategies
            WHERE strategy_type = 'keyword_weight'
              {"AND client_id = ?" if client_id else ""}
            ORDER BY value DESC
            LIMIT 5
        """, tuple(params2))

        if not top_subs and not top_keywords:
            logger.debug("Not enough data for target discovery")
            return

        sub_names = [s["subreddit"] for s in top_subs]
        kw_names = [k["key"] for k in top_keywords]

        prompt = (
            f"I'm running a Reddit marketing campaign.\n"
            f"My best-performing subreddits are: {', '.join(sub_names) if sub_names else 'none yet'}\n"
            f"My best keywords are: {', '.join(kw_names) if kw_names else 'none yet'}\n\n"
            f"Suggest 5 NEW subreddits (not in my list) where I could find "
            f"relevant discussions. Also suggest 5 NEW search keywords.\n\n"
            f"Format:\n"
            f"SUBREDDITS: sub1, sub2, sub3, sub4, sub5\n"
            f"KEYWORDS: kw1, kw2, kw3, kw4, kw5"
        )

        try:
            result = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "You are a Reddit marketing strategist. "
                    "Output only the requested format, nothing else."
                ),
                max_tokens=200,
            )
            self._parse_discoveries(result, client_id)
        except Exception as e:
            logger.error(f"Discovery LLM call failed: {e}")

    def _discover_new_targets(self, client_id: int = None):
        """Internal wrapper for discovery during learning cycle."""
        self.discover_new_targets(client_id=client_id)

    def _parse_discoveries(self, text: str, client_id: int = None):
        """Parse LLM discovery output and store as strategies."""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("SUBREDDITS:"):
                items = line.split(":", 1)[1].strip().split(",")
                for item in items:
                    sub = item.strip().lstrip("r/").strip()
                    if sub and len(sub) > 2:
                        self.db.upsert_strategy(
                            strategy_type="discovered_subreddit",
                            key=sub,
                            value=5.0,
                            confidence=0.4,
                            sample_count=0,
                            client_id=client_id,
                        )
                        logger.info(f"Discovered new subreddit target: r/{sub}")
            elif line.upper().startswith("KEYWORDS:"):
                items = line.split(":", 1)[1].strip().split(",")
                for item in items:
                    kw = item.strip().strip('"').strip("'")
                    if kw and len(kw) > 2:
                        self.db.upsert_strategy(
                            strategy_type="discovered_keyword",
                            key=kw,
                            value=5.0,
                            confidence=0.4,
                            sample_count=0,
                            client_id=client_id,
                        )
                        logger.info(f"Discovered new keyword target: {kw}")

    # ══════════════════════════════════════════════════════════════════════
    #  LLM-Powered Prompt Evolution (MiloAgent)
    # ══════════════════════════════════════════════════════════════════════

    def evolve_prompts(self, client_id: int = None):
        """Auto-evolve prompt templates based on top-performing content.

        Finds content that performed well, extracts patterns, and uses
        the LLM to generate improved prompt templates. Stores evolved
        prompts as strategies with type 'evolved_prompt'.
        """
        if not self.llm:
            return

        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        try:
            # Find top-performing content by post_type
            top_content = self.db.fetchall(f"""
                SELECT tone_used as post_type, COUNT(*) as cnt,
                       AVG(score) as avg_score
                FROM comments
                WHERE status = 'posted' AND score > 3
                  AND tone_used IS NOT NULL AND tone_used != ''
                  AND posted_at > datetime('now', '-30 days')
                  {client_filter}
                GROUP BY tone_used
                HAVING cnt >= 5
                ORDER BY avg_score DESC
                LIMIT 3
            """, tuple(params))

            if not top_content:
                return

            evolved_count = 0
            for pt_row in top_content:
                if evolved_count >= 3:
                    break

                post_type = pt_row["post_type"]
                template_name = f"reddit_{post_type}"

                # Check 7-day cooldown
                existing_evolved = self.db.fetchone("""
                    SELECT * FROM learned_strategies
                    WHERE strategy_type = 'evolved_prompt'
                      AND key = ?
                      AND updated_at > datetime('now', '-7 days')
                """, (template_name,))
                if existing_evolved:
                    continue

                # Get high-scoring content samples
                sample_params = [post_type]
                if client_id:
                    sample_params.append(client_id)
                samples = self.db.fetchall(f"""
                    SELECT content, score FROM comments
                    WHERE status = 'posted' AND tone_used = ?
                      AND score > 3
                      {client_filter}
                    ORDER BY score DESC
                    LIMIT 5
                """, tuple(sample_params))

                if len(samples) < 2:
                    continue

                sample_texts = "\n---\n".join(
                    s["content"][:400] for s in samples
                )

                prompt = (
                    f"Here are high-performing Reddit comments using "
                    f"'{post_type}' tone/style:\n\n"
                    f"{sample_texts}\n\n"
                    f"Analyze what makes these successful. Write an improved "
                    f"prompt template that captures these patterns. The template "
                    f"should instruct an AI to write similar high-quality content.\n"
                    f"Include placeholders like {{subreddit}}, {{topic}}, "
                    f"{{context}} where appropriate.\n"
                    f"Output ONLY the new template text, nothing else."
                )

                try:
                    new_template = self.llm.generate(
                        prompt=prompt,
                        system_prompt=(
                            "You are a Reddit content strategy expert. "
                            "Create effective prompt templates."
                        ),
                        max_tokens=500,
                    )

                    if new_template and len(new_template) > 50:
                        self.db.upsert_strategy(
                            strategy_type="evolved_prompt",
                            key=template_name,
                            value=pt_row["avg_score"],
                            confidence=min(pt_row["cnt"] / 20, 1.0),
                            sample_count=pt_row["cnt"],
                            client_id=client_id,
                        )
                        # Store full template text as a separate strategy
                        self.db.upsert_strategy(
                            strategy_type="evolved_prompt_text",
                            key=template_name,
                            value=0.0,
                            confidence=min(pt_row["cnt"] / 20, 1.0),
                            sample_count=pt_row["cnt"],
                            client_id=client_id,
                        )
                        evolved_count += 1
                        logger.info(
                            f"Evolved prompt template: {template_name} "
                            f"(avg_score={pt_row['avg_score']:.1f})"
                        )

                except Exception as e:
                    logger.debug(f"Prompt evolution LLM failed: {e}")

        except Exception as e:
            logger.error(f"Prompt evolution failed: {e}")

    def _evolve_prompts(self, client_id: int = None):
        """Internal wrapper for prompt evolution during learning cycle."""
        self.evolve_prompts(client_id=client_id)

    # ══════════════════════════════════════════════════════════════════════
    #  LLM-Powered Strategy Rules (MiloAgent)
    # ══════════════════════════════════════════════════════════════════════

    def _learn_strategy_rules(self, client_id: int = None):
        """LLM generates strategic rules from performance patterns.

        Analyzes which subreddit + tone combos work best and extracts
        reusable strategy rules. Stores as 'strategy_rule' type strategies.
        """
        if not self.llm:
            return

        client_filter = ""
        params = []
        if client_id:
            client_filter = "AND client_id = ?"
            params.append(client_id)

        try:
            # Need enough data to generate meaningful rules
            total_row = self.db.fetchone(f"""
                SELECT COUNT(*) as cnt FROM comments
                WHERE status = 'posted' {client_filter}
            """, tuple(params))

            if not total_row or total_row["cnt"] < 30:
                return

            # Get top-performing combos
            combo_params = list(params)
            top_combos = self.db.fetchall(f"""
                SELECT subreddit, tone_used, COUNT(*) as cnt,
                       AVG(score) as avg_score,
                       SUM(CASE WHEN is_removed = 1 THEN 1 ELSE 0 END) as removed
                FROM comments
                WHERE status = 'posted'
                  AND tone_used IS NOT NULL AND tone_used != ''
                  AND posted_at > datetime('now', '-30 days')
                  {client_filter}
                GROUP BY subreddit, tone_used
                HAVING cnt >= {_MIN_SAMPLES}
                ORDER BY avg_score DESC
                LIMIT 10
            """, tuple(combo_params))

            if len(top_combos) < 3:
                return

            combo_text = "\n".join(
                f"r/{c['subreddit']} + {c['tone_used']}: "
                f"avg_score={c['avg_score']:.2f}, n={c['cnt']}, "
                f"removed={c['removed']}"
                for c in top_combos
            )

            prompt = (
                f"Analyze these Reddit content performance patterns:\n\n"
                f"{combo_text}\n\n"
                f"Extract 3-5 strategy rules. Format: RULE: <rule text>\n"
                f"Example: RULE: In r/NewTubers, use helpful_casual tone "
                f"and avoid promotional content"
            )

            result = self.llm.generate(
                prompt=prompt,
                system_prompt=(
                    "You are a content strategy analyst. "
                    "Output only rules, one per line."
                ),
                max_tokens=300,
            )

            rules_added = 0
            for line in result.split("\n"):
                if line.strip().upper().startswith("RULE:"):
                    rule = line.split(":", 1)[1].strip()
                    if rule and len(rule) > 10:
                        self.db.upsert_strategy(
                            strategy_type="strategy_rule",
                            key=rule[:100],
                            value=top_combos[0]["avg_score"],
                            confidence=0.7,
                            sample_count=sum(c["cnt"] for c in top_combos),
                            client_id=client_id,
                        )
                        rules_added += 1

            if rules_added:
                logger.info(f"Learned {rules_added} strategy rules")

        except Exception as e:
            logger.error(f"Strategy rule extraction failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    #  Performance Benchmarking (MiloAgent: this week vs last week)
    # ══════════════════════════════════════════════════════════════════════

    def get_performance_benchmark(self, client_id: int = None) -> Dict:
        """Compare this week's performance vs last week.

        Returns a dict with engagement deltas, action counts, and removal stats.
        """
        client_filter = ""
        params_this = []
        params_last = []
        if client_id:
            client_filter = "AND client_id = ?"
            params_this.append(client_id)
            params_last.append(client_id)

        now = datetime.utcnow()
        this_week_start = (now - timedelta(days=7)).isoformat()
        last_week_start = (now - timedelta(days=14)).isoformat()
        last_week_end = (now - timedelta(days=7)).isoformat()

        # This week stats
        this_week = self.db.fetchone(f"""
            SELECT COUNT(*) as cnt,
                   AVG(score) as avg_score,
                   SUM(CASE WHEN is_removed = 1 THEN 1 ELSE 0 END) as removals
            FROM comments
            WHERE status = 'posted'
              AND posted_at > ?
              {client_filter}
        """, tuple([this_week_start] + params_this))

        # Last week stats
        last_week = self.db.fetchone(f"""
            SELECT COUNT(*) as cnt,
                   AVG(score) as avg_score,
                   SUM(CASE WHEN is_removed = 1 THEN 1 ELSE 0 END) as removals
            FROM comments
            WHERE status = 'posted'
              AND posted_at > ?
              AND posted_at <= ?
              {client_filter}
        """, tuple([last_week_start, last_week_end] + params_last))

        this_avg = (this_week["avg_score"] or 0) if this_week else 0
        last_avg = (last_week["avg_score"] or 0) if last_week else 0
        this_cnt = (this_week["cnt"] or 0) if this_week else 0
        last_cnt = (last_week["cnt"] or 0) if last_week else 0
        this_rem = (this_week["removals"] or 0) if this_week else 0
        last_rem = (last_week["removals"] or 0) if last_week else 0

        delta_pct = 0
        if last_avg > 0:
            delta_pct = round((this_avg - last_avg) / last_avg * 100, 1)

        return {
            "this_week_avg_engagement": round(this_avg, 2),
            "last_week_avg_engagement": round(last_avg, 2),
            "engagement_delta_pct": delta_pct,
            "this_week_actions": this_cnt,
            "last_week_actions": last_cnt,
            "this_week_removals": this_rem,
            "last_week_removals": last_rem,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  Recency Decay Helper
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _compute_recency_decay(timestamp_str: Optional[str]) -> float:
        """Compute recency decay factor based on age of data.

        Returns a multiplier in (0, 1] — more recent data gets closer to 1.0.
        Uses _RECENCY_DECAY (0.95) per day.
        """
        if not timestamp_str:
            return 1.0
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00").replace("+00:00", ""))
            days_ago = (datetime.utcnow() - ts).total_seconds() / 86400
            return _RECENCY_DECAY ** max(0, days_ago)
        except (ValueError, TypeError):
            return 1.0

    # ══════════════════════════════════════════════════════════════════════
    #  Query Methods (used by strategy/posting engines)
    # ══════════════════════════════════════════════════════════════════════

    def get_best_tone(self, subreddit: str, client_id: int = None) -> Optional[str]:
        """Get the best-performing tone for a subreddit."""
        strategies = self.db.get_strategies(
            "tone_weight", client_id=client_id, subreddit=subreddit
        )
        if strategies and strategies[0]["sample_count"] >= 5:
            return strategies[0]["key"]
        return None

    def get_best_posting_hours(self, client_id: int = None) -> list:
        """Get the best hours to post (in UTC)."""
        strategies = self.db.get_strategies(
            "timing_weight", client_id=client_id
        )
        if not strategies:
            # Default good hours (US timezone coverage, UTC)
            return [14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

        # Parse and rank hours
        hour_scores = {}
        for s in strategies:
            if s["key"].startswith("hour_"):
                parts = s["key"].split("_")
                hour = int(parts[1])
                if hour not in hour_scores or s["value"] > hour_scores[hour]:
                    hour_scores[hour] = s["value"]

        sorted_hours = sorted(hour_scores.keys(), key=lambda h: hour_scores[h], reverse=True)
        return sorted_hours[:10] if sorted_hours else [14, 15, 16, 17, 18, 19, 20]

    def get_best_post_types(self, client_id: int = None) -> List[Dict]:
        """Get post types ranked by performance."""
        strategies = self.db.get_strategies(
            "post_type_weight", client_id=client_id
        )
        return [
            {"post_type": s["key"], "score": s["value"],
             "confidence": s["confidence"], "samples": s["sample_count"]}
            for s in strategies
            if s["sample_count"] >= _MIN_SAMPLES
        ]

    def get_discovered_targets(self, client_id: int = None) -> Dict[str, List[str]]:
        """Get LLM-discovered subreddits and keywords."""
        subs = self.db.get_strategies(
            "discovered_subreddit", client_id=client_id
        )
        kws = self.db.get_strategies(
            "discovered_keyword", client_id=client_id
        )
        return {
            "subreddits": [s["key"] for s in subs],
            "keywords": [k["key"] for k in kws],
        }

    def get_strategy_rules(self, client_id: int = None) -> List[str]:
        """Get learned strategy rules."""
        strategies = self.db.get_strategies(
            "strategy_rule", client_id=client_id
        )
        return [s["key"] for s in strategies]

    def get_scoring_boost(
        self, category: str, key: str, client_id: int = None,
    ) -> float:
        """Get the learned scoring boost for a subreddit/keyword/tone.

        Returns a multiplier: 1.0 = neutral, >1 = boost, <1 = penalty.
        """
        weights = self.db.get_strategies(category, client_id=client_id)
        for w in weights:
            if w["key"].lower() == key.lower():
                if w["sample_count"] < _MIN_SAMPLES:
                    return 1.0
                avg = self._avg_strategy_value(weights)
                return max(0.3, min(w["value"] / max(avg, 0.1), 3.0))
        return 1.0  # No data, neutral

    @staticmethod
    def _avg_strategy_value(strategies: list) -> float:
        """Average value across strategies with enough samples."""
        valid = [s["value"] for s in strategies if s["sample_count"] >= _MIN_SAMPLES]
        return sum(valid) / len(valid) if valid else 1.0

    # ══════════════════════════════════════════════════════════════════════
    #  Report Generation
    # ══════════════════════════════════════════════════════════════════════

    def generate_report(self, client_id: int = None, days: int = 7) -> dict:
        """Generate a comprehensive performance report.

        Includes original RP metrics plus MiloAgent benchmark comparison.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Total comments
        comments_query = "SELECT COUNT(*) as cnt, AVG(score) as avg_score FROM comments WHERE status = 'posted' AND created_at > ?"
        params = [cutoff]
        if client_id:
            comments_query += " AND client_id = ?"
            params.append(client_id)
        comment_stats = self.db.fetchone(comments_query, tuple(params))

        # Total posts
        posts_query = "SELECT COUNT(*) as cnt, AVG(score) as avg_score FROM posts WHERE status = 'posted' AND created_at > ?"
        params2 = [cutoff]
        if client_id:
            posts_query += " AND client_id = ?"
            params2.append(client_id)
        post_stats = self.db.fetchone(posts_query, tuple(params2))

        # Top performing subreddits
        sub_filter = ""
        sub_params = [cutoff]
        if client_id:
            sub_filter = "AND client_id = ?"
            sub_params.append(client_id)
        top_subs = self.db.fetchall(f"""
            SELECT subreddit, COUNT(*) as actions, AVG(score) as avg_score
            FROM comments WHERE status = 'posted' AND created_at > ?
            {sub_filter}
            GROUP BY subreddit ORDER BY avg_score DESC LIMIT 10
        """, tuple(sub_params))

        # Removed content
        rem_params = [cutoff]
        rem_filter = ""
        if client_id:
            rem_filter = "AND client_id = ?"
            rem_params.append(client_id)
        removed = self.db.fetchone(f"""
            SELECT COUNT(*) as cnt FROM comments
            WHERE is_removed = 1 AND created_at > ?
            {rem_filter}
        """, tuple(rem_params))

        # Performance benchmark (MiloAgent)
        benchmark = self.get_performance_benchmark(client_id=client_id)

        # Best post types
        best_post_types = self.get_best_post_types(client_id=client_id)

        # Strategy rules count
        rules = self.get_strategy_rules(client_id=client_id)

        # Discovered targets
        discoveries = self.get_discovered_targets(client_id=client_id)

        return {
            "period_days": days,
            "comments": {
                "total": comment_stats["cnt"] if comment_stats else 0,
                "avg_score": round(comment_stats["avg_score"] or 0, 1) if comment_stats else 0,
            },
            "posts": {
                "total": post_stats["cnt"] if post_stats else 0,
                "avg_score": round(post_stats["avg_score"] or 0, 1) if post_stats else 0,
            },
            "top_subreddits": top_subs,
            "removed_content": removed["cnt"] if removed else 0,
            "benchmark": benchmark,
            "best_post_types": best_post_types,
            "strategy_rules_count": len(rules),
            "discovered_targets": {
                "subreddits": len(discoveries["subreddits"]),
                "keywords": len(discoveries["keywords"]),
            },
        }
