"""RedditPilot — Reddit outreach engine.

Subreddit scanning, opportunity discovery, human-in-the-loop comment/post
generation, A/B testing, and learning loop. Runs in-process via a lazy
singleton managed by `shim.py`.
"""
from .manifest import manifest
from .router import router

__all__ = ["manifest", "router"]
