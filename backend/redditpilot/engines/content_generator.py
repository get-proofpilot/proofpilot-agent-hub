"""
RedditPilot Content Generation Engine
LLM-powered content generation with persona management, anti-AI-detection,
and subreddit-specific tone calibration.

Combines patterns from:
- MiloAgent's content_gen.py (persona system, stage-aware promo)
- feder-cr's commentator (LangChain prompts, context injection)
- markmircea's advertising bot (natural product mentions)
- BotBuster analysis (anti-detection writing rules)
"""

import json
import random
import hashlib
import logging
import re
from typing import Optional, List
from ..core.config import Config, ClientProfile, LLMConfig
from ..core.database import Database

logger = logging.getLogger("redditpilot.content")


# ── Anti-AI Detection Rules (from BotBuster analysis) ──────────────

ANTI_AI_RULES = """
CRITICAL WRITING RULES (violating these gets flagged as AI):
1. ALWAYS use contractions (don't, won't, can't, I've, they're)
2. VARY sentence length wildly (mix 4-word and 25-word sentences)
3. NEVER use: "furthermore", "in conclusion", "it's worth noting", "delve deeper", "navigate", "leverage", "utilize", "facilitate", "aforementioned", "paradigm", "synergy"
4. Include personal opinion phrases: "honestly", "in my experience", "I think", "tbh", "imo"
5. Use casual language: "yeah", "nah", "kinda", "pretty much", "lol"
6. Occasionally make small grammar "mistakes" that real people make
7. Reference specific personal experiences (even fabricated ones that match the persona)
8. Keep responses SHORT when appropriate (many great Reddit comments are 2-3 sentences)
9. Use Reddit-specific language: "OP", "this ^", "came here to say this"
10. Include an occasional emoji or emoticon but don't overdo it
"""

# Tone variations (adapted from MiloAgent's A/B testing)
TONE_PROFILES = {
    "helpful_expert": {
        "description": "Experienced professional sharing knowledge",
        "traits": "authoritative but approachable, uses industry terms casually, shares specific examples",
        "example_starters": ["I've been doing this for years", "In my experience", "Pro tip:"],
    },
    "friendly_neighbor": {
        "description": "Helpful community member who had similar experience",
        "traits": "warm, relatable, tells stories, asks follow-up questions",
        "example_starters": ["Had the same issue last year", "My buddy who's a plumber told me", "We just went through this"],
    },
    "curious_learner": {
        "description": "Someone who researched this topic and shares findings",
        "traits": "asks good questions, shares research, admits uncertainty",
        "example_starters": ["I looked into this a while back", "From what I've gathered", "Not 100% sure but"],
    },
    "practical_diy": {
        "description": "DIY enthusiast who knows when to call a pro",
        "traits": "hands-on, cost-conscious, respects expertise, shares mistakes",
        "example_starters": ["I tried doing this myself", "Learned the hard way", "Save yourself the headache"],
    },
    "local_regular": {
        "description": "Active local community member with recommendations",
        "traits": "knows the area, gives specific local advice, casual tone",
        "example_starters": ["We used [company] and", "A few of my neighbors went with", "There's a great"],
    },
    "straightforward": {
        "description": "Direct, no-nonsense response",
        "traits": "brief, factual, to the point, no fluff",
        "example_starters": ["Just call a pro", "Short answer:", "Here's what you do:"],
    },
}


