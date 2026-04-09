"""
RedditPilot Platforms

Alternate platform adapters for Reddit interaction.
- reddit_web: Cookie-based web session (no API app registration needed)
- The default PRAW client lives at core/reddit_client.py
"""

from .reddit_web import RedditWebClient

__all__ = ["RedditWebClient"]
