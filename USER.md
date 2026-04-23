# USER.md

> Who Matthew is and how he wants to work with agents in this repo.
> Read this before asking clarifying questions.

## Who

**Matthew Anderson** — founder/operator of **ProofPilot**, a digital
marketing agency running SEO for 9 home-service clients (~$25-30K MRR)
with a growth plan to $5M+ ARR. Team: Matthew (founder/strategy/sales),
Jo Paula, Marcos, Rachalle.

## Role in this repo

Matthew is the **sole developer** of agent-hub. Jo Paula is the
**primary consumer** of the output (reviews/publishes content). Railway
is the production environment — there is no staging.

This means:
- Every push to `main` is a production deploy. Test locally first.
- A broken deploy blocks Jo Paula and every client's content pipeline.
- Speed-to-value matters more than purity. The platform exists to remove
  Matthew from the fulfillment bottleneck, not to be an elegant system.

## What Matthew cares about

1. **Shipping > architecture.** Working code on prod beats beautiful
   code in a branch. If it takes 10 minutes, ship it; if it takes 3
   days, discuss scope.
2. **His time.** Protect it. If a task can be automated, that's the
   most valuable move. He should be selling and strategizing, not doing
   bookkeeping or manual QA.
3. **Client visibility.** Every client deliverable reflects on
   ProofPilot's brand. QA matters. AI-obvious copy is unshippable.
4. **Revenue impact.** Tier 1 clients before Tier 2-3. New-client audits
   (AuditPilot) are as important as existing-client fulfillment — they
   grow the business.
5. **Leverage.** One action should update multiple surfaces. An agent
   that writes content should also log it, approve it, and push to Drive.

## How Matthew communicates

- **Direct.** No fluff, no hedging, no "I think maybe we could consider."
- **Terse.** If nothing's wrong, say nothing. If something's urgent, say
  it clearly with the recommended action.
- **Scope-minimal.** He'll push back on gold-plating. Deliver the ask,
  not adjacent improvements.
- **Skeptical of over-engineering.** No abstractions, frameworks, or
  helpers created on spec. Three similar lines is better than a
  premature abstraction.

## Review & deploy rituals

- **Local test:** `cd backend && .venv/bin/uvicorn server:app --reload`
  before any push.
- **Commit:** conventional format, descriptive. No `Co-Authored-By`
  attribution (globally disabled).
- **Push to main:** triggers Railway auto-deploy (~2-3 min).
- **Verify:** `curl https://proofpilot-agents.up.railway.app/health`
  → hit the UI → spot-check the feature actually works.
- **Rollback = revert commit + re-push.** The Railway Volume persists,
  so SQLite data and memory/ survive rollbacks.

## Things Matthew has already asked for (don't re-ask)

- "Don't do more than I asked."
- "Test locally before pushing."
- "Don't push to main without my sign-off on risky changes."
- "Never auto-publish content to client sites."
- "Never commit `.env` or client API keys."
- "Absorb existing shims instead of leaving them at the root."
- "Prompts as files, not Python strings."

## Things Matthew generally wants you to propose

- Removing dead code you find along the way.
- Extracting duplicated logic into shared utilities WHEN the duplication
  is real (same exact pattern across 3+ callers) — not speculative.
- Adding per-feature test coverage (pytest, not snapshot testing).
- Upgrading prompts or models when a meaningful improvement exists.

## When to pause and ask

- Anything that modifies production data (DB migrations, content approvals).
- Anything that sends to clients (email, Drive upload, WordPress publish).
- Anything that breaks an existing public route (rename, delete, restructure).
- Anything that costs non-trivial money at scale (bulk DataForSEO, bulk Recraft).
- Anything involving BYND Agency clients — those route through a separate
  Composio account (`mcp__composio-bynd__*`).

## Personal preferences

- `zsh` on macOS (Darwin 25.x).
- Python 3.11 in production; local venvs may be older — don't assume.
- VS Code with Claude Code extension.
- Slack (`#seo-team`, `#general`, per-client channels) is the team nervous system.
- ClickUp is the task board; Obsidian is the knowledge vault.
- Granola captures meeting transcripts; Fireflies is the transcript archive.
