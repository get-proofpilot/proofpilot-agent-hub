"""Content Roadmap CRUD operations.

Roadmap items flow through these statuses:
  planned → assigned → researching → writing → designed → qa_review →
  ready_for_approval → approved → published

When assigned to the pipeline agent, the pipeline_id links the roadmap
item to the pipeline run. Status updates automatically as stages complete.
"""
import sqlite3
from datetime import datetime, timezone
from utils.db import _get_db_path


# Status progression for pipeline-driven items
PIPELINE_STAGE_TO_STATUS = {
    "research": "researching",
    "strategy": "researching",
    "copywrite": "writing",
    "design": "designed",
    "images": "designed",
    "qa": "qa_review",
}


def _conn():
    c = sqlite3.connect(_get_db_path())
    c.row_factory = sqlite3.Row
    # Migration: add pipeline_id column if not present
    try:
        c.execute("ALTER TABLE content_roadmap ADD COLUMN pipeline_id TEXT DEFAULT ''")
        c.commit()
    except Exception:
        pass  # already exists
    return c


def get_content_roadmap(client_id, month=None, page_type=None, status=None):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM content_roadmap WHERE client_id = ?"
    params = [client_id]
    if month:
        sql += " AND month = ?"
        params.append(month)
    if page_type:
        sql += " AND page_type = ?"
        params.append(page_type)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY month DESC, title ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_content_stats(client_id):
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM content_roadmap WHERE client_id = ?", [client_id]).fetchone()[0]
    published = conn.execute("SELECT COUNT(*) FROM content_roadmap WHERE client_id = ? AND status = 'published'", [client_id]).fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM content_roadmap WHERE client_id = ? AND status IN ('assigned', 'written')", [client_id]).fetchone()[0]
    planned = conn.execute("SELECT COUNT(*) FROM content_roadmap WHERE client_id = ? AND status = 'planned'", [client_id]).fetchone()[0]
    # Type breakdown
    rows = conn.execute("SELECT page_type, COUNT(*) as cnt FROM content_roadmap WHERE client_id = ? GROUP BY page_type", [client_id]).fetchall()
    conn.close()
    types = {r[0]: r[1] for r in rows}
    return {"total": total, "published": published, "in_progress": in_progress, "planned": planned, "types": types}


def bulk_insert_content(client_id, items, source="csv"):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        conn.execute(
            """INSERT INTO content_roadmap (client_id, month, title, page_type, content_silo, status, keyword, volume, difficulty, sheets_source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [client_id, item.get("month", ""), item.get("title", ""), item.get("page_type", ""),
             item.get("content_silo", ""), item.get("status", "planned"), item.get("keyword", ""),
             int(item.get("volume", 0)), int(item.get("difficulty", 0)), source, now, now]
        )
    conn.commit()
    conn.close()
    return len(items)


def clear_content_roadmap(client_id, source=None):
    conn = _conn()
    if source:
        conn.execute("DELETE FROM content_roadmap WHERE client_id = ? AND sheets_source = ?", [client_id, source])
    else:
        conn.execute("DELETE FROM content_roadmap WHERE client_id = ?", [client_id])
    conn.commit()
    conn.close()


# ── Pipeline Assignment ──────────────────────────────────────────────────

def assign_to_pipeline(roadmap_id, pipeline_id):
    """Link a roadmap item to a pipeline run and set status to 'assigned'."""
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE content_roadmap SET status = 'assigned', pipeline_id = ?, updated_at = ? WHERE id = ?",
        [pipeline_id, now, roadmap_id],
    )
    conn.commit()
    conn.close()


def update_roadmap_status(roadmap_id, status):
    """Update roadmap item status (called as pipeline stages complete)."""
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE content_roadmap SET status = ?, updated_at = ? WHERE id = ?",
        [status, now, roadmap_id],
    )
    conn.commit()
    conn.close()


def update_roadmap_from_stage(pipeline_id, stage_name):
    """Auto-update roadmap status when a pipeline stage completes."""
    status = PIPELINE_STAGE_TO_STATUS.get(stage_name)
    if not status:
        return
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE content_roadmap SET status = ?, updated_at = ? WHERE pipeline_id = ?",
        [status, now, pipeline_id],
    )
    conn.commit()
    conn.close()


def mark_roadmap_ready(pipeline_id):
    """Mark a roadmap item as ready for approval (called after QA passes)."""
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE content_roadmap SET status = 'ready_for_approval', updated_at = ? WHERE pipeline_id = ?",
        [now, pipeline_id],
    )
    conn.commit()
    conn.close()


def mark_roadmap_approved(pipeline_id):
    """Mark roadmap item as approved."""
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE content_roadmap SET status = 'approved', updated_at = ? WHERE pipeline_id = ?",
        [now, pipeline_id],
    )
    conn.commit()
    conn.close()


def get_roadmap_item(roadmap_id):
    """Get a single roadmap item by ID."""
    conn = _conn()
    row = conn.execute("SELECT * FROM content_roadmap WHERE id = ?", [roadmap_id]).fetchone()
    conn.close()
    return dict(row) if row else None


def get_assignable_items(client_id, month=None):
    """Get roadmap items that can be assigned to the pipeline (status = 'planned')."""
    conn = _conn()
    sql = "SELECT * FROM content_roadmap WHERE client_id = ? AND status = 'planned'"
    params = [client_id]
    if month:
        sql += " AND month = ?"
        params.append(month)
    sql += " ORDER BY month ASC, page_type ASC, title ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
