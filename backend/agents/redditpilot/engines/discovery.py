"""
RedditPilot Subreddit Discovery Engine
Finds relevant subreddits for each client using keyword search + AI verification.
Adapted from tonisives/subreddit-discovery and MiloAgent's scanning.
"""

import logging
import json
from typing import List, Optional
from ..core.config import ClientProfile, Config
from ..core.database import Database
from ..core.reddit_client import RedditClient

logger = logging.getLogger("redditpilot.discovery")

# Business-focused discovery queries (adapted from tonisives)
DISCOVERY_QUERIES = {
    "home_services": [
        "plumber recommendation", "hvac contractor", "electrician near me",
        "home repair help", "best plumbing company", "ac not working",
        "water heater replacement", "electrical panel upgrade",
        "drain cleaning", "furnace repair", "home renovation contractor",
        "bathroom remodel", "kitchen plumbing", "emergency plumber",
        "hvac maintenance tips", "electrical wiring help",
    ],
    "general_business": [
        "small business recommendation", "local service provider",
        "contractor recommendation", "home improvement advice",
        "who should I hire for", "looking for a good",
        "anyone used", "experience with", "reviews for",
    ],
    "local": [
        "recommendations", "who do you use for",
        "best in the area", "local business", "service provider",
    ],
}

# Subreddits to always consider for home services
SEED_SUBREDDITS = [
    "HomeImprovement", "Plumbing", "HVAC", "electricians",
    "HomeRepair", "DIY", "Renovations", "RealEstate",
    "smallbusiness", "homeowners", "AskAnElectrician",
]


