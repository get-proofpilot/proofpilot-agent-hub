# QAPilot Examples

Quality-review outputs worth calibrating against. This is where we
keep the "is QAPilot too lenient?" evidence.

## What to capture

- **Gold PASS** — a page that actually shipped clean, with QAPilot's report.
- **Gold FAIL (Layer 1)** — a copy-paste contamination catch. Wrong city,
  wrong company name, placeholder text. These are the most valuable —
  one escaped = one client brand hit.
- **AI-detection catches** — specific examples where QAPilot flagged
  "comprehensive," "leverage," em dashes, semicolons, etc.
- **Inflated scores** — the ones where QAPilot said 85 but Jo Paula
  found 5 issues. These drive prompt iteration.

## Structure

```
examples/YYYY-MM-DD-<client>-<layer-focus>-<pass|fail>/
├── input.json       # {"content": "...", "keyword": "...", "client_name": "..."}
├── output.json      # QAPilot's 7-layer report
├── ground_truth.md  # what a human reviewer actually found
└── notes.md         # why this is gold / what needs to improve
```

## When to add one

Add a new example every time:
- QAPilot catches something Jo Paula would have missed (gold PASS pattern).
- QAPilot misses something Jo Paula catches (calibration drift).
- A new tell-word or failure mode emerges (prompt needs updating).
