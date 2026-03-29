"""
Test design v3 — Re-extract brand with improved filters, run design stage
with the upgraded prompts, compare output quality against v2 baseline.

Tests: Owl Roofing (client_id=15) — "Large Home Roofing Phoenix"
Reuses the copywrite content from the v2 test to isolate design changes.
"""

import asyncio
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before importing anthropic
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass  # dotenv not installed, rely on env vars

import anthropic
from utils.db import init_db, _connect
from memory.store import ClientMemoryStore, init_memory_table
from pipeline.engine import PipelineEngine, PipelineRun, PipelineStatus
from pipeline.stages import STAGE_RUNNERS
from pipeline.artifacts import ContentArtifact, StrategyArtifact

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_output")
CLIENT_ID = 15
CLIENT_NAME = "Owl Roofing"
DOMAIN = "owlroofing.com"


# ── Copywrite content (extracted from the v2 test run) ─────────────────────

COPYWRITE_MARKDOWN = """# Large Home Roofing Specialists Serving Phoenix's Premier Properties

When your Phoenix-area luxury home demands the finest roofing expertise, you need contractors who understand the unique challenges of large, custom properties. Owl Roofing brings over 20 years of specialized experience to Phoenix's most prestigious communities — from Arcadia estates to Paradise Valley compounds.

Large homes aren't just bigger versions of standard houses. They feature complex roof lines, multiple elevation changes, and architectural details that demand specialized knowledge. Our team has built its reputation handling properties that other contractors turn away.

## Why Large Homes Need Specialized Roofing Expertise

Homes over 4,000 square feet present roofing challenges that standard residential contractors often underestimate. The scale, complexity, and architectural requirements of substantial properties demand specialized knowledge and experience.

### Complex Structural Engineering

Homes over 4,000 square feet feature complex roof lines with multiple levels, angles, and architectural elements that require careful engineering analysis and specialized load calculations.

### Advanced Drainage Systems

Large homes generate substantially more runoff volume, requiring sophisticated drainage solutions that handle Phoenix's monsoon seasons and prevent structural damage.

### Premium Material Integration

Luxury homes demand materials that complement custom architectural elements while providing superior performance across extensive roof areas.

### Extended Timeline Management

Large home projects require months of planning and weeks of installation, demanding sophisticated project coordination to minimize family disruption.

## Our Proven Process for Phoenix Large Home Projects

Our systematic approach ensures exceptional results while minimizing disruption to your family's lifestyle. We've refined this process over two decades.

### Step 1: Architectural Consultation

Comprehensive consultation with detailed architectural analysis, thermal imaging, and structural assessment tailored to Phoenix's climate demands.

### Step 2: Custom Design & Engineering

Phoenix-specific engineering that addresses UV exposure, thermal expansion, and monsoon wind loads across substantial roof planes.

### Step 3: Premium Material Selection

Guided material selection with samples and mockups, considering both performance and aesthetic requirements for your luxury property.

### Step 4: Staged Installation

Coordinated installation phases that prioritize weather protection while allowing families to remain comfortable throughout the project.

### Step 5: Quality Assurance

Comprehensive inspection phases with thermal imaging verification, moisture testing, and detailed warranty documentation.

## Premium Roofing Materials Engineered for Phoenix Heat

Phoenix temperatures regularly exceed 115°F during summer months, creating roof surface temperatures that can reach 160°F or higher. Our material selection ensures optimal performance.

### Premium Tile Systems

Clay and concrete tiles with enhanced reflective properties that excel in Phoenix conditions, providing 50+ years of service life with superior heat resistance.

### Advanced Metal Roofing

Specialized metal systems with heat-reflective coatings, excellent wind resistance, and 30-50 year durability perfect for contemporary luxury designs.

### Cool Roof Technologies

Advanced reflective membrane and coating systems that dramatically reduce roof surface temperatures. These technologies can lower interior cooling costs by 20-40%.

## Phoenix Service Areas for Large Home Roofing

We serve Phoenix's most prestigious residential communities:

- **Arcadia** — Custom estates with complex multi-level roof lines
- **Paradise Valley** — Sprawling luxury compounds on large lots
- **Scottsdale North** — Contemporary desert architecture with flat and mixed roof systems
- **Camelback Corridor** — High-end renovations and historic estate roofing
- **Ahwatukee** — Established luxury communities with tile and shake roofs
- **Biltmore Area** — Classic Phoenix estates requiring premium materials

## Why Phoenix Homeowners Choose Owl Roofing

### 20+ Years of Luxury Home Experience

Two decades focused exclusively on substantial residential properties means we've encountered and solved every large home roofing challenge Phoenix can present.

### Family-Owned Accountability

As a family business, your project gets direct owner involvement from consultation through final inspection. No project managers acting as middlemen.

### Local Climate Expertise

We engineer every roof system specifically for Phoenix conditions — extreme heat, UV exposure, monsoon winds, and thermal cycling that can destroy improperly installed roofs.

### Transparent Project Communication

Weekly progress reports, dedicated project coordinator, and direct owner access throughout every phase of your project.

## Frequently Asked Questions

### What type of roofing is best for large homes in Phoenix?

The best roofing depends on architectural style and performance requirements. Clay and concrete tiles excel for traditional southwestern styles. Metal roofing works well for contemporary designs. We evaluate each property individually and recommend materials based on your specific situation.

### How much does it cost to roof a large custom home?

Large home roofing costs in Phoenix typically range from $15,000 to $75,000, depending on size, complexity, and material selection.

### How long does it take to roof a large house?

Large home roofing projects typically require 2-4 weeks for completion. Projects over 6,000 square feet or those with extensive architectural details may require longer timelines.

### Do large homes need special roofing considerations in Arizona heat?

Yes. Extensive roof areas absorb tremendous heat, requiring enhanced ventilation systems and reflective materials. Thermal expansion across large roof planes demands expansion joint systems to prevent cracking.

## Protect Your Phoenix Investment

Your large home is likely your most significant investment. The right roofing system protects that investment for decades while enhancing your property's curb appeal and energy efficiency.

Schedule a comprehensive roofing consultation with our large home specialists. We'll evaluate your property's unique requirements and provide a detailed proposal.

---
TITLE_TAG: Large Home Roofing Phoenix | Custom & Luxury Specialists | Owl Roofing
META_DESCRIPTION: Phoenix's premier large home roofing specialists. Custom solutions for luxury homes 4,000+ sq ft. Expert installation, premium materials, minimal disruption. Free consultation.
SCHEMA_TYPE: LocalBusiness|Service|FAQPage
"""

