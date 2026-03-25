# SEO Playbook Command Center — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 5th "Command Center" tab to the SEO Playbook that executes audit/plan/wrap-up operations via the Anthropic API and syncs with ClickUp for task management.

**Architecture:** FastAPI endpoints call the Anthropic Messages API with vault data injected as context. Results stream via SSE. ClickUp REST API handles bi-directional task sync. Frontend renders operations panel, results feed, and ClickUp progress.

**Tech Stack:** Python/FastAPI, Anthropic SDK (already installed), ClickUp REST API, vanilla JS (matching existing playbook pattern)

---

### Task 1: Add ClickUp API key to Railway

**Step 1: Set env var via Railway CLI**
```bash
cd /tmp/proofpilot-hub-deploy/backend
railway vars set CLICKUP_API_KEY=pk_57244480_FAGS639TN7ZXG8EB4XEVGZRMMCOJVMG4
```

**Step 2: Get ClickUp workspace info**

Use ClickUp MCP to get workspace ID and space/list structure:
```
mcp__claude_ai_ClickUp__clickup_get_workspace_hierarchy
```

Store workspace ID and relevant list IDs as env vars or in vault_data config.

---

### Task 2: Build the execution engine

**Files:**
- Create: `backend/seo_executor.py`

This module takes a command name + client slug, reads vault data, constructs a prompt, calls the Anthropic API, and yields output chunks.

**Key functions:**
- `execute_command(command, client_slug, vault_dir)` → async generator of text chunks
- `build_prompt(command, client_data)` → string prompt with full context
- `read_client_context(client_slug, vault_dir)` → dict of all YAML/MD data for a client

**Prompt templates per command:**

| Command | Context needed | Output format |
|---------|---------------|---------------|
| audit | recurring.yaml + tracker.yaml + last month plan + log.md | Findings: what was planned vs done, gaps, recommendations |
| monthly-plan | roadmap.yaml + recurring.yaml + log.md | Month plan with tasks by week by category |
| weekly-plan | All clients' tiers + recurring + roadmaps | Prioritized weekly checklist by manager |
| wrap-up | tracker.yaml + log.md + current month work | Summary, email draft, next actions |
| workload | All clients' recurring + tiers + managers | Team completion rates, who's behind |

**Step 1: Create seo_executor.py**

```python
import os
import anthropic
from pathlib import Path

PROMPTS = {
    'audit': """You are an SEO operations auditor for ProofPilot agency.
Review this client's last month and compare planned deliverables vs actual completion.

Client: {name}
Tier: {tier} | MRR: ${mrr} | Manager: {manager}

PLANNED DELIVERABLES (from recurring.yaml):
{recurring}

WORK LOG (from log.md):
{log}

Analyze:
1. What was planned vs what was done
2. Any gaps or missed deliverables
3. Quality assessment
4. Recommendations for next month

Format as a clear audit report with sections.""",

    'monthly-plan': """You are an SEO operations planner for ProofPilot agency.
Generate next month's plan for this client.

Client: {name}
Tier: {tier} | MRR: ${mrr} | Manager: {manager}

MONTHLY RECURRING TASKS:
{recurring}

ROADMAP (next pages to build):
{roadmap}

LAST MONTH'S LOG:
{log}

Generate a detailed monthly plan organized by week (1-4) and category.
Include specific page URLs from the roadmap for content tasks.""",

    # ... (other prompts follow same pattern)
}

async def execute_command(command, client_slug, vault_dir):
    """Execute an SEO command and yield output chunks."""
    vault = Path(vault_dir)
    client = read_client_context(client_slug, vault)
    prompt = build_prompt(command, client)

    api_client = anthropic.Anthropic()
    with api_client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        for text in stream.text_stream:
            yield text
```

**Step 2: Add execution endpoint to server.py**

```python
@app.post("/api/seo/execute")
async def seo_execute(body: SeoExecuteRequest):
    # Validate command is in allowed list
    # Stream response via SSE
    pass
```

