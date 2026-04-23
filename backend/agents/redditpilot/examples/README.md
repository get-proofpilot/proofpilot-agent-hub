# RedditPilot Examples

Reddit comments, posts, and opportunity decisions worth calibrating against.

## What to capture

- **Gold comments** — comments that got upvotes and didn't feel like
  marketing. Screenshot + the original opportunity + the persona used.
- **Ban triggers** — the exact content or pattern that caused a warning,
  shadowban, or removal. Worth its weight in gold as "never do this."
- **Persona exemplars** — one canonical example per persona showing
  voice-fit. Good curious-learner ≠ good helpful-expert.
- **Opportunity false positives** — subreddit posts the scanner flagged
  as opportunities but the human reviewer rejected. Used to tune filters.

## Structure

```
examples/YYYY-MM-DD-<subreddit>-<persona>-<comment|post>-<outcome>/
├── opportunity.json    # scanned subreddit post that triggered this
├── generated.md        # what RedditPilot produced
├── posted.md           # what actually went live (may differ after human edit)
├── reddit_url.txt      # permalink
└── notes.md            # outcome: upvotes, replies, modpol response
```

## Calibration metrics

For each example, capture:
- Upvotes at 1hr / 24hr / 7d
- Replies (count + sentiment)
- Mod actions (removed / sticky / flair change)
- Detection signals (were there any "this feels AI" replies?)

## When to add one

- Any comment that gets > 10 upvotes
- Any post that gets a mod action (positive or negative)
- Any rejection where the human reviewer overruled RedditPilot's
  confidence
- Any ban or shadowban event — full post-mortem
