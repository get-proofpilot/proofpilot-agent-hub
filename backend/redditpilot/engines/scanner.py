"""
RedditPilot Opportunity Scanner
Finds relevant posts to engage with across target subreddits.
Adapted from MiloAgent's strategy.py scoring and feder-cr's post filtering.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional
from ..core.config import ClientProfile, Config
from ..core.database import Database
from ..core.reddit_client import RedditClient

logger = logging.getLogger("redditpilot.scanner")


class OpportunityScorer:
    """Multi-signal scoring for post opportunities."""

    # Intent signals that indicate high-value opportunities
    INTENT_SIGNALS = {
        "direct_ask": [
            r"\bwho do you (use|recommend|suggest)\b",
            r"\blooking for (a |an )?(good |reliable )?(plumber|electrician|hvac|contractor)\b",
            r"\bneed (a |an )?(plumber|electrician|hvac|contractor)\b",
            r"\bany (recommendations?|suggestions?)\b.*(plumber|electrician|hvac|contractor|service)",
            r"\bbest (plumber|electrician|hvac|contractor)\b",
            r"\bcan anyone recommend\b",
        ],
        "problem_post": [
            r"\b(my |our )?(ac|air conditioner|furnace|heater|water heater)\b.*(broken|not working|stopped|leaking)",
            r"\b(toilet|sink|drain|pipe|faucet)\b.*(clog|leak|broken|drip|burst)",
            r"\b(outlet|switch|circuit|breaker|wiring)\b.*(not working|sparking|tripping|hot)",
            r"\bno (hot water|heat|ac|cooling|power)\b",
            r"\b(water|gas) leak\b",
            r"\bemergency (plumb|electric|hvac)\b",
        ],
        "diy_question": [
            r"\bshould i (call|hire|get) a (pro|professional|plumber|electrician)\b",
            r"\bdiy or (hire|call|professional)\b",
            r"\bcan i (do|fix|replace|install) (this|it) myself\b",
            r"\bhow (much|hard|difficult|long)\b.*(to |would it )?(fix|replace|install|repair)",
            r"\bis (this|it) (safe|normal|ok|okay) to\b",
        ],
        "cost_question": [
            r"\bhow much (does|should|would|will)\b.*(cost|charge|pay|spend)\b",
            r"\b(fair|reasonable|average|typical) (price|cost|rate|quote)\b",
            r"\bgetting (quoted|charged|billed)\b",
            r"\bis \$?\d+.*(fair|reasonable|too much|overpriced)\b",
        ],
    }

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        # Pre-compile regex patterns
        self._compiled_patterns = {}
        for category, patterns in self.INTENT_SIGNALS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def score_post(self, post: dict, client: ClientProfile) -> dict:
        """
        Score a post across multiple dimensions.
        Returns scores dict with individual and composite scores.
        """
        text = f"{post.get('title', '')} {post.get('body', '')}"

        scores = {
            "relevance": self._score_relevance(text, client),
            "intent": self._score_intent(text),
            "engagement": self._score_engagement(post),
            "freshness": self._score_freshness(post),
            "competition": self._score_competition(post),
            "seo_value": self._score_seo_value(post),
        }

        # Weighted composite score (adapted from MiloAgent)
        weights = {
            "relevance": 0.30,
            "intent": 0.25,
            "engagement": 0.15,
            "freshness": 0.10,
            "competition": 0.10,
            "seo_value": 0.10,
        }

        # Check for learned weight adjustments
        learned = self.db.get_strategies("scoring_weight", client_id=None)
        for strategy in learned:
            if strategy["key"] in weights:
                weights[strategy["key"]] = strategy["value"]

        scores["composite"] = sum(
            scores[dim] * weights.get(dim, 0.1)
            for dim in scores
        )

        # Matched intent categories
        scores["matched_intents"] = self._get_matched_intents(text)
        scores["matched_keywords"] = self._get_matched_keywords(text, client)

        return scores

    def _score_relevance(self, text: str, client: ClientProfile) -> float:
        """How relevant is this post to the client's business?"""
        text_lower = text.lower()
        score = 0.0

        # Keyword matches
        for keyword in client.keywords:
            if keyword.lower() in text_lower:
                score += 0.2

        # Industry terms
        industry_terms = {
            "plumbing": ["plumb", "pipe", "drain", "faucet", "toilet", "water heater", "sewer", "leak"],
            "hvac": ["hvac", "air condition", "furnace", "heat pump", "thermostat", "duct", "ac ", "a/c"],
            "electrical": ["electric", "wiring", "outlet", "circuit", "breaker", "panel", "switch", "volt"],
        }
        terms = industry_terms.get(client.industry, [])
        matches = sum(1 for t in terms if t in text_lower)
        score += min(matches * 0.15, 0.5)

        # Service area mention
        if client.service_area:
            city = client.service_area.split(",")[0].strip().lower()
            if city in text_lower:
                score += 0.3

        return min(score, 1.0)

    def _score_intent(self, text: str) -> float:
        """How strong is the purchase/service intent?"""
        score = 0.0
        intent_weights = {
            "direct_ask": 1.0,
            "problem_post": 0.8,
            "cost_question": 0.7,
            "diy_question": 0.6,
        }

        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    weight = intent_weights.get(category, 0.5)
                    score = max(score, weight)
                    break  # One match per category is enough

        return score

    def _score_engagement(self, post: dict) -> float:
        """Engagement potential based on post metrics."""
        score = post.get("score", 0)
        comments = post.get("num_comments", 0)
        ratio = post.get("upvote_ratio", 0.5)

        # Sweet spot: enough engagement to be seen, not so much that we're buried
        eng_score = 0.0

        if 5 <= score <= 100:
            eng_score += 0.4
        elif 100 < score <= 500:
            eng_score += 0.3
        elif score > 500:
            eng_score += 0.1  # Too popular, we'll be buried

        if 3 <= comments <= 30:
            eng_score += 0.3  # Active but not overcrowded
        elif comments < 3:
            eng_score += 0.2  # Early entry
        elif comments > 100:
            eng_score += 0.05  # Too late

        if ratio >= 0.85:
            eng_score += 0.15  # Well-received post

        return min(eng_score, 1.0)

    def _score_freshness(self, post: dict) -> float:
        """Recency decay - fresher posts score higher."""
        created_utc = post.get("created_utc", 0)
        if not created_utc:
            return 0.3

        age_hours = (datetime.utcnow() - datetime.utcfromtimestamp(created_utc)).total_seconds() / 3600

        if age_hours < 2:
            return 1.0
        elif age_hours < 6:
            return 0.8
        elif age_hours < 12:
            return 0.6
        elif age_hours < 24:
            return 0.4
        elif age_hours < 48:
            return 0.2
        return 0.05

    def _score_competition(self, post: dict) -> float:
        """Lower competition = higher score."""
        comments = post.get("num_comments", 0)
        if comments == 0:
            return 0.9  # First responder advantage
        elif comments < 5:
            return 0.7
        elif comments < 15:
            return 0.5
        elif comments < 50:
            return 0.3
        return 0.1

    def _score_seo_value(self, post: dict) -> float:
        """Estimate SEO/AI citation potential."""
        score = 0.0
        title = post.get("title", "").lower()

        # "Best X" and recommendation posts rank well in Google
        seo_patterns = [
            r"\bbest\b", r"\brecommend", r"\btop \d",
            r"\bvs\.?\b", r"\bcompare\b", r"\breview",
            r"\bwhat .* (use|recommend|suggest)\b",
        ]
        for pattern in seo_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                score += 0.2

        # Higher upvotes = more likely to rank
        post_score = post.get("score", 0)
        if post_score > 50:
            score += 0.2
        if post_score > 200:
            score += 0.1

        # Posts with many comments tend to rank
        if post.get("num_comments", 0) > 10:
            score += 0.1

        return min(score, 1.0)

    def _get_matched_intents(self, text: str) -> list:
        matched = []
        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    matched.append(category)
                    break
        return matched

    def _get_matched_keywords(self, text: str, client: ClientProfile) -> list:
        text_lower = text.lower()
        return [k for k in client.keywords if k.lower() in text_lower]


