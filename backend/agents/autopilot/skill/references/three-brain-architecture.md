# The Three-Brain Design Architecture

> How AutoPilot builds a website that feels custom, not templated. Each stage has a distinct "brain" with a distinct job. Do not merge them.

## Why three brains

Running the design work as a single "run_design" stage produces template skins. Splitting it forces deliberate decisions at each layer, and each layer can be debugged independently.

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│  BRAND BRAIN   │────▶│ DESIGNER BRAIN │────▶│ WEBSITE BRAIN  │
│                │     │                │     │                │
│ What exists?   │     │ What should    │     │ How do we      │
│ What's the     │     │ we preserve,   │     │ execute this   │
│ actual brand?  │     │ elevate, or    │     │ with code?     │
│                │     │ invent?        │     │                │
└────────────────┘     └────────────────┘     └────────────────┘
       │                       │                       │
       ▼                       ▼                       ▼
 brand-brain.json       design-spec.md          /demo-site/
 (raw facts)            (creative decisions)    (actual HTML)
```

Each stage reads only its predecessor's output. The Brand Brain does NOT make design decisions. The Designer Brain does NOT write HTML. The Website Brain does NOT re-decide the palette.

---

## Stage 1 — Brand Brain (archaeologist + photographer + reporter)

**Single job:** capture what the client's brand actually IS right now. No opinions, no design moves. Just facts.

### Inputs
- Client domain
- Optional: competitor domains

### Procedure (run this exact sequence)

1. **Pull the live page data.** Prefer Firecrawl when available (it has purpose-built brand extraction via the `extract` format with a schema). Fallback: Playwright + Python + raw HTML parsing. Either way, capture:
   - Raw HTML of `/`, `/about`, primary service pages
   - Full CSS from linked stylesheets (resolve `<link rel="stylesheet">` URLs, concat)
   - Every `<img>` src + alt, every `<link rel*="icon">` URL, every OG meta image
   - Computed styles on `body`, `h1`, `h2`, `h3`, primary button (if any), links, footer — for the color-in-use fingerprint

2. **Download the logo.** Find the header `<img>` that matches `/logo|brand|<clientName>/i`. Try the high-res variant (`?format=1500w` for Squarespace). `curl -L -o assets/logo-original.png`. Verify with `file`.

3. **Pixel-analyze the logo.** Python + Pillow:
   - Open RGBA, filter to opaque pixels
   - Quantize each channel to nearest 16
   - Top 20 buckets = the actual logo palette
   - Save to `assets/logo-palette.json`

4. **Download the favicon + OG image** (these often reveal a stripped logo-mark).

5. **Classify every `<img>` URL** as logo / stock (unsplash.com, squarespace-cdn placeholder paths) / authentic (client's own CDN, custom filename with no stock markers). **Download every authentic asset.** These are gold — real fleet shots, team photos, storefront, project galleries.

6. **Capture typography.** Page-evaluate `document.fonts` + computed `font-family` on H1/H2/body/button. Capture `@font-face` URLs from CSS. Note whether the wordmark in the logo uses a DIFFERENT face than the page CSS (it usually does — record both).

7. **Read voice signals.** Load `/`, `/about`, primary service page. Scan 200 words each. Note:
   - Tone (formal / casual / technical / friendly / aggressive)
   - Audience signals (addresses homeowners, GCs, property managers, builders, all?)
   - Industry vocabulary worth preserving (e.g. "panel upgrade", "tract communities", "rough-in")

### Output: `brand-brain.json`

```json
{
  "logo": {
    "source_url": "...",
    "local_path": "...",
    "composition": "wordmark|iconmark|combo",
    "description": "1-3 sentences on what the logo is visually",
    "dominant_colors_hex": ["#...", ...]
  },
  "typography": {
    "headings": {"family": "...", "weights_used": [...], "source": "google_fonts|self_hosted|default"},
    "body": {"family": "...", "weights_used": [...], "source": "..."},
    "wordmark_face_distinct": true|false,
    "font_load_urls": [...]
  },
  "colors_in_use": ["#...", ...],
  "imagery": {
    "stock_count": N,
    "authentic_count": N,
    "authentic_paths": [...],
    "notes": "..."
  },
  "favicon": {"url": "...", "local_path": "..."},
  "css_captured": "path to concatenated CSS file if pulled",
  "voice": {
    "tone": "...",
    "audience_signals": [...],
    "industry_vocabulary": [...]
  },
  "salvageable_equity_verdict": "PRESERVE+ELEVATE | PARTIAL ANCHOR | INVENT"
}
```

The verdict is mandatory:
- **PRESERVE+ELEVATE** — the existing brand has real equity (logo, palette, photography). Preserve tightly; elevate execution.
- **PARTIAL ANCHOR** — only the logo is salvageable; everything else is template. Use the logo + its colors as anchors; invent typography/motif carefully.
- **INVENT** — even the logo is weak. Invent from industry + audience + market.

**Most clients are PARTIAL ANCHOR.** The failure mode: treating them as INVENT and abandoning real equity.

### Hard rules

- The Brand Brain does NOT pick a new palette. It reports.
- The Brand Brain does NOT decide between typography options. It captures what exists.
- If the client's site has only red + blue + black + white + grey as actual brand colors, that's what the report says. It does NOT add copper "because builders like metallic" — that's the next brain's job.

---

## Stage 2 — Designer Brain (strategist + creative director)

**Single job:** decide what to preserve, what to elevate, and what to invent. Produce a concrete brand spec the Website Brain will execute.

### Inputs
- `brand-brain.json` from previous stage
- Strategy doc (positioning, audience, market)
- `gold-standard-playbook.md` (the pillars + cross-vertical patterns)
- `inspiration/inspiration-guide.md` (ProofPilot's gold-standard list)

### Procedure

1. **Apply the preserve/elevate/invent test** on each brand element. For each row:

   | Element | Current state | Equity? | Decision |
   |---------|---------------|---------|----------|
   | Logo | Custom combo mark, red+blue lightning bolt | Strong | **Preserve** — use as-is, make it the visual anchor |
   | Palette | Template-default black-on-grey | No | **Elevate** — anchor in the logo's actual colors, nothing else |
   | Typography | Squarespace Manrope+Poppins | Weak | **Preserve** the families (the client has some muscle memory), **elevate** weight + pairing |
   | Photography | 1 authentic fleet photo, rest stock | Partial | **Preserve** the fleet photo, replace stock with treated Recraft |
   | Motif | None | None | **Invent** from the logo — the bolt becomes THE motif |

2. **Lock the palette.** Critical rule: **do not add colors the logo doesn't have.** If the logo is red + blue + black + white, that's the palette plus one neutral grey. Period. Don't add copper because "builders like metallic." Don't add cream because "warmth." The brand's color DNA is already in the logo.

   Write the palette as a token table: 8 tokens max.

3. **Lock typography.** If the client already loads Manrope + Poppins on their site, keep those — the brand equity includes the typographic memory their existing customers have. Elevate only with weight (ExtraBold / Black) and pairing discipline, not by replacing the family.

   **Only replace typography when the current site uses truly generic system fonts** (Arial, Georgia, Times, default san-serif) AND the brand has enough equity to invent a new face.

4. **Pick ONE motif** from the logo or industry. Specify 6+ placement locations.

5. **Pick ONE signature section-transition.** Choose from: angled wedge, torn paper, halftone, sawtooth chevron, thin colored line with motif center, plain 1px divider with motif prefix. Apply consistently.

6. **Spec the button system** (primary / secondary / tertiary). Colors, radius, padding, font, icon, shadow, hover.

7. **Spec the icon system.** Custom 2-tone or single-tone, stroke weight, never lucide-as-is.

8. **Spec the photography strategy.** Authentic-first decision tree (see `design-strategist.md`).

9. **Spec the motion system.** Scroll reveals, stat counters, hover micro-interactions.

### Output: `design-spec.md`

Template exactly matches `design-strategist.md`'s "Output" section (11 numbered sections + implementation order + success test).

### Hard rules (the ones I got wrong on Prestige v2)

- **Don't add colors the logo doesn't have.** If the logo has 4 brand colors, the palette has 4-5 colors + neutrals. Not 8, not 10.
- **Don't invent metallics, accents, or "personality" colors** unless the client's brand genuinely lacks any equity and the Brand Brain verdict is INVENT.
- **Don't add typography the client doesn't already use** unless their current type is genuinely generic. Preserve > elevate > invent, in that order.
- **Every addition must be justified in 1 sentence** in the spec. If you can't justify it in 1 sentence, don't add it.

---

## Stage 3 — Website Brain (builder)

**Single job:** apply the Designer Brain's spec to a template selected from the WebsitePilot library. Produce running code.

### Inputs
- `design-spec.md` from previous stage
- Selected template (from WebsitePilot registry, scored against the brief)
- Copy from the Copywrite stage
- Images (authentic + Recraft-generated) from the Images stage

### Procedure

1. Clone the selected template to a scratch dir.
2. `npm install`.
3. Apply the design-spec.md in Implementation Order — priority 1 → 14:
   - Logo swap
   - Palette swap (CSS vars + tailwind config + legacy aliases)
   - Typography swap (Google Fonts import + tailwind fontFamily)
   - Hero background + overlay
   - Motif SVG component + 6+ placements
   - Button system rewrite
   - Section transitions
   - Motif-specific backgrounds (blueprint grid / etc — ONLY if the design spec specified it)
   - Service card treatment
   - Stat counters (if specified)
   - Eyebrow treatments
   - Custom icons
   - Favicon + OG
   - Motion polish

4. `npm run build` — must pass with zero TS errors.
5. Start dev server. Screenshot. Run the "remove the logo" success test.

### Hard rules

- The Website Brain does NOT re-decide the palette. It executes.
- The Website Brain does NOT invent additional motifs, sections, or treatments beyond the spec.
- If the Designer Brain's spec is ambiguous, ask for clarification — don't default to the template's existing styling (that's how you end up with template skin).
- Use legacy aliases in tailwind.config.ts to avoid breaking unchanged components when you swap the palette, but every NEW component must use the new tokens directly.

---

## Failure modes each brain prevents

| Failure mode | Which brain prevents it |
|--------------|-------------------------|
| "The demo used generic navy + gold instead of the client's logo colors." | Designer Brain's "don't add colors the logo doesn't have" rule |
| "The demo didn't pull the real logo." | Brand Brain's mandatory logo-download step |
| "The demo uses Exo 2 but their site uses Manrope." | Designer Brain's "preserve typography equity when present" rule |
| "The demo looks like a template with a name swap." | Designer Brain's motif + section-transition signature |
| "The brand extraction was a JSON blob the design stage ignored." | Three-stage separation forces the Designer Brain to read it |

---

## Running locally via Claude Code (no external models)

This entire pipeline runs in a single Claude Code conversation:

1. **Brand Brain** is Claude + Playwright + Python (for Pillow pixel analysis) + Bash (for asset downloads). No external LLM.
2. **Designer Brain** is Claude reasoning. No external LLM. No Opus vs Sonnet distinction.
3. **Website Brain** is Claude writing/editing TS/TSX/CSS. No external LLM.

Dispatched as three sequential subagents in the same session. Each reads the previous stage's output file. No API calls to Railway, no VPS SSH, no model swaps.

---

## Prestige v2 retro: what I did wrong

- Pulled the real logo (✓ Brand Brain)
- Analyzed logo pixel colors (✓ Brand Brain)
- Downloaded fleet photo (✓ Brand Brain)
- **Then picked navy + copper + cream for the palette** (✗ Designer Brain — introduced colors the logo didn't have)
- **Picked Exo 2 + Barlow Condensed + Inter Tight + JetBrains Mono** (✗ Designer Brain — replaced typography that had brand equity to preserve)
- **Added a blueprint grid motif** (✗ Designer Brain — invented a second motif when the bolt was the one committed motif)
- Website Brain executed all of the above faithfully, which made the demo feel "designed but not THEM"

## Prestige v3 correction: strict logo discipline

- Palette: red + blue + black + white + grey (logo-only)
- Typography: Manrope + Poppins (matches their current site)
- Motif: bolt only (from logo, one motif)
- Section transition: simple red bolt divider (not copper angled wedge)
- No blueprint grid, no copper, no cream, no navy