TITLE_TAG = "Large Home Roofing Phoenix | Custom & Luxury Specialists | Owl Roofing"
META_DESCRIPTION = "Phoenix's premier large home roofing specialists. Custom solutions for luxury homes 4,000+ sq ft. Expert installation, premium materials, minimal disruption. Free consultation."


async def step_1_reextract_brand(api_client):
    """Re-run brand extraction with improved tracking pixel filters."""
    from pipeline.brand_extractor import extract_brand
    from pipeline.brand_memory import save_brand_to_memory, format_brand_for_design_prompt

    store = ClientMemoryStore(_connect)

    print("=" * 70)
    print("  STEP 1: Re-extract brand from owlroofing.com")
    print("=" * 70)

    brand_data = await extract_brand(DOMAIN, api_client)

    # Check what we got
    palette = brand_data.get("color_palette", {})
    typo = brand_data.get("typography", {})
    logos = brand_data.get("assets", {}).get("images", {}).get("logos", [])
    nav = brand_data.get("assets", {}).get("navigation", [])

    print(f"\n  Colors: {json.dumps(palette, indent=2)}")
    print(f"\n  Typography: heading={typo.get('heading_font')}, body={typo.get('body_font')}")
    print(f"  Google Fonts URL: {typo.get('google_fonts_url', 'NONE')}")
    print(f"\n  Logos found: {len(logos)}")
    for l in logos[:5]:
        print(f"    - {l['src'][:80]}")
    print(f"\n  Nav items: {len(nav)}")
    for n in nav[:8]:
        print(f"    - {n.get('text', '')}: {n.get('href', '')}")

    # Save to memory (overwrites old data)
    count = save_brand_to_memory(store, CLIENT_ID, brand_data)
    print(f"\n  Saved {count} memory entries")

    # Verify the formatted prompt
    brand_block = format_brand_for_design_prompt(store, CLIENT_ID)
    print(f"\n  Formatted brand block: {len(brand_block)} chars")

    # Check for critical elements
    checks = {
        "Has CRITICAL BUILD DIRECTIVES": "CRITICAL BUILD DIRECTIVES" in brand_block,
        "Has LOGO directive": "LOGO:" in brand_block,
        "Has FONTS directive": "FONT" in brand_block,
        "Has PHONE directive": "PHONE:" in brand_block,
        "Has NAV links": "NAV LINKS:" in brand_block or "HEADER:" in brand_block,
        "NO Bootstrap vars in CSS": "--bs-" not in brand_block,
        "Has color palette": "Color Palette" in brand_block or "--primary" in brand_block,
        "Has typography section": "Typography" in brand_block or "--font-heading" in brand_block,
    }

    print("\n  Brand block quality checks:")
    all_pass = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"    [{status}] {check}")

    if not all_pass:
        print("\n  >> WARNING: Some brand checks failed. Printing full block:")
        print(brand_block[:2000])

    return brand_block


