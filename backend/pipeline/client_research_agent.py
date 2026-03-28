"""
Client Research Agent — orchestrates brand + voice + business extractors
to build a complete client brain in one operation.

Usage:
    from pipeline.client_research_agent import build_client_brain
    result = await build_client_brain(client_id, domain, location, anthropic_client, memory_store)
    # result = {"brand": 19, "voice": 8, "business": 10, "total": 37}
"""

import json
import logging
from typing import AsyncGenerator, Optional

import anthropic

from memory.store import (
    ClientMemoryStore,
    BRAND_VOICE,
    BUSINESS_INTEL,
    DESIGN_SYSTEM,
)

logger = logging.getLogger(__name__)


async def build_client_brain(
    client_id: int,
    domain: str,
    location: str,
    anthropic_client: anthropic.AsyncAnthropic,
    memory_store: ClientMemoryStore,
    service: str = "",
    force: bool = False,
) -> dict:
    """Build the complete client brain by running all extractors.

    Returns a dict with entry counts per section.
    Skips sections that already have entries unless force=True.
    """
    result = {"brand": 0, "voice": 0, "business": 0, "total": 0}

    # 1. Brand Identity (existing extractor)
    if force or not memory_store.has_entries(client_id, DESIGN_SYSTEM):
        try:
            from pipeline.brand_memory import ensure_brand_memory
            extracted = await ensure_brand_memory(
                memory_store, client_id, domain, anthropic_client, force=force
            )
            if extracted:
                brand_entries = memory_store.load_by_type(client_id, DESIGN_SYSTEM)
                result["brand"] = len(brand_entries)
            logger.info("Brand extraction complete for client %d: %d entries", client_id, result["brand"])
        except Exception as e:
            logger.error("Brand extraction failed for client %d: %s", client_id, e)
    else:
        brand_entries = memory_store.load_by_type(client_id, DESIGN_SYSTEM)
        result["brand"] = len(brand_entries)
        logger.info("Brand memory exists for client %d (%d entries), skipping", client_id, result["brand"])

    # 2. Writing Voice
    if force or not memory_store.has_entries(client_id, BRAND_VOICE):
        try:
            from pipeline.voice_extractor import extract_voice
            voice_data = await extract_voice(domain, anthropic_client)

            if voice_data:
                _save_voice_to_memory(memory_store, client_id, voice_data)
                voice_entries = memory_store.load_by_type(client_id, BRAND_VOICE)
                result["voice"] = len(voice_entries)
            logger.info("Voice extraction complete for client %d: %d entries", client_id, result["voice"])
        except Exception as e:
            logger.error("Voice extraction failed for client %d: %s", client_id, e)
    else:
        voice_entries = memory_store.load_by_type(client_id, BRAND_VOICE)
        result["voice"] = len(voice_entries)
        logger.info("Voice memory exists for client %d (%d entries), skipping", client_id, result["voice"])

    # 3. Business Intelligence
    if force or not memory_store.has_entries(client_id, BUSINESS_INTEL):
        try:
            from pipeline.business_researcher import research_business
            biz_data = await research_business(domain, location, anthropic_client, service=service)

            if biz_data:
                _save_business_to_memory(memory_store, client_id, biz_data)
                biz_entries = memory_store.load_by_type(client_id, BUSINESS_INTEL)
                result["business"] = len(biz_entries)
            logger.info("Business research complete for client %d: %d entries", client_id, result["business"])
        except Exception as e:
            logger.error("Business research failed for client %d: %s", client_id, e)
    else:
        biz_entries = memory_store.load_by_type(client_id, BUSINESS_INTEL)
        result["business"] = len(biz_entries)
        logger.info("Business memory exists for client %d (%d entries), skipping", client_id, result["business"])

    result["total"] = result["brand"] + result["voice"] + result["business"]
    logger.info("Client brain build complete for client %d: %d total entries", client_id, result["total"])
    return result


