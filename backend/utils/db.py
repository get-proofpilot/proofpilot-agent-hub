"""
ProofPilot — SQLite job store

DATABASE_PATH env var: path to jobs.db (default: ./jobs.db relative to backend/)
Set to a Railway volume mount path (e.g. /app/data/jobs.db) for persistence.
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    str(Path(__file__).parent.parent / "jobs.db")
)


def _get_db_path() -> str:
    """Return the resolved database file path (used by content_db / tasks_db)."""
    return DB_PATH


def _connect() -> sqlite3.Connection:
    # Ensure parent directory exists (required when using a Railway Volume path)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                client_name   TEXT NOT NULL DEFAULT '',
                workflow_title TEXT NOT NULL DEFAULT '',
                workflow_id   TEXT NOT NULL DEFAULT '',
                inputs        TEXT NOT NULL DEFAULT '{}',
                content       TEXT NOT NULL DEFAULT '',
                docx_path     TEXT,
                created_at    TEXT NOT NULL
            )
        """)

        # ── Clients table ───────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                domain           TEXT NOT NULL DEFAULT '',
                service          TEXT NOT NULL DEFAULT '',
                location         TEXT NOT NULL DEFAULT '',
                plan             TEXT NOT NULL DEFAULT 'Starter',
                monthly_revenue  TEXT NOT NULL DEFAULT '',
                avg_job_value    TEXT NOT NULL DEFAULT '',
                status           TEXT NOT NULL DEFAULT 'active',
                color            TEXT NOT NULL DEFAULT '#0051FF',
                initials         TEXT NOT NULL DEFAULT '',
                notes            TEXT NOT NULL DEFAULT '',
                strategy_context TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            )
        """)
        conn.commit()

        # ── Jobs table migrations ────────────────────────────────────
        for col_sql in [
            "ALTER TABLE jobs ADD COLUMN client_id INTEGER DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN approved INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN approved_at TEXT",
        ]:
            try:
                conn.execute(col_sql)
                conn.commit()
            except Exception:
                pass  # Column already exists

        # ── Clients table migrations ──────────────────────────────
        for col_sql in [
            "ALTER TABLE clients ADD COLUMN gsc_property TEXT DEFAULT ''",
            "ALTER TABLE clients ADD COLUMN ga4_property_id TEXT DEFAULT ''",
            "ALTER TABLE clients ADD COLUMN google_ads_customer_id TEXT DEFAULT ''",
            "ALTER TABLE clients ADD COLUMN meta_ad_account_id TEXT DEFAULT ''",
            "ALTER TABLE clients ADD COLUMN sheets_config TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(col_sql)
                conn.commit()
            except Exception:
                pass  # Column already exists

        # ── Metrics tables ─────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id     INTEGER NOT NULL,
                source        TEXT NOT NULL,
                metric_type   TEXT NOT NULL,
                dimension     TEXT NOT NULL DEFAULT '',
                value         REAL NOT NULL,
                date          TEXT NOT NULL,
                metadata      TEXT NOT NULL DEFAULT '{}',
                synced_at     TEXT NOT NULL,
                UNIQUE(client_id, source, metric_type, dimension, date)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_client_source
            ON metrics(client_id, source, metric_type, date)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_dimension
            ON metrics(client_id, source, metric_type, dimension)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                rows_synced INTEGER DEFAULT 0,
                error_msg TEXT DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_tokens (
                token TEXT PRIMARY KEY,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tokens_client
            ON dashboard_tokens(client_id)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_roadmap (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                month TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                page_type TEXT NOT NULL DEFAULT '',
                content_silo TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                keyword TEXT NOT NULL DEFAULT '',
                volume INTEGER DEFAULT 0,
                difficulty INTEGER DEFAULT 0,
                sheets_source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_roadmap_client_month
            ON content_roadmap(client_id, month)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                status TEXT NOT NULL DEFAULT 'not_started',
                month TEXT NOT NULL DEFAULT '',
                job_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_tasks_client_month
            ON client_tasks(client_id, month)
        """)
        conn.commit()

        # ── Scheduled jobs table ───────────────────────────────────────
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

        # ── Pipeline tables ───────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                pipeline_id        TEXT PRIMARY KEY,
                page_type          TEXT NOT NULL,
                client_id          INTEGER NOT NULL,
                client_name        TEXT NOT NULL DEFAULT '',
                inputs_json        TEXT NOT NULL DEFAULT '{}',
                stages_json        TEXT NOT NULL DEFAULT '[]',
                approval_mode      TEXT NOT NULL DEFAULT 'autopilot',
                status             TEXT NOT NULL DEFAULT 'pending',
                current_stage_index INTEGER NOT NULL DEFAULT 0,
                artifacts_json     TEXT NOT NULL DEFAULT '{}',
                stage_outputs_json TEXT NOT NULL DEFAULT '{}',
                error              TEXT,
                created_at         TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_client
            ON pipeline_runs(client_id, status)
        """)

        # ── Client memory table ───────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(client_id, memory_type, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_memory_client
            ON client_memory(client_id, memory_type)
        """)
        conn.commit()

        # ── Sprint runs table ────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sprint_runs (
                sprint_id     TEXT PRIMARY KEY,
                client_id     INTEGER NOT NULL,
                name          TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'pending',
                items_json    TEXT NOT NULL DEFAULT '[]',
                pipeline_ids  TEXT NOT NULL DEFAULT '[]',
                results_json  TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL,
                completed_at  TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sprint_runs_client
            ON sprint_runs(client_id, created_at)
        """)
        conn.commit()

        # ── Seed clients if table is empty ──────────────────────────
        count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            seed_clients = [
                ("All Thingz Electric",          "allthingzelectric.com",         "Starter",    "active",   "#7C3AED", "AE"),
                ("Adam Levinstein Photography",  "adamlevinstein.com",            "Starter",    "active",   "#7C3AED", "AL"),
                ("Dolce Electric",               "dolceelectric.com",             "Starter",    "active",   "#7C3AED", "DE"),
                ("Integrative Sports and Spine", "integrativesportsandspine.com", "Agency",     "active",   "#0D9488", "IS"),
                ("Saiyan Electric",              "saiyanelectric.com",            "Starter",    "active",   "#7C3AED", "SE"),
                ("Cedar Gold Group",             "cedargoldgroup.com",            "Agency",     "active",   "#0D9488", "CG"),
                ("Pelican Coast Electric",       "pelicancoastelectric.com",      "Starter",    "active",   "#7C3AED", "PC"),
                ("ProofPilot",                   "proofpilot.com",                "Agency",     "active",   "#0051FF", "PP"),
                ("Xsite Belize",                 "xsitebelize.com",               "Starter",    "active",   "#7C3AED", "XB"),
                ("Power Route Electric",         "powerrouteelectric.com",        "Starter",    "active",   "#7C3AED", "PR"),
                ("Alpha Property Management",    "alphapropertymgmt.com",         "Agency",     "active",   "#7C3AED", "AP"),
                ("Trading Academy",              "tradingacademy.com",            "Enterprise", "active",   "#7C3AED", "TA"),
                ("Youth Link",                   "youthlink.org",                 "Starter",    "inactive", "#F59E3B", "YL"),
                ("LAF Counseling",               "lafcounseling.com",             "Starter",    "active",   "#EA580C", "LC"),
            ]
            conn.executemany(
                """INSERT INTO clients
                   (name, domain, plan, status, color, initials, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(name, domain, plan, status, color, initials, now, now)
                 for name, domain, plan, status, color, initials in seed_clients]
            )
            conn.commit()