async def step_2_run_design(api_client):
    """Run the design stage with the improved prompt and brand data."""
    store = ClientMemoryStore(_connect)
    engine = PipelineEngine(api_client, _connect, store)

    print("\n" + "=" * 70)
    print("  STEP 2: Run design stage with improved prompts")
    print("=" * 70)

    # Create pipeline run
    run = engine.create_run(
        page_type="service-page",
        client_id=CLIENT_ID,
        client_name=CLIENT_NAME,
        inputs={
            "domain": DOMAIN,
            "service": "roofing for large homes",
            "location": "Phoenix, AZ",
            "differentiators": "Family owned, 20+ years experience, luxury home specialists",
            "price_range": "$15,000-$75,000",
            "notes": "Phoenix climate: extreme heat, monsoon seasons, UV exposure",
        },
        stages=["research", "strategy", "copywrite", "design", "qa"],
        approval_mode="autopilot",
    )

    # Inject the copywrite artifact (skip earlier stages)
    h1_match = re.search(r'^# (.+)$', COPYWRITE_MARKDOWN, re.MULTILINE)
    artifact = ContentArtifact(
        markdown=COPYWRITE_MARKDOWN,
        word_count=len(COPYWRITE_MARKDOWN.split()),
        h1=h1_match.group(1) if h1_match else "",
        title_tag=TITLE_TAG,
        meta_description=META_DESCRIPTION,
    )
    run.artifacts["copywrite"] = artifact.to_json()

    # Inject a strategy artifact
    strategy = StrategyArtifact(
        page_type="service-page",
        target_keyword="large home roofing phoenix",
        brief_text="Service page targeting 'large home roofing phoenix' with luxury positioning.",
    )
    run.artifacts["strategy"] = strategy.to_json()

    # Skip to design stage
    run.current_stage_index = 3  # index 3 = design
    run.status = PipelineStatus.RUNNING
    engine._persist_run(run)

    print(f"\n  Starting from stage: {run.current_stage} (index {run.current_stage_index})")

    # Execute and capture output
    stage_outputs = {}
    current_stage = None
    start_time = time.time()

    async for chunk_json in engine.execute(run, STAGE_RUNNERS):
        data = json.loads(chunk_json)

        if data["type"] == "stage_start":
            current_stage = data["stage"]
            stage_outputs[current_stage] = []
            print(f"\n  {'─' * 50}")
            print(f"  STAGE: {data['stage'].upper()}")
            print(f"  {'─' * 50}")

        elif data["type"] == "token":
            stage = data.get("stage", current_stage)
            if stage and stage in stage_outputs:
                stage_outputs[stage].append(data["text"])
            # Print progress dots instead of full text
            if len(stage_outputs.get(stage, [])) % 100 == 0:
                print(".", end="", flush=True)

        elif data["type"] == "stage_complete":
            stage = data["stage"]
            output = "".join(stage_outputs.get(stage, []))
            elapsed = time.time() - start_time
            print(f"\n  >> {stage} complete: {len(output)} chars ({elapsed:.1f}s)")

        elif data["type"] == "pipeline_complete":
            elapsed = time.time() - start_time
            print(f"\n  Pipeline complete in {elapsed:.1f}s")

        elif data["type"] == "error":
            print(f"\n  ERROR: {data['message']}")
            return None

    return run