**Step 3: Test with a single audit command**

---

### Task 3: Build ClickUp sync endpoints

**Files:**
- Create: `backend/clickup_sync.py`

Uses ClickUp REST API (not MCP) since this runs on Railway:
- `POST /api/seo/clickup/sync-plan` — reads recurring.yaml, creates ClickUp tasks
- `GET /api/seo/clickup/progress` — pulls task completion per client
- `GET /api/seo/clickup/progress/{client}` — detailed tasks for one client

**ClickUp task creation mapping:**

```
recurring.yaml category → ClickUp task
─────────────────────────────────────
content[0].task → Task: "Write and publish 2 blog posts"
                  Assignee: {manager}
                  Due: Week 2 of the month
                  Priority: High
                  Tags: ["content", client_name]
```

---

### Task 4: Build Command Center frontend

**Files:**
- Modify: `backend/web/seo-playbook.js` — add 5th tab + rendering
- Modify: `backend/web/seo-playbook.css` — add Command Center styles

**UI Structure:**

```
COMMAND CENTER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─ OPERATIONS ─────────────────────────────────────┐
│                                                   │
│  MONTH START (Week 1)         MID-MONTH           │
│  ┌─────────────┐ ┌──────────┐ ┌─────────────┐   │
│  │ Run Audits  │ │ Monthly  │ │ Workload    │   │
│  │ [All ▾] [▶]│ │ Plans    │ │ Check       │   │
│  └─────────────┘ │ [All ▾] │ │ [▶ Run]     │   │
│                   │ [▶ Run]  │ └─────────────┘   │
│  ┌─────────────┐ └──────────┘                     │
│  │ Weekly Plan │              MONTH END           │
│  │ [▶ Run]     │ ┌──────────────────────┐         │
│  └─────────────┘ │ Wrap-up + ClickUp    │         │
│                   │ [All ▾] [▶ Run]      │         │
│                   └──────────────────────┘         │
└───────────────────────────────────────────────────┘

┌─ CLICKUP PROGRESS ──────────────────────────────┐
│  Saiyan ████████░░ 80%  ATE █████░░░░░ 50%      │
│  ISS    ██████░░░░ 60%  PCE ███░░░░░░░ 30%      │
│  ... per client progress bars                     │
└───────────────────────────────────────────────────┘

┌─ RESULTS FEED ──────────────────────────────────┐
│  [Today 2:30 PM] Audit — Saiyan Electric        │
│  > 4/5 content deliverables complete...          │
│                                                   │
│  [Today 1:15 PM] Monthly Plan — All Thingz       │
│  > April plan: 2 blogs, 3 location pages...      │
└───────────────────────────────────────────────────┘
```

---

### Task 5: Wire up SSE streaming for operation output

When a user clicks "Run", the frontend:
1. Sends POST to `/api/seo/execute`
2. Opens SSE connection to `/api/seo/execute/stream/{run_id}`
3. Renders output in the results panel as it streams
4. Shows completion checkmark when done

---

### Task 6: Deploy and test

**Step 1: Commit all files**
```bash
git add backend/seo_executor.py backend/clickup_sync.py backend/web/seo-playbook.js backend/web/seo-playbook.css backend/server.py
git commit -m "feat: add Command Center tab with Anthropic API execution and ClickUp sync"
```

**Step 2: Push to GitHub**
```bash
git push origin main
```

**Step 3: Verify on Railway**
- Navigate to SEO Playbook → Command Center tab
- Run a single audit for Saiyan Electric
- Verify output streams
- Test ClickUp sync button

---

## Execution Order

1. Task 1: ClickUp API key (1 min)
2. Task 2: Execution engine (core — build first)
3. Task 4: Frontend tab (can see the UI while building backend)
4. Task 3: ClickUp sync (after execution engine works)
5. Task 5: SSE wiring (connect frontend to backend)
6. Task 6: Deploy
