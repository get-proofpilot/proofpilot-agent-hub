"""
SEO Executor — runs SEO operations by calling the Anthropic API with vault data.

Takes a command name (audit, monthly-plan, weekly-plan, wrap-up, workload),
optionally a client slug, reads YAML/MD files from vault_data/, builds a
purpose-built prompt, and streams the Claude response back as an async generator.
"""

from pathlib import Path
from typing import AsyncGenerator

import yaml
import anthropic


# ---------------------------------------------------------------------------
# Vault readers
# ---------------------------------------------------------------------------

def _safe_read_yaml(filepath: Path):
    """Read and parse a YAML file, returning None on any failure."""
    if not filepath.exists():
        return None
    try:
        return yaml.safe_load(filepath.read_text())
    except Exception:
        return None


def _safe_read_text(filepath: Path) -> str:
    """Read a text file, returning a fallback message on any failure."""
    if not filepath.exists():
        return "Not available"
    try:
        return filepath.read_text()
    except Exception:
        return "Not available"


def read_client_context(slug: str, vault_dir: Path) -> dict:
    """Read all YAML/MD files for a single client and return structured data."""
    index_data = _safe_read_yaml(vault_dir / '_clients-index.yaml')
    if not index_data or 'clients' not in index_data:
        raise ValueError(f"Cannot read client index at {vault_dir / '_clients-index.yaml'}")

    # Find the client entry in the index by matching folder slug
    client_entry = None
    for c in index_data['clients']:
        if c.get('folder') == slug:
            client_entry = c
            break

    if client_entry is None:
        raise ValueError(f"Client '{slug}' not found in _clients-index.yaml")

    client_dir = vault_dir / 'clients' / slug

    recurring_data = _safe_read_yaml(client_dir / 'recurring.yaml')
    recurring_text = (client_dir / 'recurring.yaml').read_text() if (client_dir / 'recurring.yaml').exists() else "No recurring tasks available"

    roadmap_text = (client_dir / 'roadmap.yaml').read_text() if (client_dir / 'roadmap.yaml').exists() else "No roadmap available"

    context_text = _safe_read_text(client_dir / 'context.md')

    return {
        'name': client_entry.get('client', slug),
        'slug': slug,
        'tier': client_entry.get('tier', 3),
        'mrr': client_entry.get('mrr', 0),
        'manager': client_entry.get('manager', 'Unknown'),
        'recurring': recurring_text,
        'roadmap': roadmap_text,
        'context': context_text,
    }


def read_all_clients(vault_dir: Path) -> list[dict]:
    """Read _clients-index.yaml and return basic info for all active clients."""
    index_data = _safe_read_yaml(vault_dir / '_clients-index.yaml')
    if not index_data or 'clients' not in index_data:
        raise ValueError(f"Cannot read client index at {vault_dir / '_clients-index.yaml'}")

    results = []
    for c in index_data['clients']:
        if c.get('status') != 'active':
            continue

        slug = c.get('folder', '')
        client_dir = vault_dir / 'clients' / slug

        # Read recurring tasks for summary
        recurring_data = _safe_read_yaml(client_dir / 'recurring.yaml')
        key_tasks = []
        if recurring_data:
            for category in ('content', 'gbp', 'off_page', 'technical', 'reporting'):
                items = recurring_data.get(category, [])
                if isinstance(items, list):
                    for item in items[:3]:
                        if isinstance(item, dict) and item.get('task'):
                            key_tasks.append(item['task'])

        services = c.get('services', [])
        if isinstance(services, str):
            services = [s.strip() for s in services.split(',')]

        results.append({
            'name': c.get('client', slug),
            'slug': slug,
            'tier': c.get('tier', 3),
            'mrr': c.get('mrr', 0),
            'manager': c.get('manager', 'Unknown'),
            'cadence': c.get('cadence', 'monthly'),
            'services': services,
            'key_tasks': key_tasks,
        })

    return results


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_PROMPTS = {
    'audit': (
        "You are an SEO operations auditor for ProofPilot agency. "
        "Compare this client's planned monthly deliverables against what was actually completed.\n\n"
        "Client: {name}, Tier {tier}, ${mrr}/mo, Manager: {manager}\n\n"
        "RECURRING TASKS:\n{recurring}\n\n"
        "CLIENT CONTEXT:\n{context}\n\n"
        "Produce a clear audit report with:\n"
        "1) Planned vs completed\n"
        "2) Gaps or missed items\n"
        "3) Quality notes\n"
        "4) Recommendations for next month"
    ),
    'monthly-plan': (
        "You are an SEO operations planner for ProofPilot agency. "
        "Generate next month's detailed plan for this client.\n\n"
        "Client: {name}, Tier {tier}, ${mrr}/mo, Manager: {manager}\n\n"
        "RECURRING TASKS:\n{recurring}\n\n"
        "ROADMAP (pages to build):\n{roadmap}\n\n"
        "CLIENT CONTEXT:\n{context}\n\n"
        "Produce a plan organized by Week 1-4 with specific tasks, page URLs from roadmap, "
        "and category groupings (Content, GBP, Off-Page, Technical, Reporting)."
    ),
    'wrap-up': (
        "You are an SEO operations coordinator for ProofPilot agency. "
        "Generate a month-end wrap-up for this client.\n\n"
        "Client: {name}, Tier {tier}, ${mrr}/mo, Manager: {manager}\n\n"
        "RECURRING TASKS:\n{recurring}\n\n"
        "CLIENT CONTEXT:\n{context}\n\n"
        "Produce:\n"
        "1) Summary of what should have been completed this month\n"
        "2) Client update email draft (professional, results-focused)\n"
        "3) Recommendations for next month"
    ),
}


