"""
Brain Formatter (US-005) — context-aware client brain selection for workflow prompts.

Selects and formats the right client brain sections for each workflow type,
producing structured markdown for system prompt injection. Replaces the
generic load_snapshot() approach with workflow-specific context windows
that give each agent exactly the memory it needs.

Usage:
    from pipeline.brain_formatter import format_brain_for_workflow

    context = format_brain_for_workflow(memory_store, client_id=3, workflow_type="service-page")
    # Returns formatted markdown ready for build_stage_prompt(client_memory=context)
"""

import json
import logging
from typing import Optional

from memory.store import (
    ClientMemoryStore,
    BRAND_VOICE,
    BUSINESS_INTEL,
    STYLE_PREFERENCES,
    PAST_CONTENT,
    LEARNINGS,
    DESIGN_SYSTEM,
    ASSET_CATALOG,
)

logger = logging.getLogger(__name__)

# Maximum approximate token budget for the formatted brain output.
# Leaves room in the 200k context window for skills, artifacts, and generation.
_MAX_CHARS = 12000  # ~3000 tokens at ~4 chars/token


# ── Injection Map ────────────────────────────────────────────────────────────
# Maps workflow_type -> list of (memory_type, formatter_fn, filter_keys) tuples.
# filter_keys is None for "full" or a list of key prefixes to include.
#
# The store uses these memory types:
#   brand_voice        -> voice, tone, value_propositions, business_info, phone, trust_signals
#   business_intel     -> service_catalog, differentiators, certifications, guarantees,
#                         service_areas, customer_personas, competitive_position,
#                         response_time, cta_style
#   past_content       -> page_type:keyword entries with title/keyword/page_type
#   learnings          -> agent observations about the client
#   design_system      -> CSS, typography, section patterns, component styles, CTA patterns
#   asset_catalog      -> logos, hero images, navigation, footer, social links


def _normalize_workflow(workflow_type: str) -> str:
    """Normalize workflow type to a canonical form for injection map lookup."""
    return workflow_type.lower().strip().replace("_", "-")


# ── Section Formatters ───────────────────────────────────────────────────────

def _format_voice_section(entries: list[dict], tone_only: bool = False) -> str:
    """Format brand_voice memory entries as a Writing Guide block.

    When tone_only=True, only include the tone/voice entry (used for design workflows
    where the agent needs voice direction but not full writing guidance).
    """
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}
    parts = ["## Writing Guide\n"]

    # Tone is always first -- it's the core voice directive
    tone = entry_map.get("tone", "")
    if tone:
        parts.append(f"**Voice & Tone:** {tone}\n")

    if tone_only:
        return "\n".join(parts).strip()

    # Value propositions
    vp_raw = entry_map.get("value_propositions", "")
    if vp_raw:
        props = _safe_parse_json(vp_raw)
        if isinstance(props, list) and props:
            parts.append("**Key Value Propositions:**")
            for p in props:
                parts.append(f"- {p}")
            parts.append("")

    # Business info (name, phone, address, license)
    biz_raw = entry_map.get("business_info", "")
    if biz_raw:
        biz = _safe_parse_json(biz_raw)
        if isinstance(biz, dict):
            parts.append("**Business Details:**")
            for field in ("name", "phone", "address", "license", "email"):
                if biz.get(field):
                    parts.append(f"- {field.title()}: {biz[field]}")
            parts.append("")

    # Phone (standalone entry)
    phone = entry_map.get("phone", "")
    if phone and "phone" not in (biz_raw or "").lower():
        parts.append(f"**Phone:** {phone}\n")

    # Trust signals
    trust = entry_map.get("trust_signals", "")
    if trust:
        parts.append(f"**Trust Signals:** {trust}\n")

    # Any remaining brand_voice entries not yet handled
    handled = {"tone", "value_propositions", "business_info", "phone", "trust_signals"}
    for key, value in entry_map.items():
        if key not in handled:
            parts.append(f"**{_humanize_key(key)}:** {_render_value(value)}")

    return "\n".join(parts).strip()


def _format_business_section(entries: list[dict], keys: Optional[list[str]] = None) -> str:
    """Format business_intel entries as structured business intelligence.

    The business_intel type stores operational business data: service catalog,
    service areas, differentiators, certifications, guarantees, CTA preferences,
    customer personas, competitive position, and response time.

    When keys is provided, only entries whose key matches one of the given
    prefixes are included. When keys is None, all entries are included.
    """
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}

    # Filter to requested keys if specified
    if keys is not None:
        filtered = {}
        for k, v in entry_map.items():
            for prefix in keys:
                if k == prefix or k.startswith(prefix + "_") or k.startswith(prefix + ":"):
                    filtered[k] = v
                    break
        entry_map = filtered

    if not entry_map:
        return ""

    parts = ["## Business Intelligence\n"]
    for key, value in entry_map.items():
        label = _humanize_key(key)
        rendered = _render_value(value)
        parts.append(f"**{label}:** {rendered}\n")

    return "\n".join(parts).strip()