class DiscoveryEngine:
    """Discovers and ranks relevant subreddits for clients."""

    def __init__(self, config: Config, db: Database, llm_client=None):
        self.config = config
        self.db = db
        self.llm = llm_client

    def discover_subreddits_for_client(self, client: ClientProfile,
                                        reddit: RedditClient) -> List[dict]:
        """
        Full discovery pipeline for a client.
        Returns list of discovered subreddits with relevance scores.
        """
        logger.info(f"Starting subreddit discovery for client: {client.name}")
        discovered = {}

        # Step 1: Seed subreddits (always include these)
        for sub_name in SEED_SUBREDDITS:
            info = reddit.get_subreddit_info(sub_name)
            if info and not info.get("over18"):
                discovered[sub_name] = {
                    "name": sub_name,
                    "subscribers": info.get("subscribers", 0),
                    "description": info.get("description", ""),
                    "source": "seed",
                    "relevance_score": 0.7,
                }

        # Step 2: Search by client industry keywords
        industry_queries = DISCOVERY_QUERIES.get(
            "home_services" if client.industry in ["plumbing", "hvac", "electrical", "home_services"]
            else "general_business",
            DISCOVERY_QUERIES["general_business"]
        )

        for query in industry_queries:
            results = reddit.search_subreddits(f"{query} {client.industry}", limit=10)
            for sub in results:
                name = sub["name"]
                if name not in discovered and not sub.get("over18"):
                    discovered[name] = {
                        "name": name,
                        "subscribers": sub.get("subscribers", 0),
                        "description": sub.get("description", ""),
                        "source": "keyword_search",
                        "relevance_score": 0.0,
                        "matched_query": query,
                    }

        # Step 3: Search by client-specific keywords
        for keyword in client.keywords:
            results = reddit.search_subreddits(keyword, limit=10)
            for sub in results:
                name = sub["name"]
                if name not in discovered and not sub.get("over18"):
                    discovered[name] = {
                        "name": name,
                        "subscribers": sub.get("subscribers", 0),
                        "description": sub.get("description", ""),
                        "source": "client_keyword",
                        "relevance_score": 0.0,
                        "matched_keyword": keyword,
                    }

        # Step 4: Local subreddits (city/metro based)
        if client.service_area:
            city = client.service_area.split(",")[0].strip()
            local_searches = [city, f"Ask{city}", f"{city}area", f"{city}metro"]
            for search in local_searches:
                results = reddit.search_subreddits(search, limit=5)
                for sub in results:
                    name = sub["name"]
                    if name not in discovered and not sub.get("over18"):
                        discovered[name] = {
                            "name": name,
                            "subscribers": sub.get("subscribers", 0),
                            "description": sub.get("description", ""),
                            "source": "local",
                            "relevance_score": 0.6,
                        }

        # Step 5: Score and rank with AI (if available)
        subreddit_list = list(discovered.values())
        if self.llm:
            subreddit_list = self._ai_score_subreddits(subreddit_list, client)
        else:
            subreddit_list = self._heuristic_score(subreddit_list, client)

        # Step 6: Save to database
        for sub in subreddit_list:
            sub_id = self.db.upsert_subreddit(
                name=sub["name"],
                subscribers=sub.get("subscribers", 0),
                description=sub.get("description", ""),
                relevance_score=sub.get("relevance_score", 0),
                tier=self._score_to_tier(sub.get("relevance_score", 0)),
                category=sub.get("category", "general"),
            )
            # Link to client
            client_row = self.db.fetchone("SELECT id FROM clients WHERE slug = ?", (client.slug,))
            if client_row:
                self.db.execute("""
                    INSERT OR REPLACE INTO client_subreddits (client_id, subreddit_id, relevance_score)
                    VALUES (?, ?, ?)
                """, (client_row["id"], sub_id, sub.get("relevance_score", 0)))
                self.db.commit()

        # Sort by relevance
        subreddit_list.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        logger.info(f"Discovered {len(subreddit_list)} subreddits for {client.name}")
        return subreddit_list

    def _ai_score_subreddits(self, subreddits: list, client: ClientProfile) -> list:
        """Score subreddits using LLM for relevance verification."""
        prompt = f"""You are evaluating subreddits for a {client.industry} company in {client.service_area}.
Company: {client.name}
Website: {client.website}
Keywords: {', '.join(client.keywords[:10])}

Score each subreddit from 0.0 to 1.0 for relevance to this business.
Consider: Would this business's expertise be welcomed? Are there potential customers here?
Would helpful comments about {client.industry} topics be natural?

Subreddits to evaluate:
{json.dumps([{"name": s["name"], "subscribers": s["subscribers"], "description": s["description"][:100]} for s in subreddits[:30]], indent=2)}

Respond with JSON array: [{{"name": "SubName", "score": 0.85, "category": "industry|local|general|tangential", "reason": "brief reason"}}]
Only output the JSON array, nothing else."""

        try:
            response = self.llm.generate(prompt, max_tokens=2000)
            scores = json.loads(response)
            score_map = {s["name"]: s for s in scores}

            for sub in subreddits:
                if sub["name"] in score_map:
                    ai_score = score_map[sub["name"]]
                    sub["relevance_score"] = ai_score.get("score", 0)
                    sub["category"] = ai_score.get("category", "general")
                    sub["ai_reason"] = ai_score.get("reason", "")
        except Exception as e:
            logger.error(f"AI scoring failed, falling back to heuristics: {e}")
            subreddits = self._heuristic_score(subreddits, client)

        return subreddits

    def _heuristic_score(self, subreddits: list, client: ClientProfile) -> list:
        """Fallback: score subreddits using keyword matching heuristics."""
        keywords = set(w.lower() for w in client.keywords)
        industry_terms = set(client.industry.lower().split())

        for sub in subreddits:
            score = sub.get("relevance_score", 0)
            desc_lower = (sub.get("description", "") + " " + sub.get("name", "")).lower()

            # Keyword matches
            matches = sum(1 for k in keywords if k in desc_lower)
            score += min(matches * 0.15, 0.45)

            # Industry match
            if any(t in desc_lower for t in industry_terms):
                score += 0.3

            # Subscriber count (prefer medium-sized communities)
            subs = sub.get("subscribers", 0)
            if 1000 <= subs <= 100000:
                score += 0.1
            elif 100000 <= subs <= 1000000:
                score += 0.05

            # Source bonus
            if sub.get("source") == "seed":
                score += 0.1
            elif sub.get("source") == "local":
                score += 0.15

            sub["relevance_score"] = min(score, 1.0)

        return subreddits

    @staticmethod
    def _score_to_tier(score: float) -> int:
        """Convert relevance score to tier (1=best, 4=lowest)."""
        if score >= 0.75:
            return 1
        elif score >= 0.5:
            return 2
        elif score >= 0.25:
            return 3
        return 4
