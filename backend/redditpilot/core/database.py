"""
RedditPilot Database Layer
Thread-safe SQLite database with full schema for multi-client Reddit operations.
Adapted from MiloAgent's 20+ table schema with ProofPilot agency additions.

v2: Added schema migration system, intelligence tables, thread-safe write lock,
    and auto-maintenance from MiloAgent.
"""

import sqlite3
import threading
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

logger = logging.getLogger("redditpilot.database")

_CLEANUP_INTERVAL_HOURS = 3


class Database:
    """Thread-safe SQLite database for RedditPilot.

    Thread-safe via thread-local connections + write lock.
    Each thread gets its own SQLite connection (WAL mode allows concurrent reads).
    Writes are serialized with a threading.Lock to prevent WAL contention.
    """

    SCHEMA_VERSION = 2

    def __init__(self, db_path: str = "redditpilot.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        self._lock = threading.Lock()
        self._local = threading.local()
        self._last_cleanup = datetime.utcnow()
        self._closed = False

        self._init_schema()
        self._run_migrations()
        self._maybe_maintenance()

    # ── Connection Management ────────────────────────────────────────

    def _make_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection configured for WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=100")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """Thread-local connection - each thread gets its own."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._make_connection()
        return self._local.conn

    @contextmanager
    def transaction(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        return self._get_conn().executemany(sql, params_list)

    def commit(self):
        self._get_conn().commit()

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def _execute_write(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a write query with thread lock to prevent WAL contention."""
        with self._lock:
            cursor = self._get_conn().execute(query, params)
            self._get_conn().commit()
            return cursor

    def close(self):
        """Close thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
        self._closed = True

    # ── Schema Initialization ────────────────────────────────────────

    def _init_schema(self):
        """Create all v1 tables if they don't exist."""
        with self._lock:
            conn = self._get_conn()
            conn.executescript("""
                -- Schema version tracking
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT DEFAULT (datetime('now')),
                    description TEXT
                );

                -- Reddit accounts managed by the system
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    karma_tier TEXT DEFAULT 'new',
                    comment_karma INTEGER DEFAULT 0,
                    post_karma INTEGER DEFAULT 0,
                    account_age_days INTEGER DEFAULT 0,
                    is_shadowbanned INTEGER DEFAULT 0,
                    last_action_at TEXT,
                    last_shadowban_check TEXT,
                    daily_comments_today INTEGER DEFAULT 0,
                    daily_posts_today INTEGER DEFAULT 0,
                    daily_reset_date TEXT,
                    total_comments INTEGER DEFAULT 0,
                    total_posts INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- Clients we manage Reddit presence for
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    industry TEXT,
                    service_area TEXT,
                    website TEXT,
                    brand_voice TEXT,
                    promo_ratio REAL DEFAULT 0.05,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Subreddits we've discovered and are targeting
                CREATE TABLE IF NOT EXISTS subreddits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    subscribers INTEGER DEFAULT 0,
                    description TEXT,
                    rules TEXT,  -- JSON array of rules
                    relevance_score REAL DEFAULT 0.0,
                    tier INTEGER DEFAULT 3,  -- 1=best, 4=lowest
                    category TEXT,  -- business, tech, local, industry
                    posting_restrictions TEXT,  -- JSON
                    avg_engagement REAL DEFAULT 0.0,
                    last_scanned TEXT,
                    is_nsfw INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Which clients target which subreddits
                CREATE TABLE IF NOT EXISTS client_subreddits (
                    client_id INTEGER REFERENCES clients(id),
                    subreddit_id INTEGER REFERENCES subreddits(id),
                    relevance_score REAL DEFAULT 0.0,
                    PRIMARY KEY (client_id, subreddit_id)
                );

                -- Posts we've discovered as opportunities
                CREATE TABLE IF NOT EXISTS discovered_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reddit_id TEXT UNIQUE NOT NULL,
                    subreddit TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT,
                    author TEXT,
                    url TEXT,
                    score INTEGER DEFAULT 0,
                    num_comments INTEGER DEFAULT 0,
                    created_utc REAL,
                    -- Scoring
                    relevance_score REAL DEFAULT 0.0,
                    engagement_score REAL DEFAULT 0.0,
                    opportunity_score REAL DEFAULT 0.0,
                    seo_value_score REAL DEFAULT 0.0,
                    -- Status
                    status TEXT DEFAULT 'new',  -- new, queued, approved, posted, skipped, expired
                    client_id INTEGER REFERENCES clients(id),
                    matched_keywords TEXT,  -- JSON array
                    discovered_at TEXT DEFAULT (datetime('now'))
                );

                -- Comments we've generated and posted
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reddit_comment_id TEXT,
                    post_reddit_id TEXT NOT NULL,
                    subreddit TEXT NOT NULL,
                    client_id INTEGER REFERENCES clients(id),
                    account_id INTEGER REFERENCES accounts(id),
                    -- Content
                    content TEXT NOT NULL,
                    persona_used TEXT,
                    tone_used TEXT,
                    prompt_template TEXT,
                    -- Performance
                    score INTEGER DEFAULT 0,
                    is_removed INTEGER DEFAULT 0,
                    engagement_count INTEGER DEFAULT 0,  -- replies received
                    -- Status
                    status TEXT DEFAULT 'draft',  -- draft, pending_approval, approved, posted, deleted, failed
                    approved_by TEXT,
                    posted_at TEXT,
                    last_checked_at TEXT,
                    -- A/B testing
                    ab_experiment_id INTEGER,
                    ab_variant TEXT,
                    -- Meta
                    generation_model TEXT,
                    generation_tokens INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Posts we've created
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reddit_post_id TEXT,
                    subreddit TEXT NOT NULL,
                    client_id INTEGER REFERENCES clients(id),
                    account_id INTEGER REFERENCES accounts(id),
                    -- Content
                    title TEXT NOT NULL,
                    body TEXT,
                    post_type TEXT DEFAULT 'text',  -- text, link, image
                    link_url TEXT,
                    persona_used TEXT,
                    tone_used TEXT,
                    -- Performance
                    score INTEGER DEFAULT 0,
                    num_comments INTEGER DEFAULT 0,
                    upvote_ratio REAL DEFAULT 0.0,
                    is_removed INTEGER DEFAULT 0,
                    -- Status
                    status TEXT DEFAULT 'draft',
                    approved_by TEXT,
                    posted_at TEXT,
                    last_checked_at TEXT,
                    -- Meta
                    generation_model TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- A/B testing experiments
                CREATE TABLE IF NOT EXISTS ab_experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    dimension TEXT NOT NULL,  -- tone, length, promo_ratio, post_type
                    variants TEXT NOT NULL,  -- JSON array of variant configs
                    client_id INTEGER REFERENCES clients(id),
                    subreddit TEXT,
                    status TEXT DEFAULT 'active',  -- active, concluded, paused
                    winner TEXT,
                    sample_size INTEGER DEFAULT 0,
                    significance REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    concluded_at TEXT
                );

                -- Learning: tracked metrics over time
                CREATE TABLE IF NOT EXISTS performance_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_type TEXT NOT NULL,  -- comment_score, post_score, engagement_rate
                    metric_value REAL NOT NULL,
                    client_id INTEGER,
                    subreddit TEXT,
                    account_id INTEGER,
                    tone TEXT,
                    post_type TEXT,
                    day_of_week INTEGER,
                    hour_of_day INTEGER,
                    recorded_at TEXT DEFAULT (datetime('now'))
                );

                -- Learning: discovered strategies and rules
                CREATE TABLE IF NOT EXISTS learned_strategies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT NOT NULL,  -- keyword_weight, tone_weight, timing_rule
                    key TEXT NOT NULL,
                    value REAL NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    sample_count INTEGER DEFAULT 0,
                    client_id INTEGER,
                    subreddit TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(strategy_type, key, client_id, subreddit)
                );

                -- Action log for rate limiting and audit
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER REFERENCES accounts(id),
                    action_type TEXT NOT NULL,  -- comment, post, upvote, scan, discovery
                    subreddit TEXT,
                    client_id INTEGER,
                    reddit_id TEXT,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Content deduplication
                CREATE TABLE IF NOT EXISTS content_hashes (
                    hash TEXT PRIMARY KEY,
                    content_type TEXT NOT NULL,  -- comment, post_title, post_body
                    subreddit TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Persona definitions per client
                CREATE TABLE IF NOT EXISTS personas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER REFERENCES clients(id),
                    name TEXT NOT NULL,
                    description TEXT,
                    tone TEXT DEFAULT 'helpful',
                    expertise_areas TEXT,  -- JSON array
                    writing_style TEXT,
                    example_phrases TEXT,  -- JSON array
                    banned_phrases TEXT,  -- JSON array
                    subreddit_assignments TEXT,  -- JSON array of subreddit names
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- v1 Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_posts_status ON discovered_posts(status);
                CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON discovered_posts(subreddit);
                CREATE INDEX IF NOT EXISTS idx_posts_client ON discovered_posts(client_id);
                CREATE INDEX IF NOT EXISTS idx_comments_status ON comments(status);
                CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_reddit_id);
                CREATE INDEX IF NOT EXISTS idx_action_log_account ON action_log(account_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_action_log_type ON action_log(action_type, created_at);
                CREATE INDEX IF NOT EXISTS idx_perf_log_type ON performance_log(metric_type, recorded_at);
            """)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    # ── Schema Migration System ──────────────────────────────────────

    def _get_schema_version(self) -> int:
        """Get current schema version from DB. Returns 1 if no version table."""
        try:
            row = self.fetchone("SELECT MAX(version) as ver FROM schema_version")
            if row and row["ver"] is not None:
                return row["ver"]
        except sqlite3.OperationalError:
            pass
        return 1  # v1 = original schema, no version tracking

    def _set_schema_version(self, version: int, description: str = ""):
        """Record that a migration was applied."""
        self._execute_write(
            "INSERT OR REPLACE INTO schema_version (version, applied_at, description) "
            "VALUES (?, datetime('now'), ?)",
            (version, description),
        )

    def _run_migrations(self):
        """Run any pending schema migrations."""
        current = self._get_schema_version()
        target = self.SCHEMA_VERSION

        if current >= target:
            logger.debug(f"Schema up to date at v{current}")
            return

        logger.info(f"Migrating schema from v{current} to v{target}")

        migrations = {
            2: self._migrate_v1_to_v2,
        }

        for ver in range(current + 1, target + 1):
            if ver in migrations:
                try:
                    migrations[ver]()
                    self._set_schema_version(ver, f"Migration to v{ver}")
                    logger.info(f"Applied migration v{ver}")
                except Exception as e:
                    logger.error(f"Migration v{ver} failed: {e}")
                    raise

    def _migrate_v1_to_v2(self):
        """Add intelligence tables: subreddit_intel, decision_log, failure_patterns, account_health."""
        with self._lock:
            conn = self._get_conn()
            conn.executescript("""
                -- Subreddit intelligence / analysis cache
                CREATE TABLE IF NOT EXISTS subreddit_intel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subreddit TEXT NOT NULL UNIQUE,
                    subscribers INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0,
                    posts_per_day REAL DEFAULT 0.0,
                    avg_score REAL DEFAULT 0.0,
                    avg_comments_per_post REAL DEFAULT 0.0,
                    mod_count INTEGER DEFAULT -1,
                    opportunity_score REAL DEFAULT 0.0,
                    relevance_score REAL DEFAULT 0.0,
                    posting_rules TEXT,         -- JSON summary of rules
                    top_themes TEXT,            -- JSON array of current hot themes
                    best_posting_hours TEXT,    -- JSON array of {hour, avg_score}
                    metadata TEXT,              -- JSON for extra data
                    last_analyzed TEXT DEFAULT (datetime('now')),
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Decision audit log for transparency
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    client_id INTEGER,
                    action_type TEXT NOT NULL,  -- skip, post, comment, escalate
                    target_id TEXT,             -- reddit post/comment id
                    decision TEXT NOT NULL,     -- approved, rejected, deferred
                    reason TEXT,                -- human-readable explanation
                    score REAL DEFAULT 0.0,     -- confidence/opportunity score
                    metadata TEXT               -- JSON for extra context
                );

                -- Failure pattern tracking for self-improvement
                CREATE TABLE IF NOT EXISTS failure_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    client_id INTEGER,
                    error_type TEXT NOT NULL,   -- rate_limit, shadowban, removed, api_error, etc
                    context TEXT,               -- JSON: subreddit, account, action attempted
                    resolution TEXT,            -- what was done about it
                    llm_analysis TEXT,          -- LLM's analysis of root cause
                    frequency INTEGER DEFAULT 1,
                    last_seen TEXT DEFAULT (datetime('now'))
                );

                -- Account health monitoring
                CREATE TABLE IF NOT EXISTS account_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    status TEXT DEFAULT 'healthy',  -- healthy, warning, cooldown, banned
                    last_check TEXT DEFAULT (datetime('now')),
                    shadowban_confidence REAL DEFAULT 0.0,  -- 0.0 to 1.0
                    indicators_json TEXT,       -- JSON: {karma_drop, removed_count, etc}
                    cooldown_until TEXT,         -- ISO datetime when cooldown expires
                    action_count_1h INTEGER DEFAULT 0,
                    action_count_24h INTEGER DEFAULT 0,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- v2 Indexes
                CREATE INDEX IF NOT EXISTS idx_subreddit_intel_score
                    ON subreddit_intel(opportunity_score DESC);
                CREATE INDEX IF NOT EXISTS idx_subreddit_intel_analyzed
                    ON subreddit_intel(last_analyzed);
                CREATE INDEX IF NOT EXISTS idx_decision_log_ts
                    ON decision_log(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_decision_log_client
                    ON decision_log(client_id, action_type, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_failure_patterns_type
                    ON failure_patterns(error_type, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_failure_patterns_client
                    ON failure_patterns(client_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_account_health_status
                    ON account_health(status);
                CREATE INDEX IF NOT EXISTS idx_account_health_username
                    ON account_health(username);
            """)
            conn.commit()

    # ── Auto-Maintenance ─────────────────────────────────────────────

    def _maybe_maintenance(self):
        """Run periodic maintenance: WAL checkpoint + old data cleanup."""
        now = datetime.utcnow()
        if (now - self._last_cleanup).total_seconds() < _CLEANUP_INTERVAL_HOURS * 3600:
            return
        self._last_cleanup = now
        try:
            self._wal_checkpoint()
            self._cleanup_old_data()
        except Exception as e:
            logger.warning(f"Maintenance error (non-fatal): {e}")

    def _wal_checkpoint(self):
        """Force a WAL checkpoint to keep the WAL file from growing unbounded."""
        try:
            with self._lock:
                self._get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")

    def _cleanup_old_data(self, days: int = 30):
        """Remove old data that's no longer needed."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        tables_and_cols = [
            ("action_log", "created_at"),
            ("performance_log", "recorded_at"),
            ("decision_log", "timestamp"),
            ("failure_patterns", "timestamp"),
            ("content_hashes", "created_at"),
        ]
        with self._lock:
            conn = self._get_conn()
            total_deleted = 0
            for table, col in tables_and_cols:
                try:
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE {col} < ?", (cutoff,)
                    )
                    total_deleted += cur.rowcount
                except sqlite3.OperationalError:
                    pass  # table might not exist yet
            conn.commit()
            if total_deleted > 0:
                logger.info(f"Cleanup: removed {total_deleted} rows older than {days} days")

    # ── Account Operations ──────────────────────────────────────────

    def upsert_account(self, username: str, **kwargs) -> int:
        existing = self.fetchone("SELECT id FROM accounts WHERE username = ?", (username,))
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            if sets:
                self.execute(f"UPDATE accounts SET {sets}, updated_at = datetime('now') WHERE username = ?",
                             (*kwargs.values(), username))
                self.commit()
            return existing["id"]
        else:
            cols = ["username"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_str = ", ".join(cols)
            cur = self.execute(f"INSERT INTO accounts ({col_str}) VALUES ({placeholders})",
                               (username, *kwargs.values()))
            self.commit()
            return cur.lastrowid

    def get_available_account(self, subreddit: str = None) -> Optional[dict]:
        """Get the best available account for posting, respecting daily caps."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        # Reset daily counters if needed
        self.execute("""
            UPDATE accounts SET daily_comments_today = 0, daily_posts_today = 0, daily_reset_date = ?
            WHERE daily_reset_date IS NULL OR daily_reset_date < ?
        """, (today, today))
        self.commit()

        sql = """
            SELECT * FROM accounts
            WHERE enabled = 1
              AND is_shadowbanned = 0
              AND daily_comments_today < CASE karma_tier
                  WHEN 'new' THEN 3
                  WHEN 'growing' THEN 7
                  WHEN 'established' THEN 12
                  WHEN 'veteran' THEN 20
                  ELSE 5 END
            ORDER BY
                CASE WHEN last_action_at IS NULL THEN 0 ELSE 1 END,
                last_action_at ASC
            LIMIT 1
        """
        return self.fetchone(sql)

    def record_action(self, account_id: int, action_type: str, subreddit: str = None,
                      client_id: int = None, reddit_id: str = None, success: bool = True,
                      error_message: str = None):
        """Log an action and update account counters."""
        self.execute("""
            INSERT INTO action_log (account_id, action_type, subreddit, client_id, reddit_id, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (account_id, action_type, subreddit, client_id, reddit_id, int(success), error_message))

        if action_type == "comment":
            self.execute("UPDATE accounts SET daily_comments_today = daily_comments_today + 1, "
                         "total_comments = total_comments + 1, last_action_at = datetime('now'), "
                         "updated_at = datetime('now') WHERE id = ?", (account_id,))
        elif action_type == "post":
            self.execute("UPDATE accounts SET daily_posts_today = daily_posts_today + 1, "
                         "total_posts = total_posts + 1, last_action_at = datetime('now'), "
                         "updated_at = datetime('now') WHERE id = ?", (account_id,))
        self.commit()

    # ── Post Discovery Operations ───────────────────────────────────

    def save_discovered_post(self, reddit_id: str, subreddit: str, title: str,
                             body: str = "", author: str = "", url: str = "",
                             score: int = 0, num_comments: int = 0,
                             created_utc: float = 0, **scores) -> bool:
        """Save a discovered post. Returns True if new, False if already exists."""
        existing = self.fetchone("SELECT id FROM discovered_posts WHERE reddit_id = ?", (reddit_id,))
        if existing:
            return False
        self.execute("""
            INSERT INTO discovered_posts
            (reddit_id, subreddit, title, body, author, url, score, num_comments, created_utc,
             relevance_score, engagement_score, opportunity_score, seo_value_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (reddit_id, subreddit, title, body, author, url, score, num_comments, created_utc,
              scores.get("relevance_score", 0), scores.get("engagement_score", 0),
              scores.get("opportunity_score", 0), scores.get("seo_value_score", 0)))
        self.commit()
        return True

    def get_pending_opportunities(self, client_id: int = None, limit: int = 20) -> list:
        """Get top-scored posts awaiting action."""
        sql = """
            SELECT * FROM discovered_posts
            WHERE status IN ('new', 'queued')
        """
        params = []
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        sql += " ORDER BY opportunity_score DESC LIMIT ?"
        params.append(limit)
        return self.fetchall(sql, tuple(params))

    # ── Comment Operations ──────────────────────────────────────────

    def save_comment(self, post_reddit_id: str, subreddit: str, content: str,
                     client_id: int = None, account_id: int = None,
                     persona_used: str = None, tone_used: str = None,
                     generation_model: str = None, **kwargs) -> int:
        cur = self.execute("""
            INSERT INTO comments
            (post_reddit_id, subreddit, content, client_id, account_id,
             persona_used, tone_used, generation_model, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
        """, (post_reddit_id, subreddit, content, client_id, account_id,
              persona_used, tone_used, generation_model))
        self.commit()
        return cur.lastrowid

    def update_comment_status(self, comment_id: int, status: str, **kwargs):
        sets = ["status = ?"]
        vals = [status]
        for k, v in kwargs.items():
            sets.append(f"{k} = ?")
            vals.append(v)
        self.execute(f"UPDATE comments SET {', '.join(sets)} WHERE id = ?",
                     (*vals, comment_id))
        self.commit()

    # ── Subreddit Operations ────────────────────────────────────────

    def upsert_subreddit(self, name: str, **kwargs) -> int:
        existing = self.fetchone("SELECT id FROM subreddits WHERE name = ?", (name,))
        if existing:
            if kwargs:
                sets = ", ".join(f"{k} = ?" for k in kwargs)
                self.execute(f"UPDATE subreddits SET {sets} WHERE name = ?",
                             (*kwargs.values(), name))
                self.commit()
            return existing["id"]
        else:
            cols = ["name"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(cols))
            cur = self.execute(f"INSERT INTO subreddits ({', '.join(cols)}) VALUES ({placeholders})",
                               (name, *kwargs.values()))
            self.commit()
            return cur.lastrowid

    # ── Content Dedup ───────────────────────────────────────────────

    def is_duplicate_content(self, content_hash: str) -> bool:
        return self.fetchone("SELECT hash FROM content_hashes WHERE hash = ?",
                             (content_hash,)) is not None

    def save_content_hash(self, content_hash: str, content_type: str, subreddit: str = None):
        self.execute("INSERT OR IGNORE INTO content_hashes (hash, content_type, subreddit) VALUES (?, ?, ?)",
                     (content_hash, content_type, subreddit))
        self.commit()

    # ── Performance Tracking ────────────────────────────────────────

    def log_performance(self, metric_type: str, metric_value: float,
                        client_id: int = None, subreddit: str = None,
                        account_id: int = None, tone: str = None,
                        post_type: str = None):
        now = datetime.utcnow()
        self.execute("""
            INSERT INTO performance_log
            (metric_type, metric_value, client_id, subreddit, account_id,
             tone, post_type, day_of_week, hour_of_day)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (metric_type, metric_value, client_id, subreddit, account_id,
              tone, post_type, now.weekday(), now.hour))
        self.commit()

    def get_performance_summary(self, metric_type: str, days: int = 30,
                                client_id: int = None) -> dict:
        """Get aggregated performance metrics."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sql = """
            SELECT AVG(metric_value) as avg_val, MAX(metric_value) as max_val,
                   MIN(metric_value) as min_val, COUNT(*) as sample_count
            FROM performance_log
            WHERE metric_type = ? AND recorded_at > ?
        """
        params = [metric_type, cutoff]
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        return self.fetchone(sql, tuple(params))

    # ── Learned Strategies ──────────────────────────────────────────

    def upsert_strategy(self, strategy_type: str, key: str, value: float,
                        confidence: float = 0.5, sample_count: int = 1,
                        client_id: int = None, subreddit: str = None):
        self.execute("""
            INSERT INTO learned_strategies (strategy_type, key, value, confidence, sample_count, client_id, subreddit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_type, key, client_id, subreddit)
            DO UPDATE SET value = ?, confidence = ?, sample_count = sample_count + ?,
                          updated_at = datetime('now')
        """, (strategy_type, key, value, confidence, sample_count, client_id, subreddit,
              value, confidence, sample_count))
        self.commit()

    def get_strategies(self, strategy_type: str, client_id: int = None,
                       subreddit: str = None) -> list:
        sql = "SELECT * FROM learned_strategies WHERE strategy_type = ?"
        params = [strategy_type]
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        if subreddit:
            sql += " AND subreddit = ?"
            params.append(subreddit)
        sql += " ORDER BY confidence DESC"
        return self.fetchall(sql, tuple(params))

    # ── Subreddit Intelligence (v2) ─────────────────────────────────

    def upsert_subreddit_intel(self, subreddit: str, **kwargs) -> int:
        """Insert or update subreddit intelligence data."""
        existing = self.fetchone(
            "SELECT id FROM subreddit_intel WHERE subreddit = ?", (subreddit,)
        )
        if existing:
            if kwargs:
                sets = ", ".join(f"{k} = ?" for k in kwargs)
                self._execute_write(
                    f"UPDATE subreddit_intel SET {sets}, last_analyzed = datetime('now') "
                    f"WHERE subreddit = ?",
                    (*kwargs.values(), subreddit),
                )
            return existing["id"]
        else:
            cols = ["subreddit"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(cols))
            cur = self._execute_write(
                f"INSERT INTO subreddit_intel ({', '.join(cols)}) VALUES ({placeholders})",
                (subreddit, *kwargs.values()),
            )
            return cur.lastrowid

    def get_subreddit_intel(self, subreddit: str) -> Optional[dict]:
        """Get intelligence data for a subreddit."""
        return self.fetchone(
            "SELECT * FROM subreddit_intel WHERE subreddit = ?", (subreddit,)
        )

    def get_top_subreddit_intel(self, limit: int = 20) -> list:
        """Get subreddits ranked by opportunity score."""
        return self.fetchall(
            "SELECT * FROM subreddit_intel ORDER BY opportunity_score DESC LIMIT ?",
            (limit,),
        )

    def get_stale_subreddit_intel(self, hours: int = 24, limit: int = 10) -> list:
        """Get subreddits that haven't been analyzed recently."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self.fetchall(
            "SELECT * FROM subreddit_intel WHERE last_analyzed < ? "
            "ORDER BY opportunity_score DESC LIMIT ?",
            (cutoff, limit),
        )

    # ── Decision Log (v2) ───────────────────────────────────────────

    def log_decision(self, action_type: str, decision: str, reason: str = "",
                     client_id: int = None, target_id: str = None,
                     score: float = 0.0, metadata: Dict = None):
        """Log a decision for audit trail and transparency."""
        self._execute_write(
            """INSERT INTO decision_log
               (client_id, action_type, target_id, decision, reason, score, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (client_id, action_type, target_id, decision, reason, score,
             json.dumps(metadata) if metadata else None),
        )

    def get_recent_decisions(self, client_id: int = None, action_type: str = None,
                             hours: int = 24, limit: int = 50) -> list:
        """Get recent decisions for review."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        sql = "SELECT * FROM decision_log WHERE timestamp > ?"
        params: list = [cutoff]
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        if action_type:
            sql += " AND action_type = ?"
            params.append(action_type)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        return self.fetchall(sql, tuple(params))

    def get_decision_stats(self, client_id: int = None, days: int = 7) -> dict:
        """Get decision statistics for dashboard."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sql = """
            SELECT decision, COUNT(*) as count, AVG(score) as avg_score
            FROM decision_log WHERE timestamp > ?
        """
        params: list = [cutoff]
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        sql += " GROUP BY decision"
        return self.fetchall(sql, tuple(params))

    # ── Failure Patterns (v2) ───────────────────────────────────────

    def log_failure_pattern(self, error_type: str, context: Dict = None,
                            resolution: str = None, llm_analysis: str = None,
                            client_id: int = None):
        """Log a failure for pattern detection and self-improvement."""
        # Try to update frequency if same error type exists recently
        recent = self.fetchone(
            "SELECT id, frequency FROM failure_patterns "
            "WHERE error_type = ? AND client_id IS ? AND timestamp > datetime('now', '-1 hour')",
            (error_type, client_id),
        )
        if recent:
            self._execute_write(
                "UPDATE failure_patterns SET frequency = frequency + 1, "
                "last_seen = datetime('now'), resolution = COALESCE(?, resolution), "
                "llm_analysis = COALESCE(?, llm_analysis) WHERE id = ?",
                (resolution, llm_analysis, recent["id"]),
            )
        else:
            self._execute_write(
                """INSERT INTO failure_patterns
                   (client_id, error_type, context, resolution, llm_analysis)
                   VALUES (?, ?, ?, ?, ?)""",
                (client_id, error_type,
                 json.dumps(context) if context else None,
                 resolution, llm_analysis),
            )

    def get_failure_patterns(self, error_type: str = None, client_id: int = None,
                             days: int = 7, limit: int = 20) -> list:
        """Get recent failure patterns."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sql = "SELECT * FROM failure_patterns WHERE timestamp > ?"
        params: list = [cutoff]
        if error_type:
            sql += " AND error_type = ?"
            params.append(error_type)
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        sql += " ORDER BY frequency DESC, timestamp DESC LIMIT ?"
        params.append(limit)
        return self.fetchall(sql, tuple(params))

    def get_top_failure_types(self, days: int = 7) -> list:
        """Get most frequent failure types."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self.fetchall(
            """SELECT error_type, SUM(frequency) as total_count, COUNT(*) as unique_events,
                      MAX(timestamp) as last_seen
               FROM failure_patterns WHERE timestamp > ?
               GROUP BY error_type ORDER BY total_count DESC LIMIT 10""",
            (cutoff,),
        )

    # ── Account Health (v2) ─────────────────────────────────────────

    def upsert_account_health(self, username: str, status: str = "healthy",
                              shadowban_confidence: float = 0.0,
                              indicators: Dict = None,
                              cooldown_until: str = None,
                              notes: str = None) -> int:
        """Insert or update account health record."""
        existing = self.fetchone(
            "SELECT id FROM account_health WHERE username = ?", (username,)
        )
        indicators_json = json.dumps(indicators) if indicators else None
        if existing:
            self._execute_write(
                """UPDATE account_health SET
                   status = ?, last_check = datetime('now'),
                   shadowban_confidence = ?, indicators_json = COALESCE(?, indicators_json),
                   cooldown_until = COALESCE(?, cooldown_until),
                   notes = COALESCE(?, notes),
                   updated_at = datetime('now')
                   WHERE username = ?""",
                (status, shadowban_confidence, indicators_json,
                 cooldown_until, notes, username),
            )
            return existing["id"]
        else:
            cur = self._execute_write(
                """INSERT INTO account_health
                   (username, status, shadowban_confidence, indicators_json,
                    cooldown_until, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, status, shadowban_confidence, indicators_json,
                 cooldown_until, notes),
            )
            return cur.lastrowid

    def get_account_health(self, username: str) -> Optional[dict]:
        """Get health status for an account."""
        return self.fetchone(
            "SELECT * FROM account_health WHERE username = ?", (username,)
        )

    def get_accounts_needing_cooldown(self) -> list:
        """Get accounts currently in cooldown."""
        now = datetime.utcnow().isoformat()
        return self.fetchall(
            "SELECT * FROM account_health WHERE cooldown_until IS NOT NULL AND cooldown_until > ?",
            (now,),
        )

    def get_unhealthy_accounts(self) -> list:
        """Get accounts with non-healthy status."""
        return self.fetchall(
            "SELECT * FROM account_health WHERE status != 'healthy' ORDER BY shadowban_confidence DESC"
        )

    def is_account_in_cooldown(self, username: str) -> bool:
        """Check if an account is currently in cooldown."""
        now = datetime.utcnow().isoformat()
        row = self.fetchone(
            "SELECT id FROM account_health WHERE username = ? AND cooldown_until > ?",
            (username, now),
        )
        return row is not None

    def clear_cooldown(self, username: str):
        """Clear cooldown for an account."""
        self._execute_write(
            "UPDATE account_health SET cooldown_until = NULL, status = 'healthy', "
            "updated_at = datetime('now') WHERE username = ?",
            (username,),
        )
