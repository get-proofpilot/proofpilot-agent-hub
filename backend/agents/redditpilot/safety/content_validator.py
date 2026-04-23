"""
RedditPilot Content Validator (merged)
Pre-posting safety checks: anti-AI detection, spam filter, Reddit rules compliance,
business-profile fact-checking, organic-mode enforcement, and quality scoring.

Combines:
  - RedditPilot's BotBuster heuristics & subreddit-specific rules
  - MiloAgent's 50+ pre-compiled regex patterns, business-profile validation,
    pricing-claim verification, organic-mode enforcement, and RSS/feed spam detection
"""

import re
import hashlib
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from ..core.config import Config
from ..core.database import Database

logger = logging.getLogger("redditpilot.validator")


# ──────────────────────────────────────────────────────────────────────────────
# ValidationResult dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Unified validation result returned by all validate_*() methods."""
    is_valid: bool = True
    score: float = 1.0           # Quality score 0.0-1.0  (higher = better)
    issues: List[str] = field(default_factory=list)
    ai_score: float = 0.0       # BotBuster AI score 0-10+ (higher = more bot-like)
    blocked_by: Optional[str] = None  # First hard-block reason, if any

    # Backward-compat aliases so existing code using dict access still works
    # e.g.  validation["passed"], validation["issues"], validation["warnings"]
    def __getitem__(self, key):
        _map = {
            "passed": self.is_valid,
            "is_valid": self.is_valid,
            "score": self.score,
            "issues": self.issues,
            "warnings": [i for i in self.issues if "CRITICAL" not in i],
            "ai_score": self.ai_score,
            "blocked_by": self.blocked_by,
            "word_count": None,        # filled dynamically below
            "content_hash": None,
        }
        if key in _map:
            return _map[key]
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


# ──────────────────────────────────────────────────────────────────────────────
# Module-level pre-compiled regex patterns (compiled once at import time)
# ──────────────────────────────────────────────────────────────────────────────

# --- RP's original string-based bot patterns (kept for ai_score matching) ---
_RP_BOT_PATTERN_STRINGS = [
    # Promotional patterns
    r"(?:check out|visit|go to)\s+(?:my|our)\s+(?:website|site|page|blog|channel)",
    r"(?:use|try)\s+(?:my|our)\s+(?:product|service|tool|app|platform)",
    r"(?:sign up|subscribe|register)\s+(?:for|to|at)\s+(?:my|our)",
    r"(?:discount|promo|coupon)\s+code",
    r"(?:click|tap)\s+(?:here|the link|below)",
    r"limited\s+time\s+(?:offer|deal)",
    r"act\s+(?:now|fast|quick)",
    # AI giveaway patterns
    r"as an ai",
    r"i (?:don't|cannot) have (?:personal )?(?:experience|opinions)",
    r"i'm (?:just )?(?:a |an )?(?:language model|ai|bot|assistant)",
    r"(?:my |)(?:training|knowledge) (?:data |)(?:cutoff|only goes)",
    # Over-structured patterns
    r"^\d+\.\s.*\n\d+\.\s.*\n\d+\.\s",  # Numbered lists (3+)
    r"^[-*]\s.*\n[-*]\s.*\n[-*]\s.*\n[-*]\s",  # Bullet lists (4+)
    # Formulaic openings
    r"^(?:hello|greetings)[!,]?\s*(?:thank|thanks)",
    r"^i (?:completely |totally |fully )?(?:understand|appreciate) (?:your|the)",
]

# Pre-compiled versions of RP's patterns
COMPILED_RP_BOT_PATTERNS = [
    re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _RP_BOT_PATTERN_STRINGS
]

# Keep the old names as public aliases for any external callers
BOT_PATTERNS = _RP_BOT_PATTERN_STRINGS
COMPILED_BOT_PATTERNS = COMPILED_RP_BOT_PATTERNS

