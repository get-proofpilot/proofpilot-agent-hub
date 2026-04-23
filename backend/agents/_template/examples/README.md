# Examples

> Calibration samples for this Pilot. Treat these like unit tests for tone,
> structure, and quality — not for runtime logic.

## What goes here

Each example is a pair (or triple) of files in a dated folder:

```
examples/
├── 2026-04-22-homeservice-good/
│   ├── input.json         # the exact request we sent
│   ├── output.md          # what the Pilot produced
│   └── notes.md           # why this is "good" — what to preserve
├── 2026-04-22-homeservice-bad/
│   ├── input.json
│   ├── output.md
│   └── notes.md           # what went wrong; the fix landed in commit abc1234
```

## Naming

`YYYY-MM-DD-<shortdesc>-<good|bad|edge>/`

- `good` — canonical output this Pilot should aim for
- `bad` — regression example; keep as a reminder
- `edge` — unusual input, partial data, error path

## Why we keep bad examples

Every failure that reaches a client is a lesson. Log it here with the
fix link so the pattern stops reappearing.

## Linking to tests

When an example captures a behavior we actually enforce, reference it
from `tests/`:

```python
# tests/test_layer1_accuracy.py
def test_wrong_city_is_critical_issue():
    """Matches examples/2026-04-22-copypaste-contamination-bad/."""
    ...
```

## Not for runtime

Pilots do NOT load files from `examples/` at runtime. These are human-
and agent-readable references for calibration and onboarding only.
