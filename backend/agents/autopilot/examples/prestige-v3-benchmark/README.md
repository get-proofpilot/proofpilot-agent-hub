# Prestige Electrical v3 — Canonical Design Benchmark

**Dated:** 2026-04-23
**Template used:** `state48-authority-blue` (from WebsitePilot library)
**Verdict:** the bar for every future AutoPilot design run.

---

## Why this is the benchmark

After two failed iterations (v1 = shadcn defaults with state48 template colors; v2 = over-invented navy + copper + cream palette with Exo 2 + Barlow Condensed typography), v3 passed the user review with: *"the branding and overall design look way more dialed in. This is what we want the strategy and level of design and branding to be at moving forward. The branding agent did a good job making it cohesive, feel custom, feel unique."*

The lock: **strict discipline on the client's actual brand equity.** Colors from the logo, typography from their current site, motif from the logo, with deliberate elevation only where there's no existing signal.

---

## What's in this folder

- `hero-screenshot.png` — the v3 hero render (1440×900 viewport)
- `design-spec.md` — the v3 brand spec that drove the build (Designer Brain output)
- `brand-brain.json` — the v3 brand archaeology (Brand Brain output)

---

## The v3 discipline (copy this into every future design spec)

### Palette — ONLY what's in the logo + minimal neutrals

| Token | Hex | Source |
|-------|-----|--------|
| `red-600` | `#C01000` | Logo (heating half) |
| `red-700` | `#A00E00` | Depth variant of logo red |
| `blue-500` | `#0080A0` | Logo (cooling/electric half) |
| `blue-700` | `#003060` | Depth variant of logo blue |
| `black` | `#0A0A0A` | Wordmark ink |
| `white` | `#FFFFFF` | Page surface |
| `grey-50 → 700` | `#F8F8F7 → #374151` | Neutrals only |

No copper. No navy drift. No cream. No invented accents.

### Typography — Match what the client's current site already loads

| Role | Family | Weights |
|------|--------|---------|
| Display / H1-H2 | Manrope | 700, 800 |
| H3 / eyebrows | Manrope | 600, 700 |
| Body | Poppins | 400, 500 |

Squarespace template fonts? Keep them. Brand memory > novelty.

Replace typography ONLY when the current site uses truly generic system fonts (Arial, Times, default sans) AND brand equity justifies new identity.

### Motif — One, from the logo

**Lightning bolt.** From the logo. Used 15+ times:
- Hero eyebrow
- Service card corners (color-matched to card accent)
- Primary button (white bolt)
- Footer watermark (low-opacity white)
- Process step numerals
- Every section eyebrow (small red bolt prefix)

No second motif. No blueprint grid. No competing patterns.

### Section transitions — Simple and consistent

- 1px `grey-200` divider OR small centered bolt accent
- Hero → trust bar: subtle drop
- CTA band: 2px red top border as accent, nothing more

No angled copper wedges. No sawtooth chevrons. Simple is the signature.

### Photography strategy

- **Hero:** Real Prestige fleet photo at their actual Mesa storefront. Pure black gradient overlay (`linear-gradient(to right, rgba(10,10,10,0.88) 0%, rgba(10,10,10,0.70) 55%, rgba(10,10,10,0.35) 100%)`).
- **Service cards:** Recraft-generated images with duotone filter to tie them to the blue/grey/red palette.
- **Builder Moat:** Same authentic fleet photo paired with stat row. No stock.

Authentic first. Treated stock second. Raw stock never.

### Buttons

- Primary: `bg-black` + white text + white bolt + `rounded-md` (6px) + hover → `bg-blue-500 #0080A0`
- Secondary: transparent + 2px white border + white text
- No copper. No gradient. No fill changes beyond the blue hover.

### Shadows

Blue-tinted (`rgba(0,48,96,0.2)`), not grey. Tints cards to the brand's blue.

---

## The Three Brains used on this run

1. **Brand Brain** (Playwright + Python Pillow) pulled the logo, analyzed pixel colors, downloaded the authentic fleet photo, captured Manrope/Poppins from Squarespace. Verdict: **PARTIAL ANCHOR** — logo is strong, everything else is template default.

2. **Designer Brain** applied the Three-Brain discipline:
   - Preserve the logo (perfectly — no wordmark rewrite)
   - Preserve the typography families (Manrope + Poppins)
   - Elevate typography by committing to extreme-weight contrast (Manrope 800 hero at 96px, Poppins 400 body)
   - Elevate palette by picking strict logo-derived tokens (not invented metallics)
   - Invent: the one committed motif (bolt) and one signature section treatment (simple grey line + bolt prefix)

3. **Website Brain** cloned `state48-authority-blue`, applied the spec in priority order, purged every state48 token, reached build-passing with zero TS errors.

---

## Success test verdict (from `gold-standard-playbook.md`)

Remove the logo. Can a visitor still tell:

- **Electrician?** ✓ Lightning bolt visible 15+ times
- **HVAC too?** ✓ Red + blue duality in accents (red service card border on HVAC, blue on Residential)
- **Arizona / real shop?** ✓ Authentic Mesa storefront fleet photo in hero
- **For builders + homeowners?** ✓ Manrope ExtraBold authority type, "Builder-Preferred" positioning
- **Premium, not template?** ✓ Extreme type weight contrast, cohesive logo palette, authentic photography

All five checks pass.

---

## What future AutoPilot runs should reference

When building any new demo site:

1. Read `../../skill/references/three-brain-architecture.md` first
2. Read `../../skill/references/gold-standard-playbook.md`
3. Read `../../skill/references/inspiration/inspiration-guide.md`
4. Read this `design-spec.md` as a concrete example of what a Designer Brain output should look like
5. Read this `brand-brain.json` as a concrete example of what a Brand Brain output should look like

**If at any point the design starts adding invented colors, invented motifs, or replacing brand equity without cause, stop and re-read this example.** v3 worked because it didn't do those things.
