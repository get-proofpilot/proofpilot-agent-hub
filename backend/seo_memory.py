"""
SEO Memory — structured per-client month-over-month SEO intelligence.

Stores and retrieves memory per client on the Railway persistent volume.
Each client gets a JSON file with monthly plan summaries, pages planned/completed,
audit findings, strategic notes, and learnings.  Memory is automatically
injected into executor prompts.

This module is fully standalone — no imports from server.py or seo_executor.py.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Storage directory
# ---------------------------------------------------------------------------

_FALLBACK_DIR = Path(__file__).parent / 'seo-memory'

try:
    MEMORY_DIR = Path(os.environ.get('DOCS_DIR', Path(__file__).parent / 'data')) / 'seo-memory'
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    MEMORY_DIR = _FALLBACK_DIR
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_slug(slug: str) -> str:
    """Allow only alphanumeric characters, dashes, and underscores."""
    return re.sub(r'[^a-zA-Z0-9_-]', '', slug)


def _client_path(client_slug: str) -> Path:
    """Return the JSON file path for a given client slug."""
    safe = _sanitize_slug(client_slug)
    return MEMORY_DIR / f'{safe}.json'


def _empty_client_schema(client_slug: str) -> dict:
    return {
        'client': client_slug,
        'last_updated': None,
        'months': {},
        'roadmap_status': {},
        'strategic_context': [],
        'learnings': [],
    }


def _empty_global_schema() -> dict:
    return {
        'type': 'global',
        'last_updated': None,
        'patterns': [],
        'process_improvements': [],
    }


_MONTH_LABELS = [
    'Last Month', 'Two Months Ago', 'Three Months Ago',
    'Four Months Ago', 'Five Months Ago', 'Six Months Ago',
]

_MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


# ---------------------------------------------------------------------------
# Core read / write
# ---------------------------------------------------------------------------

def read_memory(client_slug: str) -> dict:
    """Read a client's memory file. Returns empty schema if missing."""
    path = _client_path(client_slug)
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return _empty_client_schema(client_slug)


def write_memory(client_slug: str, data: dict) -> None:
    """Save a client's memory file with updated timestamp."""
    data['last_updated'] = datetime.utcnow().isoformat()
    path = _client_path(client_slug)
    try:
        path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def read_global_memory() -> dict:
    """Read the global memory file. Returns empty schema if missing."""
    path = MEMORY_DIR / '_global.json'
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return _empty_global_schema()


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_current_month_key() -> str:
    """Return the current month as 'YYYY-MM'."""
    return datetime.utcnow().strftime('%Y-%m')


def get_previous_month_key() -> str:
    """Return the previous month as 'YYYY-MM'."""
    today = datetime.utcnow()
    first_of_month = today.replace(day=1)
    last_month = first_of_month - timedelta(days=1)
    return last_month.strftime('%Y-%m')


# ---------------------------------------------------------------------------
# Plan / Audit / Wrap-up updates
# ---------------------------------------------------------------------------

def update_after_plan(client_slug: str, plan_output: str, result_id: str) -> None:
    """Extract plan data and store in the current month's memory."""
    data = read_memory(client_slug)
    month_key = get_current_month_key()

    # Extract plan summary — first paragraph after Strategic Theme / Focus
    summary = ''
    theme_match = re.search(
        r'(?:Strategic\s+Theme|Strategic\s+Focus)[:\s]*(.+?)(?:\n\n|\n-|\n#)',
        plan_output,
        re.IGNORECASE | re.DOTALL,
    )
    if theme_match:
        summary = theme_match.group(1).strip()
    else:
        # Fallback: use the first non-empty paragraph
        for paragraph in plan_output.split('\n\n'):
            cleaned = paragraph.strip()
            if cleaned and not cleaned.startswith('#'):
                summary = cleaned
                break
    summary = summary[:200]

    # Extract page URLs from checkbox lines (- [ ] ... /something/)
    urls: list[str] = []
    for line in plan_output.splitlines():
        if re.match(r'\s*-\s*\[[ x]?\]', line, re.IGNORECASE):
            found = re.findall(r'(/[a-z0-9][a-z0-9-]*/)', line, re.IGNORECASE)
            urls.extend(found)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    month_data = {
        'plan_id': result_id,
        'plan_summary': summary,
        'pages_planned': unique_urls,
        'pages_completed': [],
        'pages_missed': [],
        'audit_findings': '',
        'strategic_notes': [],
        'wrap_up_summary': '',
    }

    data.setdefault('months', {})[month_key] = month_data
    write_memory(client_slug, data)


def update_after_audit(client_slug: str, audit_output: str) -> None:
    """Extract audit findings and store in the previous month's memory."""
    data = read_memory(client_slug)
    prev_key = get_previous_month_key()

    # Try to extract the Deliverables Scorecard section
    findings = ''
    scorecard_match = re.search(
        r'(Deliverables\s+Scorecard.+?)(?:\n#{1,3}\s|\Z)',
        audit_output,
        re.IGNORECASE | re.DOTALL,
    )
    if scorecard_match:
        findings = scorecard_match.group(1).strip()[:300]
    else:
        findings = audit_output.strip()[:300]

    month_data = data.setdefault('months', {}).setdefault(prev_key, {
        'plan_id': '',
        'plan_summary': '',
        'pages_planned': [],
        'pages_completed': [],
        'pages_missed': [],
        'audit_findings': '',
        'strategic_notes': [],
        'wrap_up_summary': '',
    })
    month_data['audit_findings'] = findings
    write_memory(client_slug, data)