# ── Job functions ────────────────────────────────────────────────────────────

def save_job(job_id: str, data: dict) -> None:
    """Insert or replace a completed job. Called from asyncio.to_thread()."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs
              (job_id, client_name, workflow_title, workflow_id,
               inputs, content, docx_path, created_at, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                data.get("client_name", ""),
                data.get("workflow_title", ""),
                data.get("workflow_id", ""),
                json.dumps(data.get("inputs", {})),
                data.get("content", ""),
                data.get("docx_path"),
                data.get("created_at", datetime.now(timezone.utc).isoformat()),
                data.get("client_id", 0),
            ),
        )
        conn.commit()


def update_docx_path(job_id: str, docx_path: str) -> None:
    """Set docx_path after the document is generated."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET docx_path = ? WHERE job_id = ?",
            (docx_path, job_id),
        )
        conn.commit()


def update_job_content(job_id: str, content: str) -> None:
    """Update the content field of an existing job (used by document editing)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET content = ? WHERE job_id = ?",
            (content, job_id),
        )
        conn.commit()


def get_job(job_id: str) -> Optional[dict]:
    """Return a single job dict or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["inputs"] = json.loads(d["inputs"])
        return d


def get_all_jobs() -> list:
    """Return all jobs sorted newest-first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["inputs"] = json.loads(d["inputs"])
            result.append(d)
        return result


def approve_job(job_id: str) -> bool:
    """Set approved=1 and record approval time."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET approved=1, approved_at=? WHERE job_id=?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        conn.commit()
        return cur.rowcount > 0