async def build_client_brain_streaming(
    client_id: int,
    domain: str,
    location: str,
    anthropic_client: anthropic.AsyncAnthropic,
    memory_store: ClientMemoryStore,
    service: str = "",
    force: bool = False,
) -> AsyncGenerator[str, None]:
    """Build client brain with SSE-compatible progress streaming."""
    result = {"brand": 0, "voice": 0, "business": 0, "total": 0}

    # 1. Brand Identity
    yield "> Phase 1/3: Extracting brand identity...\n"
    if force or not memory_store.has_entries(client_id, DESIGN_SYSTEM):
        try:
            from pipeline.brand_memory import ensure_brand_memory
            extracted = await ensure_brand_memory(
                memory_store, client_id, domain, anthropic_client, force=force
            )
            brand_entries = memory_store.load_by_type(client_id, DESIGN_SYSTEM)
            result["brand"] = len(brand_entries)
            yield f"> Brand identity: {result['brand']} entries saved (colors, typography, logos, patterns)\n\n"
        except Exception as e:
            yield f"> Brand extraction failed: {e}\n\n"
            logger.error("Brand extraction failed: %s", e)
    else:
        brand_entries = memory_store.load_by_type(client_id, DESIGN_SYSTEM)
        result["brand"] = len(brand_entries)
        yield f"> Brand identity: already populated ({result['brand']} entries), skipping\n\n"

    # 2. Writing Voice
    yield "> Phase 2/3: Analyzing writing voice...\n"
    if force or not memory_store.has_entries(client_id, BRAND_VOICE):
        try:
            from pipeline.voice_extractor import extract_voice
            voice_data = await extract_voice(domain, anthropic_client)

            if voice_data:
                _save_voice_to_memory(memory_store, client_id, voice_data)
                voice_entries = memory_store.load_by_type(client_id, BRAND_VOICE)
                result["voice"] = len(voice_entries)
                profile = voice_data.get("voice_profile", "")
                if profile:
                    yield f"> Voice profile: {profile[:200]}...\n"
            yield f"> Writing voice: {result['voice']} entries saved\n\n"
        except Exception as e:
            yield f"> Voice extraction failed: {e}\n\n"
            logger.error("Voice extraction failed: %s", e)
    else:
        voice_entries = memory_store.load_by_type(client_id, BRAND_VOICE)
        result["voice"] = len(voice_entries)
        yield f"> Writing voice: already populated ({result['voice']} entries), skipping\n\n"

    # 3. Business Intelligence
    yield "> Phase 3/3: Researching business intelligence...\n"
    if force or not memory_store.has_entries(client_id, BUSINESS_INTEL):
        try:
            from pipeline.business_researcher import research_business
            biz_data = await research_business(domain, location, anthropic_client, service=service)

            if biz_data:
                _save_business_to_memory(memory_store, client_id, biz_data)
                biz_entries = memory_store.load_by_type(client_id, BUSINESS_INTEL)
                result["business"] = len(biz_entries)
                services = biz_data.get("service_catalog", [])
                if services:
                    names = [s.get("name", "") for s in services[:5] if isinstance(s, dict)]
                    yield f"> Services found: {', '.join(names)}\n"
                diffs = biz_data.get("differentiators", [])
                if diffs:
                    yield f"> Differentiators: {', '.join(diffs[:3])}\n"
            yield f"> Business intelligence: {result['business']} entries saved\n\n"
        except Exception as e:
            yield f"> Business research failed: {e}\n\n"
            logger.error("Business research failed: %s", e)
    else:
        biz_entries = memory_store.load_by_type(client_id, BUSINESS_INTEL)
        result["business"] = len(biz_entries)
        yield f"> Business intelligence: already populated ({result['business']} entries), skipping\n\n"

    result["total"] = result["brand"] + result["voice"] + result["business"]
    yield f"> Client brain complete: {result['total']} total entries\n"
    yield f">   Brand: {result['brand']} | Voice: {result['voice']} | Business: {result['business']}\n"


def _save_voice_to_memory(memory_store: ClientMemoryStore, client_id: int, voice_data: dict) -> int:
    """Save extracted voice data into client memory entries."""
    saved = 0

    if voice_data.get("voice_profile"):
        memory_store.save(client_id, BRAND_VOICE, "voice_profile", voice_data["voice_profile"])
        saved += 1

    if voice_data.get("tone_attributes"):
        memory_store.save(client_id, BRAND_VOICE, "tone_attributes",
                          json.dumps(voice_data["tone_attributes"]))
        saved += 1

    if voice_data.get("vocabulary_use"):
        memory_store.save(client_id, BRAND_VOICE, "vocabulary_use",
                          json.dumps(voice_data["vocabulary_use"]))
        saved += 1

    if voice_data.get("vocabulary_avoid"):
        memory_store.save(client_id, BRAND_VOICE, "vocabulary_avoid",
                          json.dumps(voice_data["vocabulary_avoid"]))
        saved += 1

    if voice_data.get("sentence_patterns"):
        memory_store.save(client_id, BRAND_VOICE, "sentence_patterns",
                          json.dumps(voice_data["sentence_patterns"]))
        saved += 1

    if voice_data.get("sample_passages"):
        memory_store.save(client_id, BRAND_VOICE, "sample_passages",
                          json.dumps(voice_data["sample_passages"]))
        saved += 1

    if voice_data.get("customer_language"):
        memory_store.save(client_id, BRAND_VOICE, "customer_language",
                          json.dumps(voice_data["customer_language"]))
        saved += 1

    if voice_data.get("tagline"):
        memory_store.save(client_id, BRAND_VOICE, "tagline", voice_data["tagline"])
        saved += 1

    logger.info("Saved %d voice memory entries for client %d", saved, client_id)
    return saved


def _save_business_to_memory(memory_store: ClientMemoryStore, client_id: int, biz_data: dict) -> int:
    """Save extracted business intelligence into client memory entries."""
    saved = 0

    str_fields = [
        "competitive_position", "response_time", "owner_name",
        "year_established", "license_number",
    ]
    for field in str_fields:
        val = biz_data.get(field)
        if val and isinstance(val, str) and val.strip():
            memory_store.save(client_id, BUSINESS_INTEL, field, val)
            saved += 1

    json_fields = [
        "service_catalog", "service_areas", "differentiators",
        "certifications", "customer_personas", "guarantees",
        "payment_methods",
    ]
    for field in json_fields:
        val = biz_data.get(field)
        if val:
            memory_store.save(client_id, BUSINESS_INTEL, field, json.dumps(val))
            saved += 1

    logger.info("Saved %d business intel entries for client %d", saved, client_id)
    return saved
