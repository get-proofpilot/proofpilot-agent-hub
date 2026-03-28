"""
ProofPilot — Metrics storage layer for client reporting dashboard.

Separate from db.py to keep metrics concerns isolated.
Uses the same SQLite database and _connect() helper.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from utils.db import _connect


# ── Write functions ──────────────────────────────────────────────────────────

def upsert_metrics(
    client_id: int,
    source: str,
    metric_type: str,
    dimension: str,
    value: float,
    date: str,
    metadata: str = "{}",
) -> None:
    """Insert or replace a single metric row."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO metrics
               (client_id, source, metric_type, dimension, value, date, metadata, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, source, metric_type, dimension, value, date, metadata, now),
        )
        conn.commit()


def bulk_upsert_metrics(rows: list[dict]) -> int:
    """Batch upsert metrics rows. Each dict needs: client_id, source, metric_type, dimension, value, date.
    Returns number of rows written."""
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO metrics
               (client_id, source, metric_type, dimension, value, date, metadata, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    r["client_id"], r["source"], r["metric_type"],
                    r.get("dimension", "total"), r["value"], r["date"],
                    r.get("metadata", "{}"), now,
                )
                for r in rows
            ],
        )
        conn.commit()
    return len(rows)


def save_sync_log(
    client_id: int,
    source: str,
    status: str,
    rows_synced: int = 0,
    error_msg: str = "",
) -> None:
    """Log a sync attempt."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sync_log
               (client_id, source, status, rows_synced, error_msg, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (client_id, source, status, rows_synced, error_msg, now, now),
        )
        conn.commit()


# ── Read functions ───────────────────────────────────────────────────────────

def get_metric_timeseries(
    client_id: int,
    source: str,
    metric_type: str,
    dimension: str = "total",
    days: int = 30,
) -> list[dict]:
    """Return [{date, value}, ...] sorted by date."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            """SELECT date, value FROM metrics
               WHERE client_id = ? AND source = ? AND metric_type = ?
                 AND dimension = ? AND date >= ?
               ORDER BY date ASC""",
            (client_id, source, metric_type, dimension, cutoff),
        ).fetchall()
    return [{"date": r["date"], "value": r["value"]} for r in rows]


def get_metric_breakdown(
    client_id: int,
    source: str,
    metric_type: str,
    days: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Return [{dimension, value}, ...] grouped by dimension, summed over period."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            """SELECT dimension, SUM(value) as total FROM metrics
               WHERE client_id = ? AND source = ? AND metric_type = ?
                 AND dimension != 'total' AND date >= ?
               GROUP BY dimension
               ORDER BY total DESC
               LIMIT ?""",
            (client_id, source, metric_type, cutoff, limit),
        ).fetchall()
    return [{"dimension": r["dimension"], "value": r["total"]} for r in rows]


def get_keyword_rankings(client_id: int, days: int = 30, limit: int = 50) -> list[dict]:
    """Return keyword ranking data with position change."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    mid = (datetime.now(timezone.utc) - timedelta(days=days // 2)).strftime("%Y-%m-%d")

    with _connect() as conn:
        # Latest positions (second half of period)
        latest = conn.execute(
            """SELECT dimension,
                      AVG(value) as avg_position,
                      SUM(CASE WHEN metric_type='clicks' THEN value ELSE 0 END) as clicks,
                      SUM(CASE WHEN metric_type='impressions' THEN value ELSE 0 END) as impressions
               FROM metrics
               WHERE client_id = ? AND source = 'gsc'
                 AND metric_type IN ('position', 'clicks', 'impressions')
                 AND dimension LIKE 'query:%' AND date >= ?
               GROUP BY dimension
               ORDER BY clicks DESC
               LIMIT ?""",
            (client_id, mid, limit),
        ).fetchall()

        # Previous positions (first half)
        prev_rows = conn.execute(
            """SELECT dimension, AVG(value) as avg_position
               FROM metrics
               WHERE client_id = ? AND source = 'gsc' AND metric_type = 'position'
                 AND dimension LIKE 'query:%' AND date >= ? AND date < ?
               GROUP BY dimension""",
            (client_id, cutoff, mid),
        ).fetchall()

    prev_map = {r["dimension"]: r["avg_position"] for r in prev_rows}

    results = []
    for r in latest:
        keyword = r["dimension"].replace("query:", "", 1)
        current_pos = round(r["avg_position"], 1)
        prev_pos = round(prev_map.get(r["dimension"], current_pos), 1)
        results.append({
            "keyword": keyword,
            "position": current_pos,
            "previous_position": prev_pos,
            "change": round(prev_pos - current_pos, 1),  # positive = improved
            "clicks": int(r["clicks"]),
            "impressions": int(r["impressions"]),
        })

    return results


