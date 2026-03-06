"""Client Tasks CRUD operations."""
import sqlite3
from datetime import datetime, timezone
from utils.db import _get_db_path


def _conn():
    return sqlite3.connect(_get_db_path())


def get_client_tasks(client_id, month=None):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM client_tasks WHERE client_id = ?"
    params = [client_id]
    if month:
        sql += " AND month = ?"
        params.append(month)
    sql += " ORDER BY category ASC, status ASC, title ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_client_task(client_id, title, category="other", month="", job_id=""):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO client_tasks (client_id, title, category, status, month, job_id, created_at, updated_at)
           VALUES (?, ?, ?, 'not_started', ?, ?, ?, ?)""",
        [client_id, title, category, month, job_id, now, now]
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def update_task_status(task_id, status):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE client_tasks SET status = ?, updated_at = ? WHERE id = ?", [status, now, task_id])
    conn.commit()
    conn.close()


def sync_tasks_from_jobs(client_id, month):
    """Auto-create tasks from completed jobs for this client/month."""
    conn = _conn()
    conn.row_factory = sqlite3.Row
    # Find jobs for this client in the given month
    like_pattern = f"{month}%"
    jobs = conn.execute(
        "SELECT id, workflow_id, workflow_title FROM jobs WHERE client_id = ? AND created_at LIKE ? AND status = 'completed'",
        [client_id, like_pattern]
    ).fetchall()

    category_map = {
        "seo-blog-post": "content", "service-page": "content", "location-page": "content",
        "home-service-content": "content", "programmatic-content": "content",
        "website-seo-audit": "seo", "keyword-gap": "seo", "seo-research": "seo",
        "backlink-audit": "seo", "onpage-audit": "seo", "competitor-seo-analysis": "seo",
        "google-ads-copy": "paid", "monthly-report": "reporting",
        "proposals": "reporting", "content-strategy": "content",
    }
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for job in jobs:
        job_id_str = str(job["id"])
        existing = conn.execute(
            "SELECT id FROM client_tasks WHERE client_id = ? AND job_id = ?",
            [client_id, job_id_str]
        ).fetchone()
        if existing:
            continue
        cat = category_map.get(job["workflow_id"], "other")
        conn.execute(
            """INSERT INTO client_tasks (client_id, title, category, status, month, job_id, created_at, updated_at)
               VALUES (?, ?, ?, 'complete', ?, ?, ?, ?)""",
            [client_id, job["workflow_title"], cat, month, job_id_str, now, now]
        )
        created += 1
    conn.commit()
    conn.close()
    return created
