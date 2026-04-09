"""
RedditPilot agent integration for ProofPilot Agent Hub.

Lazy-loads the vendored `redditpilot` package and manages a singleton
orchestrator instance. All heavy imports (praw, bs4, apscheduler) happen
on first use — Agent Hub starts fine even if deps are broken or no
config file exists.

Config file lives at $REDDITPILOT_CONFIG_PATH or
$DOCS_DIR/redditpilot/config.yaml (Railway volume persistent path).

Routes in server.py import helper functions from this module instead of
talking HTTP to a separate service. Everything runs in-process.

SAFETY: get_orch() instantiates the RedditPilot orchestrator but does
NOT call .start() — autonomous cycles only run when the user explicitly
clicks "Start Scheduler" from the dashboard. This prevents accidental
posting after a deploy.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("proofpilot.reddit_agent")

# ── Config path resolution ────────────────────────────────────────
# Priority:
#   1. $REDDITPILOT_CONFIG_PATH (explicit override)
#   2. $DOCS_DIR/redditpilot/config.yaml (Railway volume)
#   3. ./data/redditpilot/config.yaml (local dev)
_DEFAULT_DATA_DIR = Path(os.environ.get("DOCS_DIR", "./data")) / "redditpilot"
_CONFIG_PATH = Path(
    os.environ.get("REDDITPILOT_CONFIG_PATH", _DEFAULT_DATA_DIR / "config.yaml")
)

# Seeded template path — bundled in the Docker image. If no user config
# exists on the volume, we copy this template on first access so the
# orchestrator can boot with all clients pre-populated.
_SEEDED_TEMPLATE = Path(__file__).parent / "redditpilot" / "config.seeded.yaml"


def config_path() -> Path:
    return _CONFIG_PATH


def seeded_template_path() -> Path:
    return _SEEDED_TEMPLATE


def is_configured() -> bool:
    """True if a RedditPilot config file exists (user config OR seeded template)."""
    return _CONFIG_PATH.exists() or _SEEDED_TEMPLATE.exists()


def _bootstrap_config() -> bool:
    """If no user config exists but the seeded template does, copy it to
    the user config path. Returns True if a config file is available."""
    if _CONFIG_PATH.exists():
        return True
    if not _SEEDED_TEMPLATE.exists():
        return False
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SEEDED_TEMPLATE, _CONFIG_PATH)
        logger.info(f"RedditPilot: bootstrapped user config from seeded template → {_CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"RedditPilot: failed to bootstrap config: {e}")
        return False


# ── Singleton orchestrator ────────────────────────────────────────
_orch = None
_orch_lock = threading.Lock()
_orch_error: Optional[str] = None
_init_time: Optional[float] = None


def get_orch():
    """Return the RedditPilot orchestrator singleton, or None if unavailable.

    On first call, attempts to import the vendored `redditpilot` package,
    load config, and instantiate the orchestrator. Errors are captured in
    `_orch_error` and returned as None so the frontend can show a clear
    "not configured" state.

    IMPORTANT: Does NOT start the orchestrator's APScheduler. The scheduler
    must be explicitly started via POST /api/reddit/control/start_scheduler
    to avoid accidental autonomous posting after deploys.
    """
    global _orch, _orch_error, _init_time
    if _orch is not None:
        return _orch
    with _orch_lock:
        if _orch is not None:
            return _orch
        # Bootstrap user config from seeded template if needed
        if not _bootstrap_config():
            _orch_error = (
                f"No config file found. Expected user config at {_CONFIG_PATH} "
                f"or seeded template at {_SEEDED_TEMPLATE}"
            )
            return None
        try:
            # Lazy import — avoids loading praw/bs4 until actually needed
            from redditpilot.core.config import Config
            from redditpilot.orchestrator import RedditPilot

            cfg = Config.load(str(_CONFIG_PATH))
            # Force data_dir to the config's parent so DB lives alongside config
            cfg.data_dir = str(_CONFIG_PATH.parent)

            # Wire LLM API keys from Agent Hub env vars.
            # Primary: OpenRouter (preferred — matches pipeline/image_gen.py convention).
            # Fallback: REDDITPILOT_LLM_API_KEY for backwards compat.
            if not cfg.llm.primary_api_key:
                cfg.llm.primary_api_key = (
                    os.environ.get("OPENROUTER_API_KEY", "")
                    or os.environ.get("REDDITPILOT_LLM_API_KEY", "")
                )
            if not cfg.llm.fallback_api_key:
                cfg.llm.fallback_api_key = (
                    os.environ.get("ANTHROPIC_API_KEY", "")
                    or os.environ.get("REDDITPILOT_LLM_FALLBACK_KEY", "")
                )

            _orch = RedditPilot(cfg)
            _init_time = __import__("time").time()
            _init_logger_capture()
            n_clients = len(cfg.get_enabled_clients())
            n_accounts = len(cfg.get_enabled_accounts())
            logger.info(
                f"RedditPilot orchestrator initialized from {_CONFIG_PATH} "
                f"({n_clients} clients, {n_accounts} accounts, "
                f"llm={cfg.llm.primary_provider}/{cfg.llm.primary_model}, "
                f"key_set={bool(cfg.llm.primary_api_key)})"
            )
            return _orch
        except Exception as e:
            _orch_error = f"{type(e).__name__}: {e}"
            logger.error(f"Failed to init RedditPilot: {e}", exc_info=True)
            return None


def get_error() -> Optional[str]:
    return _orch_error


def shutdown():
    """Gracefully shut down the orchestrator (called by FastAPI shutdown)."""
    global _orch
    with _orch_lock:
        if _orch is None:
            return
        try:
            if hasattr(_orch, "scheduler") and _orch.scheduler.running:
                _orch.scheduler.shutdown(wait=False)
            if hasattr(_orch, "resource_monitor"):
                try:
                    _orch.resource_monitor.stop()
                except Exception:
                    pass
            logger.info("RedditPilot orchestrator shut down")
        except Exception as e:
            logger.warning(f"Error during RedditPilot shutdown: {e}")


def reset():
    """Drop the cached orchestrator (e.g., after config change)."""
    global _orch, _orch_error, _init_time
    shutdown()
    with _orch_lock:
        _orch = None
        _orch_error = None
        _init_time = None


# ── Log capture for WebSocket ─────────────────────────────────────
_log_capture = None


class _LogCapture(logging.Handler):
    """Captures log records for WebSocket broadcast (mirrors RedditPilot's pattern)."""

    def __init__(self, maxlen: int = 500):
        super().__init__()
        self.records: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord):
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            msg = record.getMessage()[:300]
            name_lower = record.name.lower()
            msg_lower = msg.lower()
            cat = ""
            if "scan" in name_lower or "scan" in msg_lower:
                cat = "SCAN"
            elif "action" in msg_lower or "post" in msg_lower or "comment" in msg_lower:
                cat = "ACT"
            elif "learn" in msg_lower:
                cat = "LEARN"
            elif "error" in msg_lower or record.levelno >= logging.ERROR:
                cat = "ERR"
            elif "discover" in msg_lower:
                cat = "DISC"
            elif "safety" in msg_lower or "ban" in msg_lower or "dedup" in msg_lower:
                cat = "SAFE"
            with self._lock:
                self._seq += 1
                entry = {
                    "seq": self._seq,
                    "ts": ts,
                    "level": record.levelname,
                    "cat": cat,
                    "msg": msg,
                }
                self.records.append(entry)
        except Exception:
            pass

    def snapshot(self) -> List[dict]:
        with self._lock:
            return list(self.records)

    def since(self, seq: int) -> List[dict]:
        with self._lock:
            return [r for r in self.records if r["seq"] > seq]


