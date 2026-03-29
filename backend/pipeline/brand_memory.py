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

    # Save font files if self-hosted
    font_files = brand_data.get("typography", {}).get("font_files", [])
    if font_files:
        memory_store.save(client_id, "design_system", "font_files",
                          json.dumps(font_files))
        saved += 1

    # Save layout patterns if extracted
    layout = brand_data.get("layout_patterns", {})
    if layout:
        memory_store.save(client_id, "design_system", "layout_patterns",
                          json.dumps(layout))
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

    Filters out generic framework variables (Bootstrap, WordPress, Elementor)
    that pollute the output and confuse the design agent.
    """
    palette = brand_data.get("color_palette", {})
    typo = brand_data.get("typography", {})
    custom_props = brand_data.get("css_custom_properties", {})

    if not palette and not custom_props:
        return ""

    # Framework variable prefixes to filter out
    _FRAMEWORK_PREFIXES = ("--bs-", "--wp-", "--elementor-", "--e-", "--tcb-", "--flavor-")

    lines = [":root {"]

    # Use original CSS custom properties if available, filtering framework vars
    if custom_props:
        for prop, val in custom_props.items():
            prop_name = prop if prop.startswith("--") else f"--{prop}"
            if any(prop_name.startswith(prefix) for prefix in _FRAMEWORK_PREFIXES):
                continue
            lines.append(f"  {prop_name}: {val};")
    else:
        # Build from extracted palette
        for key, val in palette.items():
            if val:
                lines.append(f"  --{key.replace('_', '-')}: {val};")

    # Typography — only add if not already present from custom properties
    existing = "\n".join(lines)
    if typo.get("heading_font") and "--font-heading" not in existing:
        lines.append(f"  --font-heading: '{typo['heading_font']}', sans-serif;")
    if typo.get("body_font") and "--font-body" not in existing:
        lines.append(f"  --font-body: '{typo['body_font']}', sans-serif;")
    if typo.get("body_size") and "--font-size-body" not in existing:
        lines.append(f"  --font-size-body: {typo['body_size']};")
    if typo.get("body_line_height") and "--line-height-body" not in existing:
        lines.append(f"  --line-height-body: {typo['body_line_height']};")

    lines.append("}")

    # If we only have :root { }, return empty
    if len(lines) <= 2:
        return ""

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

    Structure: Critical directives FIRST (logo, fonts), then design system,
    then reference data. The top section is formatted as non-negotiable
    build requirements so the model cannot overlook them.
    """
    entries = memory_store.load_by_type(client_id, "design_system")
    if not entries:
        return ""

    entry_map = {e["key"]: e["value"] for e in entries}

    # Load assets early — we need logos and fonts for the critical section
    asset_entries = memory_store.load_by_type(client_id, "asset_catalog")
    asset_map = {e["key"]: e["value"] for e in asset_entries}

    # Load brand voice early for business info
    voice_entries = memory_store.load_by_type(client_id, "brand_voice")
    voice_map = {e["key"]: e["value"] for e in voice_entries}

    # Parse typography and assets once
    typo = {}
    typo_json = entry_map.get("typography", "")
    if typo_json:
        try:
            typo = json.loads(typo_json)
        except json.JSONDecodeError:
            pass

    logos = []
    logos_json = asset_map.get("logos", "")
    if logos_json:
        try:
            logos = json.loads(logos_json)
        except json.JSONDecodeError:
            pass

    nav = []
    nav_json = asset_map.get("navigation", "")
    if nav_json:
        try:
            nav = json.loads(nav_json)
        except json.JSONDecodeError:
            pass

    biz = {}
    biz_json = voice_map.get("business_info", "")
    if biz_json:
        try:
            biz = json.loads(biz_json)
        except json.JSONDecodeError:
            pass

    cta = {}
    cta_json = entry_map.get("cta_patterns", "")
    if cta_json:
        try:
            cta = json.loads(cta_json)
        except json.JSONDecodeError:
            pass

    footer = {}
    footer_json = asset_map.get("footer", "")
    if footer_json:
        try:
            footer = json.loads(footer_json)
        except json.JSONDecodeError:
            pass

    parts = []

    # ── CRITICAL DIRECTIVES (top of prompt — must not be skipped) ──────

    parts.append("## CRITICAL BUILD DIRECTIVES — YOU MUST USE THESE EXACTLY\n")

    # Logo directive
    if logos:
        logo_url = logos[0].get("src", "")
        if logo_url:
            parts.append(f"**LOGO:** Include this EXACT logo image in the page header:")
            parts.append(f'`<img src="{logo_url}" alt="{biz.get("name", "Logo")}" class="site-logo">`')
            if len(logos) > 1:
                parts.append(f"Alt/white logo variant: `{logos[1].get('src', '')}`")
            parts.append("")

    # Font directive — use self-hosted @font-face if available, else Google Fonts
    google_fonts_url = typo.get("google_fonts_url", "")
    heading_font = typo.get("heading_font", "")
    body_font = typo.get("body_font", "")
    font_files = typo.get("font_files", [])

    # Also check stored font_files in memory
    if not font_files:
        font_files_json = entry_map.get("font_files", "")
        if font_files_json:
            try:
                font_files = json.loads(font_files_json)
            except json.JSONDecodeError:
                pass

    if font_files and len(font_files) > 0:
        # Self-hosted fonts — emit @font-face CSS block
        parts.append("**FONTS (SELF-HOSTED):** Include these EXACT @font-face declarations in your <style> block:")
        parts.append("```css")
        for ff in font_files:
            family = ff.get("family", "")
            weight = ff.get("weight", "400")
            url = ff.get("url", "")
            if family and url:
                fmt = "woff2" if ".woff2" in url else "woff"
                parts.append(f"@font-face {{")
                parts.append(f'  font-family: "{family}";')
                parts.append(f"  font-weight: {weight};")
                parts.append(f'  src: url("{url}") format("{fmt}");')
                parts.append(f"  font-display: swap;")
                parts.append(f"}}")
        parts.append("```")
        parts.append("Do NOT use a Google Fonts <link> — these fonts are self-hosted on the client's server.")
    elif google_fonts_url:
        parts.append(f"**FONTS:** Include this EXACT Google Fonts link in <head>:")
        parts.append(f"`{google_fonts_url}`")
    elif heading_font or body_font:
        # Build a Google Fonts URL from font names
        font_families = []
        if heading_font and heading_font.lower() not in ("system-ui", "sans-serif", "arial", "helvetica"):
            font_families.append(heading_font.replace(" ", "+") + ":wght@400;500;600;700")
        if body_font and body_font != heading_font and body_font.lower() not in ("system-ui", "sans-serif", "arial", "helvetica"):
            font_families.append(body_font.replace(" ", "+") + ":wght@400;500;600;700")
        if font_families:
            built_url = f'<link href="https://fonts.googleapis.com/css2?family={"&family=".join(font_families)}&display=swap" rel="stylesheet">'
            parts.append(f"**FONTS:** Include this Google Fonts link in <head>:")
            parts.append(f"`{built_url}`")

    if heading_font:
        parts.append(f"- Heading font-family: `'{heading_font}', sans-serif`")
    if body_font:
        parts.append(f"- Body font-family: `'{body_font}', sans-serif`")
    parts.append("")

    # Phone directive
    phone = cta.get("phone_number", "") or biz.get("phone", "") or (footer.get("phones", [None])[0] if footer.get("phones") else "")
    if phone:
        parts.append(f"**PHONE:** Display prominently in header and CTAs: `{phone}`")
        parts.append("")

    # Header/Nav directive
    if nav:
        parts.append("**HEADER:** Build a sticky header with: logo (left) | nav links (center) | phone + CTA button (right)")
        parts.append("Nav links:")
        for item in nav[:8]:
            parts.append(f"  - [{item.get('text', '')}]({item.get('href', '')})")
        parts.append("")

    # ── DESIGN SYSTEM ─────────────────────────────────────────────────

    parts.append("## Client Design System\n")

    # CSS Custom Properties
    css = entry_map.get("design_system_css", "")
    if css:
        # Strip any generic framework variables that leaked in
        clean_lines = []
        for line in css.split("\n"):
            if not any(prefix in line for prefix in ("--bs-", "--wp-", "--elementor-")):
                clean_lines.append(line)
        clean_css = "\n".join(clean_lines)
        parts.append(f"### CSS Custom Properties (use in your :root)\n```css\n{clean_css}\n```\n")

    # Typography details
    if typo:
        parts.append("### Typography")
        if typo.get("h1_size"):
            parts.append(f"- H1: {typo['h1_size']} / weight {typo.get('heading_weight', '700')}")
        if typo.get("h2_size"):
            parts.append(f"- H2: {typo['h2_size']}")
        if typo.get("h3_size"):
            parts.append(f"- H3: {typo['h3_size']}")
        if typo.get("body_size"):
            parts.append(f"- Body: {typo['body_size']} / line-height {typo.get('body_line_height', '1.6')}")
        parts.append("")

    # Color Palette
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
            parts.append("### Section Patterns (match this visual rhythm)")
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
    if cta:
        parts.append("### CTA Patterns")
        if cta.get("primary_cta_text"):
            parts.append(f"- Primary CTA: \"{cta['primary_cta_text']}\"")
        if cta.get("phone_prominent"):
            parts.append("- Phone is prominently displayed on the site")
        parts.append("")

    # Layout Patterns
    layout_json = entry_map.get("layout_patterns", "")
    if layout_json:
        try:
            layout = json.loads(layout_json)
            if layout:
                parts.append("### Layout Patterns (match this site structure)")
                if layout.get("primary_layout"):
                    parts.append(f"- Primary layout: **{layout['primary_layout']}**")
                if layout.get("hero_style"):
                    parts.append(f"- Hero style: {layout['hero_style']}")
                if layout.get("section_alternation"):
                    parts.append(f"- Section alternation: {layout['section_alternation']}")
                parts.append("")
        except json.JSONDecodeError:
            pass

    # Photography Style
    photo_style = entry_map.get("photography_style", "")
    if photo_style:
        parts.append(f"### Photography Style\n{photo_style}\n")

    # ── EXISTING ASSETS ───────────────────────────────────────────────

    heroes_json = asset_map.get("hero_images", "")
    if heroes_json:
        try:
            heroes = json.loads(heroes_json)
            if heroes:
                parts.append("### Hero Images (use as background-image)")
                for h in heroes[:3]:
                    parts.append(f"- `{h['src']}` (alt: {h.get('alt', '')})")
                parts.append("")
        except json.JSONDecodeError:
            pass

    # Social links for footer
    social_json = asset_map.get("social_links", "")
    if social_json:
        try:
            social = json.loads(social_json)
            if social:
                parts.append("### Social Links (for footer)")
                for platform, url in social.items():
                    parts.append(f"- {platform.replace('_', ' ').title()}: `{url}`")
                parts.append("")
        except json.JSONDecodeError:
            pass

    # Footer info
    if footer:
        parts.append("### Footer Info")
        if footer.get("phones"):
            parts.append(f"- Phone: {footer['phones'][0]}")
        if footer.get("emails"):
            parts.append(f"- Email: {footer['emails'][0]}")
        if footer.get("copyright"):
            parts.append(f"- {footer['copyright']}")
        parts.append("")

    # ── BRAND VOICE (brief for design context) ────────────────────────

    if voice_map.get("tone"):
        parts.append(f"### Brand Voice\n{voice_map['tone']}\n")

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

    if biz.get("name"):
        parts.append("### Business Info")
        parts.append(f"- Name: {biz['name']}")
        if biz.get("phone"):
            parts.append(f"- Phone: {biz['phone']}")
        if biz.get("address"):
            parts.append(f"- Address: {biz['address']}")
        if biz.get("license"):
            parts.append(f"- License: {biz['license']}")
        parts.append("")

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