def _build_all_clients_block(clients: list[dict]) -> str:
    """Format all clients into a text block for global prompts."""
    lines = []
    for c in clients:
        tasks_str = ', '.join(c['key_tasks'][:5]) if c['key_tasks'] else 'See recurring tasks'
        services_str = ', '.join(c['services']) if c['services'] else 'N/A'
        lines.append(
            f"- {c['name']} | Tier {c['tier']} | ${c['mrr']}/mo | "
            f"Manager: {c['manager']} | Cadence: {c['cadence']} | "
            f"Services: {services_str} | Key tasks: {tasks_str}"
        )
    return '\n'.join(lines)


_GLOBAL_PROMPTS = {
    'weekly-plan': (
        "You are an SEO operations planner for ProofPilot agency. "
        "Generate this week's prioritized work plan across ALL clients.\n\n"
        "Prioritize by:\n"
        "1) Contractual/overdue\n"
        "2) Tier 1 high-impact\n"
        "3) Tier 1 recurring\n"
        "4) Tier 2\n"
        "5) Tier 3\n\n"
        "ALL CLIENTS:\n{clients_block}\n\n"
        "Produce a prioritized checklist grouped by manager (Matthew, Marcos, Jo Paula) "
        "with specific tasks and client names."
    ),
    'workload': (
        "You are an SEO operations manager for ProofPilot agency. "
        "Analyze team workload across ALL clients.\n\n"
        "ALL CLIENTS:\n{clients_block}\n\n"
        "Produce:\n"
        "1) Hours per manager this month\n"
        "2) Who's over/under capacity\n"
        "3) Stalled clients or blocked work\n"
        "4) Rebalancing recommendations"
    ),
}


def build_prompt(command: str, client_data_or_list) -> str:
    """Build the full prompt for the given command.

    For per-client commands (audit, monthly-plan, wrap-up), client_data_or_list
    is a dict from read_client_context().

    For global commands (weekly-plan, workload), it is a list from
    read_all_clients().
    """
    if command in ('weekly-plan', 'workload'):
        clients_block = _build_all_clients_block(client_data_or_list)
        return _GLOBAL_PROMPTS[command].format(clients_block=clients_block)

    if command not in _PROMPTS:
        raise ValueError(f"Unknown command: {command}")

    return _PROMPTS[command].format(**client_data_or_list)


# ---------------------------------------------------------------------------
# Executor (async generator that streams text chunks)
# ---------------------------------------------------------------------------

async def execute(
    command: str,
    client_slug: str | None,
    vault_dir: Path,
) -> AsyncGenerator[str, None]:
    """Run an SEO command and yield streamed text chunks from Claude."""

    # Read vault data
    if command in ('weekly-plan', 'workload'):
        data = read_all_clients(vault_dir)
    else:
        if not client_slug:
            raise ValueError(f"Client slug is required for command '{command}'")
        data = read_client_context(client_slug, vault_dir)

    prompt = build_prompt(command, data)

    client = anthropic.Anthropic()

    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
