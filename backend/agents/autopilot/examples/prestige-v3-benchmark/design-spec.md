# Prestige Electrical — Final Brand Spec (v3 synthesis)

**Inputs synthesized:**
- Prestige's actual logo: red-meets-blue circle with white lightning bolt
- Gold-standard design recon (`/tmp/prestige/design-recon.md`): B2B builder audience needs architectural/blueprint cues, not consumer mascots
- Gold-standard pillars: Cohesive + Detail + Dynamic

**Decision:** keep the logo's red+blue as signature equity BUT execute in an architectural/blueprint register, not consumer-playful. Commit to ONE signature section-transition move (angled copper wedge). One committed motif (bolt + blueprint grid). Extreme type weight contrast.

---

## Color System

| Token | Hex | Role |
|-------|-----|------|
| `navy-900` (primary anchor) | `#0F1E3C` | Header, hero bg, builder moat |
| `prestige-blue-700` | `#003B6E` | From logo — secondary anchor for depth |
| `electric-cyan-500` | `#0080A0` | From logo — links, small accents, icon highlights |
| `heat-red-600` | `#C01000` | From logo — signature sparingly: bolt mark, "Since 1998" underline, HVAC card accent |
| `copper-600` | `#B8763A` | Builder metallic — Builder Moat accent line, stat divider, single hero underline |
| `copper-400` | `#D69759` | Hover state for copper |
| `ink` | `#0A0A0A` | Body headings in light mode, wordmark black |
| `cream-50` (page bg) | `#F6F2EA` | Page background — warmer than white, blueprint-paper adjacent |
| `cream-100` | `#EFE7DA` | Alt section bg (stucco tone) |
| `border-subtle` | `#DDD6CA` | Form borders, dividers |

**Rules:**
- Navy owns 70% of color weight. Prestige-blue + electric-cyan fill 20%. Red + copper share the last 10%.
- Red is the SIGNATURE accent — never used for CTA bg. Used as: (1) the bolt mark color in one hero detail, (2) an underline on "Since 1998" in the hero H1, (3) the HVAC service card's 4px top-border, (4) a single stat divider in the Builder Moat. Four places, total.
- Copper is the BUILDER accent — only in the Builder Moat band + one stat row.

---

## Typography — extreme weight contrast

| Role | Family | Weight | Size hero |
|------|--------|--------|-----------|
| Display H1 | **Exo 2** | 900 (Black) | 80-96px, slight negative tracking (-0.02em) |
| Display H2 | Exo 2 | 800 | 48px |
| H3 | Exo 2 | 700 | 24px |
| Eyebrow | **Barlow Condensed** | 900 uppercase, 0.14em tracking | 14px |
| Stat numbers | **Barlow Condensed** | 900 | 72px (huge, blueprint-era feel) |
| Body | **Inter Tight** | 400-500 | 16px |
| Data (phone, ROC, schema) | **JetBrains Mono** | 500 | varies |

**Why this pairing:** Exo 2 Black echoes the wordmark's wide geometric weight. Barlow Condensed Black adds the condensed/personality variant for eyebrows + stats (the "extreme weight contrast" move the gold-standard sites use). Inter Tight (not regular Inter) for body gives a marginally more distinctive read.

**Google fonts import:**
```html
<link href="https://fonts.googleapis.com/css2?family=Exo+2:wght@700;800;900&family=Barlow+Condensed:wght@700;900&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
```

---

## The Committed Motif: Bolt + Blueprint

**Two motifs, one language.**

1. **The bolt** (from their logo) — electrical trade shorthand.
   - Extract the bolt as `src/assets/bolt.svg` (solid white fill)
   - Use 5+ times: hero eyebrow, process step numerals, service card corner, Builder Moat watermark, Primary button icon
2. **The blueprint grid** — builder trade shorthand.
   - A subtle 32×32 grid of 1px copper lines at 8% opacity as a repeating background pattern on the Builder Moat section ONLY. Sells the architect/builder frame.
   - Optional: apply as a low-opacity print-layer on the page bg (4%) — gives every page a faint blueprint-paper feel.

The bolt says "electrical." The grid says "built for builders." Together they tell the whole positioning story.

---

## Section-Transition Signature (THE one move)

**Pick:** angled copper wedge at every section boundary.

- Each section separator is a thin 1px horizontal line in `copper-600` that angles up 3° across the full width
- Or alternately: the next section's top edge is clipped at 3° (using `clip-path: polygon(0 3%, 100% 0, 100% 100%, 0 100%)`), revealing the cream bg beneath as a thin wedge
- Alternating direction (up-left, up-right) every other section

**Do not use:** plain `border-top`, centered fade dividers, or flat full-width solid bands. Those are template defaults.

---

## Button System

