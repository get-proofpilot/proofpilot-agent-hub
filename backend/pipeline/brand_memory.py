"""
Brand Memory Bridge — saves extracted brand data to client memory
and formats it for injection into pipeline stage prompts.

This module connects brand_extractor.py output to the memory store,
and provides optimized formatting for the design + image + copy stages.
"""

import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


def save_brand_to_memory(memory_store, client_id: int, brand_data: dict) -> int:
    """Save extracted brand data into client memory entries.

    Maps the brand_data dict (from brand_extractor) to individual
    memory entries in the client_memory table.

    Returns: count of entries saved.
    """
    saved = 0

    # ── Design System entries ──
    if brand_data.get("color_palette"):
        memory_store.save(client_id, "design_system", "color_palette",
                          json.dumps(brand_data["color_palette"]))
        saved += 1

    if brand_data.get("css_custom_properties"):
        memory_store.save(client_id, "design_system", "css_custom_properties",
                          json.dumps(brand_data["css_custom_properties"]))
        saved += 1

    if brand_data.get("typography"):
        memory_store.save(client_id, "design_system", "typography",
                          json.dumps(brand_data["typography"]))
        saved += 1

    # Build a ready-to-paste CSS :root block
    css_block = build_design_system_css(brand_data)
    if css_block:
        memory_store.save(client_id, "design_system", "design_system_css", css_block)
        saved += 1

    if brand_data.get("section_patterns"):
        memory_store.save(client_id, "design_system", "section_patterns",
                          json.dumps(brand_data["section_patterns"]))
        saved += 1

    if brand_data.get("component_styles"):
        memory_store.save(client_id, "design_system", "component_styles",
                          json.dumps(brand_data["component_styles"]))
        saved += 1

    if brand_data.get("cta_patterns"):
        memory_store.save(client_id, "design_system", "cta_patterns",
                          json.dumps(brand_data["cta_patterns"]))
        saved += 1

    if brand_data.get("photography_style"):
        memory_store.save(client_id, "design_system", "photography_style",
                          brand_data["photography_style"])
        saved += 1

    # ── Asset Catalog entries ──
    assets = brand_data.get("assets", {})

    logos = assets.get("images", {}).get("logos", [])
    if logos:
        memory_store.save(client_id, "asset_catalog", "logos",
                          json.dumps([{"src": l["src"], "alt": l.get("alt", "")} for l in logos]))
        saved += 1

    heroes = assets.get("images", {}).get("heroes", [])
    if heroes:
        memory_store.save(client_id, "asset_catalog", "hero_images",
                          json.dumps([{"src": h["src"], "alt": h.get("alt", "")} for h in heroes]))
        saved += 1

    portfolio = assets.get("images", {}).get("portfolio", [])
    if portfolio:
        memory_store.save(client_id, "asset_catalog", "portfolio_images",
                          json.dumps([{"src": p["src"], "alt": p.get("alt", "")} for p in portfolio]))
        saved += 1

    team = assets.get("images", {}).get("team", [])
    if team:
        memory_store.save(client_id, "asset_catalog", "team_images",
                          json.dumps([{"src": t["src"], "alt": t.get("alt", "")} for t in team]))
        saved += 1

    if assets.get("social_links"):
        memory_store.save(client_id, "asset_catalog", "social_links",
                          json.dumps(assets["social_links"]))
        saved += 1

    if assets.get("schema_data"):
        memory_store.save(client_id, "asset_catalog", "schema_data",
                          json.dumps(assets["schema_data"][:5]))  # Cap at 5 schemas
        saved += 1

    if assets.get("navigation"):
        memory_store.save(client_id, "asset_catalog", "navigation",
                          json.dumps(assets["navigation"]))
        saved += 1

    if assets.get("footer"):
        memory_store.save(client_id, "asset_catalog", "footer",
                          json.dumps(assets["footer"]))
        saved += 1

    # ── Brand Voice entries ──
    if brand_data.get("brand_voice"):
        memory_store.save(client_id, "brand_voice", "tone", brand_data["brand_voice"])
        saved += 1

    if brand_data.get("value_propositions"):
        memory_store.save(client_id, "brand_voice", "value_propositions",
                          json.dumps(brand_data["value_propositions"]))
        saved += 1

    if brand_data.get("business_info"):
        memory_store.save(client_id, "brand_voice", "business_info",
                          json.dumps(brand_data["business_info"]))
        saved += 1

    logger.info("Saved %d brand memory entries for client %d", saved, client_id)
    return saved


