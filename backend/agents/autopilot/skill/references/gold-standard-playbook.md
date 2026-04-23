# Gold-Standard Design Playbook

> Reference for every AutoPilot + WebsitePilot design run. These are the patterns observed across ProofPilot's home-service design heroes (Hook Agency, 180 Sites, Be The Anomaly, Get Local Leads) and the sites we benchmark against (Volt Vikings, Bears Plumbing, Doggone Good H&C, Tiger Roofing, Owl Roofing, Genz Ryan, Smock HVAC).

## The Three Pillars

Every site ProofPilot ships should hit all three.

### 1. Cohesive

Unified visual system. Everything feels like it belongs.

- **Color application is intentional.** Primary for key elements. Secondary for accents. Clear hierarchy. Consider blocking, overlays, gradients, and how color directs attention to CTAs.
- **Typography reflects personality.** Pairing is deliberate. Weights express hierarchy. The combination feels intentional.
- **Photos are treated, not just dropped in.** Color overlays, consistent crops, custom masks, frames that integrate with the brand's visual identity.
- **Brand personality is load-bearing.** Every element reinforces who the company is. The "remove the logo" test: if you stripped the logo, the design itself should still communicate the brand's personality, industry, and values.

### 2. Detail

Custom elements that make the site feel designed, not assembled.

- **Custom icons.** No generic icon packs used as-is. Icons match brand style, palette, and visual language. Feel like they were made for this company.
- **Patterns, textures, and background elements.** Subtle textures, geometric patterns, line work, gradients, shapes, industry-specific motifs. Complement content without competing.
- **Borders, dividers, and section treatments.** How sections separate matters. Custom dividers, angled breaks, overlapping elements, unique borders. Rounded vs sharp edges are consistent and intentional.
- **Buttons and interactive elements.** Designed, not default. Shape, padding, border radius, shadow, hover states follow a system.

### 3. Dynamic

Movement and rhythm. The site feels alive, not static.

- **Section layout and flow.** Each section is composed thoughtfully. Rhythm between text and visuals. Eye-movement is guided, not random.
- **Visual rhythm.** Alternate between section types. Vary pacing. Use whitespace strategically. Peaks and valleys keep visitors engaged.
- **Movement and animation.** Subtle scroll animations, hover effects, micro-interactions. Purposeful and restrained. Energy without distraction.

## The Cross-Site Patterns We Repeatedly See

From the recon study:

### 1. Committed metaphor drives everything

Each gold-standard site picks ONE character / object / concept and carries it EVERYWHERE. Mascot + icons + copy voice + section ornamentation. The mascot isn't a logo; it's a 500px cutout in the hero, a faded watermark in section backgrounds, a reappearing character motif.

**For B2B builder-oriented brands, avoid cartoon mascots.** Use architectural/craftsmanship shorthand instead — blueprint grids, wire/pipe schematics, section cutaways, trade seals.

### 2. One signature section-transition move

Never plain `border-top` between sections. The single repeating transition detail is what reads as "designed" instead of "template."

Options:
- **Angled copper wedge** (architectural, mature) — Prestige Electrical demo
- **Torn paper edge** (warmer, hand-made feel) — Bears Plumbing
- **Halftone dot gradient** (consumer, playful) — Doggone
- **Sawtooth chevrons** (industrial, bold) — Volt Vikings

Pick one. Apply consistently.

### 3. Unusual primary color for the vertical

Safe colors = template. Distinctive primary = brand.

- Volt Vikings chose purple for an electrician (not yellow/red).
- Doggone chose burgundy + gold for HVAC (not blue/red).
- Tiger Roofing leaned orange + charcoal (not roofing-red).

When possible, anchor in the client's logo colors — but if their logo is weak, DO NOT default to the safe palette for the vertical.

### 4. Extreme type weight contrast (900 vs 400)

No serifs, no default Inter. Display type goes huge (72-96px) with weight 800-900. Body stays 400-500. The contrast does visual work.

Often mix outlined + filled variants in the same heading (Volt Vikings signature). Always pair a condensed/personality face with a workhorse body face.

### 5. Authentic photography beats stock every time

Hook Agency and 180 Sites consistently feature real client photography — fleet shots, crew shots, project galleries. When generated/stock photography is unavoidable, they treat it with brand color overlays to tie it into the palette.

