"""
Pilot Context Builder — aggregates client data from all sources into a pulse snapshot.

Pulls from: vault data (YAML/MD), job history (SQLite), and optionally
Slack/Gmail/Calendar via MCP when available.

Produces a structured context dict that briefing, digest, and escalation modules consume.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

VAULT_DIR = Path(__file__).parent.parent.parent / "vault_data"
CLIENTS_INDEX = VAULT_DIR / "_clients-index.yaml"


def _load_clients_index() -> list[dict]:
    """Load all clients from the vault index."""
    if not CLIENTS_INDEX.exists():
        return []
    try:
        with open(CLIENTS_INDEX) as f:
            data = yaml.safe_load(f)
        return data.get("clients", []) if isinstance(data, dict) else data or []
    except Exception as e:
        logger.error(f"Failed to load clients index: {e}")
        return []


def _load_client_file(slug: str, filename: str) -> Optional[str]:
    """Load a client file from vault_data/clients/{slug}/{filename}."""
    path = VAULT_DIR / "clients" / slug / filename
    if path.exists():
        return path.read_text()
    return None


def _load_client_yaml(slug: str, filename: str) -> Optional[dict]:
    """Load and parse a client YAML file."""
    content = _load_client_file(slug, filename)
    if content:
        try:
            return yaml.safe_load(content)
        except Exception:
            return None
    return None


def build_context(db_connect=None) -> dict:
    """
    Build a full context snapshot across all clients.

    Returns:
    {
        "timestamp": "...",
        "clients": [
            {
                "slug": "...",
                "name": "...",
                "tier": 1,
                "manager": "...",
                "mrr": 0,
                "cadence": "...",
                "has_roadmap": true,
                "roadmap_pages_total": 0,
                "roadmap_pages_done": 0,
                "recurring_tasks": [],
                "recent_jobs": [],
                "days_since_last_work": 0,
                "status": "on_track|attention|overdue"
            }
        ],
        "team_workload": { "matthew": 0, "jo_paula": 0, ... },
        "overdue_clients": [],
        "attention_clients": [],
    }
    """
    clients_raw = _load_clients_index()
    now = datetime.now(timezone.utc)

    # Get recent jobs from DB if available
    recent_jobs_by_client = {}
    if db_connect:
        try:
            from utils.db import get_all_jobs
            jobs = get_all_jobs()
            for j in (jobs or []):
                cn = j.get("client_name", "").lower().replace(" ", "-")
                if cn not in recent_jobs_by_client:
                    recent_jobs_by_client[cn] = []
                recent_jobs_by_client[cn].append({
                    "id": j.get("id"),
                    "workflow": j.get("workflow_title", ""),
                    "created_at": j.get("created_at", ""),
                })
        except Exception as e:
            logger.error(f"Failed to load jobs: {e}")

    clients = []
    team_workload = {}
    overdue = []
    attention = []

    for c in clients_raw:
        slug = c.get("folder") or c.get("slug", "")
        if not slug:
            continue

        # Load vault data
        roadmap = _load_client_yaml(slug, "roadmap.yaml")
        recurring = _load_client_yaml(slug, "recurring.yaml")

        # Roadmap stats
        roadmap_total = 0
        roadmap_done = 0
        if roadmap and isinstance(roadmap, dict):
            pages = roadmap.get("pages", [])
            if isinstance(pages, list):
                roadmap_total = len(pages)
                roadmap_done = sum(1 for p in pages if p.get("status") in ("done", "published", "live"))

        # Recurring tasks
        recurring_tasks = []
        if recurring and isinstance(recurring, dict):
            for category, tasks in recurring.items():
                if isinstance(tasks, list):
                    recurring_tasks.extend(tasks)

        # Recent jobs
        client_jobs = recent_jobs_by_client.get(slug, [])
        client_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Days since last work (from jobs or log)
        days_since = 999
        if client_jobs:
            last_date_str = client_jobs[0].get("created_at", "")
            if last_date_str:
                try:
                    last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00"))
                    days_since = (now - last_date).days
                except Exception:
                    pass

        # Determine status
        cadence = c.get("cadence", "monthly")
        cadence_days = {"weekly": 7, "biweekly": 14, "monthly": 30}.get(cadence, 30)
        if days_since >= 999:
            # No job history available — can't determine status from jobs alone
            # Mark as attention so it shows up in reviews but isn't a false alarm
            status = "unknown"
        elif days_since > cadence_days * 1.5:
            status = "overdue"
            overdue.append(slug)
        elif days_since > cadence_days:
            status = "attention"
            attention.append(slug)
        else:
            status = "on_track"

        manager = c.get("manager", "matthew")
        if manager not in team_workload:
            team_workload[manager] = 0
        team_workload[manager] += 1

        clients.append({
            "slug": slug,
            "name": c.get("client") or c.get("name", slug),
            "tier": c.get("tier", 3),
            "manager": manager,
            "mrr": c.get("mrr", 0),
            "cadence": cadence,
            "has_roadmap": roadmap is not None,
            "roadmap_pages_total": roadmap_total,
            "roadmap_pages_done": roadmap_done,
            "recurring_tasks_count": len(recurring_tasks),
            "recent_jobs_count": len(client_jobs),
            "recent_jobs": client_jobs[:5],
            "days_since_last_work": days_since if days_since < 999 else None,
            "status": status,
        })

    # Sort by tier (Tier 1 first), then by status urgency
    status_order = {"overdue": 0, "attention": 1, "unknown": 2, "on_track": 3}
    clients.sort(key=lambda x: (x["tier"], status_order.get(x["status"], 2)))

    return {
        "timestamp": now.isoformat(),
        "clients": clients,
        "team_workload": team_workload,
        "overdue_clients": overdue,
        "attention_clients": attention,
        "total_clients": len(clients),
    }