def build_design_system_css(brand_data: dict) -> str:
    """Convert extracted brand data into a ready-to-paste CSS :root {} block.

    This CSS block is stored in memory and injected into the design prompt
    so the designer agent can use the client's exact colors and sizing.
    """
    palette = brand_data.get("color_palette", {})
    typo = brand_data.get("typography", {})
    custom_props = brand_data.get("css_custom_properties", {})

    if not palette and not custom_props:
        return ""

    lines = [":root {"]

    # Use original CSS custom properties if available
    if custom_props:
        for prop, val in custom_props.items():
            prop_name = prop if prop.startswith("--") else f"--{prop}"
            lines.append(f"  {prop_name}: {val};")
    else:
        # Build from extracted palette
        for key, val in palette.items():
            if val:
                lines.append(f"  --{key.replace('_', '-')}: {val};")

    # Typography
    if typo.get("heading_font"):
        lines.append(f"  --font-heading: '{typo['heading_font']}', sans-serif;")
    if typo.get("body_font"):
        lines.append(f"  --font-body: '{typo['body_font']}', sans-serif;")
    if typo.get("body_size"):
        lines.append(f"  --font-size-body: {typo['body_size']};")
    if typo.get("body_line_height"):
        lines.append(f"  --line-height-body: {typo['body_line_height']};")

    lines.append("}")
    return "\n".join(lines)


async def ensure_brand_memory(
    memory_store,
    client_id: int,
    domain: str,
    anthropic_client: anthropic.AsyncAnthropic,
    force: bool = False,
) -> bool:
    """Auto-extract brand data if not already in memory.

    Called by the pipeline engine at startup. If brand memory is missing
    (or force=True), runs the full extraction and saves to memory.

    Returns: True if extraction was performed.
    """
    if not force and memory_store.has_entries(client_id, "design_system"):
        logger.info("Brand memory exists for client %d, skipping extraction", client_id)
        return False

    if not domain:
        logger.warning("No domain provided for client %d, cannot extract brand", client_id)
        return False

    logger.info("Auto-extracting brand for client %d from %s", client_id, domain)

    from pipeline.brand_extractor import extract_brand
    brand_data = await extract_brand(domain, anthropic_client)

    if not brand_data.get("color_palette"):
        logger.warning("Brand extraction returned no color data for %s", domain)
        return False

    count = save_brand_to_memory(memory_store, client_id, brand_data)
    logger.info("Auto-extracted %d brand entries for client %d", count, client_id)
    return True


