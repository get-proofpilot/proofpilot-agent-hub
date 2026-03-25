# SEO Playbook Command Center — Design

## Problem

The playbook teaches the SEO operations framework but doesn't execute it. Commands like /audit, /monthly-plan, /weekly-plan, /wrap-up, and /workload only run locally in Matthew's Claude Code session. The team (Jo, Marcos) can see the SOP but can't trigger operations or track completion. ClickUp is used for task management but isn't connected to the playbook.

## Solution

A 5th tab in the SEO Playbook called "Command Center" that:
1. Executes operations via the Anthropic API (not claude CLI)
2. Pushes generated plans as tasks to ClickUp
3. Pulls ClickUp task completion status for live progress tracking

## Architecture

### Tab Structure (5 tabs)
1. Framework — SOP reference (existing)
2. Month Calendar — visual task distribution (existing)
3. SOP Reference — step-by-step processes (existing)
4. My Clients — client cards with manager filter (existing)
5. **Command Center** — execute operations, view results, ClickUp sync (NEW)

### Command Center UI — Three Sections

**Section 1: Operations Panel**

Organized by when in the month they run:

| Timing | Command | Scope | Description |
|--------|---------|-------|-------------|
| Week 1 | Audit | Per client or all | Compare last month plan vs actual |
| Week 1 | Monthly Plan | Per client or all | Generate plan from roadmap + recurring |
| Week 1 | Weekly Plan | Global | Prioritized weekly checklist |
| Week 2-3 | Workload | Global | Team completion rates, stalled clients |
| Week 4 | Wrap-up | Per client or all | Update tracker, log, generate report |
| Anytime | Sync Calendar | Global | Regenerate playbook vault data |

Each operation:
- Has a prominent Run button
- Shows a dropdown to select a specific client or "All"
- Displays a streaming output panel when running
- Shows last run timestamp and result summary

**Section 2: Results Feed**

Reverse-chronological feed of operation results:
- Audit findings per client
- Generated monthly plan highlights
- Weekly plan summary
- Wrap-up outputs
- Stored in Railway persistent volume

**Section 3: ClickUp Sync**

Two-way integration:
- **Push**: "Sync Plan to ClickUp" button creates tasks per deliverable per client
  - Maps recurring.yaml tasks to ClickUp tasks with assignees, due dates, priorities
  - Groups by category (Content, GBP, Off-Page, Technical, Reporting)
- **Pull**: Live progress cards per client showing:
  - Tasks completed / total for current month
  - Completion percentage with progress bar
  - Who's behind (red highlight)
  - Last ClickUp sync timestamp

### Backend Endpoints

**Execution:**
```
POST /api/seo/execute
  body: { command: "audit"|"monthly-plan"|"weekly-plan"|"wrap-up"|"workload", client?: "slug" }
  → Reads vault_data/ for client context
  → Constructs appropriate prompt with full context
  → Calls Anthropic Messages API (claude-sonnet-4-20250514)
  → Streams response via SSE
  → Saves result to /app/data/seo-results/{command}-{client}-{date}.md

GET /api/seo/results
  → Returns list of past operation results

GET /api/seo/results/{id}
  → Returns a specific result
```

**ClickUp Integration:**
```
POST /api/seo/clickup/sync-plan
  body: { client: "slug", month: "2026-04" }
  → Reads recurring.yaml for the client
  → Creates ClickUp tasks with proper list, assignee, due dates
  → Returns created task IDs

GET /api/seo/clickup/progress
  → Reads ClickUp tasks for current month
  → Returns completion rates per client

GET /api/seo/clickup/progress/{client}
  → Detailed task list for a client from ClickUp
```

### Prompt Construction

Each command gets a purpose-built prompt with vault context injected:

**Audit prompt**: Reads last month's monthly-plan + tracker.yaml + log.md → asks Claude to compare planned vs actual, identify gaps

**Monthly Plan prompt**: Reads roadmap.yaml + recurring.yaml + last month's log.md → asks Claude to generate next month's plan

**Weekly Plan prompt**: Reads all clients' trackers + tiers + cadences → asks Claude to prioritize this week's work

**Wrap-up prompt**: Reads tracker.yaml + current work → asks Claude to summarize, generate email draft, flag issues

**Workload prompt**: Reads all clients' trackers → asks Claude to assess team completion rates

### Environment Variables Needed

```
ANTHROPIC_API_KEY — already exists
CLICKUP_API_KEY — needs to be added
CLICKUP_WORKSPACE_ID — needs to be added
CLICKUP_LIST_ID — per client mapping (stored in vault_data config)
```

## Implementation Steps

1. Add ClickUp API key to Railway env vars
2. Build execution engine (prompt construction + Anthropic API streaming)
3. Build ClickUp sync endpoints
4. Build Command Center UI (tab 5)
5. Wire up SSE streaming for operation output
6. Add results storage and feed
7. Deploy and test

## Verification

1. Click "Run Audit" for a single client → output streams in real-time
2. Click "Run All Audits" → 9 audits run sequentially with progress
3. "Sync to ClickUp" creates tasks in the correct ClickUp list
4. ClickUp progress panel shows live completion percentages
5. Results feed shows past operation outputs
