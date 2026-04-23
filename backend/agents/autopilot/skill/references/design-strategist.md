# Design Strategist — Stage 2.5 of AutoPilot

> A new pipeline stage between Strategy and Copywrite/Design. Takes the Brand Archaeology output + the Strategy doc + the gold-standard playbook and produces a concrete brand spec that the Design stage will execute against.

## Why this exists

Without this stage, AutoPilot jumps from "we did some brand extraction and content strategy" straight to "render HTML." The result is templates with the client's name swapped in — not custom-designed sites.

The Design Strategist's job is to make the deliberate brand decisions a human designer would make:
- What's the palette and why?
- What's the typography and why?
- What's the one visual motif this site will commit to?
- What's the one signature section-transition move?
- How do icons, buttons, photography, and section treatments express the brand personality?

Output is a `brand-spec-v2.md` document that downstream Design + Image generation stages consume.

## Inputs required

1. `brand-archaeology-v2.json` from the previous stage
2. The Strategy doc (StrategyPilot output) — establishes positioning, audience, market
3. `gold-standard-playbook.md` (sibling doc) — the design pillars + cross-vertical patterns
4. Optional: 3-5 competitor URLs to inspect for vertical context

## Procedure

### 1. Synthesize the brand thesis (1 paragraph)

Answer: "If someone removed the logo from this site, what should they still be able to tell?"

Write the answer in 3-5 specific bullets. Examples (Prestige):
- This is an electrician (lightning bolt motif)
- This does HVAC too (red+blue split signals heating + cooling duality)
- This is Arizona (warm neutrals, stucco tones, real fleet/storefront photo)
- This is for builders + homeowners (architectural type, not consumer-playful)
- Premium + trusted (extreme weight contrast, custom icons, authentic photography)

These bullets are your design north star.

### 2. Decide the palette

Rules:
- **Anchor in real brand equity if it exists.** If the logo has 2-3 ownable colors, those become the palette's spine. Don't invent unnecessarily.
- **For verticals, avoid the safe template colors.** Electrician = not generic yellow/red. Plumbing = not just blue. Pick something distinctive (Volt Vikings chose purple, Doggone chose burgundy + gold).
- **Always add one architectural / "trust metallic" accent for B2B-leaning brands** — copper, brass, bronze, or gunmetal. This signals craftsmanship for builder audiences.
- **Cap at 8 tokens total**: 2 primary, 2 accent, 1-2 neutrals, 2 functional (success / border).

Output as a table with hex + token name + role.

### 3. Decide typography (extreme weight contrast)

Rules:
- **Display face** echoes brand personality. If wordmark is geometric-bold, pair with Exo 2 / Space Grotesk / Archivo Black. If wordmark is humanist, use Manrope / Inter Display.
- **Body face** is workhorse modern sans: Inter, Inter Tight, Manrope.
- **Always add a third condensed face** (Barlow Condensed / Oswald / Bebas Neue) for stat numbers + eyebrows. The condensed/regular contrast is what gold-standard sites use to feel "designed."
- **Use mono on data** (phone numbers, ROC numbers) — JetBrains Mono / IBM Plex Mono.

Hero H1 should be 80-96px on desktop with weight 800-900. Body 16-17px regular. The contrast does the work.

### 4. Pick THE motif (one, not three)

Look at the client's logo + industry. Pick ONE visual element to commit to:
- Logo has a lightning bolt? Make the bolt the motif (Prestige).
- Plumber? A pipe joint, water drop, wrench cross.
- Roofer? A roof angle, shingle pattern, drip edge.
- Builder? A blueprint grid, level/tape-measure, joist pattern.
- HVAC? Airflow waves, vent geometry, thermostat dial.

The motif appears in:
1. Hero eyebrow (small)
2. Section eyebrows (small, sometimes colored)
3. Process-step numerals (faint background)
4. Service card corners (matching card's accent color)
5. CTA button icon (left of label)
6. Featured section background watermark (large, low opacity)

Six placements minimum. Otherwise it's not a motif, it's decoration.

### 5. Pick ONE signature section-transition

Reject: plain `border-top`, centered fade dividers, flat full-width solid bands. Those are template defaults.

Choose one:
- **Angled wedge** — diagonal 3-5° clip-path on section top (mature, architectural)
- **Torn paper** — soft jagged edge (warmer brands)
- **Halftone gradient** — dot pattern fade (consumer brands)
- **Sawtooth chevron** — repeated triangular notches (industrial brands)

Apply consistently across every major section break. Alternate direction for visual rhythm.

### 6. Define the button system

Three button types minimum:
- **Primary** — filled, brand-anchor color, has motif icon, distinctive radius (usually 6-10px, not pill, not sharp), elevated shadow tinted with brand color (not gray).
- **Secondary** — outline, same shape, hover fills.
- **Tertiary / phone CTA** — distinctive treatment for the one most-important action.

For each: bg, text color, radius, padding, font + weight + tracking, icon, shadow, hover state. Spec it concretely so the Design stage can implement.

### 7. Define the icon system

- Custom SVGs preferred over lucide / shadcn defaults
- Two-tone icons (primary stroke + accent stroke) signal "designed"
- Stroke weight consistent (typically 2px)
- Generate via Recraft `vector_illustration / bold_stroke` or hand-write SVG paths

For service cards specifically, never reuse generic lucide icons. Generate ONE custom icon per service lane.

### 8. Photography strategy

- **Always preserve and use authentic client photos** (fleet, team, storefront, projects). Even one is better than ten Recraft generations.
- **Apply consistent treatment to all generated/stock imagery** — duotone overlay, color tint, consistent crop ratio. This is what makes photography feel "designed" instead of "dropped in."
- **Hero photo decision tree**:
  1. Authentic on-brand photo exists? Use it with a brand-color gradient overlay.
  2. No authentic photo? Use Recraft with a moodboard prompt + post-process with duotone.
  3. Never use a raw stock image on hero.

### 9. Define the motion system

Restrained, purposeful:
- Scroll reveals on section entry (fade + 8px translate)
- Stat counters animate on scroll-into-view
- Primary button hover (translateY + bg shift)
- Service card hover (lift + shadow + icon color shift)
- Hero text reveal on load (word stagger)

Honor `prefers-reduced-motion: reduce`.

## Output: `brand-spec-v2.md`

Document structure (mirror this verbatim):

1. **Brand Thesis** — the "remove the logo" test answer
2. **Color System** — table with 8 tokens
3. **Typography** — table with 5 roles + Google Fonts import line
4. **The Committed Motif** — what + 6+ placements
5. **Section-Transition Signature** — pick one + implementation
6. **Button System** — primary / secondary / tertiary specs
7. **Icon System** — generation approach + 3 service icons
8. **Photography Strategy** — authentic-first decision tree + treatment rules
9. **Motion System** — list of micro-interactions
10. **Implementation Order** — priority-ordered list of changes the Design stage will execute (1-14 typical)
11. **Success Test** — the 5-question "remove the logo" checklist

## Hand-off rules

- Brand spec ALWAYS comes from real brand archaeology, not from the template's defaults.
- The Design stage reads `brand-spec-v2.md` and executes the Implementation Order in priority order.
- The Image stage reads section 8 (Photography Strategy) for moodboard + duotone treatment instructions.
- The QA stage reads section 11 (Success Test) for the explicit pass/fail rubric.

If the spec doesn't exist or isn't this format, the downstream stages will produce a generic template skin. That's the failure mode this stage prevents.