# --- MiloAgent's extended (compiled_regex, description) tuple patterns ---
MILO_BOT_PATTERNS: List[tuple] = [
    # ── Generic openers (instant bot tell) ──
    (re.compile(r"^(Great question|I totally agree|This is amazing|This!)"), "generic opener"),
    (re.compile(r"^(Hey there|Hi there|Hello there|Hey!)"), "bot-like greeting"),
    (re.compile(r"^(Absolutely|Definitely|Totally|Certainly|Exactly)[,!]"), "LLM cliche opener"),
    (re.compile(r"^(This resonates|This hits|This is so relatable|Love this)"), "sycophantic opener"),
    (re.compile(r"^(Well,|So,|Honestly,|Actually,|In my experience,)\s"), "formulaic opener"),
    (re.compile(r"^(As someone who|Speaking as a|Coming from a)"), "role-declaration opener"),
    # ── AI self-reference ──
    (re.compile(r"(As an AI|I'm an AI|As a language model)"), "AI self-reference"),
    # ── Formatting tells ──
    (re.compile(r"(!!+)"), "excessive exclamation"),
    (re.compile(r"(#\w+\s*){2,}"), "hashtags"),
    (re.compile(r"\*\*.+?\*\*.*\*\*.+?\*\*"), "too much bold formatting"),
    (re.compile(r"(?:^[-•] .+\n?){3,}", re.MULTILINE), "excessive bullet list"),
    (re.compile(r"(?:^\d+[.)]\s.+\n?){3,}", re.MULTILINE), "numbered list"),
    # ── LLM structural tells ──
    (re.compile(r"(?i)in\s+(?:conclusion|summary|short)[,:]"), "essay conclusion"),
    (re.compile(r"(?i)let me\s+(?:break this down|explain|elaborate|walk you)"), "LLM explanation"),
    (re.compile(r"(?i)here'?s\s+(?:the thing|what I think|my take|the deal)[,:]"), "formulaic transition"),
    (re.compile(r"(?i)(?:that being said|with that said|having said that|not to mention)"), "transition cliche"),
    (re.compile(r"(?i)(?:on top of that|to add to this|building on this|to piggyback)"), "stacking transition"),
    # ── Corporate / marketing language ──
    (re.compile(r"(?i)\b(?:leverage|utilize|streamline|optimize|maximize)\s+(?:your|the|this)\b"), "corporate language"),
    (re.compile(r"(?i)\bgame[- ]?changer\b"), "marketing cliche"),
    (re.compile(r"(?i)\b(?:next level|level up|up your game|take it to)\b"), "hype phrase"),
    (re.compile(r"(?i)\b(?:don'?t sleep on|hidden gem|you won'?t regret|must[- ]have)\b"), "promotional cliche"),
    (re.compile(r"(?i)\b(?:robust|seamless|comprehensive|cutting[- ]edge|innovative)\b"), "corporate adjective"),
    (re.compile(r"(?i)\b(?:landscape|paradigm|synergy|ecosystem|holistic)\b"), "corporate noun"),
    # ── AI hedging / service phrases ──
    (re.compile(r"(?i)\bit(?:'?s| is) worth (?:noting|mentioning|pointing out)\b"), "AI hedging phrase"),
    (re.compile(r"(?i)\b(?:I'?d be happy to|feel free to|don't hesitate to)\b"), "AI service phrase"),
    (re.compile(r"(?i)\b(?:it'?s important to (?:note|remember|understand))\b"), "AI didactic phrase"),
    (re.compile(r"(?i)\b(?:I would (?:recommend|suggest|argue|say) that)\b"), "AI hedging recommendation"),
    # ── Bot-like closers ──
    (re.compile(r"(?i)(?:Hope this helps|Happy to help|Good luck|You'?ve got this)[!.]?\s*$"), "bot-like closer"),
    (re.compile(r"(?i)(?:Let me know if|Feel free to ask|Happy coding|Cheers!)\s*$"), "bot-like closer"),
    (re.compile(r"(?i)(?:Best of luck|Wishing you|All the best)[!.]?\s*$"), "bot-like closer"),
    # ── Unnatural superlatives ──
    (re.compile(r"(?i)\b(?:incredibly|remarkably|phenomenally|extraordinarily|insanely)\s+(?:useful|helpful|powerful|important|good)\b"), "unnatural superlative"),
    # ── AI empathy / validation ──
    (re.compile(r"(?i)^(?:I completely understand|I hear you|That's a great point|I can relate)"), "AI empathy opener"),
    (re.compile(r"(?i)^(?:What a great|Such a great|Really great)\s+(?:question|post|point|topic)"), "AI validation opener"),
    # ── AI favorite words ──
    (re.compile(r"(?i)\bdelve\s+(?:into|deeper)\b"), "LLM favorite word 'delve'"),
    (re.compile(r"(?i)\b(?:straightforward|arguably|nuanced|multifaceted)\b"), "LLM favorite word"),
    (re.compile(r"(?i)\b(?:a plethora of|a myriad of|a wealth of)\b"), "LLM quantity phrase"),
    # ── Repetitive sentence starts ──
    (re.compile(r"(?:^|\n)(I [a-z]+[^.!?]*[.!?]\s*I [a-z]+[^.!?]*[.!?]\s*I [a-z]+)"), "3+ sentences starting with I"),
    # ── LLM structural fingerprints ──
    (re.compile(r"(?i)the part about\b"), "LLM template phrase 'the part about'"),
    (re.compile(r"(?i)\bpersonally,?\s+I\b"), "LLM 'personally I' pattern"),
    (re.compile(r"(?i)\b(?:it'?s|this is) (?:kinda|pretty) (?:intriguing|interesting|fascinating)\b"), "forced casual pattern"),
    (re.compile(r"(?i)\bagentic breakthroughs?\b"), "leaked research context"),
    (re.compile(r"(?i)\bOpenClaw\b"), "leaked research context"),
    (re.compile(r"(?i)(?:^|\. )(?:nah|tbh|kinda|imo|fwiw)[,.]?\s+(?:nah|tbh|kinda|imo|fwiw)\b"), "forced slang stacking"),
]