def format_brand_for_design_prompt(memory_store, client_id: int) -> str:
    """Format brand data optimally for the design stage prompt.

    This produces the structured format that DESIGN_BASE_PROMPT expects:
    design_system_css, typography, section_patterns, component_styles, etc.
    """
    entries = memory_store.load_by_type(client_id, "design_system")
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}
    parts = ["## Client Design System\n"]

    # CSS Custom Properties (most important — designer uses these directly)
    css = entry_map.get("design_system_css", "")
    if css:
        parts.append(f"### CSS Custom Properties\n```css\n{css}\n```\n")

    # Typography
    typo_json = entry_map.get("typography", "")
    if typo_json:
        try:
            typo = json.loads(typo_json)
            parts.append("### Typography")
            if typo.get("heading_font"):
                parts.append(f"- Heading font: **{typo['heading_font']}**")
            if typo.get("body_font"):
                parts.append(f"- Body font: **{typo['body_font']}**")
            if typo.get("google_fonts_url"):
                parts.append(f"- Google Fonts: `{typo['google_fonts_url']}`")
            if typo.get("h1_size"):
                parts.append(f"- H1: {typo['h1_size']} / {typo.get('heading_weight', '700')}")
            if typo.get("h2_size"):
                parts.append(f"- H2: {typo['h2_size']}")
            if typo.get("body_size"):
                parts.append(f"- Body: {typo['body_size']} / line-height {typo.get('body_line_height', '1.6')}")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Color Palette (human-readable)
    palette_json = entry_map.get("color_palette", "")
    if palette_json:
        try:
            palette = json.loads(palette_json)
            parts.append("### Color Palette")
            for name, hex_val in palette.items():
                if hex_val:
                    parts.append(f"- {name.replace('_', ' ').title()}: `{hex_val}`")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Section Patterns
    patterns_json = entry_map.get("section_patterns", "")
    if patterns_json:
        try:
            patterns = json.loads(patterns_json)
            parts.append("### Section Patterns")
            for i, p in enumerate(patterns, 1):
                notes = p.get("notes", "")
                parts.append(f"{i}. **{p.get('type', 'section')}**: bg={p.get('bg', '?')}, text={p.get('text_color', '?')} {f'— {notes}' if notes else ''}")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Component Styles
    components_json = entry_map.get("component_styles", "")
    if components_json:
        try:
            components = json.loads(components_json)
            parts.append("### Component Styles")
            for name, props in components.items():
                if isinstance(props, dict):
                    desc = ", ".join(f"{k}: {v}" for k, v in props.items() if v)
                    parts.append(f"- **{name.replace('_', ' ').title()}**: {desc}")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # CTA Patterns
    cta_json = entry_map.get("cta_patterns", "")
    if cta_json:
        try:
            cta = json.loads(cta_json)
            parts.append("### CTA Patterns")
            if cta.get("primary_cta_text"):
                parts.append(f"- Primary CTA: \"{cta['primary_cta_text']}\"")
            if cta.get("phone_number"):
                parts.append(f"- Phone: **{cta['phone_number']}**")
            if cta.get("phone_prominent"):
                parts.append("- Phone is prominently displayed")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Photography Style
    photo_style = entry_map.get("photography_style", "")
    if photo_style:
        parts.append(f"### Photography Style\n{photo_style}\n")

    # Client Assets (logos, existing images to reuse)
    asset_entries = memory_store.load_by_type(client_id, "asset_catalog")
    asset_map = {e["key"]: e["value"] for e in asset_entries}

    logos_json = asset_map.get("logos", "")
    if logos_json:
        try:
            logos = json.loads(logos_json)
            if logos:
                parts.append("### Client Assets (USE THESE — do not generate)")
                parts.append(f"- Logo: `{logos[0]['src']}`")
                if len(logos) > 1:
                    parts.append(f"- Alt logo: `{logos[1]['src']}`")
        except json.JSONDecodeError:
            pass

    heroes_json = asset_map.get("hero_images", "")
    if heroes_json:
        try:
            heroes = json.loads(heroes_json)
            if heroes:
                for h in heroes[:3]:
                    parts.append(f"- Hero image: `{h['src']}` (alt: {h.get('alt', '')})")
        except json.JSONDecodeError:
            pass

    # Navigation (so designer can replicate nav structure)
    nav_json = asset_map.get("navigation", "")
    if nav_json:
        try:
            nav = json.loads(nav_json)
            if nav:
                parts.append("\n### Navigation Structure")
                for item in nav[:10]:
                    parts.append(f"- [{item['text']}]({item['href']})")
                parts.append("")
        except json.JSONDecodeError:
            pass

    # Footer
    footer_json = asset_map.get("footer", "")
    if footer_json:
        try:
            footer = json.loads(footer_json)
            if footer.get("phones"):
                parts.append(f"\n### Footer Info\n- Phone: {footer['phones'][0]}")
            if footer.get("copyright"):
                parts.append(f"- {footer['copyright']}")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Brand Voice
    voice_entries = memory_store.load_by_type(client_id, "brand_voice")
    voice_map = {e["key"]: e["value"] for e in voice_entries}

    if voice_map.get("tone"):
        parts.append(f"\n### Brand Voice\n{voice_map['tone']}\n")

    props_json = voice_map.get("value_propositions", "")
    if props_json:
        try:
            props = json.loads(props_json)
            if props:
                parts.append("### Key Value Propositions")
                for p in props:
                    parts.append(f"- {p}")
                parts.append("")
        except json.JSONDecodeError:
            pass

    biz_json = voice_map.get("business_info", "")
    if biz_json:
        try:
            biz = json.loads(biz_json)
            if biz.get("name"):
                parts.append(f"### Business Info")
                parts.append(f"- Name: {biz['name']}")
                if biz.get("phone"):
                    parts.append(f"- Phone: {biz['phone']}")
                if biz.get("address"):
                    parts.append(f"- Address: {biz['address']}")
                if biz.get("license"):
                    parts.append(f"- License: {biz['license']}")
                parts.append("")
        except json.JSONDecodeError:
            pass

    return "\n".join(parts)


def get_brand_context_for_images(memory_store, client_id: int) -> dict:
    """Extract brand context relevant to image generation.

    Returns a dict with photography_style, color_palette, and existing_images
    that the image generation stage can use.
    """
    ds_entries = memory_store.load_by_type(client_id, "design_system")
    ds_map = {e["key"]: e["value"] for e in ds_entries}

    asset_entries = memory_store.load_by_type(client_id, "asset_catalog")
    asset_map = {e["key"]: e["value"] for e in asset_entries}

    result = {
        "photography_style": ds_map.get("photography_style", ""),
        "color_palette": {},
        "existing_heroes": [],
        "existing_portfolio": [],
    }

    palette_json = ds_map.get("color_palette", "")
    if palette_json:
        try:
            result["color_palette"] = json.loads(palette_json)
        except json.JSONDecodeError:
            pass

    heroes_json = asset_map.get("hero_images", "")
    if heroes_json:
        try:
            result["existing_heroes"] = json.loads(heroes_json)
        except json.JSONDecodeError:
            pass

    portfolio_json = asset_map.get("portfolio_images", "")
    if portfolio_json:
        try:
            result["existing_portfolio"] = json.loads(portfolio_json)
        except json.JSONDecodeError:
            pass

    return result
