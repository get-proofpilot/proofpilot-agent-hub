# PilotCore Examples

Briefings and escalation outputs worth calibrating against.

## What to capture

- **Briefings** — good ones are <300 words, lead with the one overdue
  Tier 1 client, and end with 3 specific actions Matthew can do today.
  Bad ones list every client or recommend generic "review your pipeline."
- **Escalations** — good ones name a client, state days overdue, and
  assign owner. Bad ones use "falling behind" or label Tier 3 as 🔴.

## Structure

See `backend/agents/_template/examples/README.md` for the canonical
folder naming + file shape. Short version:

```
examples/YYYY-MM-DD-<shortdesc>-<good|bad>/
├── input.json       # {"date": "...", "include_details": true}
├── output.md        # Slack-formatted briefing or escalation
└── notes.md         # why it's good/bad, what to keep/change
```
