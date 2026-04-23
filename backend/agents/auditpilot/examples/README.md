# AuditPilot Examples

Sales audit documents worth calibrating against. These anchor what
"good" looks like when the output is a sales tool, not a technical report.

## What to capture

- **Closed-deal audits** — the actual .docx that led to a signed
  contract. Especially valuable if Matthew remembers which section hit.
- **Pain section exemplars** — the "RANKING FOR 0 OF 10" headline stats,
  copy-paste contamination callouts, competitor gap tables that
  landed.
- **Tone misfires** — audits that were too harsh or too SEO-jargony.
  Useful as "don't do this" references.

## Structure

```
examples/YYYY-MM-DD-<prospect-slug>-<outcome>/
├── input.json       # {"domain": "...", "service": "...", "location": "..."}
├── output.md        # the raw markdown AuditPilot produced
├── output.docx      # the branded final artifact (optional)
└── notes.md         # what landed, what didn't, outcome (closed/lost)
```

## Tell-word bank

Start collecting real examples of AI drift found in drafts here —
"comprehensive," "leverage," "unlock," "in today's landscape." If it
shows up in a draft, capture it. QAPilot and StrategyPilot share the
same tell-word list via their synthesis prompts.