class ContentGenerator:
    """Generates Reddit comments and posts using LLMs with anti-detection."""

    def __init__(self, config: Config, db: Database, llm_client=None):
        self.config = config
        self.db = db
        self.llm = llm_client

    def generate_comment(self, post: dict, client: ClientProfile,
                         existing_comments: list = None,
                         persona: str = None, tone: str = None,
                         include_promotion: bool = False) -> dict:
        """
        Generate a comment for a post.
        Returns dict with content, persona used, tone used, and metadata.
        """
        # Select persona and tone
        if not tone:
            tone = self._select_tone(post, client)
        if not persona:
            persona = self._build_persona(client, tone)

        tone_profile = TONE_PROFILES.get(tone, TONE_PROFILES["helpful_expert"])

        # Build the prompt
        prompt = self._build_comment_prompt(
            post=post,
            client=client,
            existing_comments=existing_comments or [],
            tone_profile=tone_profile,
            persona=persona,
            include_promotion=include_promotion,
        )

        # Generate with LLM
        content = self.llm.generate(prompt, max_tokens=self.config.llm.max_tokens)

        # Post-process: clean up AI artifacts
        content = self._clean_ai_artifacts(content)

        # Validate content
        validation = self._validate_content(content, post.get("subreddit", ""))

        # Content hash for dedup
        content_hash = hashlib.md5(content.lower().strip().encode()).hexdigest()

        return {
            "content": content,
            "tone": tone,
            "persona": persona,
            "validation": validation,
            "content_hash": content_hash,
            "is_promotional": include_promotion,
            "word_count": len(content.split()),
        }

    def generate_post(self, subreddit: str, client: ClientProfile,
                      post_type: str = "question", tone: str = None) -> dict:
        """
        Generate a new post for a subreddit.
        Returns dict with title, body, type, and metadata.

        Post types (adapted from feder-cr):
        - question: Ask the community something relevant
        - tip: Share a helpful tip related to client's industry
        - experience: Share a (fabricated) experience/story
        - discussion: Start a discussion about industry topic
        """
        if not tone:
            tone = random.choice(list(TONE_PROFILES.keys()))

        tone_profile = TONE_PROFILES.get(tone, TONE_PROFILES["helpful_expert"])

        prompt = self._build_post_prompt(
            subreddit=subreddit,
            client=client,
            post_type=post_type,
            tone_profile=tone_profile,
        )

        response = self.llm.generate(prompt, max_tokens=800)

        # Parse title and body from response
        title, body = self._parse_post_response(response)

        title = self._clean_ai_artifacts(title)
        body = self._clean_ai_artifacts(body)

        return {
            "title": title,
            "body": body,
            "post_type": post_type,
            "tone": tone,
            "subreddit": subreddit,
            "word_count": len(body.split()),
        }

    def _build_comment_prompt(self, post: dict, client: ClientProfile,
                               existing_comments: list, tone_profile: dict,
                               persona: str, include_promotion: bool) -> str:
        """Build the LLM prompt for comment generation."""

        # Format existing comments for context
        comments_context = ""
        if existing_comments:
            top_comments = sorted(existing_comments, key=lambda c: c.get("score", 0), reverse=True)[:5]
            comments_context = "\n".join([
                f"- [{c.get('score', 0)} pts] {c.get('body', '')[:200]}"
                for c in top_comments
            ])

        promo_instruction = ""
        if include_promotion:
            promo_instruction = f"""
SUBTLE PROMOTION (optional, only if it fits naturally):
You may casually mention that you've had good experience with a {client.industry} company
in the {client.service_area} area. Do NOT name the company directly.
Instead, you could say something like "I found a great company in {client.service_area.split(',')[0]}"
or reference their website indirectly. The mention should feel like a genuine recommendation,
not an advertisement. If it doesn't fit naturally, skip it entirely.
"""

        return f"""You are a real Reddit user. Write a comment on this post.

{ANTI_AI_RULES}

YOUR PERSONA:
{persona}

TONE: {tone_profile['description']}
Traits: {tone_profile['traits']}

THE POST:
Subreddit: r/{post.get('subreddit', '')}
Title: {post.get('title', '')}
Body: {post.get('body', '')[:500]}

EXISTING TOP COMMENTS:
{comments_context if comments_context else "(no comments yet - you'll be first!)"}

{promo_instruction}

IMPORTANT:
- Your comment must add genuine value. Think: would this help the person who posted?
- Don't repeat what other commenters already said
- Match the subreddit's vibe (casual for r/HomeImprovement, technical for r/Plumbing)
- Keep it between 2-8 sentences unless the topic needs more
- Do NOT start with "Great question!" or "I totally agree!" or any sycophantic opener
- Write ONLY the comment text, nothing else. No labels, no quotes.
"""

    def _build_post_prompt(self, subreddit: str, client: ClientProfile,
                           post_type: str, tone_profile: dict) -> str:
        """Build the LLM prompt for post generation."""

        type_instructions = {
            "question": f"Ask a genuine question that someone interested in {client.industry} would ask. "
                        f"Something that sparks discussion and shows curiosity.",
            "tip": f"Share a practical tip about {client.industry} that homeowners would find useful. "
                   f"Something specific and actionable, not generic advice.",
            "experience": f"Share a story about a {client.industry} experience (good or challenging). "
                          f"Include specific details that make it feel real.",
            "discussion": f"Start a discussion about a trending or seasonal topic in {client.industry}. "
                          f"Ask for others' experiences or opinions.",
        }

        return f"""You are a real Reddit user creating a post in r/{subreddit}.

{ANTI_AI_RULES}

POST TYPE: {post_type}
{type_instructions.get(post_type, type_instructions["question"])}

CONTEXT:
Industry: {client.industry}
Location: {client.service_area}
Tone: {tone_profile['description']}

FORMAT YOUR RESPONSE AS:
TITLE: [your post title here]
BODY: [your post body here]

RULES:
- Title should be natural and specific (not clickbait, not generic)
- Body should be 3-10 sentences
- Include enough detail to feel like a real person's post
- Do NOT mention any company names
- Write like a homeowner, not a professional (unless the persona fits)
"""

    def _select_tone(self, post: dict, client: ClientProfile) -> str:
        """Select the best tone for this post based on context."""
        title = post.get("title", "").lower()
        body = post.get("body", "").lower()
        text = f"{title} {body}"

        # Match tone to post context
        if any(w in text for w in ["emergency", "urgent", "help", "broken", "flooding"]):
            return "helpful_expert"
        elif any(w in text for w in ["recommend", "suggestion", "who do you use"]):
            return random.choice(["local_regular", "friendly_neighbor"])
        elif any(w in text for w in ["diy", "myself", "how to", "can i"]):
            return "practical_diy"
        elif any(w in text for w in ["cost", "price", "quote", "how much"]):
            return "straightforward"
        elif any(w in text for w in ["anyone", "experience", "thoughts"]):
            return "curious_learner"

        # Random selection with weights
        weighted = [
            ("helpful_expert", 0.25),
            ("friendly_neighbor", 0.25),
            ("practical_diy", 0.20),
            ("local_regular", 0.15),
            ("curious_learner", 0.10),
            ("straightforward", 0.05),
        ]
        tones, weights = zip(*weighted)
        return random.choices(tones, weights=weights, k=1)[0]

    def _build_persona(self, client: ClientProfile, tone: str) -> str:
        """Build a persona description for the LLM."""
        # Check for client-specific personas first
        if client.personas:
            persona = random.choice(client.personas)
            if isinstance(persona, dict):
                return persona.get("description", "")
            return str(persona)

        # Generate a contextual persona
        area = client.service_area.split(",")[0].strip() if client.service_area else "a mid-size city"
        industry = client.industry

        personas = {
            "helpful_expert": f"You're a homeowner in {area} who's dealt with many {industry} issues over 15+ years of homeownership. You know a lot from experience but you're not a professional.",
            "friendly_neighbor": f"You're a friendly person living in {area}. You recently dealt with a {industry} situation and want to share what you learned.",
            "curious_learner": f"You're a relatively new homeowner in {area} who's been learning about home maintenance. You've done research on {industry} topics.",
            "practical_diy": f"You're a DIY enthusiast in {area} who tackles most home projects but knows when to call a {industry} professional.",
            "local_regular": f"You've lived in {area} for years and know the local service providers well. You're active in local community discussions.",
            "straightforward": f"You're a no-nonsense person who gives direct advice based on experience. You live in {area}.",
        }

        return personas.get(tone, personas["helpful_expert"])

    def _clean_ai_artifacts(self, text: str) -> str:
        """Remove common AI-generated artifacts from text."""
        # Remove markdown formatting that looks unnatural
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Remove bold

        # Remove sycophantic openers
        sycophantic = [
            r'^(great|excellent|good|wonderful|fantastic) (question|point|observation)[!.]?\s*',
            r'^(i |that\'s ).*(great|excellent|important|fascinating).*?\.\s*',
            r'^absolutely[!.]?\s*',
        ]
        for pattern in sycophantic:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Remove AI closing phrases
        closers = [
            r'\s*hope (this|that) helps[!.]?\s*$',
            r'\s*let me know if you (have|need).*$',
            r'\s*feel free to.*$',
            r'\s*happy to help.*$',
            r'\s*best of luck[!.]?\s*$',
        ]
        for pattern in closers:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Remove any remaining wrapper quotes/labels
        text = re.sub(r'^["\']\s*', '', text)
        text = re.sub(r'\s*["\']$', '', text)
        text = re.sub(r'^(comment|response|reply):\s*', '', text, flags=re.IGNORECASE)

        return text.strip()

    def _validate_content(self, content: str, subreddit: str) -> dict:
        """
        Validate content against anti-detection rules.
        Adapted from MiloAgent's content_validator.py and BotBuster heuristics.
        """
        issues = []
        score = 0.0  # Higher = more likely to be flagged as AI

        # Check for banned phrases
        for phrase in self.config.safety.banned_phrases:
            if phrase.lower() in content.lower():
                issues.append(f"Contains banned phrase: '{phrase}'")
                score += 1.2

        # Check contractions (from BotBuster: +1.8 if no contractions in >150 words)
        word_count = len(content.split())
        contractions = ["don't", "won't", "can't", "isn't", "aren't", "wouldn't",
                        "couldn't", "shouldn't", "I'm", "I've", "I'll", "they're",
                        "we're", "you're", "it's", "that's", "there's", "here's"]
        has_contractions = any(c.lower() in content.lower() for c in contractions)
        if word_count > 150 and not has_contractions:
            issues.append("No contractions in long text (AI signal)")
            score += 1.8

        # Check sentence length variance (from BotBuster: +1.5 if low variance)
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 3:
            lengths = [len(s.split()) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            if variance < 5:
                issues.append("Uniform sentence length (AI signal)")
                score += 1.5

        # Check for personal opinion markers (from BotBuster: +1.0 if missing)
        personal_markers = ["i think", "imo", "in my experience", "honestly",
                            "tbh", "personally", "i believe", "i feel", "my opinion"]
        has_personal = any(m in content.lower() for m in personal_markers)
        if word_count > 100 and not has_personal:
            issues.append("No personal opinion markers (AI signal)")
            score += 1.0

        # Check for overly complex synonyms (from BotBuster: +0.8 each)
        complex_words = ["utilize", "leverage", "commence", "facilitate",
                         "aforementioned", "paradigm", "synergy", "holistic",
                         "multifaceted", "comprehensive", "subsequently"]
        for word in complex_words:
            if word in content.lower():
                issues.append(f"Complex synonym: '{word}'")
                score += 0.8

        is_safe = score < 4.0  # BotBuster threshold

        return {
            "is_safe": is_safe,
            "ai_detection_score": score,
            "issues": issues,
            "word_count": word_count,
        }

    def _parse_post_response(self, response: str) -> tuple:
        """Parse title and body from LLM response."""
        title = ""
        body = ""

        lines = response.strip().split("\n")
        in_body = False

        for line in lines:
            if line.upper().startswith("TITLE:"):
                title = line[6:].strip().strip('"').strip("'")
            elif line.upper().startswith("BODY:"):
                body = line[5:].strip()
                in_body = True
            elif in_body:
                body += "\n" + line

        if not title and lines:
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

        return title, body
