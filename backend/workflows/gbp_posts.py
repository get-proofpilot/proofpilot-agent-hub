"""
GBP Posts Workflow
Generates a batch of Google Business Profile posts — seasonal, promotional,
service spotlights, and evergreen tips. Ready to copy-paste into GBP.

inputs keys: business_type, location, post_count, services, promos, notes
"""

import anthropic
from typing import AsyncGenerator

SYSTEM_PROMPT = """You are a Google Business Profile content strategist for ProofPilot, a digital marketing agency that manages GBP for home service businesses.

Your job is to write GBP posts that drive engagement, phone calls, and local visibility — not generic filler content.

## GBP post principles
- Every post should feel like it was written by the business owner, not a marketing agency
- Lead with the customer's situation or pain point — not the service name
- Include the city/area naturally — Google indexes GBP post content for local search
- End every post with a clear, specific CTA (phone number placeholder: use "Call us today" or "Book online")
- Mix post types: seasonal/timely, service spotlights, tips/education, promotions, social proof/trust
- Keep posts between 100-300 words — enough to rank, short enough to read
- Include 3-5 relevant hashtags per post (local + service + industry)

## Post types to rotate through
1. **Seasonal/Timely** — tie the service to current weather, holidays, or local events
2. **Service Spotlight** — highlight one specific service with details that build confidence
3. **Tips & Education** — teach something useful that positions the business as the expert
4. **Promotional** — feature a current offer, discount, or free inspection/estimate
5. **Trust Builder** — years in business, certifications, warranties, local involvement

## Format (strict)
Use this exact format for each post:

# GBP Posts: [Client Name] — [Location]

Then for each post:

---

## Post N: [Type]
**[Opening hook line — bold, attention-grabbing]**
[Body text — 2-4 short paragraphs]

[CTA line]

#Hashtag1 #Hashtag2 #Hashtag3

---

Do NOT write any preamble or explanation. Start immediately with the H1 title."""


async def run_gbp_posts(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str,
    client_name: str,
) -> AsyncGenerator[str, None]:
    """
    Streams a batch of GBP posts for a home service business.

    inputs keys:
        business_type   e.g. "electrician", "plumber", "HVAC contractor"
        location        e.g. "Chandler, AZ"
        post_count      e.g. "8" (number of posts to generate)
        services        e.g. "panel upgrade, EV charger, rewiring" (optional)
        promos          e.g. "10% off panel upgrades this month" (optional)
        notes           e.g. brand voice, topics to avoid (optional)
    """
    business_type = inputs.get("business_type", "home service business").strip()
    location      = inputs.get("location", "").strip()
    post_count    = inputs.get("post_count", "8").strip()
    services      = inputs.get("services", "").strip()
    promos        = inputs.get("promos", "").strip()
    notes         = inputs.get("notes", "").strip()

    yield f"> Generating {post_count} GBP posts for **{client_name}**...\n\n"

    # ── Build the user prompt ──────────────────────────────
    lines = [
        f"Write {post_count} Google Business Profile posts for **{client_name}**, a {business_type} serving {location}.",
        f"",
        f"**Number of posts:** {post_count}",
        f"**Mix the post types** — rotate through seasonal, service spotlight, tips, promotional, and trust builder.",
    ]

    if services:
        lines.append(f"**Services to feature across the posts:** {services}")

    if promos:
        lines.append(f"**Current promotions or offers to include:** {promos}")

    if strategy_context and strategy_context.strip():
        lines += [
            f"",
            f"**Strategy direction — follow this carefully:**",
            f"{strategy_context.strip()}",
        ]

    if notes:
        lines += [
            f"",
            f"**Additional notes:** {notes}",
        ]

    lines += [
        f"",
        f"Write all {post_count} posts now. Start directly with the H1 title. No preamble.",
    ]

    user_prompt = "\n".join(lines)

    # ── Stream from Claude ─────────────────────────────────
    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