# Pre-compiled URL shortener detection
_URL_SHORTENER_RE = re.compile(
    r"https?://(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|is\.gd|buff\.ly|adf\.ly|shorte\.st)/\S*",
    re.IGNORECASE,
)

# Pre-compiled URL finder
_URL_FINDER_RE = re.compile(r"https?://[^\s\)\]>\"']+")

# Pre-compiled price pattern
_PRICE_RE = re.compile(r"\$\d+(?:\.\d{2})?")

# RSS/feed spam phrases (lower-cased for quick `in` check)
_RSS_SPAM_PHRASES = [
    "found this earlier", "came across this", "saw this and thought",
    "stumbled upon this", "check this out:", "interesting read:",
    "news.google.com", "rss/articles/",
]

# Domains allowed in organic (non-promotional) comments
SAFE_DOMAINS = {
    "reddit.com", "wikipedia.org", "en.wikipedia.org",
    "stackoverflow.com", "github.com", "youtube.com",
    "docs.google.com", "imgur.com", "i.imgur.com",
    "arxiv.org", "bbc.com", "nytimes.com",
}

# ──────────────────────────────────────────────────────────────────────────────
# Subreddit-specific restrictions (RP original)
# ──────────────────────────────────────────────────────────────────────────────

SUBREDDIT_RESTRICTIONS = {
    "HomeImprovement": {
        "max_links": 1,
        "min_words": 10,
        "no_solicitation": True,
    },
    "Plumbing": {
        "max_links": 1,
        "min_words": 5,
        "requires_flair": False,
    },
    "electricians": {
        "max_links": 0,
        "min_words": 5,
        "trade_only_flairs": True,
    },
}

# Pre-compiled solicitation patterns (used inside _check_subreddit_rules)
_SOLICITATION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(?:call|contact|reach out to)\s+(?:us|me|our)",
        r"(?:we|i)\s+(?:offer|provide|specialize)",
        r"(?:our|my)\s+(?:company|business|service|team)",
        r"(?:free|no.?cost)\s+(?:estimate|quote|consultation)",
    ]
]


# ──────────────────────────────────────────────────────────────────────────────
# ContentValidator
# ──────────────────────────────────────────────────────────────────────────────