def update_after_wrapup(client_slug: str, wrapup_output: str) -> None:
    """Extract wrap-up summary and store in the current month's memory."""
    data = read_memory(client_slug)
    cur_key = get_current_month_key()

    summary = wrapup_output.strip()[:300]

    month_data = data.setdefault('months', {}).setdefault(cur_key, {
        'plan_id': '',
        'plan_summary': '',
        'pages_planned': [],
        'pages_completed': [],
        'pages_missed': [],
        'audit_findings': '',
        'strategic_notes': [],
        'wrap_up_summary': '',
    })
    month_data['wrap_up_summary'] = summary
    write_memory(client_slug, data)


# ---------------------------------------------------------------------------
# Strategic notes & learnings
# ---------------------------------------------------------------------------

def add_strategic_note(client_slug: str, note: str) -> None:
    """Append a timestamped note. Keep max 20 (trim oldest)."""
    data = read_memory(client_slug)
    entry = f"{datetime.utcnow().strftime('%Y-%m-%d')}: {note}"
    ctx = data.setdefault('strategic_context', [])
    ctx.append(entry)
    if len(ctx) > 20:
        data['strategic_context'] = ctx[-20:]
    write_memory(client_slug, data)


def add_learning(client_slug: str, learning: str) -> None:
    """Append a learning. Keep max 15 (trim oldest)."""
    data = read_memory(client_slug)
    learnings = data.setdefault('learnings', [])
    learnings.append(learning)
    if len(learnings) > 15:
        data['learnings'] = learnings[-15:]
    write_memory(client_slug, data)


# ---------------------------------------------------------------------------
# Roadmap tracking
# ---------------------------------------------------------------------------

def mark_page_complete(client_slug: str, url: str) -> None:
    """Mark a page as live in roadmap_status and add to current month's pages_completed."""
    data = read_memory(client_slug)
    data.setdefault('roadmap_status', {})[url] = 'live'

    cur_key = get_current_month_key()
    month_data = data.get('months', {}).get(cur_key)
    if month_data:
        planned = month_data.get('pages_planned', [])
        completed = month_data.get('pages_completed', [])
        if url in planned and url not in completed:
            completed.append(url)
            month_data['pages_completed'] = completed

    write_memory(client_slug, data)


# ---------------------------------------------------------------------------
# Prompt injection — recent history
# ---------------------------------------------------------------------------

def get_recent_history(client_slug: str, num_months: int = 3) -> str:
    """Return a formatted text block of recent months for prompt injection."""
    data = read_memory(client_slug)
    months = data.get('months', {})

    if not months:
        return 'No previous history available \u2014 this is the first month of tracking.'

    # Sort month keys in reverse chronological order
    sorted_keys = sorted(months.keys(), reverse=True)[:num_months]

    if not sorted_keys:
        return 'No previous history available \u2014 this is the first month of tracking.'

    lines: list[str] = ['## Memory: Previous Months']

    for idx, month_key in enumerate(sorted_keys):
        m = months[month_key]

        # Build a human-readable label
        try:
            dt = datetime.strptime(month_key, '%Y-%m')
            month_name = f"{_MONTH_NAMES[dt.month - 1]} {dt.year}"
        except (ValueError, IndexError):
            month_name = month_key

        label = _MONTH_LABELS[idx] if idx < len(_MONTH_LABELS) else f"{idx + 1} Months Ago"
        lines.append(f'\n### {label} ({month_name})')

        plan_summary = m.get('plan_summary', '')
        if plan_summary:
            lines.append(f'- Plan: {plan_summary}')

        pages_planned = m.get('pages_planned', [])
        if pages_planned:
            lines.append(f"- Pages planned: {', '.join(pages_planned)}")

        pages_completed = m.get('pages_completed', [])
        if pages_completed:
            lines.append(f"- Pages completed: {', '.join(pages_completed)}")

        if pages_planned:
            total = len(pages_planned)
            done = len(pages_completed)
            pct = round((done / total) * 100) if total else 0
            lines.append(f'- Completion rate: {pct}%')

        audit_findings = m.get('audit_findings', '')
        if audit_findings:
            lines.append(f'- Audit findings: {audit_findings}')

        wrap_up = m.get('wrap_up_summary', '')
        if wrap_up:
            lines.append(f'- Wrap-up: {wrap_up}')

    # Strategic context
    strategic = data.get('strategic_context', [])
    if strategic:
        lines.append('\n### Strategic Context (accumulated)')
        for note in strategic:
            lines.append(f'- {note}')

    # Learnings
    learnings = data.get('learnings', [])
    if learnings:
        lines.append('\n### Learnings')
        for learning in learnings:
            lines.append(f'- {learning}')

    return '\n'.join(lines)