### Primary
- Bg: `navy-900`
- Text: white
- Radius: 6px (the recon's architect-mature move — NOT pill, NOT pointed)
- Padding: 14px 26px
- Font: Exo 2 800, uppercase, 0.08em tracking
- Icon: 14px bolt SVG on the left (white)
- Shadow: `0 4px 14px -4px rgba(15,30,60,0.35)`
- **Hover**: bg becomes `copper-600`, bolt stays white. Subtle translateY(-1px).

### Secondary (outline)
- Bg: transparent
- Border: 2px `navy-900`
- Text: `navy-900` Exo 2 700
- **Hover**: fill with `navy-900`, text + icon go white

### Phone CTA (mobile sticky)
- Bg: `heat-red-600`
- Text: white
- Same radius + shape
- Only place red appears as a fill.

---

## Icon System

Custom 2-tone line icons, NOT lucide defaults.

- Line weight: 2px
- Primary stroke: `navy-900`
- Accent stroke: `copper-600` on the emphasis detail (e.g. a single filament line in the residential-panel icon)
- Style: architectural, thin-line, precise. NOT rounded, NOT cartoon.
- Sizes: 24×24 badges, 32×32 service cards, 20×20 in process

Generate 3 custom service icons via Recraft `vector_illustration` + `bold_stroke` substyle:
1. Residential — stylized house outline with a small panel inside
2. Commercial — stylized building outline with a pendant light
3. HVAC — stylized rooftop with an airflow wave

Save to `src/assets/icons/`.

---

## Photography Strategy

**The hero image problem:** the v1 Recraft "electrician on panel" is fine but not OWNABLE. We have the real Prestige fleet photo. Use it.

- **Hero bg**: the Prestige fleet photo (`/tmp/prestige/assets/luxury-watch-ad.jpeg`) — 4 vans + Cybertruck + real Mesa storefront with Prestige signage. Apply a `linear-gradient(95deg, rgba(15,30,60,0.92) 0%, rgba(15,30,60,0.68) 55%, rgba(15,30,60,0.35) 100%)` overlay so the left 60% hosts the H1 copy, right 40% shows fleet through the overlay. Tag line "Our actual Mesa fleet" small caption lower-right.
- **Alt: Builder Moat image**: use the same fleet photo, but this time as a full-bleed right-column image next to the builder copy (no overlay). This is the authentic "we're real" proof.
- **Service card images**: keep Recraft v1, apply CSS duotone treatment to tie to palette:
  ```css
  filter: saturate(0) contrast(1.1);
  background-image: linear-gradient(135deg, #0F1E3C, #003B6E);
  background-blend-mode: lighten;
  ```
  Tints all 3 service photos blue. Instant cohesion.
- **Service area aerial**: fine as-is. Add a thin blueprint-grid overlay in copper at 6% opacity.
- **Favicon**: replace with 32×32 bolt mark only (no wordmark). Use Recraft or extract from logo.

---

## Motion System

- **Scroll reveals**: fade + 8px translate on section entry, 0.4s ease-out, 80ms stagger
- **Hero H1 reveal**: words stagger 60ms on page load, red underline on "Since 1998" draws last (0.6s delay)
- **Stat counters**: Barlow Black numerals count up on scroll-into-view, 900ms, ease-out-cubic
- **Primary button hover**: 200ms bg transition to copper, 150ms translateY, subtle bolt icon rotate(-8deg)
- **Service card hover**: translateY(-4px), card corner bolt fills from outline to solid, shadow deepens
- **Builder Moat background**: blueprint grid has a subtle 40s parallax on scroll — 4% depth, barely perceptible

Honor `prefers-reduced-motion: reduce`.

---

## Implementation Order (for the re-customize subagent)

Priority-ordered so if time runs short, the most impactful changes land first:

1. **Logo swap** — replace "PRESTIGE" text with actual logo image in Header + Footer. Use `/tmp/prestige/assets/logo-original.png` (copy to `public/images/prestige/logo.png`).
2. **Palette swap** — update all design tokens in `src/index.css` + `tailwind.config.ts` to the new palette above. Remove state48 leftovers.
3. **Typography swap** — update `index.html` to load Exo 2 Black + Barlow Condensed Black + Inter Tight + JetBrains Mono. Update `tailwind.config.ts` fontFamily to reflect.
4. **Hero bg** — swap the Recraft electrician photo for the Prestige fleet photo with the navy gradient overlay. Move the electrician photo to Process section or drop.
5. **Bolt SVG** — extract bolt from logo (or redraw clean SVG). Add to `src/assets/bolt.svg`. Embed in: hero eyebrow, process steps, service card corners, Builder Moat watermark, primary button.
6. **Button component** — rewrite the primary/secondary Button to the new spec. Replace all `<Button>` usages on the page to use the new styles.
7. **Section transitions** — add the angled copper wedge to section breaks. Easiest: a `::after` pseudo-element on each section with clip-path + copper border-top.
8. **Blueprint grid in Builder Moat** — add as a repeating CSS background pattern on that section.
9. **Service card treatment** — add 4px top border (blue for residential, red for HVAC, copper for commercial); duotone filter on images; bolt corner icon.
10. **Stat counters** — Barlow Condensed Black styling + count-up animation (use `react-countup` or a simple IntersectionObserver).
11. **Eyebrow treatment** — every section gets "BOLT-ICON + UPPERCASE BARLOW" eyebrow.
12. **Custom service icons** — replace lucide icons with the 3 custom ones (generate via Recraft in a separate step, or as SVG paths inline).
13. **Favicon + OG** — replace defaults.
14. **Motion polish** — scroll reveals, hover states, counters.

If #1-9 land, the site already feels custom. 10-14 are polish.

---

## Success Test

Remove the logo from the new header. Can a visitor still tell:
- **Electrician?** YES — lightning bolt appears in eyebrow, process numerals, service cards, button, Builder Moat watermark.
- **HVAC too?** YES — red/blue signature (heating half in red, cooling/electric in blue) preserved in palette accents + service card 4px borders.
- **Arizona + stucco-textured small business?** YES — cream/stucco tones, real Mesa fleet/storefront photo in hero.
- **For builders, not homeowners only?** YES — navy + copper, blueprint grid, architectural type weights, Builder Moat band with blueprint pattern.
- **Premium + trusted, not a template?** YES — extreme weight contrast, angled copper transitions, custom 2-tone icons, authentic fleet photo, Barlow stat numerals.

If v3 passes all 5 checks, we've hit the gold-standard bar.
