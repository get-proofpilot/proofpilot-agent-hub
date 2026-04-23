"""
Pilot Morning Briefing — generates a daily status update.

Aggregates client context, identifies attention items, and produces
a formatted briefing that can be posted to Slack or displayed in the dashboard.
"""

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import anthropic

from agents.pilotcore.context_builder import build_context
from agents.pilotcore.prompts import load_prompt

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM = load_prompt("briefing_system")


async def generate_briefing(
    client: anthropic.AsyncAnthropic,
    db_connect=None,
) -> AsyncGenerator[str, None]:
    """Generate a morning briefing from current context."""
    context = build_context(db_connect)

    prompt = f"""Generate the morning briefing for {datetime.now(timezone.utc).strftime('%A, %B %d, %Y')}.

CLIENT STATUS:
{json.dumps(context['clients'], indent=2, default=str)}

TEAM WORKLOAD:
{json.dumps(context['team_workload'], indent=2)}

OVERDUE: {', '.join(context['overdue_clients']) or 'None'}
ATTENTION: {', '.join(context['attention_clients']) or 'None'}
TOTAL CLIENTS: {context['total_clients']}"""

    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=BRIEFING_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\nBriefing generation error: {e}\n"
        logger.error(f"Briefing failed: {e}", exc_info=True)
