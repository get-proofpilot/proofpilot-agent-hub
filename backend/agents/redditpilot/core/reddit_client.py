"""
RedditPilot Reddit Client
PRAW wrapper with anti-detection, rate limiting, and multi-account support.
Combines patterns from MiloAgent, markmelnic/reddit-bot, and feder-cr bots.
"""

import praw
import time
import random
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from .config import RedditAccount, Config
from .database import Database

logger = logging.getLogger("redditpilot.reddit")


class RedditClient:
    """
    Manages PRAW connections with anti-detection features.
    One instance per Reddit account.
    """

    # Realistic user agent rotation pool (from markmelnic/reddit-bot)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    ]

    def __init__(self, account: RedditAccount, db: Database):
        self.account = account
        self.db = db
        self._reddit = None
        self._last_action_time = None

    @property
    def reddit(self) -> praw.Reddit:
        """Lazy-initialize PRAW connection."""
        if self._reddit is None:
            self._reddit = praw.Reddit(
                client_id=self.account.client_id,
                client_secret=self.account.client_secret,
                username=self.account.username,
                password=self.account.password,
                user_agent=self.account.user_agent,
            )
            logger.info(f"Connected as /u/{self.account.username}")
        return self._reddit

    def _human_delay(self, min_sec: int = 30, max_sec: int = 120):
        """
        Wait a human-like random duration before acting.
        Adapted from MiloAgent's rate_limiter.py with jitter.
        """
        base = random.uniform(min_sec, max_sec)
        # Add Gaussian jitter for natural variation
        jitter = random.gauss(0, base * 0.15)
        delay = max(min_sec * 0.5, base + jitter)

        if self._last_action_time:
            elapsed = (datetime.utcnow() - self._last_action_time).total_seconds()
            remaining = delay - elapsed
            if remaining > 0:
                logger.debug(f"Human delay: {remaining:.1f}s")
                time.sleep(remaining)

        self._last_action_time = datetime.utcnow()

    # ── Reading Operations (no rate limit concerns) ─────────────────

    def get_subreddit_info(self, subreddit_name: str) -> dict:
        """Fetch subreddit metadata."""
        try:
            sub = self.reddit.subreddit(subreddit_name)
            return {
                "name": sub.display_name,
                "subscribers": sub.subscribers,
                "description": sub.public_description or "",
                "rules": [r.short_name for r in sub.rules] if hasattr(sub, 'rules') else [],
                "over18": sub.over18,
                "created_utc": sub.created_utc,
            }
        except Exception as e:
            logger.error(f"Failed to get subreddit {subreddit_name}: {e}")
            return {}

    def search_subreddits(self, query: str, limit: int = 25) -> list:
        """Search for relevant subreddits by keyword."""
        results = []
        try:
            for sub in self.reddit.subreddits.search(query, limit=limit):
                results.append({
                    "name": sub.display_name,
                    "subscribers": sub.subscribers,
                    "description": sub.public_description or "",
                    "over18": sub.over18,
                })
        except Exception as e:
            logger.error(f"Subreddit search failed for '{query}': {e}")
        return results

    def get_hot_posts(self, subreddit_name: str, limit: int = 25,
                      time_filter: str = "day") -> list:
        """Get hot posts from a subreddit."""
        posts = []
        try:
            sub = self.reddit.subreddit(subreddit_name)
            for post in sub.hot(limit=limit):
                posts.append(self._post_to_dict(post))
        except Exception as e:
            logger.error(f"Failed to get hot posts from r/{subreddit_name}: {e}")
        return posts

    def get_new_posts(self, subreddit_name: str, limit: int = 25) -> list:
        """Get new posts from a subreddit."""
        posts = []
        try:
            sub = self.reddit.subreddit(subreddit_name)
            for post in sub.new(limit=limit):
                posts.append(self._post_to_dict(post))
        except Exception as e:
            logger.error(f"Failed to get new posts from r/{subreddit_name}: {e}")
        return posts

    def search_posts(self, subreddit_name: str, query: str,
                     sort: str = "relevance", time_filter: str = "week",
                     limit: int = 25) -> list:
        """Search posts within a subreddit."""
        posts = []
        try:
            sub = self.reddit.subreddit(subreddit_name)
            for post in sub.search(query, sort=sort, time_filter=time_filter, limit=limit):
                posts.append(self._post_to_dict(post))
        except Exception as e:
            logger.error(f"Search failed in r/{subreddit_name}: {e}")
        return posts

    def get_post_comments(self, post_id: str, limit: int = 10) -> list:
        """Get top comments on a post for context."""
        comments = []
        try:
            submission = self.reddit.submission(id=post_id)
            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:limit]:
                comments.append({
                    "id": comment.id,
                    "body": comment.body,
                    "score": comment.score,
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "created_utc": comment.created_utc,
                })
        except Exception as e:
            logger.error(f"Failed to get comments for {post_id}: {e}")
        return comments

    # ── Writing Operations (rate limited, logged) ───────────────────

    def post_comment(self, post_id: str, comment_text: str,
                     client_id: int = None, subreddit: str = None) -> Optional[str]:
        """
        Post a comment on a submission.
        Returns comment ID on success, None on failure.
        """
        self._human_delay()

        try:
            submission = self.reddit.submission(id=post_id)
            comment = submission.reply(comment_text)

            # Log the action
            account_row = self.db.fetchone(
                "SELECT id FROM accounts WHERE username = ?",
                (self.account.username,)
            )
            if account_row:
                self.db.record_action(
                    account_id=account_row["id"],
                    action_type="comment",
                    subreddit=subreddit or str(submission.subreddit),
                    client_id=client_id,
                    reddit_id=comment.id,
                )

            logger.info(f"Posted comment {comment.id} on {post_id} as /u/{self.account.username}")
            return comment.id

        except praw.exceptions.RedditAPIException as e:
            for error in e.items:
                if error.error_type == "RATELIMIT":
                    wait_time = self._parse_ratelimit_message(error.message)
                    logger.warning(f"Rate limited. Waiting {wait_time}s")
                    time.sleep(wait_time)
                    return self.post_comment(post_id, comment_text, client_id, subreddit)
                else:
                    logger.error(f"Reddit API error: {error.error_type} - {error.message}")
            return None
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
            return None

    def create_post(self, subreddit_name: str, title: str, body: str = None,
                    url: str = None, client_id: int = None) -> Optional[str]:
        """
        Create a new post in a subreddit.
        Returns post ID on success, None on failure.
        """
        self._human_delay(min_sec=60, max_sec=300)

        try:
            sub = self.reddit.subreddit(subreddit_name)

            if url:
                submission = sub.submit(title=title, url=url)
            else:
                submission = sub.submit(title=title, selftext=body or "")

            account_row = self.db.fetchone(
                "SELECT id FROM accounts WHERE username = ?",
                (self.account.username,)
            )
            if account_row:
                self.db.record_action(
                    account_id=account_row["id"],
                    action_type="post",
                    subreddit=subreddit_name,
                    client_id=client_id,
                    reddit_id=submission.id,
                )

            logger.info(f"Created post {submission.id} in r/{subreddit_name}")
            return submission.id

        except praw.exceptions.RedditAPIException as e:
            for error in e.items:
                logger.error(f"Reddit API error: {error.error_type} - {error.message}")
            return None
        except Exception as e:
            logger.error(f"Failed to create post: {e}")
            return None

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment (for auto-removing negative-score comments)."""
        try:
            comment = self.reddit.comment(id=comment_id)
            comment.delete()
            logger.info(f"Deleted comment {comment_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete comment {comment_id}: {e}")
            return False

    # ── Monitoring Operations ───────────────────────────────────────

    def check_comment_performance(self, comment_id: str) -> Optional[dict]:
        """Check how a posted comment is performing."""
        try:
            comment = self.reddit.comment(id=comment_id)
            return {
                "id": comment.id,
                "score": comment.score,
                "body": comment.body,
                "is_removed": comment.body == "[removed]" or comment.body == "[deleted]",
                "replies": len(comment.replies) if hasattr(comment.replies, '__len__') else 0,
            }
        except Exception as e:
            logger.error(f"Failed to check comment {comment_id}: {e}")
            return None

    def check_shadowban(self) -> bool:
        """
        Check if the current account is shadowbanned.
        Adapted from MiloAgent's ban_detector.py
        """
        try:
            # Method 1: Try to access own profile
            user = self.reddit.redditor(self.account.username)
            # If we can access karma, we're probably fine
            _ = user.link_karma
            return False
        except Exception:
            logger.warning(f"Account /u/{self.account.username} may be shadowbanned!")
            return True

    # ── Helpers ─────────────────────────────────────────────────────

    def _post_to_dict(self, post) -> dict:
        """Convert a PRAW submission to a clean dict."""
        return {
            "id": post.id,
            "title": post.title,
            "body": post.selftext[:2000] if post.selftext else "",
            "author": str(post.author) if post.author else "[deleted]",
            "subreddit": str(post.subreddit),
            "url": post.url,
            "permalink": f"https://reddit.com{post.permalink}",
            "score": post.score,
            "upvote_ratio": post.upvote_ratio,
            "num_comments": post.num_comments,
            "created_utc": post.created_utc,
            "is_self": post.is_self,
            "link_flair_text": post.link_flair_text,
            "over_18": post.over_18,
            "locked": post.locked,
        }

    @staticmethod
    def _parse_ratelimit_message(message: str) -> int:
        """Parse Reddit's rate limit message to get wait time in seconds."""
        import re
        minutes = re.search(r"(\d+) minute", message)
        seconds = re.search(r"(\d+) second", message)
        wait = 0
        if minutes:
            wait += int(minutes.group(1)) * 60
        if seconds:
            wait += int(seconds.group(1))
        return max(wait, 30)  # minimum 30s wait