class ContentValidator:
    """Validates content before posting to Reddit.

    Merges RedditPilot's BotBuster heuristics with MiloAgent's business-profile
    fact-checking, organic-mode enforcement, and quality scoring.
    """

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def validate_comment(
        self,
        content: str,
        subreddit: str,
        post_context: Optional[dict] = None,
        project: Optional[Dict] = None,
        is_promotional: Optional[bool] = None,
    ) -> ValidationResult:
        """Full validation pipeline for a comment.

        Args:
            content: The comment text.
            subreddit: Target subreddit name (without r/).
            post_context: Optional dict with parent post info.
            project: Optional business-profile dict (MiloAgent-style).
            is_promotional: None=unknown, True=promo, False=organic.

        Returns:
            ValidationResult with is_valid, score, issues, ai_score, blocked_by.
        """
        result = ValidationResult()

        # -- 0. Empty / trivial guard -------------------------------------------
        if not content or not content.strip():
            return ValidationResult(
                is_valid=False, score=0.0,
                issues=["Empty content"], ai_score=0.0, blocked_by="empty_content",
            )

        word_count = len(content.split())
        content_lower = content.lower()

        if word_count < 3:
            result.issues.append(f"Too short ({word_count} words)")
            result.blocked_by = result.blocked_by or "too_short"

        if word_count > 500:
            result.issues.append(f"Very long ({word_count} words) - may look unnatural")

        # -- 1. Bot pattern detection (RP patterns) -----------------------------
        rp_bot_matches = self._check_rp_bot_patterns(content)
        if rp_bot_matches:
            result.issues.extend(rp_bot_matches)

        # -- 2. Bot pattern detection (Milo patterns) ---------------------------
        milo_bot_matches = self._check_milo_bot_patterns(content)
        if milo_bot_matches:
            result.issues.extend(milo_bot_matches)

        # -- 3. AI detection score (BotBuster heuristics) -----------------------
        ai_score = self._calculate_ai_score(content)
        result.ai_score = ai_score
        if ai_score >= 4.0:
            result.issues.append(f"AI detection score too high: {ai_score:.1f}/10")
            result.blocked_by = result.blocked_by or "ai_score"
        elif ai_score >= 3.0:
            result.issues.append(f"AI detection score borderline: {ai_score:.1f}/10")

        # -- 4. Spam filter check -----------------------------------------------
        spam_issues = self._check_spam_patterns(content)
        if spam_issues:
            result.issues.extend(spam_issues)
            result.blocked_by = result.blocked_by or "spam_patterns"

        # -- 5. RSS / feed spam detection (Milo) --------------------------------
        rss_issues = self._check_rss_spam(content_lower)
        if rss_issues:
            result.issues.extend(rss_issues)
            result.blocked_by = result.blocked_by or "rss_spam"

        # -- 6. Subreddit-specific rules ----------------------------------------
        sub_issues = self._check_subreddit_rules(content, subreddit)
        if sub_issues:
            result.issues.extend(sub_issues)
            result.blocked_by = result.blocked_by or "subreddit_rules"

        # -- 7. Content deduplication -------------------------------------------
        content_hash = hashlib.md5(content.lower().strip().encode()).hexdigest()
        if self.db.is_duplicate_content(content_hash):
            result.issues.append("Duplicate content detected")
            result.blocked_by = result.blocked_by or "duplicate"

        # -- 8. URL checks (shortener detection + count) ------------------------
        urls = _URL_FINDER_RE.findall(content)
        if len(urls) > 1:
            result.issues.append(
                f"Multiple URLs ({len(urls)}) - may trigger spam filters"
            )
        for url in urls:
            if _URL_SHORTENER_RE.match(url):
                result.issues.append(f"URL shortener detected: {url}")
                result.blocked_by = result.blocked_by or "url_shortener"

        # -- 9. Business-profile fact-checking (Milo features) ------------------
        if project:
            proj = project.get("project", project)
            profile = proj.get("business_profile", {})

            # Product name accuracy
            name_issues = self._check_product_name(content, proj)
            result.issues.extend(name_issues)

            # URL accuracy
            url_accuracy_issues = self._check_url_accuracy(content, proj)
            result.issues.extend(url_accuracy_issues)

            # Forbidden phrases
            forbidden_issues = self._check_forbidden(content, profile)
            result.issues.extend(forbidden_issues)
            if forbidden_issues:
                result.blocked_by = result.blocked_by or "forbidden_phrase"

            # Pricing claims
            if profile:
                pricing_issues = self._check_pricing_claims(content, proj, profile)
                result.issues.extend(pricing_issues)

            # Organic mode enforcement
            if is_promotional is False:
                organic_issues = self._check_organic_leakage(content, proj)
                result.issues.extend(organic_issues)
                if organic_issues:
                    result.blocked_by = result.blocked_by or "organic_leakage"

        # -- 10. Compute quality score (0.0-1.0) --------------------------------
        result.score = self._compute_quality_score(result.issues, ai_score, word_count)

        # -- 11. Final is_valid decision ----------------------------------------
        has_critical = any("CRITICAL" in i for i in result.issues)
        hard_blocked = result.blocked_by in (
            "empty_content", "too_short", "ai_score", "duplicate",
            "url_shortener", "forbidden_phrase", "organic_leakage",
        )
        result.is_valid = (
            result.score >= 0.6
            and not has_critical
            and not hard_blocked
        )

        if result.issues:
            logger.info(
                "Content validation: valid=%s score=%.2f ai=%.1f issues=%s",
                result.is_valid, result.score, result.ai_score, result.issues,
            )
        else:
            logger.debug(
                "Content validation: valid=%s score=%.2f ai=%.1f clean",
                result.is_valid, result.score, result.ai_score,
            )

        return result

    def validate_post(
        self,
        title: str,
        body: str,
        subreddit: str,
        project: Optional[Dict] = None,
        is_promotional: Optional[bool] = None,
    ) -> ValidationResult:
        """Validate a post (title + body).

        Returns:
            ValidationResult with is_valid, score, issues, ai_score, blocked_by.
        """
        issues: List[str] = []

        # Title checks
        if not title or len(title) < 5:
            issues.append("Title too short")
        if title and len(title) > 300:
            issues.append("Title too long (max 300 chars)")
        if title and title.upper() == title and len(title) > 10:
            issues.append("ALL CAPS title")

        # Body validation (reuse comment pipeline)
        body_result = self.validate_comment(
            body, subreddit,
            project=project, is_promotional=is_promotional,
        )
        issues.extend(body_result.issues)

        is_valid = len(issues) == 0 and body_result.is_valid
        blocked_by = body_result.blocked_by
        if not is_valid and not blocked_by:
            blocked_by = "title_check" if any("Title" in i for i in issues) else None

        return ValidationResult(
            is_valid=is_valid,
            score=body_result.score,
            issues=issues,
            ai_score=body_result.ai_score,
            blocked_by=blocked_by,
        )

    # ──────────────────────────────────────────────────────────────────────
    # RP original: bot pattern checks
    # ──────────────────────────────────────────────────────────────────────

    def _check_rp_bot_patterns(self, content: str) -> List[str]:
        """Check content against RP's original bot patterns."""
        matches = []
        for i, pattern in enumerate(COMPILED_RP_BOT_PATTERNS):
            if pattern.search(content):
                matches.append(
                    f"Bot pattern detected: {_RP_BOT_PATTERN_STRINGS[i][:50]}..."
                )
        return matches

    # ──────────────────────────────────────────────────────────────────────
    # Milo: extended bot pattern checks (compiled tuples)
    # ──────────────────────────────────────────────────────────────────────

    def _check_milo_bot_patterns(self, content: str) -> List[str]:
        """Check content against MiloAgent's 50+ compiled bot patterns."""
        issues = []
        for compiled_re, desc in MILO_BOT_PATTERNS:
            if compiled_re.search(content):
                issues.append(f"Bot-like pattern: {desc}")
        return issues

    # ──────────────────────────────────────────────────────────────────────
    # RP original: BotBuster AI score
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_ai_score(self, content: str) -> float:
        """Calculate AI detection score using BotBuster's heuristics.

        Score 0-10+, threshold 4.0 for flagging.
        """
        score = 0.0

        # Formulaic phrases (+1.2 each)
        formulaic = [
            "in conclusion", "furthermore", "moreover", "it's worth noting",
            "it's important to note", "delve deeper", "navigate the complexities",
            "as a matter of fact", "in today's world", "at the end of the day",
            "having said that", "it goes without saying", "needless to say",
            "rest assured", "that being said", "without further ado",
        ]
        content_lower = content.lower()
        for phrase in formulaic:
            if phrase in content_lower:
                score += 1.2

        # Missing contractions (+1.8 for text >150 words)
        word_count = len(content.split())
        contractions = [
            "don't", "won't", "can't", "isn't", "aren't", "wouldn't",
            "couldn't", "shouldn't", "I'm", "I've", "I'll", "they're",
            "we're", "you're", "it's", "that's", "there's", "here's",
            "what's", "who's", "didn't", "doesn't", "hasn't", "haven't",
        ]
        has_contractions = any(c.lower() in content_lower for c in contractions)
        if word_count > 150 and not has_contractions:
            score += 1.8

        # Complex synonyms (+0.8 each)
        complex_words = [
            "utilize", "leverage", "commence", "facilitate",
            "aforementioned", "paradigm", "synergy", "holistic",
            "multifaceted", "subsequently", "ameliorate", "elucidate",
        ]
        for word in complex_words:
            if word in content_lower:
                score += 0.8

        # Missing personal opinion markers (+1.0)
        personal = [
            "i think", "imo", "in my experience", "honestly",
            "tbh", "personally", "i believe", "i feel",
        ]
        if word_count > 100 and not any(m in content_lower for m in personal):
            score += 1.0

        # Low sentence length variance (+1.5)
        sentences = [s.strip() for s in re.split(r"[.!?]+", content) if s.strip()]
        if len(sentences) >= 3:
            lengths = [len(s.split()) for s in sentences]
            avg = sum(lengths) / len(lengths)
            variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
            if variance < 5:
                score += 1.5

        # Emoji presence (-1.0 bonus for natural feel)
        if re.search(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]",
            content,
        ):
            score -= 1.0

        # Short comments are inherently less suspicious
        if word_count < 25:
            score = max(score - 2.0, 0)

        return max(score, 0)

    # ──────────────────────────────────────────────────────────────────────
    # RP original: spam patterns
    # ──────────────────────────────────────────────────────────────────────

    def _check_spam_patterns(self, content: str) -> List[str]:
        """Check for spam-like content."""
        issues = []

        # Repeated words/phrases
        words = content.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                issues.append(
                    f"High word repetition (unique ratio: {unique_ratio:.2f})"
                )

        # Excessive exclamation marks
        if content.count("!") > 3:
            issues.append("Excessive exclamation marks")

        # All caps sections
        caps_words = [w for w in words if w.isupper() and len(w) > 2]
        if len(caps_words) > 3:
            issues.append("Excessive ALL CAPS")

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # Milo: RSS / feed spam detection
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_rss_spam(content_lower: str) -> List[str]:
        """Detect RSS link-spam patterns."""
        for phrase in _RSS_SPAM_PHRASES:
            if phrase in content_lower:
                return [f"RSS spam pattern: '{phrase}'"]
        return []

    # ──────────────────────────────────────────────────────────────────────
    # RP original: subreddit-specific rules
    # ──────────────────────────────────────────────────────────────────────

    def _check_subreddit_rules(self, content: str, subreddit: str) -> List[str]:
        """Check content against subreddit-specific rules."""
        issues = []
        rules = SUBREDDIT_RESTRICTIONS.get(subreddit, {})
        if not rules:
            return issues

        # Link count
        urls = _URL_FINDER_RE.findall(content)
        max_links = rules.get("max_links", 3)
        if len(urls) > max_links:
            issues.append(f"Too many links for r/{subreddit} (max {max_links})")

        # Minimum words
        word_count = len(content.split())
        min_words = rules.get("min_words", 0)
        if word_count < min_words:
            issues.append(
                f"Below minimum word count for r/{subreddit} ({min_words})"
            )

        # No solicitation
        if rules.get("no_solicitation"):
            for pattern in _SOLICITATION_PATTERNS:
                if pattern.search(content):
                    issues.append(f"Solicitation detected in r/{subreddit}")
                    break

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # Milo: business-profile fact-checking
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_product_name(content: str, proj: Dict) -> List[str]:
        """Check if product name appears with correct spelling."""
        issues = []
        name = proj.get("name", "")
        if not name or len(name) < 2:
            return issues

        name_lower = name.lower()
        content_lower = content.lower()

        if name_lower not in content_lower:
            return issues  # Product not mentioned — that's fine

        # Find all occurrences and check spelling
        for match in re.finditer(re.escape(name_lower), content_lower):
            start, end = match.start(), match.end()
            actual = content[start:end]
            if actual != name:
                issues.append(f"Product name case: '{actual}' vs '{name}'")

        return issues

    @staticmethod
    def _check_url_accuracy(content: str, proj: Dict) -> List[str]:
        """Check if URLs in content match the project URL (catch hallucinations)."""
        issues = []
        correct_url = proj.get("url", "")
        if not correct_url:
            return issues

        correct_domain = (
            correct_url.replace("https://", "").replace("http://", "").rstrip("/")
        )

        found_urls = _URL_FINDER_RE.findall(content)
        for url in found_urls:
            domain = (
                url.replace("https://", "").replace("http://", "").split("/")[0]
            )
            similarity = SequenceMatcher(
                None, domain.lower(), correct_domain.lower()
            ).ratio()
            if similarity > 0.5 and domain.lower() != correct_domain.lower():
                issues.append(
                    f"CRITICAL: Wrong URL '{url}' (should be {correct_url})"
                )

        return issues

    @staticmethod
    def _check_forbidden(content: str, profile: Dict) -> List[str]:
        """Check for forbidden phrases from business profile rules."""
        issues = []
        rules = profile.get("rules", {})
        content_lower = content.lower()
        for phrase in rules.get("never_say", []):
            if phrase.lower() in content_lower:
                issues.append(f"CRITICAL: Contains forbidden phrase: '{phrase}'")
        return issues

    # ──────────────────────────────────────────────────────────────────────
    # Milo: pricing claim verification
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_pricing_claims(
        content: str, proj: Dict, profile: Dict
    ) -> List[str]:
        """Check that pricing claims match the business profile."""
        issues = []
        content_lower = content.lower()
        name_lower = proj.get("name", "").lower()

        # Only check if the product is actually mentioned
        if not name_lower or name_lower not in content_lower:
            return issues

        pricing = profile.get("pricing", {})
        if not pricing:
            return issues

        # "free" claim vs pricing model
        if " free" in content_lower and pricing.get("model") not in (
            "free", "freemium",
        ):
            issues.append(
                f"Claims product is free but pricing model is "
                f"'{pricing.get('model', 'unknown')}'"
            )

        # Check for price amounts that don't match known plans
        mentioned_prices = _PRICE_RE.findall(content)
        if mentioned_prices and pricing.get("paid_plans"):
            valid_prices = [p.get("price", "") for p in pricing["paid_plans"]]
            for mp in mentioned_prices:
                if not any(mp in vp for vp in valid_prices):
                    issues.append(f"Price {mp} not found in business profile")

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # Milo: organic mode enforcement
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_organic_leakage(content: str, proj: Dict) -> List[str]:
        """Ensure organic (non-promotional) content has NO product mentions.

        Organic comments that 'accidentally' mention the product are the #1
        reason accounts get flagged as spam bots.
        """
        issues = []
        content_lower = content.lower()

        # Check product name
        name = proj.get("name", "")
        if name and len(name) >= 2 and name.lower() in content_lower:
            issues.append(f"CRITICAL: Product '{name}' mentioned in organic comment")

        # Check alt names
        for alt in proj.get("alt_names", []):
            if alt and len(alt) >= 2 and alt.lower() in content_lower:
                issues.append(
                    f"CRITICAL: Product alt name '{alt}' in organic comment"
                )

        # Check project URL
        url = proj.get("url", "")
        if url:
            domain = (
                url.replace("https://", "").replace("http://", "").rstrip("/")
            )
            if domain.lower() in content_lower:
                issues.append(
                    f"CRITICAL: Product URL '{domain}' in organic comment"
                )

        # Check for non-safe URLs in organic comment
        found_domains = re.findall(r"https?://([^\s/]+)", content)
        for domain in found_domains:
            if not any(domain.endswith(safe) for safe in SAFE_DOMAINS):
                issues.append(f"URL in organic comment: {domain}")

        return issues

    # ──────────────────────────────────────────────────────────────────────
    # Quality score (reconciles RP ai_score + Milo quality score)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_quality_score(
        issues: List[str], ai_score: float, word_count: int
    ) -> float:
        """Compute a 0.0-1.0 quality score from all collected issues.

        Deductions:
          - CRITICAL issue:      -0.30 each
          - Bot-like pattern:    -0.10 each
          - Other issue:         -0.08 each
          - AI score >= 4.0:     -0.25
          - AI score 3.0-4.0:    -0.10
        """
        score = 1.0

        for issue in issues:
            if "CRITICAL" in issue:
                score -= 0.30
            elif "Bot" in issue or "bot" in issue:
                score -= 0.10
            else:
                score -= 0.08

        # AI-score penalty (already added as an issue, but also impacts score)
        if ai_score >= 4.0:
            score -= 0.25
        elif ai_score >= 3.0:
            score -= 0.10

        return max(0.0, min(1.0, score))
