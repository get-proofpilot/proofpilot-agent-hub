# Local ProofPilot Agents + Skills — Design

> Source of truth: `~/ProofPilot/agent-hub/` (GitHub: `get-proofpilot/proofpilot-agent-hub`).
> Local runtime: `~/.claude/agents/` and `~/.claude/skills/` — populated via symlinks.
> Design owner: Matthew. Status: approved 2026-04-23.

## Goal

Make every backend Pilot and workflow available as a Claude Code **agent** and/or **skill** on any team member's laptop, sourced from one company GitHub repo. One `./scripts/install-local.sh` run = full Pilot + workflow registry installed locally.

## Why

Today the Pilots live as FastAPI routes on Railway. They are not invokable from Claude Code sessions outside this repo. Local install makes them a daily operating system: Matthew, Jo Paula, or any future teammate can say *"use auditpilot"* from any directory and get the same skill/agent every time, updated by `git pull`.

## Architecture

### Cognitive architecture per pilot

Each `backend/agents/<pilot>/` folder is normalized to the cognitive-architecture pattern (one shared context layer per agent):

```
backend/agents/<pilot>/
├── AGENTS.md            → symlink to repo-root AGENTS.md (universal standard)
├── CLAUDE.md            — master context: business, decisions, voice
├── SOUL.md              — agent identity: personality, values, boundaries
├── USER.md              → symlink to repo-root USER.md (operator profile)
├── TOOLS.md             — which tools this pilot connects to
├── HEARTBEAT.md         — scheduled tasks + recurring ops (new)
├── agent.md             — Claude Code subagent frontmatter file (new)
├── manifest.py          — backend-side manifest
├── engine.py            — backend runtime
├── prompts/             — stage prompts (system.md etc.)
├── skill/               — modular Claude Code skill
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── context/             — business knowledge: ICP, offer details, processes (new)
├── examples/            — real samples (good + bad outputs for calibration)
└── memory/
    └── MEMORY.md        — persistent memory index (new)
```

**Gaps to fill per pilot** (already-present files stay as-is — inventory on 2026-04-23):

| File | Existing coverage | Action |
|------|-------------------|--------|
| `CLAUDE.md` | 10/10 | keep |
| `SOUL.md` | 10/10 | keep |
| `TOOLS.md` | 10/10 | keep |
| `skill/SKILL.md` | 10/10 | keep, symlink into `~/.claude/skills/` |
| `AGENTS.md` | only at repo root | symlink into each pilot folder |
| `USER.md` | only at repo root | symlink into each pilot folder |
| `HEARTBEAT.md` | none | scaffold new file per pilot |
| `agent.md` | none | generate from SOUL + CLAUDE + manifest |
| `context/` | none | scaffold new folder per pilot (ICP, offer, voice notes) |
| `memory/MEMORY.md` | none | scaffold empty index per pilot |

### Workflow skills

The 25 single-pass workflows in `backend/workflows/*.py` each get a sibling skill folder:

```
backend/workflows/
├── <workflow_name>.py              — existing Python (unchanged)
├── website_seo_audit.py
├── ...
└── skills/
    ├── pp-website-seo-audit/
    │   └── SKILL.md                — SYSTEM_PROMPT + input schema extracted
    ├── pp-keyword-gap/
    │   └── SKILL.md
    └── ...                         — 25 total
```

`SKILL.md` for each workflow is built from:
- frontmatter `name`, `description`, `tags` derived from filename + workflow title
- the `SYSTEM_PROMPT` constant from the Python file (quoted as the skill body)
- the input schema (from `CLAUDE.md` workflow input schemas section)
- a "When to trigger" block aligned with the workflow's purpose

### Local install via symlinks

`~/.claude/` stays clean — all content stays in `agent-hub/`:

```
~/.claude/agents/
├── proofpilot-auditpilot.md       → agent-hub/backend/agents/auditpilot/agent.md
├── proofpilot-strategypilot.md    → agent-hub/backend/agents/strategypilot/agent.md
├── proofpilot-qapilot.md          → agent-hub/backend/agents/qapilot/agent.md
├── proofpilot-autopilot.md        → agent-hub/backend/agents/autopilot/agent.md
├── proofpilot-pilotcore.md        → agent-hub/backend/agents/pilotcore/agent.md
├── proofpilot-reportpilot.md      → agent-hub/backend/agents/reportpilot/agent.md
├── proofpilot-gbppilot.md         → agent-hub/backend/agents/gbppilot/agent.md
├── proofpilot-projectpilot.md     → agent-hub/backend/agents/projectpilot/agent.md
├── proofpilot-redditpilot.md      → agent-hub/backend/agents/redditpilot/agent.md
└── proofpilot-websitepilot.md     → agent-hub/backend/agents/websitepilot/agent.md

~/.claude/skills/
├── proofpilot-auditpilot/         → agent-hub/backend/agents/auditpilot/skill/
├── proofpilot-strategypilot/      → agent-hub/backend/agents/strategypilot/skill/
├── ...                            (10 pilot skill symlinks)
├── pp-website-seo-audit/          → agent-hub/backend/workflows/skills/pp-website-seo-audit/
├── pp-keyword-gap/                → agent-hub/backend/workflows/skills/pp-keyword-gap/
├── pp-prospect-audit/             → agent-hub/backend/workflows/skills/pp-prospect-audit/
└── ...                            (25 workflow skill symlinks)
```

**Total: 10 agent symlinks + 35 skill symlinks = 45 symlinks.**