def _format_content_history(entries: list[dict]) -> str:
    """Format past_content entries as an internal link reference table.

    Each past_content entry has key="page_type:keyword" and value is JSON
    with title, keyword, page_type, and generated_at fields. The output
    gives agents a list of existing pages to link to.
    """
    if not entries:
        return ""

    parts = ["## Existing Content (Internal Link Targets)\n"]
    parts.append("Use these pages for internal linking. Link naturally with descriptive anchor text.\n")

    for entry in entries:
        raw = entry["value"]
        data = _safe_parse_json(raw)
        if isinstance(data, dict):
            title = data.get("title", "")
            keyword = data.get("keyword", "")
            page_type = data.get("page_type", "")
            if title or keyword:
                label = title if title else keyword
                type_tag = f" ({page_type})" if page_type else ""
                parts.append(f"- **{label}**{type_tag} -- target keyword: \"{keyword}\"")
        else:
            # Fallback: render as key-value
            parts.append(f"- **{entry['key']}**: {raw}")

    return "\n".join(parts).strip()


def _format_learnings(entries: list[dict]) -> str:
    """Format learnings as actionable rules the agent must follow.

    Learnings are agent observations stored over time. They encode client
    preferences, past mistakes, and quality signals.
    """
    if not entries:
        return ""

    parts = ["## Client-Specific Rules\n"]
    parts.append("Follow these rules learned from past work with this client:\n")

    for entry in entries:
        key = entry["key"]
        value = entry["value"]
        # Classify as "always do" vs "never do" based on common patterns
        lower = value.lower()
        if any(word in lower for word in ("avoid", "never", "don't", "do not", "reject", "hate")):
            parts.append(f"- NEVER: {value}")
        elif any(word in lower for word in ("always", "prefer", "must", "require", "love")):
            parts.append(f"- ALWAYS: {value}")
        else:
            parts.append(f"- {value}")

    return "\n".join(parts).strip()


def _format_design_section(entries: list[dict]) -> str:
    """Format design_system entries for design-oriented workflows.

    Delegates to the existing format_brand_for_design_prompt() when available,
    falling back to a simpler rendering if the import fails.
    """
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}
    parts = ["## Design System\n"]

    # CSS custom properties
    css = entry_map.get("design_system_css", "")
    if css:
        parts.append(f"### CSS Variables\n```css\n{css}\n```\n")

    # Typography
    typo_raw = entry_map.get("typography", "")
    if typo_raw:
        typo = _safe_parse_json(typo_raw)
        if isinstance(typo, dict):
            parts.append("### Typography")
            for field in ("heading_font", "body_font", "h1_size", "h2_size", "body_size", "body_line_height"):
                if typo.get(field):
                    parts.append(f"- {_humanize_key(field)}: {typo[field]}")
            if typo.get("google_fonts_url"):
                parts.append(f"- Google Fonts: `{typo['google_fonts_url']}`")
            parts.append("")

    # Color palette
    palette_raw = entry_map.get("color_palette", "")
    if palette_raw:
        palette = _safe_parse_json(palette_raw)
        if isinstance(palette, dict):
            parts.append("### Colors")
            for name, hex_val in palette.items():
                if hex_val:
                    parts.append(f"- {name.replace('_', ' ').title()}: `{hex_val}`")
            parts.append("")

    # Section patterns
    patterns_raw = entry_map.get("section_patterns", "")
    if patterns_raw:
        patterns = _safe_parse_json(patterns_raw)
        if isinstance(patterns, list):
            parts.append("### Section Patterns")
            for i, p in enumerate(patterns, 1):
                if isinstance(p, dict):
                    notes = p.get("notes", "")
                    suffix = f" -- {notes}" if notes else ""
                    parts.append(
                        f"{i}. **{p.get('type', 'section')}**: "
                        f"bg={p.get('bg', '?')}, text={p.get('text_color', '?')}{suffix}"
                    )
            parts.append("")

    # Component styles
    comp_raw = entry_map.get("component_styles", "")
    if comp_raw:
        comp = _safe_parse_json(comp_raw)
        if isinstance(comp, dict):
            parts.append("### Component Styles")
            for name, props in comp.items():
                if isinstance(props, dict):
                    desc = ", ".join(f"{k}: {v}" for k, v in props.items() if v)
                    parts.append(f"- **{name.replace('_', ' ').title()}**: {desc}")
            parts.append("")

    # CTA patterns
    cta_raw = entry_map.get("cta_patterns", "")
    if cta_raw:
        cta = _safe_parse_json(cta_raw)
        if isinstance(cta, dict):
            parts.append("### CTA Patterns")
            if cta.get("primary_cta_text"):
                parts.append(f'- Primary CTA: "{cta["primary_cta_text"]}"')
            if cta.get("phone_number"):
                parts.append(f"- Phone: **{cta['phone_number']}**")
            parts.append("")

    # Photography style
    photo = entry_map.get("photography_style", "")
    if photo:
        parts.append(f"### Photography Style\n{photo}\n")

    return "\n".join(parts).strip()


