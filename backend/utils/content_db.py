"""Content Roadmap CRUD operations."""
import sqlite3
from datetime import datetime, timezone
from utils.db import _get_db_path


def _conn():
    return sqlite3.connect(_get_db_path())


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