### Agent markdown format

Per Claude Code subagent convention:

```markdown
---
name: proofpilot-auditpilot
description: AuditPilot — 4-stage sales audit for prospects (Firecrawl + DataForSEO + Strategic Brain + Sales Audit v2). Use when someone says "AuditPilot", "audit this site", or shares a prospect URL for evaluation.
tools: ["*"]
model: opus
---

# AuditPilot
[condensed identity + purpose from SOUL.md]

## When to use
[from CLAUDE.md + skill/SKILL.md triggers]

## How it runs
[4 stages summary]

## Source of truth
See `backend/agents/auditpilot/` in the agent-hub repo for full prompts, schemas, and examples. The corresponding skill is `proofpilot-auditpilot` which loads automatically when this agent runs.
```

### Model selection per pilot

| Pilot | Model | Rationale |
|-------|-------|-----------|
| PilotCore | opus | deep reasoning across vault + escalation |
| AuditPilot | opus | 8-dimension Strategic Brain + multi-stage synthesis |
| StrategyPilot | opus | 12-category taxonomy + ROI modelling |
| AutoPilot | opus | 6-stage page builder with revision loop |
| QAPilot | sonnet | 7-layer review with structured output |
| ReportPilot | sonnet | data-backed templated output |
| GBPPilot | sonnet | short-form GBP posts |
| ProjectPilot | sonnet | project state updates |
| RedditPilot | sonnet | comment/post generation |
| WebsitePilot | sonnet | templated page output |

Workflow skills inherit the calling agent's model (no override in SKILL.md).

## The installer

`scripts/install-local.sh` — idempotent, safe to run repeatedly:

1. Detect repo path (script's own location → `$REPO_ROOT`).
2. Create `~/.claude/agents/` and `~/.claude/skills/` if missing.
3. For each pilot in `backend/agents/<name>/`:
   - Symlink `agent.md` → `~/.claude/agents/proofpilot-<name>.md`
   - Symlink `skill/` → `~/.claude/skills/proofpilot-<name>/`
4. For each workflow skill in `backend/workflows/skills/pp-<name>/`:
   - Symlink → `~/.claude/skills/pp-<name>/`
5. Validate every symlink resolves.
6. Print summary: `X agents installed · Y skills installed · Z skipped (already linked)`.

Uninstaller: `scripts/uninstall-local.sh` — removes only the symlinks we created (match by resolved target pointing into this repo).

**Safety:** the script refuses to overwrite a non-symlink file at the target path. If `~/.claude/skills/proofpilot-auditpilot/` already exists as a real folder, it aborts with a clear error.

## Commit + deploy plan

Conventional commit series on `main`:

1. `chore(agents): normalize pilot folders to cognitive-architecture pattern` (adds HEARTBEAT.md + context/ + memory/MEMORY.md + symlinks to AGENTS.md, USER.md across 10 pilots)
2. `feat(agents): add agent.md files for all 10 pilots`
3. `feat(workflows): extract 25 skill/ folders from workflow SYSTEM_PROMPTs`
4. `feat(scripts): add install-local.sh + uninstall-local.sh`
5. `docs: document local-install flow in AGENTS.md`

None of this touches `server.py` or any runtime path → Railway deploy is a no-op. Railway does redeploy on push but the app behavior is unchanged.

## Rollout

1. Matthew runs `./scripts/install-local.sh` locally, verifies agents/skills load.
2. Matthew smoke-tests one pilot (`proofpilot-auditpilot`) and one workflow (`pp-keyword-gap`) from a fresh Claude Code session outside the repo.
3. Team members (Jo Paula, etc.) run the same script on their laptops → identical registry.
4. `git pull` updates any changed prompts/skills automatically — no re-install needed.

## Non-goals (explicitly out of scope)

- Rewriting existing pilot prompts.
- Changing FastAPI routes or `server.py`.
- Moving `autopilot/` or `redditpilot/` into the `backend/agents/` layout (they're multi-module; stay as-is).
- Publishing this as an npm package or installable Claude Code plugin.
- Sync mechanisms (e.g. pulling remote memory). Each laptop reads the repo state at `git pull` time.

## Risks + mitigations

| Risk | Mitigation |
|------|-----------|
| Install script overwrites user's existing custom skills | Script refuses non-symlink targets, aborts with diff |
| Broken symlink if repo moves | Installer detects, prints clear error, instructs re-run |
| Workflow SYSTEM_PROMPT extraction misses dynamic prompt construction | Inspect each of 25 workflows before extraction; fall back to summarized description if SYSTEM_PROMPT is built from multiple parts |
| Agent markdown `description` too vague → Claude doesn't auto-invoke | Each description names the pilot + its triggers explicitly (copy from skill SKILL.md `## When to Trigger` block) |
| Team member on Windows/WSL | symlinks work on WSL; pure-Windows out of scope (nobody on the team uses it) |

## Success criteria

1. `./scripts/install-local.sh` runs clean on Matthew's laptop.
2. `ls ~/.claude/agents/proofpilot-*.md` shows 10 files, all symlinks to `agent-hub/`.
3. `ls ~/.claude/skills/` contains 10 `proofpilot-*` and 25 `pp-*` entries.
4. From `~/` (outside the repo), typing *"use auditpilot to audit acme.com"* into Claude Code invokes `proofpilot-auditpilot` and its skill auto-loads.
5. Script reports 0 errors on second run (idempotent).