def _format_asset_section(entries: list[dict]) -> str:
    """Format asset_catalog entries (logos, images, nav, footer)."""
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}
    parts = ["## Client Assets\n"]

    # Logos
    logos_raw = entry_map.get("logos", "")
    if logos_raw:
        logos = _safe_parse_json(logos_raw)
        if isinstance(logos, list) and logos:
            parts.append("### Logos (USE THESE -- do not generate)")
            for logo in logos[:3]:
                if isinstance(logo, dict):
                    parts.append(f"- `{logo.get('src', '')}`")
            parts.append("")

    # Hero images
    heroes_raw = entry_map.get("hero_images", "")
    if heroes_raw:
        heroes = _safe_parse_json(heroes_raw)
        if isinstance(heroes, list) and heroes:
            parts.append("### Hero Images")
            for h in heroes[:3]:
                if isinstance(h, dict):
                    alt = h.get("alt", "")
                    parts.append(f"- `{h.get('src', '')}` (alt: {alt})")
            parts.append("")

    # Navigation
    nav_raw = entry_map.get("navigation", "")
    if nav_raw:
        nav = _safe_parse_json(nav_raw)
        if isinstance(nav, list) and nav:
            parts.append("### Navigation")
            for item in nav[:10]:
                if isinstance(item, dict):
                    parts.append(f"- [{item.get('text', '')}]({item.get('href', '')})")
            parts.append("")

    # Footer
    footer_raw = entry_map.get("footer", "")
    if footer_raw:
        footer = _safe_parse_json(footer_raw)
        if isinstance(footer, dict):
            parts.append("### Footer")
            if footer.get("phones"):
                parts.append(f"- Phone: {footer['phones'][0]}")
            if footer.get("copyright"):
                parts.append(f"- {footer['copyright']}")
            parts.append("")

    return "\n".join(parts).strip()


# ── Injection Map Definition ─────────────────────────────────────────────────

# Each entry: (memory_type, formatter, kwargs)
# kwargs are passed to the formatter function.

_CONTENT_PAGE_SECTIONS = [
    (BRAND_VOICE, _format_voice_section, {}),
    (BUSINESS_INTEL, _format_business_section, {
        "keys": ["service_catalog", "differentiators", "certifications", "guarantees"],
    }),
    (PAST_CONTENT, _format_content_history, {}),
    (LEARNINGS, _format_learnings, {}),
]

_INJECTION_MAP: dict[str, list[tuple]] = {
    # Content pages -- full voice + targeted business intel + links + learnings
    "service-page": _CONTENT_PAGE_SECTIONS,

    "location-page": [
        (BRAND_VOICE, _format_voice_section, {}),
        (BUSINESS_INTEL, _format_business_section, {
            "keys": ["service_areas", "service_catalog"],
        }),
        (PAST_CONTENT, _format_content_history, {}),
        (LEARNINGS, _format_learnings, {}),
    ],

    "blog-post": [
        (BRAND_VOICE, _format_voice_section, {}),
        (BUSINESS_INTEL, _format_business_section, {
            "keys": ["customer_personas", "differentiators"],
        }),
        (PAST_CONTENT, _format_content_history, {}),
        (LEARNINGS, _format_learnings, {}),
    ],

    # Design workflows -- design system + assets + CTA-relevant biz intel + tone only
    "design": [
        (DESIGN_SYSTEM, _format_design_section, {}),
        (ASSET_CATALOG, _format_asset_section, {}),
        (BUSINESS_INTEL, _format_business_section, {
            "keys": ["guarantees", "response_time", "certifications", "cta_style"],
        }),
        (BRAND_VOICE, _format_voice_section, {"tone_only": True}),
    ],

    # Audit / research workflows -- just business context, no voice
    "website-seo-audit": [
        (BUSINESS_INTEL, _format_business_section, {
            "keys": ["service_catalog", "service_areas", "competitive_position"],
        }),
    ],

    # Proposals -- everything the sales agent needs
    "proposals": [
        (BRAND_VOICE, _format_voice_section, {}),
        (BUSINESS_INTEL, _format_business_section, {}),
    ],

    # Monthly reports -- service context + content history
    "monthly-report": [
        (BUSINESS_INTEL, _format_business_section, {
            "keys": ["service_catalog", "differentiators"],
        }),
        (PAST_CONTENT, _format_content_history, {}),
    ],
}

