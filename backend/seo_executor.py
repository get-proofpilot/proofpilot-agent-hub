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
# Constants
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {'HIGH': 0, 'MED': 1, 'LOW': 2}


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


def _extract_next_pages(roadmap_data: dict, limit: int = 10) -> list[dict]:
    """Extract next pages from roadmap pages_pipeline, sorted by priority.

    Returns pages where status is 'needed' (or anything other than
    'live', 'done', 'skipped'). Sorted HIGH > MED > LOW, capped at limit.
    """
    if not roadmap_data:
        return []

    pipeline = roadmap_data.get('pages_pipeline')
    if not pipeline or not isinstance(pipeline, list):
        return []

    needed = []
    for entry in pipeline:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get('status', 'needed')).lower()
        if status in ('live', 'done', 'skipped'):
            continue
        needed.append(entry)

    needed.sort(key=lambda p: _PRIORITY_ORDER.get(str(p.get('priority', 'LOW')).upper(), 2))
    return needed[:limit]


def _extract_next_blogs(roadmap_data: dict, limit: int = 5) -> list[dict]:
    """Extract next blog posts from roadmap blogs_pipeline, sorted by priority."""
    if not roadmap_data:
        return []

    pipeline = roadmap_data.get('blogs_pipeline')
    if not pipeline or not isinstance(pipeline, list):
        return []

    needed = []
    for entry in pipeline:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get('status', 'needed')).lower()
        if status in ('live', 'done', 'published', 'skipped'):
            continue
        needed.append(entry)

    needed.sort(key=lambda p: _PRIORITY_ORDER.get(str(p.get('priority', 'LOW')).upper(), 2))
    return needed[:limit]


def _extract_targets(roadmap_data: dict) -> dict | None:
    """Extract the targets dict from roadmap data."""
    if not roadmap_data:
        return None
    return roadmap_data.get('targets')


def _format_next_pages_text(pages: list[dict]) -> str:
    """Format extracted pages into a numbered, human-readable list."""
    if not pages:
        return "No roadmap pages available"

    lines = []
    for i, p in enumerate(pages, 1):
        url = p.get('url', '/unknown/')
        name = p.get('page', 'Untitled')
        priority = str(p.get('priority', 'MED')).upper()
        page_type = p.get('type', 'page')
        volume = p.get('volume')
        keyword = p.get('keyword', '')
        notes = p.get('notes', '')

        detail = f"{i}. {url} — {name} ({priority} priority, {page_type})"
        if keyword:
            detail += f"\n   Keyword: \"{keyword}\""
            if volume:
                detail += f" | Volume: {volume}/mo"
        if notes:
            detail += f"\n   Note: {notes}"
        lines.append(detail)

    return '\n'.join(lines)


def _format_next_blogs_text(blogs: list[dict]) -> str:
    """Format extracted blog posts into a numbered, human-readable list."""
    if not blogs:
        return "No blog pipeline available"

    lines = []
    for i, b in enumerate(blogs, 1):
        title = b.get('title', 'Untitled')
        priority = str(b.get('priority', 'MED')).upper()
        keyword = b.get('keyword', '')
        volume = b.get('volume')
        funnel = b.get('funnel', '')
        links_to = b.get('links_to', '')

        detail = f"{i}. \"{title}\" ({priority} priority"
        if funnel:
            detail += f", {funnel}"
        detail += ")"
        if keyword:
            detail += f"\n   Keyword: \"{keyword}\""
            if volume:
                detail += f" | Volume: {volume}/mo"
        if links_to:
            detail += f"\n   Links to: {links_to}"
        lines.append(detail)

    return '\n'.join(lines)


