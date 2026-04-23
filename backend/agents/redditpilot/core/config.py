"""
RedditPilot Configuration System
Handles all configuration loading, validation, and defaults.
Inspired by MiloAgent's YAML config + markmelnic's multi-layer config merge.
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("redditpilot.config")

DEFAULT_CONFIG_PATH = Path.home() / ".redditpilot" / "config.yaml"
DEFAULT_DATA_DIR = Path.home() / ".redditpilot" / "data"


@dataclass
class RedditAccount:
    """A single Reddit account with credentials and metadata."""
    username: str
    password: str
    client_id: str
    client_secret: str
    user_agent: str = ""
    karma_tier: str = "new"  # new, growing, established, veteran
    daily_comment_cap: int = 3
    daily_post_cap: int = 1
    assigned_subreddits: list = field(default_factory=list)
    proxy: str = ""
    enabled: bool = True
    notes: str = ""

    def __post_init__(self):
        if not self.user_agent:
            self.user_agent = f"RedditPilot:v1.0 (by /u/{self.username})"
        # Karma tier caps (from MiloAgent)
        tier_caps = {
            "new": (3, 0),        # comment only, no posts
            "growing": (7, 2),
            "established": (12, 5),
            "veteran": (20, 10),
        }
        if self.karma_tier in tier_caps:
            self.daily_comment_cap, self.daily_post_cap = tier_caps[self.karma_tier]


@dataclass
class ClientProfile:
    """A client that RedditPilot manages Reddit presence for."""
    name: str
    slug: str  # url-safe identifier
    industry: str  # e.g. "plumbing", "hvac", "electrical"
    service_area: str  # e.g. "Phoenix, AZ"
    website: str = ""
    brand_voice: str = ""  # Description of how the brand should sound
    target_subreddits: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    competitors: list = field(default_factory=list)
    personas: list = field(default_factory=list)  # List of persona dicts
    promo_ratio: float = 0.05  # 5% max promotional content
    approval_required: bool = True  # Require Slack approval before posting
    enabled: bool = True


@dataclass
class LLMConfig:
    """LLM provider configuration. Supports multiple providers with fallback."""
    primary_provider: str = "openai"  # openai, anthropic, groq, ollama
    primary_model: str = "gpt-4o-mini"
    primary_api_key: str = ""
    fallback_provider: str = "groq"
    fallback_model: str = "llama-3.3-70b-versatile"
    fallback_api_key: str = ""
    temperature: float = 0.8
    max_tokens: int = 500
    # Anti-AI-detection settings
    casualness: float = 0.7  # 0=formal, 1=very casual
    use_contractions: bool = True
    max_reading_level: str = "8th_grade"  # Keep it simple


@dataclass
class SafetyConfig:
    """Safety and anti-detection settings."""
    min_delay_seconds: int = 30
    max_delay_seconds: int = 180
    min_account_age_days: int = 30
    min_karma_to_post: int = 50
    shadowban_check_interval_hours: int = 6
    max_actions_per_hour: int = 8
    enable_proxy_rotation: bool = True
    content_validation_enabled: bool = True
    auto_delete_negative_comments: bool = True
    negative_score_threshold: int = -2
    # Anti-AI patterns to avoid (from BotBuster analysis)
    banned_phrases: list = field(default_factory=lambda: [
        "in conclusion", "furthermore", "it's worth noting",
        "it's important to note", "delve deeper", "navigate the complexities",
        "as a matter of fact", "in today's world", "at the end of the day",
        "leverage", "utilize", "commence", "facilitate", "aforementioned",
        "paradigm", "synergy", "holistic approach", "game-changer",
    ])


@dataclass
class SlackConfig:
    """Slack integration for approval workflows."""
    enabled: bool = True
    bot_token: str = ""
    approval_channel: str = ""
    notification_channel: str = ""
    webhook_url: str = ""


@dataclass
class Config:
    """Master configuration for RedditPilot."""
    accounts: list = field(default_factory=list)  # List[RedditAccount]
    clients: list = field(default_factory=list)    # List[ClientProfile]
    llm: LLMConfig = field(default_factory=LLMConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    data_dir: str = str(DEFAULT_DATA_DIR)
    log_level: str = "INFO"
    scan_interval_minutes: int = 30
    learning_interval_hours: int = 6

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        """Load config from YAML file, merging with env vars."""
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH

        if not config_path.exists():
            logger.warning(f"Config not found at {config_path}, using defaults")
            return cls()

        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        config = cls()

        # Load accounts
        for acct_data in raw.get("accounts", []):
            config.accounts.append(RedditAccount(**acct_data))

        # Load clients
        for client_data in raw.get("clients", []):
            config.clients.append(ClientProfile(**client_data))

        # Load LLM config
        llm_data = raw.get("llm", {})
        config.llm = LLMConfig(**{
            k: v for k, v in llm_data.items()
            if k in LLMConfig.__dataclass_fields__
        })

        # Load safety config
        safety_data = raw.get("safety", {})
        config.safety = SafetyConfig(**{
            k: v for k, v in safety_data.items()
            if k in SafetyConfig.__dataclass_fields__
        })

        # Load slack config
        slack_data = raw.get("slack", {})
        config.slack = SlackConfig(**{
            k: v for k, v in slack_data.items()
            if k in SlackConfig.__dataclass_fields__
        })

        # Top-level settings
        config.data_dir = raw.get("data_dir", str(DEFAULT_DATA_DIR))
        config.log_level = raw.get("log_level", "INFO")
        config.scan_interval_minutes = raw.get("scan_interval_minutes", 30)
        config.learning_interval_hours = raw.get("learning_interval_hours", 6)

        # Override with env vars
        config._apply_env_overrides()

        return config

    def _apply_env_overrides(self):
        """Override config values with environment variables."""
        env_map = {
            "REDDITPILOT_LLM_API_KEY": ("llm", "primary_api_key"),
            "REDDITPILOT_LLM_FALLBACK_KEY": ("llm", "fallback_api_key"),
            "REDDITPILOT_SLACK_TOKEN": ("slack", "bot_token"),
            "REDDITPILOT_SLACK_CHANNEL": ("slack", "approval_channel"),
            "REDDITPILOT_LOG_LEVEL": (None, "log_level"),
        }
        for env_var, (section, key) in env_map.items():
            val = os.environ.get(env_var)
            if val:
                if section:
                    setattr(getattr(self, section), key, val)
                else:
                    setattr(self, key, val)

    def get_enabled_accounts(self) -> list:
        return [a for a in self.accounts if a.enabled]

    def get_enabled_clients(self) -> list:
        return [c for c in self.clients if c.enabled]

    def validate(self) -> list:
        """Validate config and return list of warnings."""
        warnings = []
        if not self.accounts:
            warnings.append("No Reddit accounts configured")
        if not self.clients:
            warnings.append("No clients configured")
        if not self.llm.primary_api_key:
            warnings.append("No LLM API key configured")
        for acct in self.accounts:
            if not acct.client_id or not acct.client_secret:
                warnings.append(f"Account {acct.username} missing Reddit API credentials")
        return warnings