# Aliases: multiple workflow names map to the same injection plan
_ALIASES: dict[str, str] = {
    "service_page": "service-page",
    "location_page": "location-page",
    "blog_post": "blog-post",
    "seo-blog-post": "blog-post",
    "page-design": "design",
    "prospect-audit": "website-seo-audit",
    "seo-research": "website-seo-audit",
}


# ── Main Entry Point ─────────────────────────────────────────────────────────

def format_brain_for_workflow(
    memory_store: ClientMemoryStore,
    client_id: int,
    workflow_type: str,
) -> str:
    """Select and format client brain sections for a specific workflow type.

    Args:
        memory_store: ClientMemoryStore instance with database connection.
        client_id: The client whose brain to load.
        workflow_type: The workflow being run (e.g., "service-page", "blog-post", "design").

    Returns:
        Formatted markdown string ready for system prompt injection.
        Returns empty string if the client has no memory entries.
    """
    normalized = _normalize_workflow(workflow_type)

    # Resolve aliases
    canonical = _ALIASES.get(normalized, normalized)

    # Look up injection plan, fall back to full snapshot for unknown types
    injection_plan = _INJECTION_MAP.get(canonical)

    if injection_plan is None:
        # Unknown workflow type: return full snapshot (all sections)
        logger.info(
            "Unknown workflow type '%s' for client %d, returning full snapshot",
            workflow_type, client_id,
        )
        return _build_full_snapshot(memory_store, client_id)

    # Build the formatted brain from the injection plan
    sections = []
    for memory_type, formatter, kwargs in injection_plan:
        entries = memory_store.load_by_type(client_id, memory_type)
        if not entries:
            continue
        formatted = formatter(entries, **kwargs)
        if formatted:
            sections.append(formatted)

    if not sections:
        return ""

    result = "# Client Brain\n\n" + "\n\n---\n\n".join(sections)

    # Enforce token budget by truncating if necessary
    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS].rsplit("\n", 1)[0]
        result += "\n\n[... brain context truncated to fit token budget]"

    return result


def _build_full_snapshot(memory_store: ClientMemoryStore, client_id: int) -> str:
    """Build a full brain snapshot with all memory types, nicely formatted.

    Used as the fallback for unknown workflow types. Applies formatters
    to each section for human-readable output rather than raw key-value pairs.
    """
    all_formatters = [
        (BRAND_VOICE, _format_voice_section, {}),
        (BUSINESS_INTEL, _format_business_section, {}),
        (PAST_CONTENT, _format_content_history, {}),
        (LEARNINGS, _format_learnings, {}),
        (DESIGN_SYSTEM, _format_design_section, {}),
        (ASSET_CATALOG, _format_asset_section, {}),
    ]

    sections = []
    for memory_type, formatter, kwargs in all_formatters:
        entries = memory_store.load_by_type(client_id, memory_type)
        if not entries:
            continue
        formatted = formatter(entries, **kwargs)
        if formatted:
            sections.append(formatted)

    if not sections:
        return ""

    result = "# Client Brain (Full Snapshot)\n\n" + "\n\n---\n\n".join(sections)

    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS].rsplit("\n", 1)[0]
        result += "\n\n[... brain context truncated to fit token budget]"

    return result


# ── Utilities ────────────────────────────────────────────────────────────────

def _safe_parse_json(raw: str) -> dict | list | str:
    """Parse JSON, returning the original string on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _humanize_key(key: str) -> str:
    """Convert snake_case or kebab-case keys to Title Case labels."""
    return key.replace("_", " ").replace("-", " ").title()


def _render_value(raw: str) -> str:
    """Render a memory value as human-readable text.

    If it's JSON, parse and format it. Otherwise return as-is.
    """
    parsed = _safe_parse_json(raw)

    if isinstance(parsed, list):
        if not parsed:
            return "(empty)"
        # Short lists inline, long lists as bullets
        if len(parsed) <= 3 and all(isinstance(x, str) for x in parsed):
            return ", ".join(str(x) for x in parsed)
        lines = []
        for item in parsed:
            if isinstance(item, dict):
                summary = ", ".join(f"{k}: {v}" for k, v in item.items() if v)
                lines.append(f"  - {summary}")
            else:
                lines.append(f"  - {item}")
        return "\n" + "\n".join(lines)

    if isinstance(parsed, dict):
        if not parsed:
            return "(empty)"
        lines = []
        for k, v in parsed.items():
            if v:
                lines.append(f"  - {_humanize_key(k)}: {v}")
        return "\n" + "\n".join(lines) if lines else "(empty)"

    # Plain string
    return raw