**Every AutoPilot run must download and use the client's authentic photos if they exist.** One fleet shot beats ten perfect Recraft images.

## The Anti-Patterns to Avoid

- **Template skin with brand colors swapped in.** The classic failure. Your output looks like every other home-service template.
- **Using shadcn `Button` with default styling.** Gold-standard sites always customize button shape, padding, radius, shadow, hover state.
- **Using lucide icons as-is.** If you must use lucide, at minimum override color and stroke width. Prefer custom SVG icons.
- **Gray shadows.** Card shadows should be tinted with the brand-anchor color (blue shadow for blue brands, copper shadow for brass brands). Gray shadows look template.
- **Cold pure-white backgrounds.** Warm neutrals (F6F2EA, FBF9F4) signal craft. Pure white (#FFFFFF) signals template.
- **Stock Unsplash hero on a home-service site.** The single biggest "this is a template" signal.
- **Every section has a centered eyebrow → centered H2 → centered body.** Vary composition. Mix left-aligned, split-column, offset asymmetric.
- **Zero motion.** At minimum: scroll reveals on sections, hover lifts on cards, count-up on stats. Motion communicates "alive."

## Industry-Motif Playbook

When picking the committed motif (per the Design Strategist stage), here's the cross-vertical cheat sheet:

| Trade | Motif options | Example placement |
|-------|--------------|-------------------|
| Electrician | Lightning bolt, wire/plug, electrical panel outline, current lines | Button icon, section watermark, process numerals |
| Plumbing | Pipe joint, water drop, wrench cross | Section divider, card corner, eyebrow prefix |
| HVAC | Airflow waves, thermostat dial, vent geometry | Subtle header bg, service card pattern |
| Roofing | Shingle pattern, drip-edge silhouette, roof angle | Section divider (sawtooth), card top, hero watermark |
| Landscaping | Leaf, branching vine, grass blade, property line | Section dividers, subtle bg patterns |
| Concrete | Aggregate pattern, trowel sweep, grid of squares | Stat row dividers, builder card bg |
| Builder / GC | Blueprint grid, level, T-square, joist pattern | Builder Moat bg, spec page watermark |
| Pressure Washing | Water splash, spray jet, before-after wipe | Process step bg, gallery card mask |
| Junk Removal | Dumpster silhouette, truck shape, load line | Service card bg, process numerals |
| Pool | Wave, tile pattern, filter swirl | Hero bg overlay, service card corner |
| Dog grooming | Paw, bone, collar, breed silhouette | Consumer-playful OK here — full mascot allowed |

For businesses bridging multiple trades (electrical + HVAC, roofing + gutters), combine TWO motifs — one primary, one secondary. Prestige Electrical uses bolt (primary) + blueprint grid (secondary for builder credibility).

## Template Upgrade Recipe

When starting from a WebsitePilot template (state48glass, keystonerestoration, etc.), these are the minimum 5 changes to stop it feeling like a template:

1. **Replace text wordmarks with the actual logo image.** Header + footer.
2. **Swap palette in `src/index.css` + `tailwind.config.ts` with a logo-anchored system.** All template defaults go.
3. **Load the typography trio** (display + condensed + body + mono) via Google Fonts. Update tailwind fontFamily.
4. **Add the committed motif as an SVG component used 5+ places.**
5. **Add the signature section-transition class used on every section.**

If time permits:
6. Custom service icons (not lucide).
7. Blue-tinted (or brand-tinted) card shadows replacing gray.
8. Authentic client photo in hero or builder-credibility section.
9. Scroll reveals + hover interactions.
10. Custom button component replacing shadcn defaults.

## Success Test (for every design review)

Ask these 5 questions. All answers should be "yes":

1. **Remove the logo** — can a visitor still tell what the business does, who it serves, and what vibe it has?
2. **Next to 5 template sites in the same vertical** — does this one stand out as clearly more designed?
3. **Print a black-and-white version** — does the information hierarchy still read?
4. **Scroll at 50% speed** — do the section transitions feel rhythmic, not mechanical?
5. **Show it to the client's actual target customer** — would they describe this as "designed for" their company, or "a website that happens to be for" their company?

If any answer is "no," the site is template-level. Go back to the Design Strategist stage.