def _format_targets_text(targets: dict | None) -> str:
    """Format targets into a readable summary block."""
    if not targets:
        return "No targets available"

    baseline = targets.get('baseline_mar_2026', {})
    eoy = targets.get('eoy_2026', {})
    goal = targets.get('strategic_goal', '')

    lines = []

    # Build baseline line from whatever keys exist
    baseline_parts = []
    if baseline.get('pages'):
        baseline_parts.append(f"{baseline['pages']} pages")
    if baseline.get('keywords_ranking'):
        baseline_parts.append(f"{baseline['keywords_ranking']} keywords ranking")
    if baseline.get('monthly_organic_traffic'):
        baseline_parts.append(f"{baseline['monthly_organic_traffic']} organic visits/mo")
    if baseline.get('monthly_organic_visitors'):
        baseline_parts.append(f"{baseline['monthly_organic_visitors']} organic visitors/mo")
    if baseline.get('leads_per_month'):
        baseline_parts.append(f"{baseline['leads_per_month']} leads/mo")
    if baseline_parts:
        lines.append(f"Current baseline: {', '.join(baseline_parts)}")

    # Build EOY line
    eoy_parts = []
    if eoy.get('pages'):
        eoy_parts.append(f"{eoy['pages']} pages")
    if eoy.get('keywords_ranking'):
        eoy_parts.append(f"{eoy['keywords_ranking']} keywords")
    if eoy.get('keywords_top_10'):
        eoy_parts.append(f"{eoy['keywords_top_10']} in top 10")
    if eoy.get('monthly_organic_traffic'):
        eoy_parts.append(f"{eoy['monthly_organic_traffic']} organic visits/mo")
    if eoy.get('monthly_organic_visitors'):
        eoy_parts.append(f"{eoy['monthly_organic_visitors']} organic visitors/mo")
    if eoy.get('leads_per_month'):
        eoy_parts.append(f"{eoy['leads_per_month']} leads/mo")
    if eoy_parts:
        lines.append(f"EOY 2026 target: {', '.join(eoy_parts)}")

    if goal:
        lines.append(f"Strategic goal: {goal}")

    # Include benchmark competitor if present
    benchmark = targets.get('benchmark_competitor')
    if benchmark and isinstance(benchmark, dict):
        name = benchmark.get('name', 'Unknown')
        traffic = benchmark.get('organic_traffic', '?')
        kw = benchmark.get('keywords', '?')
        lines.append(f"Benchmark competitor: {name} ({traffic} organic traffic, {kw} keywords)")

    return '\n'.join(lines) if lines else "No targets available"


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

    recurring_text = (
        (client_dir / 'recurring.yaml').read_text()
        if (client_dir / 'recurring.yaml').exists()
        else "No recurring tasks available"
    )

    roadmap_text = (
        (client_dir / 'roadmap.yaml').read_text()
        if (client_dir / 'roadmap.yaml').exists()
        else "No roadmap available"
    )

    context_text = _safe_read_text(client_dir / 'context.md')

    # Parse roadmap for structured extraction
    roadmap_data = _safe_read_yaml(client_dir / 'roadmap.yaml')

    next_pages = _extract_next_pages(roadmap_data, limit=10)
    next_blogs = _extract_next_blogs(roadmap_data, limit=5)
    targets = _extract_targets(roadmap_data)

    return {
        'name': client_entry.get('client', slug),
        'slug': slug,
        'tier': client_entry.get('tier', 3),
        'mrr': client_entry.get('mrr', 0),
        'manager': client_entry.get('manager', 'Unknown'),
        'cadence': client_entry.get('cadence', 'monthly'),
        'industry': client_entry.get('industry', 'Unknown'),
        'location': client_entry.get('location', 'Unknown'),
        'services': client_entry.get('services', []),
        'recurring': recurring_text,
        'roadmap': roadmap_text,
        'context': context_text,
        # Parsed roadmap fields
        'next_pages': next_pages,
        'next_blogs': next_blogs,
        'targets': targets,
        'next_pages_text': _format_next_pages_text(next_pages),
        'next_blogs_text': _format_next_blogs_text(next_blogs),
        'targets_text': _format_targets_text(targets),
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

        # Parse roadmap for top 3 next pages (HIGH priority, status=needed)
        roadmap_data = _safe_read_yaml(client_dir / 'roadmap.yaml')
        next_pages = _extract_next_pages(roadmap_data, limit=3)
        next_pages_text = _format_next_pages_text(next_pages)
        targets = _extract_targets(roadmap_data)
        targets_text = _format_targets_text(targets)

        results.append({
            'name': c.get('client', slug),
            'slug': slug,
            'tier': c.get('tier', 3),
            'mrr': c.get('mrr', 0),
            'manager': c.get('manager', 'Unknown'),
            'cadence': c.get('cadence', 'monthly'),
            'industry': c.get('industry', 'Unknown'),
            'location': c.get('location', 'Unknown'),
            'services': services,
            'key_tasks': key_tasks,
            'next_pages': next_pages,
            'next_pages_text': next_pages_text,
            'targets_text': targets_text,
        })

    return results


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_PROMPTS = {
    'monthly-plan': (
        "You are a senior SEO strategist for ProofPilot, a digital marketing agency.\n"
        "Generate a detailed monthly SEO plan for {name}.\n\n"
        "## Client Profile\n"
        "- Tier {tier} | ${mrr}/mo MRR | Manager: {manager}\n"
        "- Industry: {industry} | Location: {location}\n"
        "- Cadence: {cadence}\n"
        "- Services: {services_str}\n\n"
        "## Strategic Context\n"
        "{targets_text}\n\n"
        "## Next Priority Pages to Build (from roadmap)\n"
        "{next_pages_text}\n\n"
        "## Next Blog Posts to Write (from roadmap)\n"
        "{next_blogs_text}\n\n"
        "## Monthly Recurring Deliverables\n"
        "{recurring}\n\n"
        "## Client Context\n"
        "{context}\n\n"
        "## Instructions\n"
        "Generate a comprehensive monthly plan with:\n\n"
        "1. **Strategic Theme** — One sentence describing this month's focus based on "
        "roadmap priorities and business goals\n\n"
        "2. **Pages to Build** — Pull specific pages from the \"Next Priority Pages\" list above. "
        "Include the exact URL slug. Assign to weeks. Aim for the number specified in "
        "recurring deliverables or 4-6 pages if not specified.\n\n"
        "3. **Blog Posts** — Identify 2-4 topics that support the pages being built or "
        "target informational keywords. Pull from the \"Next Blog Posts\" list above when possible. "
        "Include the exact title and target keyword.\n\n"
        "4. **Week-by-Week Breakdown**:\n"
        "   - Week 1: Audit + planning + outsource kickoff + start content\n"
        "   - Week 2: Heavy content build (location pages, service pages, blogs)\n"
        "   - Week 3: Content completion + off-page + GBP\n"
        "   - Week 4: Reporting + wrap-up + next month prep\n\n"
        "5. **GBP Posts** — 8 posts with topic suggestions tied to services being highlighted "
        "(skip this section if client does not have GBP service)\n\n"
        "6. **Off-Page Tasks** — Citations, backlinks, social signals per recurring template "
        "(skip if not applicable to this client)\n\n"
        "7. **Technical** — Indexing, heat maps per recurring template\n\n"
        "Format with markdown headers, checkboxes for tasks, and include specific URLs. "
        "Do NOT include raw YAML — translate everything into actionable tasks."
    ),

    'audit': (
        "You are an SEO operations auditor for ProofPilot agency.\n"
        "Audit last month's SEO work for {name}.\n\n"
        "## Client Profile\n"
        "- Tier {tier} | ${mrr}/mo MRR | Manager: {manager}\n"
        "- Industry: {industry} | Location: {location}\n"
        "- Services: {services_str}\n\n"
        "## What Should Have Been Done (recurring template)\n"
        "{recurring}\n\n"
        "## Strategic Targets\n"
        "{targets_text}\n\n"
        "## Next Priority Pages (are we building the right things?)\n"
        "{next_pages_text}\n\n"
        "## Client Context\n"
        "{context}\n\n"
        "## Instructions\n"
        "Produce an audit with:\n\n"
        "1. **Deliverables Scorecard** — For each category (Content, GBP, Off-Page, Technical, "
        "Reporting), rate as: COMPLETE / PARTIAL / MISSING. Present as a table.\n\n"
        "2. **Critical Findings** — Items that were contractually expected but not done. "
        "Flag these as HIGH severity.\n\n"
        "3. **Warnings** — Items partially done or behind schedule relative to the roadmap "
        "targets. Flag as MEDIUM severity.\n\n"
        "4. **Wins** — What went well. Highlight any pages that went live, keyword improvements, "
        "or traffic gains mentioned in context.\n\n"
        "5. **Recommendations** — Specific actions for next month. Reference exact pages from "
        "the roadmap. Prioritize items that close the gap toward EOY targets."
    ),

    'wrap-up': (
        "You are an SEO account manager for ProofPilot agency.\n"
        "Generate a month-end wrap-up for {name}.\n\n"
        "## Client Profile\n"
        "- Tier {tier} | ${mrr}/mo MRR | Manager: {manager}\n"
        "- Industry: {industry} | Location: {location}\n"
        "- Services: {services_str}\n\n"
        "## Recurring Deliverables\n"
        "{recurring}\n\n"
        "## What's Next on the Roadmap\n"
        "{next_pages_text}\n\n"
        "## Next Blog Posts\n"
        "{next_blogs_text}\n\n"
        "## Strategic Targets\n"
        "{targets_text}\n\n"
        "## Client Context\n"
        "{context}\n\n"
        "## Instructions\n"
        "Generate a month-end wrap-up with:\n\n"
        "1. **Executive Summary** — 3-4 bullet points of what was accomplished this month\n\n"
        "2. **Client Update Email** — Professional, results-focused email draft:\n"
        "   - Subject line\n"
        "   - Greeting (use client contact name if available in context)\n"
        "   - Highlights (2-3 wins with data context where possible)\n"
        "   - What's planned next month (reference specific roadmap pages)\n"
        "   - Sign-off from the manager's name\n\n"
        "3. **Internal Notes** — Any issues, blockers, or strategic observations for the "
        "ProofPilot team. Not for client eyes.\n\n"
        "4. **Next Month Preview** — Top 3 priorities from the roadmap with specific URLs"
    ),
}


def _build_all_clients_block(clients: list[dict]) -> str:
    """Format all clients into a text block for global prompts."""
    lines = []
    for c in clients:
        tasks_str = ', '.join(c['key_tasks'][:5]) if c['key_tasks'] else 'See recurring tasks'
        services_str = ', '.join(c['services']) if c['services'] else 'N/A'

        block = (
            f"### {c['name']} — Tier {c['tier']} | ${c['mrr']}/mo | "
            f"Manager: {c['manager']} | Cadence: {c['cadence']}\n"
            f"   Industry: {c['industry']} | Location: {c['location']}\n"
            f"   Services: {services_str}\n"
            f"   Key tasks: {tasks_str}"
        )

        # Add next pages from roadmap if available
        if c.get('next_pages'):
            pages_lines = []
            for p in c['next_pages']:
                url = p.get('url', '/unknown/')
                name = p.get('page', 'Untitled')
                priority = str(p.get('priority', 'MED')).upper()
                pages_lines.append(f"   - {url} — {name} ({priority})")
            block += "\n   Next pages to build:\n" + '\n'.join(pages_lines)
        else:
            block += "\n   Next pages: No roadmap available"

        # Add targets summary
        if c.get('targets_text') and c['targets_text'] != "No targets available":
            block += f"\n   Targets: {c['targets_text'].splitlines()[0]}"

        lines.append(block)

    return '\n\n'.join(lines)


_GLOBAL_PROMPTS = {
    'weekly-plan': (
        "You are a senior SEO operations manager for ProofPilot agency.\n"
        "Generate this week's prioritized work plan across all active clients.\n\n"
        "## Priority Framework\n"
        "1. Contractual / overdue commitments (promised in meetings)\n"
        "2. Tier 1 high-impact pages (top priority from roadmaps)\n"
        "3. Tier 1 recurring deliverables\n"
        "4. Tier 2 content\n"
        "5. Tier 3 + maintenance\n\n"
        "## Team\n"
        "- **Matthew**: Agency owner — handles Saiyan Electric, All Thingz Electric, Cedar Gold\n"
        "- **Marcos**: SEO Manager — handles Pelican Coast, Alpha PM, Adam Levinstein Photography\n"
        "- **Jo Paula**: SEO Specialist — handles ISS, Trading Academy, Dolce Electric\n\n"
        "## Client Portfolio\n"
        "{clients_block}\n\n"
        "## Instructions\n"
        "Generate a weekly plan with:\n\n"
        "1. **Must Do** — Contractual commitments and highest-impact Tier 1 work. "
        "Include specific page URLs from each client's roadmap. These are non-negotiable.\n\n"
        "2. **Should Do** — Regular Tier 1 deliverables on cadence (GBP posts, off-page, "
        "technical tasks from recurring templates)\n\n"
        "3. **Could Do** — Tier 2-3 work if capacity allows\n\n"
        "Group tasks by manager (Matthew, Marcos, Jo Paula). Use checkboxes.\n"
        "Include specific page URLs from each client's roadmap.\n"
        "Output estimated page count and hours at the bottom.\n\n"
        "Format as a clean markdown document ready to paste into Obsidian."
    ),

    'workload': (
        "You are an SEO operations manager for ProofPilot agency.\n"
        "Analyze team workload and capacity.\n\n"
        "## Team\n"
        "- **Matthew**: Agency owner — handles Saiyan Electric, All Thingz Electric, Cedar Gold\n"
        "- **Marcos**: SEO Manager — handles Pelican Coast, Alpha PM, Adam Levinstein Photography\n"
        "- **Jo Paula**: SEO Specialist — handles ISS, Trading Academy, Dolce Electric\n\n"
        "## Time Allocation Guide\n"
        "- Tier 1 (~$4K MRR): 10-12 hrs/month internal\n"
        "- Tier 2 (~$2K MRR): 6-8 hrs/month internal\n"
        "- Tier 3 (~$1K MRR): 3-4 hrs/month internal\n"
        "- Each team member has ~160 hrs/month total capacity\n"
        "- Sustainable utilization target: 75-80%\n\n"
        "## All Clients\n"
        "{clients_block}\n\n"
        "## Instructions\n"
        "Produce a workload analysis with:\n\n"
        "1. **Hours by Manager** — Calculate expected monthly hours per manager based on "
        "tier allocations. Present as a table:\n"
        "   | Manager | Client | Tier | Est. Hours | MRR |\n"
        "   Show subtotals per manager.\n\n"
        "2. **Capacity Check** — Compare against ~160 hrs/month per person. "
        "Flag anyone over 80% utilization (128 hrs). Show as percentage.\n\n"
        "3. **Client Health** — Flag any clients that appear to be under-served based on "
        "their tier level and the work described in their roadmap/recurring tasks.\n\n"
        "4. **Revenue Efficiency** — Calculate $/hour for each manager "
        "(total MRR / estimated hours). Flag if any manager is below $30/hr.\n\n"
        "5. **Rebalancing Recommendations** — If any manager is overloaded, suggest "
        "specific task redistribution. Consider outsource opportunities for content writing."
    ),
}


def _prepare_client_format_dict(client_data: dict) -> dict:
    """Prepare the format dictionary for per-client prompts.

    Adds derived string fields that the prompt templates reference but
    that are not raw keys on the client_data dict (e.g. services_str).
    """
    d = dict(client_data)
    services = d.get('services', [])
    if isinstance(services, list):
        d['services_str'] = ', '.join(str(s) for s in services) if services else 'N/A'
    else:
        d['services_str'] = str(services)
    return d


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

    format_dict = _prepare_client_format_dict(client_data_or_list)
    return _PROMPTS[command].format(**format_dict)


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
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
