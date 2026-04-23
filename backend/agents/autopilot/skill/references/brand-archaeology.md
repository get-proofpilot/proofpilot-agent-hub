# Brand Archaeology — Stage 1.5 of AutoPilot

> Aggressive brand-asset extraction from a client's live site. This is what `brand_extractor.py` should do but doesn't yet — when running AutoPilot via the skill (locally in Claude Code), follow this procedure manually.

## Why this exists

Default brand extraction is HTML-scraping only. It returns CSS variable names, font families, and image URLs without ever downloading or analyzing the actual assets. The result: AutoPilot demos look "generic" because they treat the brand as a JSON blob to override, not real equity to preserve and elevate.

The user's observed failure mode (April 2026): "Didn't pull the client's brand. Didn't pull their logo. Doesn't look custom. Doesn't really have their colors. Looks pretty generic."

This stage fixes that by **downloading the actual logo, analyzing its dominant colors, and pulling every ownable asset** so the Design Strategist (next stage) can build a real brand system from real signals.

## Procedure

### 1. Download the logo

Use Playwright to load the homepage and find the header `<img>`:

```js
const logoUrl = await page.evaluate(() => {
  const candidates = Array.from(document.querySelectorAll('header img, nav img, [class*="logo" i] img, a[href="/"] img'));
  const logo = candidates.find(img => /logo|brand|prestige|company/i.test(img.alt + img.src + img.className));
  return logo?.src;
});
```

For Squarespace clients, the logo URL is typically a CDN PNG like `https://images.squarespace-cdn.com/.../<Company>+Logo.png?format=1500w` — try `?format=1500w` for the high-res version.

Then `curl -L -o /tmp/<client>/assets/logo-original.png "<logo_url>"` and verify with `file`.

### 2. Analyze the logo's dominant colors

Use Python + Pillow:

```python
from PIL import Image
from collections import Counter

img = Image.open('/tmp/<client>/assets/logo-original.png').convert('RGBA')
pixels = list(img.getdata())
opaque = [(r,g,b) for r,g,b,a in pixels if a > 200]

# Quantize each channel to nearest 16 to bucket similar colors
def quantize(c): return (c >> 4) << 4
buckets = Counter((quantize(r), quantize(g), quantize(b)) for r,g,b in opaque)

top = buckets.most_common(40)
total = sum(c for _,c in buckets.items())
palette = [
  {"hex": f"#{r:02X}{g:02X}{b:02X}", "rgb":[r,g,b], "count":c, "pct":round(c*100/total,2)}
  for (r,g,b),c in top
]
```

Save to `/tmp/<client>/assets/logo-palette.json`. The top 3-5 non-black/non-white buckets are the brand's true colors.

If Pillow isn't available: `python3 -m pip install Pillow --user --quiet`. ImageMagick fallback: `magick logo.png -resize 1x1! -format "%[pixel:u]" info:` for a single average.

### 3. Capture typography (including @font-face)

```js
await page.evaluate(() => {
  const computed = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, fontSize: cs.fontSize };
  };
  return {
    h1: computed('h1'),
    h2: computed('h2'),
    body: computed('body'),
    button: computed('button, a[class*="btn" i], a[class*="button" i]'),
    loadedFonts: Array.from(document.fonts).map(f => ({family: f.family, weight: f.weight, status: f.status})),
    fontLinks: Array.from(document.querySelectorAll('link[rel="stylesheet"][href*="font" i], link[rel="preload"][as="font"]')).map(l => l.href),
  };
});
```

If the wordmark in the logo uses a different display face than the page CSS (it usually does), note that — the wordmark face is part of the brand and may need to be approximated in CSS.

### 4. Capture all imagery, classify

```js
const allImages = await page.evaluate(() =>
  Array.from(document.querySelectorAll('img')).map(img => ({
    src: img.src,
    alt: img.alt,
    width: img.naturalWidth || img.width,
    height: img.naturalHeight || img.height,
  }))
);
```

For each `src`, classify:
- Logo (matches `/logo|brand/i`)
- Stock (host matches `unsplash.com`, `squarespace-cdn.com` placeholder paths like `unsplash-image-*`)
- Authentic (host = client's domain, or a custom CDN with non-stock filename)

Download every authentic asset to `/tmp/<client>/assets/`. Look especially for:
- Fleet / truck / van photos
- Storefront / building exterior
- Team / crew photos
- Project galleries / before-and-after
- Custom hero illustrations

These are the OWNABLE assets — gold for the demo. Generic Recraft images can never beat a real fleet shot at the actual storefront.

### 5. Pull favicon + OG image

```js
await page.evaluate(() => ({
  favicon: document.querySelector('link[rel*="icon"]')?.href,
  appleTouch: document.querySelector('link[rel="apple-touch-icon"]')?.href,
  ogImage: document.querySelector('meta[property="og:image"]')?.content,
}));
```

Download all of them. Often these reveal a stripped logo-only mark suitable for the new favicon.

### 6. Voice signals

Read `/`, `/about`, `/contact`. Capture:
- Tone (formal / casual / technical / friendly / aggressive)
- Audience signals — does copy address homeowners, GCs, builders, property managers, all?
- Trade-specific vocabulary worth preserving (e.g. "panel upgrade", "tract communities", "rough-in", "trim-out")

## Output: `brand-archaeology-v2.json`

Required keys:

```json
{
  "logo": {
    "source_url": "...",
    "local_path": "...",
    "composition": "wordmark|iconmark|combo",
    "description": "1-3 sentences on what the logo IS visually",
    "dominant_colors_hex": ["#...", ...]
  },
  "typography": {
    "headings": {"family": "...", "weights_used": [...], "source": "..."},
    "body": {"family": "...", "weights_used": [...], "source": "..."},
    "wordmark_face_distinct": true|false,
    "source_urls": [...]
  },
  "colors_in_use": ["#...", ...],
  "imagery": {
    "stock_count": N,
    "authentic_count": N,
    "authentic_paths": ["/tmp/<client>/assets/..."],
    "notes": "..."
  },
  "favicon": {"url": "...", "local_path": "..."},
  "voice": {
    "tone": "...",
    "audience_signals": [...],
    "industry_vocabulary": [...]
  },
  "salvageable_equity": "1-paragraph verdict — what to preserve, what to invent"
}
```

## Verdict format

End every brand archaeology with one of these three calls:

- **PRESERVE + ELEVATE** — the existing brand has real equity (logo, color story, photography). Build the new site around it.
- **PARTIAL ANCHOR** — only the logo is salvageable; everything else is template. Use the logo + colors as anchors, invent typography, photography, motif.
- **INVENT** — even the logo is weak. The Design Strategist needs to invent the brand from the industry + audience + market with no existing equity.

Most ProofPilot clients fall in PARTIAL ANCHOR. The mistake is treating them as INVENT and ignoring real equity.
