"""
ClickUp REST API integration for syncing monthly SEO tasks.

Creates monthly SEO lists in client ClickUp spaces, pushes tasks from
recurring.yaml, and pulls completion status for progress tracking.
"""

import os
import json
import logging
from pathlib import Path
from functools import lru_cache

import yaml
import httpx

logger = logging.getLogger(__name__)

CLICKUP_BASE = "https://api.clickup.com/api/v2"

CONFIG_PATH = Path(__file__).parent / "vault_data" / "clickup_config.json"

# Priority mapping: category → ClickUp priority integer
# ClickUp priorities: 1=urgent, 2=high, 3=normal, 4=low
CATEGORY_PRIORITY = {
    "content": 1,
    "gbp": 3,
    "off_page": 3,
    "technical": 3,
    "reporting": 1,
}

# Category → display tag name
CATEGORY_TAG = {
    "content": "Content",
    "gbp": "GBP",
    "off_page": "Off-Page",
    "technical": "Technical",
    "reporting": "Reporting",
}


def get_config() -> dict:
    """Read and return the clickup_config.json file. Cached after first read."""
    return _load_config()


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Internal cached loader for the config file."""
    if not CONFIG_PATH.exists():
        logger.warning("clickup_config.json not found at %s", CONFIG_PATH)
        return {"workspace_id": "", "clients": {}}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read clickup_config.json: %s", exc)
        return {"workspace_id": "", "clients": {}}


def _headers() -> dict:
    """Build request headers with the ClickUp API key."""
    api_key = os.environ.get("CLICKUP_API_KEY", "")
    return {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }


def _client_display_name(slug: str) -> str:
    """Convert a slug like 'saiyan-electric' to 'Saiyan Electric'."""
    return slug.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------

async def create_monthly_list(client_slug: str, month_label: str) -> dict:
    """
    Create a new list in the client's SEO folder.

    Args:
        client_slug: Client key in clickup_config.json (e.g. 'saiyan-electric')
        month_label: List name (e.g. 'April 2026 Monthly SEO')

    Returns:
        The created list object from ClickUp, or an empty dict on failure.
    """
    config = get_config()
    client_cfg = config.get("clients", {}).get(client_slug)
    if not client_cfg:
        logger.error("No ClickUp config for client: %s", client_slug)
        return {}

    folder_id = client_cfg["seo_folder_id"]
    url = f"{CLICKUP_BASE}/folder/{folder_id}/list"
    payload = {"name": month_label}

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, headers=_headers(), json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "ClickUp create list failed (%s %s): %s",
            exc.response.status_code, client_slug, exc.response.text[:300],
        )
        return {}
    except httpx.RequestError as exc:
        logger.error("ClickUp request error creating list: %s", exc)
        return {}


async def push_tasks(client_slug: str, list_id: str, tasks: list[dict]) -> list[dict]:
    """
    Create ClickUp tasks from a list of task dicts.

    Each task dict should have:
        name (str): Task title
        category (str): e.g. 'content', 'gbp', 'off_page'
        time_estimate (str, optional): e.g. '2 hours', '30 min'
        priority (int, optional): 1=urgent, 2=high, 3=normal, 4=low

    Returns:
        List of created task objects from ClickUp.
    """
    url = f"{CLICKUP_BASE}/list/{list_id}/task"
    created = []

    async with httpx.AsyncClient(timeout=30) as http:
        for task in tasks:
            # Build tags list
            tags = []
            category = task.get("category", "")
            tag_name = CATEGORY_TAG.get(category, category.replace("_", " ").title())
            if tag_name:
                tags.append(tag_name)
            if task.get("owner") == "outsource":
                tags.append("Outsource")

            # Map priority: use task-level override or category default
            priority = task.get("priority")
            if priority is None:
                priority = CATEGORY_PRIORITY.get(category, 3)

            payload = {
                "name": task["name"],
                "priority": priority,
                "tags": tags,
            }

            # Parse time estimate into milliseconds if provided
            time_est = task.get("time_estimate", "")
            if time_est:
                ms = _parse_time_to_ms(time_est)
                if ms > 0:
                    payload["time_estimate"] = ms

            try:
                resp = await http.post(url, headers=_headers(), json=payload)
                resp.raise_for_status()
                created.append(resp.json())
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Failed to create task '%s': %s %s",
                    task["name"], exc.response.status_code, exc.response.text[:200],
                )
            except httpx.RequestError as exc:
                logger.warning("Request error creating task '%s': %s", task["name"], exc)

    return created


async def sync_monthly_plan(client_slug: str, month: str, vault_dir: Path) -> dict:
    """
    Main sync function: read recurring.yaml, create a monthly list, push tasks.

    Args:
        client_slug: e.g. 'saiyan-electric'
        month: e.g. 'April 2026'
        vault_dir: Path to vault_data directory

    Returns:
        Summary dict: {"list_id": "...", "list_name": "...", "tasks_created": N}
    """
    # 1. Read client's recurring.yaml
    recurring_path = vault_dir / "clients" / client_slug / "recurring.yaml"
    if not recurring_path.exists():
        logger.error("recurring.yaml not found for %s at %s", client_slug, recurring_path)
        return {"list_id": "", "list_name": "", "tasks_created": 0, "error": "recurring.yaml not found"}

    try:
        recurring = yaml.safe_load(recurring_path.read_text())
    except Exception as exc:
        logger.error("Failed to parse recurring.yaml for %s: %s", client_slug, exc)
        return {"list_id": "", "list_name": "", "tasks_created": 0, "error": str(exc)}

    if not recurring:
        return {"list_id": "", "list_name": "", "tasks_created": 0, "error": "Empty recurring.yaml"}

    # 2. Create the monthly list
    month_label = f"{month} Monthly SEO"
    list_obj = await create_monthly_list(client_slug, month_label)
    if not list_obj or "id" not in list_obj:
        return {"list_id": "", "list_name": month_label, "tasks_created": 0, "error": "Failed to create list"}

    list_id = list_obj["id"]

    # 3. Parse recurring.yaml categories into task dicts
    tasks = _parse_recurring_to_tasks(recurring)

    # 4. Push all tasks to the new list
    created = await push_tasks(client_slug, list_id, tasks)

    return {
        "list_id": list_id,
        "list_name": month_label,
        "tasks_created": len(created),
    }


async def get_progress(vault_dir: Path) -> list[dict]:
    """
    Get task completion rates for ALL clients.

    Returns a list of dicts:
        {"client": "Saiyan Electric", "slug": "saiyan-electric",
         "total": 20, "completed": 14, "percent": 70}
    """
    config = get_config()
    clients_cfg = config.get("clients", {})
    results = []

    async with httpx.AsyncClient(timeout=30) as http:
        for slug, cfg in clients_cfg.items():
            folder_id = cfg.get("seo_folder_id", "")
            if not folder_id:
                continue

            # Find the most recent list in the SEO folder
            latest_list = await _get_latest_list(http, folder_id)
            if not latest_list:
                results.append({
                    "client": _client_display_name(slug),
                    "slug": slug,
                    "total": 0,
                    "completed": 0,
                    "percent": 0,
                })
                continue

            # Get tasks from that list
            tasks = await _get_list_tasks(http, latest_list["id"])
            total = len(tasks)
            completed = sum(1 for t in tasks if _is_completed(t))
            percent = round((completed / total) * 100) if total > 0 else 0

            results.append({
                "client": _client_display_name(slug),
                "slug": slug,
                "total": total,
                "completed": completed,
                "percent": percent,
            })

    return results


async def get_client_progress(client_slug: str) -> dict:
    """
    Detailed task list for one client from their most recent monthly list.

    Returns:
        {"client": "...", "list_name": "...", "tasks": [
            {"name": "...", "status": "...", "assignee": "...", "category": "..."}
        ]}
    """
    config = get_config()
    client_cfg = config.get("clients", {}).get(client_slug)
    if not client_cfg:
        return {
            "client": _client_display_name(client_slug),
            "list_name": "",
            "tasks": [],
            "error": "Client not found in config",
        }

    folder_id = client_cfg.get("seo_folder_id", "")
    if not folder_id:
        return {
            "client": _client_display_name(client_slug),
            "list_name": "",
            "tasks": [],
            "error": "No SEO folder configured",
        }

    async with httpx.AsyncClient(timeout=30) as http:
        latest_list = await _get_latest_list(http, folder_id)
        if not latest_list:
            return {
                "client": _client_display_name(client_slug),
                "list_name": "",
                "tasks": [],
            }

        raw_tasks = await _get_list_tasks(http, latest_list["id"])

    task_details = []
    for t in raw_tasks:
        # Extract assignee name if present
        assignees = t.get("assignees", [])
        assignee_name = assignees[0].get("username", "") if assignees else ""

        # Extract category from tags
        tags = t.get("tags", [])
        category = ""
        for tag in tags:
            tag_name = tag.get("name", "") if isinstance(tag, dict) else str(tag)
            if tag_name.lower() in ("content", "gbp", "off-page", "technical", "reporting"):
                category = tag_name
                break

        status_obj = t.get("status", {})
        status_str = status_obj.get("status", "") if isinstance(status_obj, dict) else str(status_obj)

        task_details.append({
            "name": t.get("name", ""),
            "status": status_str,
            "assignee": assignee_name,
            "category": category,
        })

    return {
        "client": _client_display_name(client_slug),
        "list_name": latest_list.get("name", ""),
        "tasks": task_details,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_recurring_to_tasks(recurring: dict) -> list[dict]:
    """
    Convert a recurring.yaml structure into a flat list of task dicts
    ready for push_tasks().
    """
    tasks = []

    for category in ("content", "gbp", "off_page", "technical", "reporting"):
        items = recurring.get(category, [])
        if not items:
            continue
        for item in items:
            task_name = item.get("task", "")
            if not task_name:
                continue
            tasks.append({
                "name": task_name,
                "category": category,
                "time_estimate": str(item.get("time", "")),
                "owner": item.get("owner", "internal"),
                "priority": CATEGORY_PRIORITY.get(category, 3),
            })

    return tasks


def _parse_time_to_ms(time_str: str) -> int:
    """
    Parse a human-readable time string into milliseconds.
    Supports: '2 hours', '30 min', '1 hour', '15 min', '1.5 hours'
    """
    time_str = time_str.strip().lower()
    if not time_str:
        return 0

    import re
    # Try "N hour(s)" pattern
    match = re.match(r"(\d+(?:\.\d+)?)\s*hours?", time_str)
    if match:
        return int(float(match.group(1)) * 3600 * 1000)

    # Try "N min(utes)" pattern
    match = re.match(r"(\d+)\s*min(?:utes?)?", time_str)
    if match:
        return int(int(match.group(1)) * 60 * 1000)

    return 0


async def _get_latest_list(http: httpx.AsyncClient, folder_id: str) -> dict | None:
    """Fetch lists from a folder and return the most recent one."""
    url = f"{CLICKUP_BASE}/folder/{folder_id}/list"
    try:
        resp = await http.get(url, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        lists = data.get("lists", [])
        if not lists:
            return None
        # ClickUp returns lists; the first one is typically the most recent
        return lists[0]
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Failed to fetch lists for folder %s: %s",
            folder_id, exc.response.status_code,
        )
        return None
    except httpx.RequestError as exc:
        logger.warning("Request error fetching lists for folder %s: %s", folder_id, exc)
        return None


async def _get_list_tasks(http: httpx.AsyncClient, list_id: str) -> list[dict]:
    """Fetch all tasks from a ClickUp list."""
    url = f"{CLICKUP_BASE}/list/{list_id}/task"
    try:
        resp = await http.get(url, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("tasks", [])
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Failed to fetch tasks for list %s: %s",
            list_id, exc.response.status_code,
        )
        return []
    except httpx.RequestError as exc:
        logger.warning("Request error fetching tasks for list %s: %s", list_id, exc)
        return []


def _is_completed(task: dict) -> bool:
    """Check whether a ClickUp task is in a completed state."""
    status = task.get("status", {})
    if isinstance(status, dict):
        if status.get("type", "").lower() == "closed":
            return True
        if status.get("status", "").lower() == "complete":
            return True
    return False
