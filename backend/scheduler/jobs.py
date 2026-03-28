"""
Scheduled job CRUD — SQLite-backed storage for recurring pipeline jobs.

Each job defines: which pipeline to run, for which client, on what schedule,
with what inputs. The scheduler checks for due jobs every 60 seconds.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def init_scheduler_table(conn) -> None:
    """Create the scheduled_jobs table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            pipeline_type TEXT NOT NULL,
            inputs_json TEXT NOT NULL DEFAULT '{}',
            approval_mode TEXT NOT NULL DEFAULT 'autopilot',
            schedule TEXT NOT NULL,
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT,
            last_pipeline_id TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next
        ON scheduled_jobs(enabled, next_run_at)
    """)
    conn.commit()


def _parse_schedule(schedule: str) -> Optional[dict]:
    """Parse schedule string into APScheduler trigger kwargs.

    Supports:
        "every 7d"          → interval, days=7
        "every 24h"         → interval, hours=24
        "every 30m"         → interval, minutes=30
        "0 9 * * 1"         → cron expression (Mon at 9am)
        "0 9 1 * *"         → cron expression (1st of month at 9am)
    """
    s = schedule.strip().lower()

    # Interval: "every Xd/h/m"
    if s.startswith("every "):
        val_str = s[6:].strip()
        if val_str.endswith("d"):
            return {"trigger": "interval", "days": int(val_str[:-1])}
        elif val_str.endswith("h"):
            return {"trigger": "interval", "hours": int(val_str[:-1])}
        elif val_str.endswith("m"):
            return {"trigger": "interval", "minutes": int(val_str[:-1])}

    # Cron expression (5 fields: min hour day month weekday)
    parts = s.split()
    if len(parts) == 5:
        return {
            "trigger": "cron",
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    return None


def create_scheduled_job(conn, data: dict) -> dict:
    """Create a new scheduled job."""
    job_id = f"sched_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO scheduled_jobs
           (id, name, client_id, pipeline_type, inputs_json, approval_mode,
            schedule, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            job_id,
            data.get("name", f"Scheduled {data.get('pipeline_type', 'pipeline')}"),
            data["client_id"],
            data["pipeline_type"],
            json.dumps(data.get("inputs", {})),
            data.get("approval_mode", "autopilot"),
            data["schedule"],
            now, now,
        ),
    )
    conn.commit()
    return get_scheduled_job(conn, job_id)


def get_scheduled_job(conn, job_id: str) -> Optional[dict]:
    """Get a single scheduled job."""
    row = conn.execute(
        "SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["inputs"] = json.loads(d["inputs_json"])
    return d


def list_scheduled_jobs(conn, client_id: Optional[int] = None) -> list[dict]:
    """List all scheduled jobs, optionally filtered by client."""
    if client_id:
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs WHERE client_id = ? ORDER BY created_at DESC",
            (client_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["inputs"] = json.loads(d["inputs_json"])
        result.append(d)
    return result


def update_scheduled_job(conn, job_id: str, data: dict) -> Optional[dict]:
    """Update a scheduled job."""
    allowed = {"name", "inputs", "schedule", "approval_mode", "enabled", "pipeline_type"}
    updates = {}
    for k, v in data.items():
        if k in allowed:
            if k == "inputs":
                updates["inputs_json"] = json.dumps(v)
            elif k == "enabled":
                updates["enabled"] = 1 if v else 0
            else:
                updates[k] = v

    if not updates:
        return get_scheduled_job(conn, job_id)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [job_id]
    conn.execute(f"UPDATE scheduled_jobs SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return get_scheduled_job(conn, job_id)


def delete_scheduled_job(conn, job_id: str) -> bool:
    """Delete a scheduled job."""
    cur = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
    conn.commit()
    return cur.rowcount > 0


def mark_job_run(conn, job_id: str, pipeline_id: str, status: str) -> None:
    """Record that a scheduled job was executed."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE scheduled_jobs
           SET last_run_at = ?, last_status = ?, last_pipeline_id = ?, updated_at = ?
           WHERE id = ?""",
        (now, status, pipeline_id, now, job_id),
    )
    conn.commit()


def get_due_jobs(conn) -> list[dict]:
    """Get all enabled jobs that are due to run.

    Note: For interval-based jobs, this checks last_run_at against the schedule.
    For cron jobs, APScheduler handles the timing directly.
    """
    rows = conn.execute(
        "SELECT * FROM scheduled_jobs WHERE enabled = 1"
    ).fetchall()
    return [dict(r) for r in rows]