def step_3_analyze_output(run):
    """Analyze the HTML output against the v2 baseline."""
    print("\n" + "=" * 70)
    print("  STEP 3: Quality analysis — v3 vs v2 baseline")
    print("=" * 70)

    if "design" not in run.artifacts:
        print("  ERROR: No design artifact produced")
        return

    design = json.loads(run.artifacts["design"])
    html = design.get("full_page", "")

    if not html:
        print("  ERROR: Empty HTML output")
        return

    # Save HTML
    html_path = os.path.join(OUTPUT_DIR, "owl_roofing_v3_improved.html")
    with open(html_path, "w") as f:
        f.write(html)
    print(f"\n  Saved: {html_path}")
    print(f"  Size: {len(html):,} chars")

    # ── Quality checks ──────────────────────────────────────────────
    print("\n  ┌─────────────────────────────────────────────────────┐")
    print("  │  DESIGN QUALITY CHECKS                              │")
    print("  └─────────────────────────────────────────────────────┘")

    html_lower = html.lower()

    checks = {
        # Structure
        "Has <header> element": "<header" in html_lower,
        "Has logo <img>": "site-logo" in html_lower or ("logo" in html_lower and "<img" in html_lower and "owlroofing" in html_lower),
        "Has <nav> or nav links": "<nav" in html_lower or "nav-links" in html_lower,
        "Has sticky header": "position: sticky" in html_lower or "position:sticky" in html_lower,
        "Has <footer> element": "<footer" in html_lower,
        "Has mobile menu toggle": "menu-toggle" in html_lower or "hamburger" in html_lower or "mobile-menu" in html_lower,

        # Brand compliance
        "Uses client primary color (#666b53)": "#666b53" in html_lower,
        "Uses client accent color (#eaa222)": "#eaa222" in html_lower,
        "Uses client dark color (#36402d)": "#36402d" in html_lower,
        "Loads Google Fonts": "fonts.googleapis.com" in html,
        "Uses Special Gothic Expanded": "special gothic" in html_lower,
        "Has phone number (651-977-6027)": "651-977-6027" in html or "6519776027" in html,

        # Visual polish
        "Has card containers (box-shadow)": "box-shadow" in html_lower,
        "Has hover effects (translateY)": "translatey" in html_lower,
        "Has section heading accents (border-bottom or section-label)": ("section-label" in html_lower or
            ("border-bottom" in html_lower and "solid" in html_lower and ("accent" in html_lower or "#eaa" in html_lower))),
        "Has background variety (gradient or accent-tinted)": ("linear-gradient" in html_lower and
            html_lower.count("background") > 8),
        "Has process step connectors (::after)": "::after" in html_lower,
        "Has FAQ with max-height transition": "max-height" in html_lower,
        "Has icon CDN (Lucide)": "lucide" in html_lower,

        # Anti-patterns (should NOT have)
        "NO Bootstrap vars (--bs-)": "--bs-" not in html,
        "NO emoji icons": not any(ord(c) > 0x1F600 and ord(c) < 0x1F650 for c in html),
        "Has Schema JSON-LD": "application/ld+json" in html,
        "Has OG meta tags": "og:title" in html,
    }

    pass_count = 0
    fail_count = 0
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if passed:
            pass_count += 1
        else:
            fail_count += 1
        print(f"    [{status}] {check}")

    total = pass_count + fail_count
    score = (pass_count / total) * 100 if total > 0 else 0
    print(f"\n  Score: {pass_count}/{total} checks passed ({score:.0f}%)")

    # Count unique background-color values to measure visual variety
    bg_colors = set(re.findall(r'background(?:-color)?:\s*(#[0-9a-fA-F]{3,8}|var\(--[^)]+\)|rgba?\([^)]+\))', html))
    print(f"\n  Background variety: {len(bg_colors)} unique background values")
    for bg in sorted(bg_colors):
        print(f"    - {bg}")

    # Count sections
    sections = re.findall(r'<section[^>]*class=["\']([^"\']+)["\']', html)
    print(f"\n  Sections found: {len(sections)}")
    for s in sections:
        print(f"    - .{s}")

    # QA stage output
    if "qa" in run.artifacts:
        qa = json.loads(run.artifacts["qa"])
        print(f"\n  QA Score: {qa.get('overall_score', 'N/A')}/100")
        approved = qa.get("approved", False)
        print(f"  Approved: {approved}")

    print(f"\n  Output file: {html_path}")
    print(f"  Open in browser to visually inspect.")

    return score


async def main():
    init_db()
    conn = _connect()
    init_memory_table(conn)
    api_client = anthropic.AsyncAnthropic()

    print("\n" + "=" * 70)
    print("  OWL ROOFING V3 DESIGN TEST")
    print("  Testing improved design prompts, brand formatting, and CSS filtering")
    print("=" * 70)

    # Step 1: Re-extract brand
    brand_block = await step_1_reextract_brand(api_client)

    # Step 2: Run design + QA
    run = await step_2_run_design(api_client)
    if not run:
        print("\n  PIPELINE FAILED — see errors above")
        return

    # Step 3: Analyze output
    score = step_3_analyze_output(run)

    print("\n" + "=" * 70)
    print(f"  TEST COMPLETE — Design quality score: {score:.0f}%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
