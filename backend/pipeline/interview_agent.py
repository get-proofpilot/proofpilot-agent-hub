"""
Interview Agent (US-010) -- conversational interview to fill gaps in client brain.

Loads current brain data, identifies missing or weak sections, asks one targeted
question at a time, parses answers into structured memory entries, and tracks
progress via session state.

Usage:
    from pipeline.interview_agent import run_interview

    async for chunk in run_interview(
        client_id=3,
        memory_store=store,
        anthropic_client=client,
        user_answer="We charge $1200-3500 for panel upgrades",
        session_state={"questions_asked": [...], "current_gap": "pricing"},
    ):
        # chunk is a JSON-serializable dict: {"type": "question"|"saved"|"complete", ...}
        pass
"""

import json
import logging
from typing import AsyncGenerator, Optional

import anthropic

from memory.store import (
    ClientMemoryStore,
    BRAND_VOICE,
    BUSINESS_INTEL,
)

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ── Gap Detection ────────────────────────────────────────────────────────────

# Each gap: (gap_id, memory_type, key_to_check, question_template, parse_target_type, parse_target_key)
# question_template uses {services} and {client_name} placeholders filled at runtime.
_GAP_DEFINITIONS = [
    (
        "pricing",
        BUSINESS_INTEL,
        "service_catalog",
        "What are your typical price ranges for {services}? Even ballpark ranges help -- e.g. '$200-500 for a standard repair'.",
        BUSINESS_INTEL,
        "pricing",
    ),
    (
        "owner_story",
        BUSINESS_INTEL,
        "owner_name",
        "What's the owner's story? How did the company get started, and who runs it today?",
        BUSINESS_INTEL,
        "owner_name",
    ),
    (
        "response_time",
        BUSINESS_INTEL,
        "response_time",
        "What's your typical response time when a customer calls or requests a quote? Same-day? 24 hours?",
        BUSINESS_INTEL,
        "response_time",
    ),
    (
        "competitive_position",
        BUSINESS_INTEL,
        "competitive_position",
        "Who's your main competitor in your area, and what do you do better than them?",
        BUSINESS_INTEL,
        "competitive_position",
    ),
    (
        "certifications",
        BUSINESS_INTEL,
        "certifications",
        "Any certifications, awards, professional memberships, or licenses we should always mention in your marketing?",
        BUSINESS_INTEL,
        "certifications",
    ),
    (
        "vocabulary_avoid",
        BRAND_VOICE,
        "vocabulary_avoid",
        "Is there anything you NEVER want said in your marketing? Words, phrases, claims, or topics to avoid?",
        BRAND_VOICE,
        "vocabulary_avoid",
    ),
    (
        "voice_profile",
        BRAND_VOICE,
        "voice_profile",
        "How would you describe your company's personality in 2-3 words? For example: 'professional but friendly' or 'no-nonsense experts'.",
        BRAND_VOICE,
        "voice_profile",
    ),
    (
        "payment_methods",
        BUSINESS_INTEL,
        "payment_methods",
        "Do you offer financing or payment plans? What payment methods do you accept?",
        BUSINESS_INTEL,
        "payment_methods",
    ),
    (
        "customer_language",
        BRAND_VOICE,
        "customer_language",
        "What do your best customers usually say when they recommend you to someone? Think about actual words they use in reviews or referrals.",
        BRAND_VOICE,
        "customer_language",
    ),
    (
        "guarantees",
        BUSINESS_INTEL,
        "guarantees",
        "Do you offer any guarantees or warranties on your work? Satisfaction guarantees, warranty periods, etc.?",
        BUSINESS_INTEL,
        "guarantees",
    ),
    (
        "customer_personas",
        BUSINESS_INTEL,
        "customer_personas",
        "Who are your ideal customers? Think about 2-3 types -- e.g. 'homeowners doing renovations' or 'property managers with multiple units'.",
        BUSINESS_INTEL,
        "customer_personas",
    ),
]