class OpportunityScanner:
    """Scans subreddits for engagement opportunities."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.scorer = OpportunityScorer(config, db)

    def scan_for_client(self, client: ClientProfile, reddit: RedditClient,
                         limit_per_sub: int = 25) -> List[dict]:
        """
        Scan all target subreddits for opportunities.
        Returns scored and ranked list of opportunities.
        """
        logger.info(f"Scanning opportunities for client: {client.name}")
        opportunities = []

        # Get client's target subreddits
        subreddits = client.target_subreddits or []

        # Also pull from database
        client_row = self.db.fetchone("SELECT id FROM clients WHERE slug = ?", (client.slug,))
        if client_row:
            db_subs = self.db.fetchall("""
                SELECT s.name FROM subreddits s
                JOIN client_subreddits cs ON s.id = cs.subreddit_id
                WHERE cs.client_id = ? AND s.enabled = 1
                ORDER BY cs.relevance_score DESC
                LIMIT 20
            """, (client_row["id"],))
            subreddits.extend([s["name"] for s in db_subs])

        # Deduplicate
        subreddits = list(set(subreddits))

        if not subreddits:
            logger.warning(f"No target subreddits for {client.name}")
            return []

        for sub_name in subreddits:
            try:
                # Get hot and new posts
                hot_posts = reddit.get_hot_posts(sub_name, limit=limit_per_sub)
                new_posts = reddit.get_new_posts(sub_name, limit=limit_per_sub)

                # Combine and deduplicate
                seen_ids = set()
                all_posts = []
                for post in hot_posts + new_posts:
                    if post["id"] not in seen_ids:
                        seen_ids.add(post["id"])
                        all_posts.append(post)

                # Score each post
                for post in all_posts:
                    # Skip locked, NSFW, or deleted posts
                    if post.get("locked") or post.get("over_18"):
                        continue
                    if post.get("author") == "[deleted]":
                        continue

                    # Skip if we've already processed this post
                    existing = self.db.fetchone(
                        "SELECT id FROM discovered_posts WHERE reddit_id = ?",
                        (post["id"],)
                    )
                    if existing:
                        continue

                    # Score the opportunity
                    scores = self.scorer.score_post(post, client)

                    # Only keep posts above threshold
                    if scores["composite"] < 0.25:
                        continue

                    opportunity = {
                        **post,
                        "scores": scores,
                        "client_slug": client.slug,
                        "client_id": client_row["id"] if client_row else None,
                    }
                    opportunities.append(opportunity)

                    # Save to database
                    self.db.save_discovered_post(
                        reddit_id=post["id"],
                        subreddit=post["subreddit"],
                        title=post["title"],
                        body=post.get("body", ""),
                        author=post.get("author", ""),
                        url=post.get("permalink", ""),
                        score=post.get("score", 0),
                        num_comments=post.get("num_comments", 0),
                        created_utc=post.get("created_utc", 0),
                        relevance_score=scores["relevance"],
                        engagement_score=scores["engagement"],
                        opportunity_score=scores["composite"],
                        seo_value_score=scores["seo_value"],
                    )

                logger.info(f"r/{sub_name}: found {len([o for o in opportunities if o.get('subreddit') == sub_name])} opportunities")

            except Exception as e:
                logger.error(f"Error scanning r/{sub_name}: {e}")
                continue

        # Sort by composite score
        opportunities.sort(key=lambda x: x["scores"]["composite"], reverse=True)

        logger.info(f"Total opportunities for {client.name}: {len(opportunities)}")
        return opportunities
