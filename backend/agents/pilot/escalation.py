"""
Pilot Escalation Engine — progressive escalation checks across all clients.

Detects stalled work, overdue deliverables, and at-risk clients.
Produces escalation alerts with increasing urgency.
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import anthropic

from agents.pilot.context_builder import build_context

logger = logging.getLogger(__name__)

ESCALATION_SYSTEM = """You are Pilot running an escalation check.

Review all client statuses and flag anything that needs action.
Use progressive urgency levels:

🔴 ESCALATION (action needed today — client at risk, deliverables severely overdue)
🟡 WARNING (action needed this week — falling behind schedule)
🔵 NOTE (worth knowing — not urgent but track it)

For each escalation, include:
- Client name and tier
- What's wrong (specific: "0 deliverables in 15 days" not "falling behind")
- Recommended action
- Who should handle it (Matthew, Jo Paula, Marcos, Rachalle)

Rules:
- Tier 1 clients get escalated faster than Tier 3
- Weekly cadence clients overdue by 7+ days = 🔴
- Monthly cadence clients with zero work by day 15 = 🟡
- Monthly cadence clients with zero work by day 20 = 🔴
- Don't escalate clients that are on track
- Be specific about what's overdue, not vague"""


async def run_escalation_check(
    client: anthropic.AsyncAnthropic,
    db_connect=None,
) -> AsyncGenerator[str, None]:
    """Run an escalation check and yield findings."""
    context = build_context(db_connect)

    # Quick pre-filter: only send clients that might need attention
    needs_review = [
        c for c in context["clients"]
        if c["status"] in ("overdue", "attention")
        or c.get("days_since_last_work") is None
        or (c.get("days_since_last_work", 0) or 999) > 10
    ]

    if not needs_review:
        yield "No escalations needed. All clients are on track.\n"
        return

    import json
    prompt = f"""Run escalation check for {datetime.now(timezone.utc).strftime('%B %d, %Y')}.

CLIENTS NEEDING REVIEW:
{json.dumps(needs_review, indent=2, default=str)}

Day of the month: {datetime.now().day}
Total clients being managed: {context['total_clients']}"""

    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=ESCALATION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\nEscalation check error: {e}\n"
        logger.error(f"Escalation check failed: {e}", exc_info=True)