def _detect_gaps(
    memory_store: ClientMemoryStore,
    client_id: int,
    questions_asked: list[str],
) -> list[tuple[str, str]]:
    """Return list of (gap_id, question_text) for missing brain data.

    Skips any gap_id already in questions_asked.
    """
    # Load all relevant entries once
    voice_entries = memory_store.load_by_type(client_id, BRAND_VOICE)
    biz_entries = memory_store.load_by_type(client_id, BUSINESS_INTEL)

    voice_keys = {e["key"] for e in voice_entries}
    biz_keys = {e["key"] for e in biz_entries}

    # Build a services string for question templates
    services_str = "your services"
    for e in biz_entries:
        if e["key"] == "service_catalog":
            try:
                catalog = json.loads(e["value"])
                if isinstance(catalog, list):
                    names = []
                    for svc in catalog[:4]:
                        if isinstance(svc, dict):
                            names.append(svc.get("name", ""))
                        elif isinstance(svc, str):
                            names.append(svc)
                    names = [n for n in names if n]
                    if names:
                        services_str = ", ".join(names)
            except (json.JSONDecodeError, TypeError):
                pass
            break

    # Check for pricing data inside service_catalog
    has_pricing = False
    for e in biz_entries:
        if e["key"] == "pricing":
            has_pricing = True
            break
        if e["key"] == "service_catalog":
            try:
                catalog = json.loads(e["value"])
                if isinstance(catalog, list):
                    for svc in catalog:
                        if isinstance(svc, dict) and svc.get("price_range"):
                            has_pricing = True
                            break
            except (json.JSONDecodeError, TypeError):
                pass

    gaps = []
    for gap_id, mem_type, key_check, question_tpl, _, _ in _GAP_DEFINITIONS:
        if gap_id in questions_asked:
            continue

        # Special case: pricing lives inside service_catalog or as separate key
        if gap_id == "pricing":
            if has_pricing:
                continue
        else:
            keys_to_check = voice_keys if mem_type == BRAND_VOICE else biz_keys
            if key_check in keys_to_check:
                continue

        question = question_tpl.format(services=services_str, client_name="your company")
        gaps.append((gap_id, question))

    return gaps


# ── Answer Parsing ───────────────────────────────────────────────────────────

_PARSE_PROMPT = """You are parsing a business owner's answer to an interview question into structured data for a client brain.

The question was about: {gap_id}
The question asked: {question}
Their answer: {answer}

Current brain context (what we already know):
{brain_context}

Parse this answer into a JSON object with these fields:
- "memory_type": one of "brand_voice" or "business_intel"
- "key": the memory key to save under (e.g. "pricing", "owner_name", "response_time", "competitive_position", "certifications", "vocabulary_avoid", "voice_profile", "payment_methods", "customer_language", "guarantees", "customer_personas")
- "value": the parsed value. For simple text answers, use a string. For lists (certifications, payment methods, personas), use a JSON array. For structured data (pricing), use a JSON object or array of objects.
- "summary": a one-sentence summary of what was learned (for the progress message)

Return ONLY valid JSON, no markdown fences. Example:
{{"memory_type": "business_intel", "key": "response_time", "value": "Same-day service, typically within 2 hours of the call", "summary": "Saved response time: same-day, within 2 hours"}}"""


async def _parse_answer(
    anthropic_client: anthropic.AsyncAnthropic,
    gap_id: str,
    question: str,
    answer: str,
    brain_context: str,
) -> Optional[dict]:
    """Use Haiku to parse a user answer into a structured memory entry."""
    try:
        response = await anthropic_client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": _PARSE_PROMPT.format(
                    gap_id=gap_id,
                    question=question,
                    answer=answer,
                    brain_context=brain_context[:3000],
                ),
            }],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        logger.error("Failed to parse interview answer for gap '%s': %s", gap_id, e)
        return None


# ── Question Generation ──────────────────────────────────────────────────────

_QUESTION_PROMPT = """You are an interviewer building a client brain for a marketing agency. You're talking to a business owner to fill gaps in what we know about their business.

Here's what we already know about them:
{brain_context}

The next gap to fill is: {gap_id}
The template question is: {template_question}

Rewrite this question to be:
1. Conversational and warm (you're talking to a busy business owner)
2. Specific to their business (reference details you already know -- their services, location, industry)
3. Brief -- one sentence, maybe two

Return ONLY the question text, nothing else. No quotes around it."""


