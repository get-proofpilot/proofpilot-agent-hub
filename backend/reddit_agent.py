"""
RedditPilot agent integration for ProofPilot Agent Hub.

Lazy-loads the vendored `redditpilot` package and manages a singleton
orchestrator instance. All heavy imports (praw, bs4, apscheduler) happen
on first use — Agent Hub starts fine even if deps are broken.

Config file lives at $REDDITPILOT_CONFIG_PATH or /app/data/redditpilot/config.yaml.
DB lives in the same directory.

Routes in server.py import helper functions from this module instead of
talking HTTP to a separate service.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("proofpilot.reddit_agent")

# ── Config path resolution ────────────────────────────────────────
_DEFAULT_DATA_DIR = Path(os.environ.get("DOCS_DIR", "./data")) / "redditpilot"
_CONFIG_PATH = Path(
    os.environ.get("REDDITPILOT_CONFIG_PATH", _DEFAULT_DATA_DIR / "config.yaml")
)


def config_path() -> Path:
    return _CONFIG_PATH


def is_configured() -> bool:
    """True if a RedditPilot config file exists."""
    return _CONFIG_PATH.exists()


# ── Singleton orchestrator ────────────────────────────────────────
_orch = None
_orch_lock = threading.Lock()
_orch_error: Optional[str] = None


def _init_logger_capture():
    """Attach a log capture handler for WebSocket broadcast."""
    global _log_capture
    if _log_capture is not None:
        return _log_capture
    _log_capture = _LogCapture(maxlen=500)
    # Attach to the redditpilot logger tree
    rp_logger = logging.getLogger("redditpilot")
    rp_logger.addHandler(_log_capture)
    rp_logger.setLevel(logging.INFO)
    return _log_capture


def get_orch():
    """Return the RedditPilot orchestrator singleton, or None if unavailable.

    On first call, attempts to import the vendored `redditpilot` package,
    load config, and instantiate the orchestrator. Errors are captured in
    `_orch_error` and returned as None so the frontend can show a clear
    "not configured" state.

    IMPORTANT: Does NOT start the orchestrator's scheduler. The user must
    explicitly trigger scans/cycles from the dashboard to avoid accidental
    autonomous posting after deploys.
    """
    global _orch, _orch_error
    if _orch is not None:
        return _orch
    with _orch_lock:
        if _orch is not None:
            return _orch
        if not is_configured():
            _orch_error = f"Config file not found at {_CONFIG_PATH}"
            return None
        try:
            # Lazy import — avoids loading praw/bs4 until actually needed
            from redditpilot.core.config import Config
            from redditpilot.orchestrator import RedditPilot

            # Force data_dir to our resolved location
            cfg = Config.load(str(_CONFIG_PATH))
            cfg.data_dir = str(_CONFIG_PATH.parent)

            _orch = RedditPilot(cfg)
            _init_logger_capture()
            logger.info(f"RedditPilot orchestrator initialized from {_CONFIG_PATH}")
            return _orch
        except Exception as e:
            _orch_error = f"{type(e).__name__}: {e}"
            logger.error(f"Failed to init RedditPilot: {e}", exc_info=True)
            return None


def get_error() -> Optional[str]:
    return _orch_error


def reset():
    """Drop the cached orchestrator (e.g., after config change)."""
    global _orch, _orch_error
    with _orch_lock:
        if _orch is not None:
            try:
                if hasattr(_orch, "scheduler") and _orch.scheduler.running:
                    _orch.scheduler.shutdown(wait=False)
            except Exception:
                pass
        _orch = None
        _orch_error = None


# ── Log capture for WebSocket ─────────────────────────────────────
_log_capture = None


class _LogCapture(logging.Handler):
    """Captures log records for WebSocket broadcast (based on RedditPilot's own handler)."""

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


def log_capture() -> Optional[_LogCapture]:
    return _log_capture


# ══════════════════════════════════════════════════════════════════
# Data query helpers
# ══════════════════════════════════════════════════════════════════


def _cutoff(hours: int = 24) -> str:
    return (datetime.utcnow() - timedelta(hours=hours)).isoformat()


def get_status() -> Dict[str, Any]:
    """Return orchestrator status (paused, uptime, client/account counts)."""
    orch = get_orch()
    if not orch:
        return {
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
    clients = []
    for c in orch.config.get_enabled_clients():
        clients.append({
            "name": c.name, "slug": c.slug,
            "industry": c.industry, "enabled": c.enabled,
        })
    paused = getattr(orch, "_paused", False)
    running = getattr(orch, "_running", False)
    scheduler_running = False
    try:
        scheduler_running = orch.scheduler.running
    except Exception:
        pass
    mode = "running" if (running or scheduler_running) and not paused else ("paused" if paused else "stopped")
    return {
        "connected": True,
        "configured": True,
        "mode": mode,
        "paused": paused,
        "running": running,
        "scheduler_running": scheduler_running,
        "uptime_seconds": 0,  # Orchestrator doesn't track start time directly
        "clients": clients,
        "client_count": len(clients),
        "account_count": len(orch.config.get_enabled_accounts()),
        "cycle_count": getattr(orch, "_cycle_count", 0),
        "emergency_stopped": getattr(orch, "_emergency_stopped", False),
    }


def get_stats(hours: int = 24) -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"total": 0, "by_type": {}, "by_client": {}, "by_subreddit": {}, "success_rate": 0, "pending_opportunities": 0}
    try:
        db = orch.db
        cutoff = _cutoff(hours)
        total_row = db.fetchone("SELECT COUNT(*) as cnt FROM action_log WHERE created_at > ?", (cutoff,))
        total = total_row["cnt"] if total_row else 0

        by_type_rows = db.fetchall(
            "SELECT action_type, COUNT(*) as cnt FROM action_log WHERE created_at > ? GROUP BY action_type ORDER BY cnt DESC",
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
            "SELECT COUNT(*) as cnt FROM action_log WHERE created_at > ? AND success = 1", (cutoff,)
        )
        successes = success_row["cnt"] if success_row else 0

        pending_row = db.fetchone(
            "SELECT COUNT(*) as cnt FROM discovered_posts WHERE status IN ('new', 'queued')"
        )
        pending = pending_row["cnt"] if pending_row else 0

        return {
            "total": total,
            "by_type": by_type,
            "by_client": by_client,
            "by_subreddit": by_subreddit,
            "success_rate": round(successes / max(total, 1), 3),
            "pending_opportunities": pending,
        }
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return {"error": str(e), "total": 0, "by_type": {}, "by_client": {}, "by_subreddit": {}}


def get_clients() -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    result = []
    try:
        db = orch.db
        cutoff = _cutoff(24)
        for client in orch.config.get_enabled_clients():
            crow = db.fetchone("SELECT id FROM clients WHERE slug = ?", (client.slug,))
            cid = crow["id"] if crow else None
            actions_24h = 0
            pending = 0
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
            result.append({
                "name": client.name, "slug": client.slug,
                "industry": client.industry, "service_area": client.service_area,
                "website": client.website, "enabled": client.enabled,
                "keyword_count": len(client.keywords or []),
                "subreddit_count": len(client.target_subreddits or []),
                "total_actions": actions_24h,
                "actions_24h": actions_24h,
                "pending_opportunities": pending,
            })
    except Exception as e:
        logger.error(f"get_clients error: {e}")
    return result


def get_client_detail(slug: str) -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"error": "not configured"}
    client = None
    for c in orch.config.get_enabled_clients():
        if c.slug == slug:
            client = c
            break
    if not client:
        return {"error": "client not found"}
    try:
        db = orch.db
        crow = db.fetchone("SELECT id FROM clients WHERE slug = ?", (slug,))
        cid = crow["id"] if crow else None
        performance = {}
        if cid:
            cutoff = _cutoff(24)
            perf = db.fetchone(
                "SELECT COUNT(*) as total_actions, SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes "
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
        return {
            "name": client.name, "slug": client.slug,
            "industry": client.industry, "service_area": client.service_area,
            "website": client.website, "brand_voice": client.brand_voice,
            "keywords": list(client.keywords or []),
            "target_subreddits": list(client.target_subreddits or []),
            "enabled": client.enabled,
            "performance": performance,
        }
    except Exception as e:
        return {"error": str(e)}


def get_accounts() -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    result = []
    try:
        db = orch.db
        for account in orch.config.get_enabled_accounts():
            username = account.username
            acc_row = db.fetchone("SELECT * FROM accounts WHERE username = ?", (username,))
            result.append({
                "username": username,
                "karma_tier": (acc_row.get("karma_tier") if acc_row else None) or account.karma_tier,
                "karma": ((acc_row.get("comment_karma") or 0) + (acc_row.get("post_karma") or 0)) if acc_row else 0,
                "daily_comments": acc_row.get("daily_comments_today", 0) if acc_row else 0,
                "daily_posts": acc_row.get("daily_posts_today", 0) if acc_row else 0,
                "daily_comment_cap": account.daily_comment_cap,
                "daily_post_cap": account.daily_post_cap,
                "daily_remaining": account.daily_comment_cap - (acc_row.get("daily_comments_today", 0) if acc_row else 0),
                "shadowbanned": bool(acc_row.get("is_shadowbanned", 0)) if acc_row else False,
                "healthy": not (acc_row.get("is_shadowbanned") if acc_row else False),
                "enabled": account.enabled,
            })
    except Exception as e:
        logger.error(f"get_accounts error: {e}")
    return result


def get_opportunities(limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    try:
        rows = orch.db.fetchall(
            "SELECT dp.*, c.name as client_name FROM discovered_posts dp "
            "LEFT JOIN clients c ON dp.client_id = c.id "
            "WHERE dp.status IN ('new', 'queued') "
            "ORDER BY dp.score DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_opportunities error: {e}")
        return []


def get_actions(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    try:
        rows = orch.db.fetchall(
            "SELECT al.*, c.name as client_name FROM action_log al "
            "LEFT JOIN clients c ON al.client_id = c.id "
            "WHERE al.created_at > ? "
            "ORDER BY al.created_at DESC LIMIT ?",
            (_cutoff(hours), limit),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_actions error: {e}")
        return []


def get_history(days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = orch.db.fetchall(
            "SELECT al.*, c.name as client_name FROM action_log al "
            "LEFT JOIN clients c ON al.client_id = c.id "
            "WHERE al.created_at > ? "
            "ORDER BY al.created_at DESC LIMIT ?",
            (cutoff, limit),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_history error: {e}")
        return []


def get_schedule() -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"jobs": []}
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
            "scheduler_running": orch.scheduler.running,
            "scan_interval_minutes": orch.config.scan_interval_minutes,
            "learning_interval_hours": orch.config.learning_interval_hours,
        }
    except Exception as e:
        return {"jobs": [], "error": str(e)}


def get_insights() -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"ab_tests": [], "top_subreddits": [], "strategies": []}
    try:
        db = orch.db
        top_subs_rows = db.fetchall(
            "SELECT subreddit, COUNT(*) as action_count, AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) as success_rate "
            "FROM action_log WHERE subreddit IS NOT NULL "
            "GROUP BY subreddit ORDER BY action_count DESC LIMIT 10"
        )
        top_subs = [
            {"subreddit": r["subreddit"], "actions": r["action_count"], "engagement_rate": r["success_rate"] or 0}
            for r in top_subs_rows
        ]
        return {"ab_tests": [], "top_subreddits": top_subs, "strategies": []}
    except Exception as e:
        return {"ab_tests": [], "top_subreddits": [], "strategies": [], "error": str(e)}


def get_performance(days: int = 7) -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"daily": []}
    try:
        rows = orch.db.fetchall(
            "SELECT DATE(created_at) as day, COUNT(*) as actions "
            "FROM action_log "
            "WHERE created_at > ? "
            "GROUP BY DATE(created_at) ORDER BY day",
            ((datetime.utcnow() - timedelta(days=days)).isoformat(),),
        )
        return {"daily": [{"date": r["day"], "actions": r["actions"]} for r in rows]}
    except Exception as e:
        return {"daily": [], "error": str(e)}


def get_heatmap() -> Dict[str, Any]:
    """Return a 7x24 activity grid (day-of-week x hour-of-day)."""
    orch = get_orch()
    if not orch:
        return {"grid": []}
    try:
        grid = [[0 for _ in range(24)] for _ in range(7)]
        rows = orch.db.fetchall(
            "SELECT created_at FROM action_log WHERE created_at > ?",
            ((datetime.utcnow() - timedelta(days=7)).isoformat(),),
        )
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["created_at"])
                grid[dt.weekday()][dt.hour] += 1
            except Exception:
                continue
        return {"grid": grid}
    except Exception as e:
        return {"grid": [], "error": str(e)}


def get_funnel() -> Dict[str, Any]:
    orch = get_orch()
    if not orch:
        return {"stages": []}
    try:
        db = orch.db
        discovered = db.fetchone("SELECT COUNT(*) as cnt FROM discovered_posts")
        scored = db.fetchone("SELECT COUNT(*) as cnt FROM discovered_posts WHERE score IS NOT NULL")
        approved = db.fetchone("SELECT COUNT(*) as cnt FROM discovered_posts WHERE status = 'approved'")
        posted = db.fetchone("SELECT COUNT(*) as cnt FROM action_log WHERE success = 1")
        stages = [
            {"stage": "Discovered", "count": discovered["cnt"] if discovered else 0},
            {"stage": "Scored", "count": scored["cnt"] if scored else 0},
            {"stage": "Approved", "count": approved["cnt"] if approved else 0},
            {"stage": "Posted", "count": posted["cnt"] if posted else 0},
        ]
        return {"stages": stages}
    except Exception as e:
        return {"stages": [], "error": str(e)}


def get_summary() -> Dict[str, Any]:
    status = get_status()
    stats = get_stats(24)
    return {"status": status, "stats": stats}


def get_decisions(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    orch = get_orch()
    if not orch:
        return []
    try:
        if hasattr(orch.db, "get_recent_decisions"):
            return orch.db.get_recent_decisions(hours=hours, limit=limit)
    except Exception as e:
        logger.error(f"get_decisions error: {e}")
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
        return {"ok": False, "error": "Emergency stop active"}

    action_map = {
        "scan": "_scan_safe",
        "learn": "_learn_safe",
        "discover": "_discover_safe",
        "generate": "_generate_safe",
        "post": "_post_safe",
        "cycle": "_run_cycle_safe",
    }

    if action in action_map:
        method = getattr(orch, action_map[action], None)
        if method:
            threading.Thread(target=method, daemon=True).start()
            return {"ok": True, "message": f"{action} started"}
        return {"ok": False, "error": f"Method not available: {action_map[action]}"}

    if action == "pause":
        orch.pause() if hasattr(orch, "pause") else setattr(orch, "_paused", True)
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
        orch._emergency_stopped = False
        orch._paused = False
        return {"ok": True, "message": "Emergency reset"}

    if action == "start_scheduler":
        try:
            if not orch.scheduler.running:
                orch.scheduler.start()
            return {"ok": True, "scheduler_running": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if action == "stop_scheduler":
        try:
            if orch.scheduler.running:
                orch.scheduler.shutdown(wait=False)
            return {"ok": True, "scheduler_running": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Unknown action: {action}"}