def unapprove_job(job_id: str) -> bool:
    """Set approved=0 and clear approval time."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET approved=0, approved_at=NULL WHERE job_id=?",
            (job_id,),
        )
        conn.commit()
        return cur.rowcount > 0


# ── Client CRUD functions ────────────────────────────────────────────────────

def _auto_initials(name: str) -> str:
    words = [w for w in name.split() if w]
    return "".join(w[0] for w in words[:2]).upper()


def create_client(data: dict) -> dict:
    """INSERT a new client and return the full row."""
    now = datetime.now(timezone.utc).isoformat()
    name = data.get("name", "").strip()
    initials = data.get("initials", "").strip() or _auto_initials(name)
    color = data.get("color", "#0051FF")
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO clients
               (name, domain, service, location, plan, monthly_revenue, avg_job_value,
                status, color, initials, notes, strategy_context, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                data.get("domain", ""),
                data.get("service", ""),
                data.get("location", ""),
                data.get("plan", "Starter"),
                data.get("monthly_revenue", ""),
                data.get("avg_job_value", ""),
                data.get("status", "active"),
                color,
                initials,
                data.get("notes", ""),
                data.get("strategy_context", ""),
                now, now,
            ),
        )
        conn.commit()
        return get_client(cur.lastrowid)


def get_client(client_id: int) -> Optional[dict]:
    """Return a single client dict or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_clients() -> list:
    """Return all non-deleted clients sorted by name."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clients WHERE status != 'deleted' ORDER BY name ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_client(client_id: int, data: dict) -> Optional[dict]:
    """PATCH semantics — only update provided keys."""
    allowed = {
        "name", "domain", "service", "location", "plan",
        "monthly_revenue", "avg_job_value", "status",
        "color", "initials", "notes", "strategy_context",
        "gsc_property", "ga4_property_id",
        "google_ads_customer_id", "meta_ad_account_id", "sheets_config",
    }
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not updates:
        return get_client(client_id)

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [client_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE clients SET {set_clause} WHERE client_id = ?", values
        )
        conn.commit()
    return get_client(client_id)


def delete_client(client_id: int) -> bool:
    """Soft-delete: set status='deleted'."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE clients SET status='deleted', updated_at=? WHERE client_id=?",
            (datetime.now(timezone.utc).isoformat(), client_id),
        )
        conn.commit()
        return cur.rowcount > 0


# ── Sprint run functions ───────────────────────────────────────────────────

def save_sprint(sprint_id: str, data: dict) -> None:
    """Insert or replace a sprint run record."""
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO sprint_runs
               (sprint_id, client_id, name, status, items_json,
                pipeline_ids, results_json, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sprint_id,
                data.get("client_id", 0),
                data.get("name", ""),
                data.get("status", "pending"),
                json.dumps(data.get("items", [])),
                json.dumps(data.get("pipeline_ids", [])),
                json.dumps(data.get("results", {})),
                data.get("created_at", datetime.now(timezone.utc).isoformat()),
                data.get("completed_at"),
            ),
        )
        conn.commit()


def get_sprint(sprint_id: str) -> Optional[dict]:
    """Return a single sprint run dict or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sprint_runs WHERE sprint_id = ?", (sprint_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["items"] = json.loads(d.pop("items_json"))
        d["pipeline_ids"] = json.loads(d.pop("pipeline_ids"))
        d["results"] = json.loads(d.pop("results_json"))
        return d


def get_client_sprints(client_id: int) -> list[dict]:
    """Return all sprints for a client, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sprint_runs WHERE client_id = ? ORDER BY created_at DESC",
            (client_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["items"] = json.loads(d.pop("items_json"))
            d["pipeline_ids"] = json.loads(d.pop("pipeline_ids"))
            d["results"] = json.loads(d.pop("results_json"))
            results.append(d)
        return results