class AccountPool:
    """
    Manages a pool of Reddit accounts with round-robin rotation.
    Adapted from MiloAgent's account_manager.py
    """

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.clients: dict = {}  # username -> RedditClient
        self._rotation_index = 0

        for account in config.get_enabled_accounts():
            self.clients[account.username] = RedditClient(account, db)
            db.upsert_account(account.username, karma_tier=account.karma_tier)

    def get_client(self, username: str = None) -> Optional[RedditClient]:
        """Get a specific client by username, or the next available one."""
        if username and username in self.clients:
            return self.clients[username]

        # Round-robin from available accounts
        available = self.db.get_available_account()
        if available and available["username"] in self.clients:
            return self.clients[available["username"]]

        # Fallback: just rotate through all
        if not self.clients:
            return None
        usernames = list(self.clients.keys())
        client = self.clients[usernames[self._rotation_index % len(usernames)]]
        self._rotation_index += 1
        return client

    def check_all_shadowbans(self):
        """Check all accounts for shadowbans."""
        for username, client in self.clients.items():
            is_banned = client.check_shadowban()
            self.db.execute(
                "UPDATE accounts SET is_shadowbanned = ?, last_shadowban_check = datetime('now') WHERE username = ?",
                (int(is_banned), username)
            )
            if is_banned:
                logger.warning(f"SHADOWBAN DETECTED: /u/{username}")
        self.db.commit()