async def _generate_contextual_question(
    anthropic_client: anthropic.AsyncAnthropic,
    gap_id: str,
    template_question: str,
    brain_context: str,
) -> str:
    """Use Haiku to generate a contextual question based on what we already know."""
    try:
        response = await anthropic_client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": _QUESTION_PROMPT.format(
                    brain_context=brain_context[:3000],
                    gap_id=gap_id,
                    template_question=template_question,
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error("Failed to generate contextual question for '%s': %s", gap_id, e)
        # Fallback to template
        return template_question


# ── Main Interview Runner ────────────────────────────────────────────────────

async def run_interview(
    client_id: int,
    memory_store: ClientMemoryStore,
    anthropic_client: anthropic.AsyncAnthropic,
    user_answer: Optional[str] = None,
    session_state: Optional[dict] = None,
) -> AsyncGenerator[dict, None]:
    """Run one step of the client brain interview.

    Each call handles one question-answer cycle:
    1. If user_answer is provided, parse and save it
    2. Detect remaining gaps
    3. Generate and yield the next question (or completion message)

    Yields dicts with type: "saved", "question", or "complete".
    Session state is included in every yield so the frontend can pass it back.
    """
    if session_state is None:
        session_state = {"questions_asked": [], "current_gap": None}

    questions_asked = session_state.get("questions_asked", [])
    current_gap = session_state.get("current_gap")

    # Build brain context for prompts
    brain_snapshot = memory_store.load_snapshot(client_id)

    # ── Step 1: Parse and save the user's answer (if provided) ──
    if user_answer and user_answer.strip() and current_gap:
        # Find the question that was asked for this gap
        question_text = ""
        for gap_id, _, _, question_tpl, _, _ in _GAP_DEFINITIONS:
            if gap_id == current_gap:
                question_text = question_tpl
                break

        parsed = await _parse_answer(
            anthropic_client,
            gap_id=current_gap,
            question=question_text,
            answer=user_answer,
            brain_context=brain_snapshot,
        )

        if parsed and parsed.get("key") and parsed.get("value"):
            mem_type = parsed.get("memory_type", BUSINESS_INTEL)
            key = parsed["key"]
            value = parsed["value"]
            # Serialize complex values
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            try:
                memory_store.save(client_id, mem_type, key, value)
                summary = parsed.get("summary", f"Saved {key}")
                yield {
                    "type": "saved",
                    "key": key,
                    "memory_type": mem_type,
                    "summary": summary,
                    "session_state": session_state,
                }
                logger.info(
                    "Interview saved %s/%s for client %d",
                    mem_type, key, client_id,
                )
            except Exception as e:
                logger.error("Failed to save interview answer: %s", e)
                yield {
                    "type": "saved",
                    "key": key,
                    "memory_type": mem_type,
                    "summary": f"Could not save {key}: {e}",
                    "session_state": session_state,
                }
        else:
            yield {
                "type": "saved",
                "key": current_gap,
                "memory_type": "unknown",
                "summary": "Noted your answer, moving on.",
                "session_state": session_state,
            }

        # Mark this gap as asked regardless of parse success
        if current_gap not in questions_asked:
            questions_asked.append(current_gap)

        # Refresh brain snapshot after saving
        brain_snapshot = memory_store.load_snapshot(client_id)

    # ── Step 2: Find remaining gaps ──
    gaps = _detect_gaps(memory_store, client_id, questions_asked)

    if not gaps:
        session_state["questions_asked"] = questions_asked
        session_state["current_gap"] = None
        yield {
            "type": "complete",
            "message": "Your client brain is looking solid! All the key sections are filled in. You can run Test Voice to see how the brain performs in content generation.",
            "session_state": session_state,
        }
        return

    # ── Step 3: Ask the next question ──
    next_gap_id, template_question = gaps[0]

    contextual_question = await _generate_contextual_question(
        anthropic_client,
        gap_id=next_gap_id,
        template_question=template_question,
        brain_context=brain_snapshot,
    )

    session_state["questions_asked"] = questions_asked
    session_state["current_gap"] = next_gap_id

    remaining = len(gaps)
    yield {
        "type": "question",
        "gap_id": next_gap_id,
        "question": contextual_question,
        "remaining_gaps": remaining,
        "total_gaps": remaining + len(questions_asked),
        "session_state": session_state,
    }