def _init_logger_capture():
    """Attach log capture handler to the redditpilot logger tree."""
    global _log_capture
    if _log_capture is not None:
        return _log_capture
    _log_capture = _LogCapture(maxlen=500)
    rp_logger = logging.getLogger("redditpilot")
    rp_logger.addHandler(_log_capture)
    if rp_logger.level == logging.NOTSET:
        rp_logger.setLevel(logging.INFO)
    return _log_capture


def log_capture() -> Optional[_LogCapture]:
    return _log_capture


# ══════════════════════════════════════════════════════════════════
# Data query helpers — all return JSON-safe plain dicts
# ══════════════════════════════════════════════════════════════════


def _cutoff_hours(hours: int) -> str:
    return (datetime.utcnow() - timedelta(hours=hours)).isoformat()


def _cutoff_days(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


def _safe_db(orch):
    """Return the orchestrator's db or None if not available."""
    if orch is None:
        return None
    return getattr(orch, "db", None)


def not_configured_payload(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = {
        "connected": False,
        "configured": is_configured(),
        "error": _orch_error,
        "mode": "stopped",
        "paused": False,
        "uptime_seconds": 0,
        "client_count": 0,
        "account_count": 0,
        "cycle_count": 0,
    }
    if extra:
        base.update(extra)
    return base


def get_status() -> Dict[str, Any]:
    """Return orchestrator status (paused, uptime, client/account counts, resources)."""
    orch = get_orch()
    if not orch:
        return not_configured_payload()
    try:
        clients = [
            {"name": c.name, "slug": c.slug, "industry": c.industry, "enabled": c.enabled}
            for c in orch.config.get_enabled_clients()
        ]
        paused = getattr(orch, "_paused", False)
        running = getattr(orch, "_running", False)
        scheduler_running = False
        try:
            scheduler_running = bool(orch.scheduler.running)
        except Exception:
            pass
        if paused:
            mode = "paused"
        elif scheduler_running or running:
            mode = "running"
        else:
            mode = "stopped"

        uptime = 0
        if _init_time:
            uptime = int(__import__("time").time() - _init_time)

        # Resource snapshot (doesn't require resource_monitor.start())
        resources = {}
        try:
            rm = orch.resource_monitor
            if hasattr(rm, "get_status_dict"):
                resources = rm.get_status_dict()
        except Exception as e:
            logger.debug(f"Failed to get resource status: {e}")

        return {
            "connected": True,
            "configured": True,
            "mode": mode,
            "paused": paused,
            "running": running,
            "scheduler_running": scheduler_running,
            "uptime_seconds": uptime,
            "clients": clients,
            "client_count": len(clients),
            "account_count": len(orch.config.get_enabled_accounts()),
            "cycle_count": getattr(orch, "_cycle_count", 0),
            "emergency_stopped": getattr(orch, "_emergency_stopped", False),
            "resources": resources,
        }
    except Exception as e:
        logger.error(f"get_status error: {e}", exc_info=True)
        return not_configured_payload({"error": str(e), "connected": True, "configured": True})


def get_stats(hours: int = 24) -> Dict[str, Any]:
    """24h action statistics by client, type, subreddit."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"total": 0, "by_type": {}, "by_client": {}, "by_subreddit": {},
                "success_rate": 0, "pending_opportunities": 0}
    try:
        cutoff = _cutoff_hours(hours)
        total_row = db.fetchone("SELECT COUNT(*) as cnt FROM action_log WHERE created_at > ?", (cutoff,))
        total = total_row["cnt"] if total_row else 0

        by_type_rows = db.fetchall(
            "SELECT action_type, COUNT(*) as cnt FROM action_log "
            "WHERE created_at > ? GROUP BY action_type ORDER BY cnt DESC",
            (cutoff,),
        )
        by_type = {r["action_type"]: r["cnt"] for r in by_type_rows}

        by_client_rows = db.fetchall(
            "SELECT c.name, COUNT(*) as cnt FROM action_log al "
            "LEFT JOIN clients c ON al.client_id = c.id "
            "WHERE al.created_at > ? GROUP BY al.client_id ORDER BY cnt DESC",
            (cutoff,),
        )
        by_client = {(r["name"] or "unassigned"): r["cnt"] for r in by_client_rows}

        by_sub_rows = db.fetchall(
            "SELECT subreddit, COUNT(*) as cnt FROM action_log WHERE created_at > ? "
            "AND subreddit IS NOT NULL GROUP BY subreddit ORDER BY cnt DESC LIMIT 20",
            (cutoff,),
        )
        by_subreddit = {r["subreddit"]: r["cnt"] for r in by_sub_rows}

        success_row = db.fetchone(
            "SELECT COUNT(*) as cnt FROM action_log WHERE created_at > ? AND success = 1",
            (cutoff,),
        )
        successes = success_row["cnt"] if success_row else 0

        pending_row = db.fetchone(
            "SELECT COUNT(*) as cnt FROM discovered_posts WHERE status IN ('new', 'queued')"
        )
        pending = pending_row["cnt"] if pending_row else 0

        return {
            "total": total,
            "actions_24h": total,  # alias for frontend compatibility
            "by_type": by_type,
            "by_client": by_client,
            "by_subreddit": by_subreddit,
            "success_rate": round(successes / max(total, 1), 3),
            "pending_opportunities": pending,
            "successes": successes,
        }
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return {"total": 0, "by_type": {}, "by_client": {}, "by_subreddit": {},
                "success_rate": 0, "pending_opportunities": 0, "error": str(e)}


def get_clients() -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    result = []
    try:
        cutoff = _cutoff_hours(24)
        for client in orch.config.get_enabled_clients():
            crow = db.fetchone("SELECT id FROM clients WHERE slug = ?", (client.slug,))
            cid = crow["id"] if crow else None
            actions_24h = 0
            pending = 0
            comments_posted = 0
            if cid:
                a = db.fetchone(
                    "SELECT COUNT(*) as cnt FROM action_log WHERE client_id = ? AND created_at > ?",
                    (cid, cutoff),
                )
                actions_24h = a["cnt"] if a else 0
                p = db.fetchone(
                    "SELECT COUNT(*) as cnt FROM discovered_posts WHERE client_id = ? AND status IN ('new','queued')",
                    (cid,),
                )
                pending = p["cnt"] if p else 0
                c2 = db.fetchone(
                    "SELECT COUNT(*) as cnt FROM comments WHERE client_id = ? AND status = 'posted'",
                    (cid,),
                )
                comments_posted = c2["cnt"] if c2 else 0

            result.append({
                "name": client.name, "slug": client.slug,
                "industry": client.industry, "service_area": client.service_area,
                "website": client.website, "enabled": client.enabled,
                "brand_voice": client.brand_voice,
                "promo_ratio": client.promo_ratio,
                "keyword_count": len(client.keywords or []),
                "subreddit_count": len(client.target_subreddits or []),
                "target_subreddits": list(client.target_subreddits or []),
                "keywords": list(client.keywords or []),
                "actions_24h": actions_24h,
                "total_actions": actions_24h,
                "pending_opportunities": pending,
                "comments_posted": comments_posted,
            })
    except Exception as e:
        logger.error(f"get_clients error: {e}")
    return result


def get_client_detail(slug: str) -> Dict[str, Any]:
    orch = get_orch()
    db = _safe_db(orch)
    if not orch or not db:
        return {"error": "not configured"}
    client = None
    for c in orch.config.get_enabled_clients():
        if c.slug == slug:
            client = c
            break
    if not client:
        return {"error": "client not found"}
    try:
        crow = db.fetchone("SELECT id FROM clients WHERE slug = ?", (slug,))
        cid = crow["id"] if crow else None
        performance: Dict[str, Any] = {}
        recent_comments: List[Dict[str, Any]] = []
        assigned_subs: List[Dict[str, Any]] = []

        if cid:
            cutoff = _cutoff_hours(24)
            perf = db.fetchone(
                "SELECT COUNT(*) as total_actions, "
                "SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes "
                "FROM action_log WHERE client_id = ? AND created_at > ?",
                (cid, cutoff),
            )
            if perf:
                ta = perf["total_actions"] or 0
                performance = {
                    "total_actions": ta,
                    "actions_24h": ta,
                    "success_rate": round((perf["successes"] or 0) / max(ta, 1), 3),
                }
            cperf = db.fetchone(
                "SELECT COUNT(*) as total, AVG(score) as avg_score "
                "FROM comments WHERE client_id = ? AND status = 'posted'",
                (cid,),
            )
            if cperf:
                performance["total_comments"] = cperf["total"] or 0
                performance["avg_comment_score"] = round(cperf["avg_score"] or 0, 1)

            rc_rows = db.fetchall(
                "SELECT reddit_comment_id, subreddit, content, score, status, posted_at "
                "FROM comments WHERE client_id = ? ORDER BY created_at DESC LIMIT 10",
                (cid,),
            )
            recent_comments = list(rc_rows)

            sub_rows = db.fetchall(
                "SELECT s.name, s.subscribers, s.relevance_score, s.tier "
                "FROM client_subreddits cs "
                "JOIN subreddits s ON cs.subreddit_id = s.id "
                "WHERE cs.client_id = ? ORDER BY cs.relevance_score DESC",
                (cid,),
            )
            assigned_subs = list(sub_rows)

        return {
            "name": client.name, "slug": client.slug,
            "industry": client.industry, "service_area": client.service_area,
            "website": client.website, "brand_voice": client.brand_voice,
            "keywords": list(client.keywords or []),
            "target_subreddits": list(client.target_subreddits or []),
            "enabled": client.enabled,
            "performance": performance,
            "recent_comments": recent_comments,
            "assigned_subreddits": assigned_subs,
        }
    except Exception as e:
        logger.error(f"get_client_detail error: {e}")
        return {"error": str(e)}


def get_accounts() -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    result = []
    try:
        for account in orch.config.get_enabled_accounts():
            username = account.username
            acc_row = db.fetchone("SELECT * FROM accounts WHERE username = ?", (username,)) or {}
            health_row = None
            try:
                health_row = db.get_account_health(username)
            except Exception:
                pass
            comment_karma = acc_row.get("comment_karma", 0) or 0
            post_karma = acc_row.get("post_karma", 0) or 0
            daily_comments_today = acc_row.get("daily_comments_today", 0) or 0
            daily_posts_today = acc_row.get("daily_posts_today", 0) or 0
            is_shadowbanned = bool(acc_row.get("is_shadowbanned", 0))

            result.append({
                "username": username,
                "karma_tier": acc_row.get("karma_tier") or account.karma_tier,
                "karma": comment_karma + post_karma,
                "comment_karma": comment_karma,
                "post_karma": post_karma,
                "account_age_days": acc_row.get("account_age_days", 0),
                "daily_comments": daily_comments_today,
                "daily_posts": daily_posts_today,
                "daily_comment_cap": account.daily_comment_cap,
                "daily_post_cap": account.daily_post_cap,
                "daily_remaining": max(account.daily_comment_cap - daily_comments_today, 0),
                "shadowbanned": is_shadowbanned,
                "healthy": not is_shadowbanned and (health_row is None or health_row.get("status") in (None, "healthy")),
                "health_status": (health_row or {}).get("status", "unknown"),
                "last_action_at": acc_row.get("last_action_at"),
                "enabled": account.enabled,
            })
    except Exception as e:
        logger.error(f"get_accounts error: {e}")
    return result


def get_opportunities(limit: int = 50) -> List[Dict[str, Any]]:
    """Return scored discovered_posts awaiting action."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        rows = db.fetchall(
            "SELECT dp.id, dp.reddit_id, dp.subreddit, dp.title, dp.author, dp.url, "
            "       dp.score as reddit_score, dp.num_comments, dp.opportunity_score, "
            "       dp.relevance_score, dp.engagement_score, dp.seo_value_score, "
            "       dp.status, dp.discovered_at, c.name as client_name, c.slug as client_slug "
            "FROM discovered_posts dp "
            "LEFT JOIN clients c ON dp.client_id = c.id "
            "WHERE dp.status IN ('new', 'queued') "
            "ORDER BY dp.opportunity_score DESC, dp.discovered_at DESC LIMIT ?",
            (limit,),
        )
        result = []
        for r in rows:
            # Compute age_hours from discovered_at
            age_hours = None
            try:
                dt = datetime.fromisoformat(r["discovered_at"])
                age_hours = round((datetime.utcnow() - dt).total_seconds() / 3600, 1)
            except Exception:
                pass
            r["age_hours"] = age_hours
            r["score"] = r.get("opportunity_score")  # alias for frontend
            r["client"] = r.get("client_name")
            r["created_at"] = r.get("discovered_at")  # alias
            result.append(r)
        return result
    except Exception as e:
        logger.error(f"get_opportunities error: {e}")
        return []


def get_actions(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        rows = db.fetchall(
            "SELECT al.id, al.action_type, al.subreddit, al.reddit_id, al.success, "
            "       al.error_message, al.created_at, "
            "       c.name as client_name, a.username as account_username "
            "FROM action_log al "
            "LEFT JOIN clients c ON al.client_id = c.id "
            "LEFT JOIN accounts a ON al.account_id = a.id "
            "WHERE al.created_at > ? "
            "ORDER BY al.created_at DESC LIMIT ?",
            (_cutoff_hours(hours), limit),
        )
        # Alias fields for frontend convenience
        for r in rows:
            r["status"] = "success" if r.get("success") else "failed"
            r["client"] = r.get("client_name")
        return rows
    except Exception as e:
        logger.error(f"get_actions error: {e}")
        return []


def get_history(days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        rows = db.fetchall(
            "SELECT al.id, al.action_type, al.subreddit, al.success, al.error_message, "
            "       al.created_at, c.name as client_name, a.username as account_username "
            "FROM action_log al "
            "LEFT JOIN clients c ON al.client_id = c.id "
            "LEFT JOIN accounts a ON al.account_id = a.id "
            "WHERE al.created_at > ? "
            "ORDER BY al.created_at DESC LIMIT ?",
            (_cutoff_days(days), limit),
        )
        for r in rows:
            r["status"] = "success" if r.get("success") else "failed"
            r["client"] = r.get("client_name")
        return rows
    except Exception as e:
        logger.error(f"get_history error: {e}")
        return []


def get_comments(hours: int = 168, limit: int = 50) -> List[Dict[str, Any]]:
    """Posted comments with content + scores."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        rows = db.fetchall(
            "SELECT cm.id, cm.reddit_comment_id, cm.subreddit, cm.content, cm.score, "
            "       cm.engagement_count, cm.status, cm.posted_at, cm.created_at, "
            "       c.name as client_name, a.username as account_username "
            "FROM comments cm "
            "LEFT JOIN clients c ON cm.client_id = c.id "
            "LEFT JOIN accounts a ON cm.account_id = a.id "
            "WHERE cm.created_at > ? "
            "ORDER BY cm.created_at DESC LIMIT ?",
            (_cutoff_hours(hours), limit),
        )
        return rows
    except Exception as e:
        logger.error(f"get_comments error: {e}")
        return []


def get_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    """Orchestrator alert log (auto-pause events, resource warnings)."""
    orch = get_orch()
    if not orch:
        return []
    try:
        raw = list(getattr(orch, "_alert_log", []))[-limit:]
        return [{"timestamp": t, "message": m} for t, m in raw]
    except Exception as e:
        logger.error(f"get_alerts error: {e}")
        return []


def get_schedule() -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"jobs": [], "scheduler_running": False}
    try:
        jobs = []
        for job in orch.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name or job.id,
                "trigger": str(job.trigger),
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "active": True,
            })
        return {
            "jobs": jobs,
            "scheduler_running": bool(orch.scheduler.running),
            "scan_interval_minutes": orch.config.scan_interval_minutes,
            "learning_interval_hours": orch.config.learning_interval_hours,
        }
    except Exception as e:
        return {"jobs": [], "scheduler_running": False, "error": str(e)}


def get_insights() -> Dict[str, Any]:
    """A/B test results + top subreddits + learned strategies."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"ab_tests": [], "top_subreddits": [], "strategies": []}
    try:
        ab_rows = db.fetchall(
            "SELECT id, name, dimension, variants, status, winner, sample_size, "
            "       significance, created_at, concluded_at "
            "FROM ab_experiments "
            "ORDER BY created_at DESC LIMIT 20"
        )
        ab_tests = []
        for r in ab_rows:
            try:
                variants = json.loads(r.get("variants") or "[]")
            except Exception:
                variants = []
            ab_tests.append({
                "id": r["id"],
                "name": r["name"],
                "dimension": r["dimension"],
                "variants": variants,
                "status": r["status"],
                "winner": r["winner"],
                "sample_size": r["sample_size"],
                "confidence": r.get("significance", 0),
                "created_at": r["created_at"],
                "concluded_at": r.get("concluded_at"),
            })

        top_subs_rows = db.fetchall(
            "SELECT subreddit, COUNT(*) as action_count, "
            "       AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) as success_rate "
            "FROM action_log WHERE subreddit IS NOT NULL "
            "GROUP BY subreddit ORDER BY action_count DESC LIMIT 10"
        )
        top_subs = [
            {"subreddit": r["subreddit"], "actions": r["action_count"],
             "engagement_rate": r["success_rate"] or 0}
            for r in top_subs_rows
        ]

        strat_rows = db.fetchall(
            "SELECT strategy_type, key, value, confidence, sample_count "
            "FROM learned_strategies "
            "WHERE confidence > 0.5 "
            "ORDER BY confidence DESC, sample_count DESC LIMIT 10"
        )
        strategies = [
            {
                "strategy": f"{r['strategy_type']}: {r['key']}",
                "insight": f"Score {r['value']:.2f} (confidence {r['confidence']:.0%}, n={r['sample_count']})",
            }
            for r in strat_rows
        ]

        return {"ab_tests": ab_tests, "top_subreddits": top_subs, "strategies": strategies}
    except Exception as e:
        logger.error(f"get_insights error: {e}")
        return {"ab_tests": [], "top_subreddits": [], "strategies": [], "error": str(e)}


def get_performance(days: int = 7) -> Dict[str, Any]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"daily": []}
    try:
        rows = db.fetchall(
            "SELECT DATE(created_at) as day, "
            "       COUNT(*) as actions, "
            "       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes "
            "FROM action_log WHERE created_at > ? "
            "GROUP BY DATE(created_at) ORDER BY day",
            (_cutoff_days(days),),
        )
        return {
            "daily": [
                {"date": r["day"], "actions": r["actions"], "successes": r["successes"] or 0}
                for r in rows
            ]
        }
    except Exception as e:
        return {"daily": [], "error": str(e)}


def get_heatmap() -> Dict[str, Any]:
    """Return 7x24 activity grid (Mon-Sun × hour)."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"grid": [[0] * 24 for _ in range(7)]}
    try:
        grid = [[0 for _ in range(24)] for _ in range(7)]
        rows = db.fetchall(
            "SELECT created_at FROM action_log WHERE created_at > ?",
            (_cutoff_days(7),),
        )
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["created_at"])
                grid[dt.weekday()][dt.hour] += 1
            except Exception:
                continue
        return {"grid": grid}
    except Exception as e:
        return {"grid": [[0] * 24 for _ in range(7)], "error": str(e)}


def get_funnel() -> Dict[str, Any]:
    """Return conversion funnel stages."""
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"stages": []}
    try:
        discovered = db.fetchone("SELECT COUNT(*) as cnt FROM discovered_posts")
        scored = db.fetchone(
            "SELECT COUNT(*) as cnt FROM discovered_posts WHERE opportunity_score > 0"
        )
        queued = db.fetchone("SELECT COUNT(*) as cnt FROM discovered_posts WHERE status = 'queued'")
        posted_ok = db.fetchone(
            "SELECT COUNT(*) as cnt FROM comments WHERE status = 'posted'"
        )
        stages = [
            {"stage": "Discovered", "count": discovered["cnt"] if discovered else 0},
            {"stage": "Scored", "count": scored["cnt"] if scored else 0},
            {"stage": "Queued", "count": queued["cnt"] if queued else 0},
            {"stage": "Posted", "count": posted_ok["cnt"] if posted_ok else 0},
        ]
        return {"stages": stages}
    except Exception as e:
        return {"stages": [], "error": str(e)}


def get_summary() -> Dict[str, Any]:
    return {"status": get_status(), "stats": get_stats(24), "alerts": get_alerts(5)}


def get_decisions(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        if hasattr(db, "get_recent_decisions"):
            return db.get_recent_decisions(hours=hours, limit=limit)
    except Exception as e:
        logger.error(f"get_decisions error: {e}")
    return []


def get_failures(days: int = 7, limit: int = 20) -> Dict[str, Any]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return {"patterns": [], "top_types": []}
    try:
        patterns = db.get_failure_patterns(days=days, limit=limit)
        top_types = db.get_top_failure_types(days=days)
        return {"patterns": patterns, "top_types": top_types}
    except Exception as e:
        logger.error(f"get_failures error: {e}")
        return {"patterns": [], "top_types": [], "error": str(e)}


def get_subreddit_intel(limit: int = 20) -> List[Dict[str, Any]]:
    orch = get_orch()
    db = _safe_db(orch)
    if not db:
        return []
    try:
        rows = db.fetchall(
            "SELECT subreddit, subscribers, active_users, posts_per_day, "
            "       avg_score, avg_comments_per_post, opportunity_score, "
            "       relevance_score, top_themes, last_analyzed "
            "FROM subreddit_intel "
            "ORDER BY opportunity_score DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            try:
                r["top_themes"] = json.loads(r.get("top_themes") or "[]")
            except Exception:
                r["top_themes"] = []
        return rows
    except Exception as e:
        logger.error(f"get_subreddit_intel error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# Control actions
# ══════════════════════════════════════════════════════════════════


def control(action: str) -> Dict[str, Any]:
    """Execute a control action against the orchestrator."""
    orch = get_orch()
    if not orch:
        return {"ok": False, "error": "RedditPilot not configured"}

    if getattr(orch, "_emergency_stopped", False) and action != "emergency_reset":
        return {"ok": False, "error": "Emergency stop active — use emergency_reset first"}

    safe_methods = {
        "scan": "_scan_safe",
        "learn": "_learn_safe",
        "discover": "_discover_safe",
        "generate": "_generate_safe",
        "post": "_post_safe",
        "cycle": "_run_cycle_safe",
        "verify": "_verify_comments_safe",
        "health_check": "_health_check_safe",
    }

    if action in safe_methods:
        method = getattr(orch, safe_methods[action], None)
        if method is None:
            return {"ok": False, "error": f"Method not available: {safe_methods[action]}"}
        threading.Thread(target=method, daemon=True, name=f"rp-{action}").start()
        return {"ok": True, "message": f"{action} started"}

    if action == "pause":
        if hasattr(orch, "pause"):
            orch.pause()
        else:
            orch._paused = True
        return {"ok": True, "paused": True}

    if action == "resume":
        if hasattr(orch, "resume"):
            orch.resume()
        else:
            orch._paused = False
        return {"ok": True, "paused": False}

    if action == "emergency_stop":
        if hasattr(orch, "e_stop"):
            orch.e_stop()
        else:
            orch._emergency_stopped = True
        return {"ok": True, "message": "Emergency stop triggered"}

    if action == "emergency_reset":
        try:
            with orch._state_lock:
                orch._emergency_stopped = False
                orch._paused = False
        except Exception:
            orch._emergency_stopped = False
            orch._paused = False
        return {"ok": True, "message": "Emergency reset — all flags cleared"}

    if action == "start_scheduler":
        try:
            if not orch.scheduler.running:
                # Use orchestrator.start() to schedule all jobs properly
                if hasattr(orch, "start"):
                    orch.start(nonblocking=True)
                else:
                    orch.scheduler.start()
            return {"ok": True, "scheduler_running": True, "message": "Scheduler started"}
        except Exception as e:
            logger.error(f"start_scheduler failed: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    if action == "stop_scheduler":
        try:
            if orch.scheduler.running:
                orch.scheduler.shutdown(wait=False)
            return {"ok": True, "scheduler_running": False, "message": "Scheduler stopped"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Unknown action: {action}"}


# ══════════════════════════════════════════════════════════════════
# Config file CRUD — account & client management via the dashboard
# ══════════════════════════════════════════════════════════════════

VALID_KARMA_TIERS = {"new", "growing", "established", "veteran"}


def _read_config_yaml() -> Dict[str, Any]:
    """Read the raw YAML config file (bootstraps from template if missing)."""
    import yaml
    if not _bootstrap_config():
        raise RuntimeError("No config file available")
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def _write_config_yaml(data: Dict[str, Any]) -> None:
    """Write the config file atomically and force orchestrator reload."""
    import yaml
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _CONFIG_PATH.with_suffix(".yaml.tmp")
    with open(tmp_path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    tmp_path.replace(_CONFIG_PATH)
    # Force reload so the next get_orch() picks up the new config
    reset()


def list_accounts_raw() -> List[Dict[str, Any]]:
    """Return the account list from the config YAML with secrets masked.

    Unlike get_accounts() (which joins DB stats), this reflects the
    declarative config file — useful for the management UI.
    """
    try:
        data = _read_config_yaml()
    except Exception as e:
        logger.error(f"list_accounts_raw error: {e}")
        return []
    accounts = data.get("accounts") or []
    masked = []
    for a in accounts:
        masked.append({
            "username": a.get("username", ""),
            "karma_tier": a.get("karma_tier", "new"),
            "enabled": a.get("enabled", True),
            "has_password": bool(a.get("password")),
            "has_client_id": bool(a.get("client_id")),
            "has_client_secret": bool(a.get("client_secret")),
            "assigned_subreddits": a.get("assigned_subreddits", []),
            "proxy": a.get("proxy", ""),
            "notes": a.get("notes", ""),
        })
    return masked


def add_account(
    username: str,
    password: str,
    client_id: str,
    client_secret: str,
    karma_tier: str = "new",
    enabled: bool = True,
    assigned_subreddits: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Add a Reddit account to the config file. If an account with the same
    username exists, it is replaced."""
    username = (username or "").strip().lstrip("u/").lstrip("/")
    if not username:
        return {"ok": False, "error": "username is required"}
    if not password:
        return {"ok": False, "error": "password is required"}
    if not client_id or not client_secret:
        return {"ok": False, "error": "client_id and client_secret are required (from https://www.reddit.com/prefs/apps)"}
    if karma_tier not in VALID_KARMA_TIERS:
        return {"ok": False, "error": f"karma_tier must be one of {sorted(VALID_KARMA_TIERS)}"}

    try:
        data = _read_config_yaml()
    except Exception as e:
        return {"ok": False, "error": f"Could not read config: {e}"}

    accounts = data.get("accounts") or []
    # Remove any existing entry with the same username
    accounts = [a for a in accounts if a.get("username") != username]

    new_entry = {
        "username": username,
        "password": password,
        "client_id": client_id,
        "client_secret": client_secret,
        "karma_tier": karma_tier,
        "enabled": enabled,
    }
    if assigned_subreddits:
        new_entry["assigned_subreddits"] = [s.strip() for s in assigned_subreddits if s.strip()]
    if notes:
        new_entry["notes"] = notes
    accounts.append(new_entry)
    data["accounts"] = accounts

    try:
        _write_config_yaml(data)
    except Exception as e:
        return {"ok": False, "error": f"Could not write config: {e}"}

    return {"ok": True, "message": f"Account u/{username} saved", "username": username}


def delete_account(username: str) -> Dict[str, Any]:
    username = (username or "").strip().lstrip("u/").lstrip("/")
    if not username:
        return {"ok": False, "error": "username is required"}
    try:
        data = _read_config_yaml()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    accounts = data.get("accounts") or []
    before = len(accounts)
    accounts = [a for a in accounts if a.get("username") != username]
    if len(accounts) == before:
        return {"ok": False, "error": f"Account u/{username} not found"}
    data["accounts"] = accounts
    try:
        _write_config_yaml(data)
    except Exception as e:
        return {"ok": False, "error": f"Could not write config: {e}"}
    return {"ok": True, "message": f"Account u/{username} removed"}


def set_account_enabled(username: str, enabled: bool) -> Dict[str, Any]:
    username = (username or "").strip().lstrip("u/").lstrip("/")
    try:
        data = _read_config_yaml()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    accounts = data.get("accounts") or []
    found = False
    for a in accounts:
        if a.get("username") == username:
            a["enabled"] = bool(enabled)
            found = True
            break
    if not found:
        return {"ok": False, "error": f"Account u/{username} not found"}
    data["accounts"] = accounts
    try:
        _write_config_yaml(data)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "enabled": bool(enabled)}


def list_clients_raw() -> List[Dict[str, Any]]:
    """Return the client list from the config YAML (not the joined DB view)."""
    try:
        data = _read_config_yaml()
    except Exception as e:
        logger.error(f"list_clients_raw error: {e}")
        return []
    return list(data.get("clients") or [])


def update_client(slug: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update editable fields of a client. Allowed fields: keywords,
    target_subreddits, brand_voice, enabled, promo_ratio, approval_required."""
    allowed = {"keywords", "target_subreddits", "brand_voice", "enabled",
               "promo_ratio", "approval_required", "service_area", "website"}
    try:
        data = _read_config_yaml()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    clients = data.get("clients") or []
    found = None
    for c in clients:
        if c.get("slug") == slug:
            found = c
            break
    if not found:
        return {"ok": False, "error": f"Client {slug} not found"}
    for k, v in (updates or {}).items():
        if k in allowed:
            found[k] = v
    data["clients"] = clients
    try:
        _write_config_yaml(data)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "client": slug}


def get_llm_status() -> Dict[str, Any]:
    """Return LLM provider status without exposing the key."""
    try:
        data = _read_config_yaml()
    except Exception as e:
        return {"configured": False, "error": str(e)}
    llm = data.get("llm") or {}
    primary_key = llm.get("primary_api_key") or os.environ.get("OPENROUTER_API_KEY", "") or os.environ.get("REDDITPILOT_LLM_API_KEY", "")
    fallback_key = llm.get("fallback_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "configured": True,
        "primary_provider": llm.get("primary_provider", ""),
        "primary_model": llm.get("primary_model", ""),
        "primary_key_set": bool(primary_key),
        "primary_key_source": "config" if llm.get("primary_api_key") else ("OPENROUTER_API_KEY" if os.environ.get("OPENROUTER_API_KEY") else ("REDDITPILOT_LLM_API_KEY" if os.environ.get("REDDITPILOT_LLM_API_KEY") else "none")),
        "fallback_provider": llm.get("fallback_provider", ""),
        "fallback_model": llm.get("fallback_model", ""),
        "fallback_key_set": bool(fallback_key),
    }
