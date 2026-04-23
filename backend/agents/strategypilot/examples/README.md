# StrategyPilot Examples

Strategy documents worth calibrating against. These are the anchor
points for "what does a good P1 list look like," "how deep should a
page-system recommendation go," and "what's a realistic ROI scenario."

## What to capture

- **Executed strategies** — docs the team actually built against for
  a quarter or more. Tag which recommendations landed and which got
  dropped.
- **Tight P1 lists** — good ones name 8-12 pages with URL, keyword,
  volume, category letter, and why. Bad ones list 40 pages with no
  prioritization.
- **Competitive gap tables** — specific competitor URLs and what
  page systems they have that the client doesn't.
- **ROI misses** — scenarios that proved wrong within 90 days. Keep
  with a note on what the real trajectory looked like.

## Structure

```
examples/YYYY-MM-DD-<client-slug>-<outcome>/
├── input.json       # {"domain": "...", "service": "...", "location": "..."}
├── output.md        # raw markdown
├── output.docx      # branded final artifact (optional)
├── executed.md      # 90/180-day retrospective — what we built vs recommended
└── notes.md         # what held up, what didn't, prompt-level takeaways
```

## Calibration targets

- A P1 list should be ≤ 12 pages. If StrategyPilot returns more, the
  prompt or the prioritization prompt has drifted.
- Each P1 page recommendation cites a specific search volume or
  competitor page (no hand-wavy justifications).
- ROI ranges, not point estimates.