def get_dashboard_summary(client_id: int, days: int = 30) -> dict:
    """Return KPIs with month-over-month deltas."""
    now = datetime.now(timezone.utc)
    current_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    prev_start = (now - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    prev_end = current_start

    def _sum_metric(conn, source, metric_type, start, end=None):
        sql = """SELECT SUM(value) as total FROM metrics
                 WHERE client_id = ? AND source = ? AND metric_type = ?
                   AND dimension = 'total' AND date >= ?"""
        params = [client_id, source, metric_type, start]
        if end:
            sql += " AND date < ?"
            params.append(end)
        row = conn.execute(sql, params).fetchone()
        return row["total"] or 0

    def _avg_metric(conn, source, metric_type, start, end=None):
        sql = """SELECT AVG(value) as avg_val FROM metrics
                 WHERE client_id = ? AND source = ? AND metric_type = ?
                   AND dimension = 'total' AND date >= ?"""
        params = [client_id, source, metric_type, start]
        if end:
            sql += " AND date < ?"
            params.append(end)
        row = conn.execute(sql, params).fetchone()
        return row["avg_val"] or 0

    with _connect() as conn:
        kpis = {}
        for name, source, mtype, agg in [
            ("total_clicks", "gsc", "clicks", "sum"),
            ("total_impressions", "gsc", "impressions", "sum"),
            ("avg_position", "gsc", "position", "avg"),
            ("avg_ctr", "gsc", "ctr", "avg"),
            ("total_sessions", "ga4", "sessions", "sum"),
            ("total_ad_spend_google", "google_ads", "cost", "sum"),
            ("total_ad_spend_meta", "meta_ads", "spend", "sum"),
            ("total_conversions_google", "google_ads", "conversions", "sum"),
            ("total_conversions_meta", "meta_ads", "conversions", "sum"),
            ("total_leads", "sheets", "leads", "sum"),
            ("total_revenue", "sheets", "revenue", "sum"),
        ]:
            fn = _sum_metric if agg == "sum" else _avg_metric
            current = fn(conn, source, mtype, current_start)
            previous = fn(conn, source, mtype, prev_start, prev_end)

            if agg == "sum":
                delta = ((current - previous) / previous * 100) if previous else 0
            else:
                delta = current - previous

            kpis[name] = {
                "current": round(current, 2),
                "previous": round(previous, 2),
                "delta": round(delta, 2),
            }

    return kpis


# ── Token functions ──────────────────────────────────────────────────────────

def create_dashboard_token(client_id: int, expires_days: Optional[int] = None) -> str:
    """Generate a shareable dashboard token."""
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    expires_at = None
    if expires_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()

    with _connect() as conn:
        conn.execute(
            """INSERT INTO dashboard_tokens (token, client_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, client_id, now, expires_at),
        )
        conn.commit()
    return token


def get_client_by_token(token: str) -> Optional[int]:
    """Return client_id if token is valid (not revoked, not expired), else None."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            """SELECT client_id, expires_at FROM dashboard_tokens
               WHERE token = ? AND revoked = 0""",
            (token,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] and row["expires_at"] < now:
            return None
        return row["client_id"]


def revoke_dashboard_token(token: str) -> bool:
    """Revoke a dashboard token."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE dashboard_tokens SET revoked = 1 WHERE token = ?",
            (token,),
        )
        conn.commit()
        return cur.rowcount > 0


# ── Sync status ──────────────────────────────────────────────────────────────

def get_sync_status(client_id: int) -> dict:
    """Return latest sync status per source."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT source, status, rows_synced, completed_at, error_msg
               FROM sync_log
               WHERE client_id = ?
               ORDER BY id DESC""",
            (client_id,),
        ).fetchall()

    status = {}
    for r in rows:
        src = r["source"]
        if src not in status:
            status[src] = {
                "status": r["status"],
                "rows_synced": r["rows_synced"],
                "completed_at": r["completed_at"],
                "error_msg": r["error_msg"],
            }
    return status
