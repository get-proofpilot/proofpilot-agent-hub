# AutoPilot Examples

Completed pages, brand extractions, and QA-driven revision rounds
worth calibrating against.

## What to capture

- **Shipped pages** — pages that Jo Paula approved and went live. The
  gold standard for "AutoPilot is doing its job."
- **Brand extractions that nailed it** — `design_system.json` outputs
  that produced pages matching the client's live site. Tag the source
  site URL.
- **Brand extractions that drifted** — outputs that produced generic
  design. Useful for tuning brand_extractor.py.
- **Revision round stories** — QA rejected round 1, round 2 recovered.
  Capture all three stages (original, directives, revised) so the
  learning loop has data.
- **Image-gen successes and regressions** — especially for Nano Banana
  (real brand logos) vs Recraft (generic scenes). Know which route is
  winning on which trades.

## Structure

```
examples/YYYY-MM-DD-<client-slug>-<page-type>-<outcome>/
├── input.json            # the job request
├── brand.json            # extracted design system
├── strategy.md           # stage 2 output
├── copywrite.md          # stage 3 output
├── design.html           # stage 4 output
├── images/               # stage 5 outputs
├── qa.json               # stage 6 report
├── revision_rounds/      # if there were any, keep each round
└── notes.md              # outcome: shipped / rejected / lessons
```

## Calibration questions

For each example, answer:
- Does the page look like it belongs on the client's site? (brand match)
- Is the voice authentically the client's? (voice match)
- Are the images trade-accurate? (image quality)
- Did QA catch what it should have? (QA calibration)
- How many revision rounds? (pipeline efficiency)
