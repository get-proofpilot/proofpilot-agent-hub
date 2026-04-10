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

from agents.pilot.context_builder import build_context

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM = """You are Pilot, ProofPilot's AI operations coworker.

Generate a morning briefing for Matthew. Be direct. Lead with what matters.
If nothing needs attention, say that clearly and move on.

Format for Slack (single asterisks for bold, emoji headers, no em dashes,
no double asterisks, no # headings):

Structure:
*Morning Briefing*

🔴 *Needs Attention* (overdue or at-risk clients)
- Client name: what's wrong and what to do

🟡 *Watch List* (approaching deadlines)
- Client name: status note

🟢 *On Track* (brief summary, don't list every client)
- X of Y clients on track

📋 *Today's Priorities* (top 3 things Matthew should focus on)
1. Most impactful action
2. Second priority
3. Third priority

Rules:
- Sort by revenue impact (Tier 1 clients first)
- Include specific numbers (days overdue, pages completed, MRR)
- If a client has zero work this month, flag it clearly
- Don't pad. If nothing needs attention, say so.
- Keep it under 300 words total."""


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
