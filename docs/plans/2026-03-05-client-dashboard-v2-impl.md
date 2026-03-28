# Client Dashboard v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the single-page reporting view into a 6-tab client-first portal (Overview, SEO, Paid, Leads, Content, Tasks) with hero KPIs, content roadmap, CSV upload with AI mapping, and task tracking.

**Architecture:** Pure JS tab switching within the existing SPA. Each tab lazy-loads its data via a new `?tab=` query param on the dashboard endpoint. Two new SQLite tables (`content_roadmap`, `client_tasks`). CSV upload uses Haiku for column mapping. All existing chart/KPI renderers are migrated into their respective tabs.

**Tech Stack:** Python/FastAPI, SQLite, vanilla JS, Chart.js, Claude Haiku (CSV mapping), existing Google Sheets sync

**Design doc:** `docs/plans/2026-03-05-client-dashboard-v2-design.md`

---

## Task 1: Tab Infrastructure (HTML + CSS + JS)

Replace the current reporting view's section-based layout with a tabbed container. All existing content moves into tab panes but renders identically until subsequent tasks restructure it.

**Files:**
- Modify: `backend/static/index.html:562-640` (reporting view)
- Modify: `backend/static/style.css` (add tab styles)
- Modify: `backend/static/script.js:3095-3130` (reporting init + client select handler)

**Step 1: Replace reporting view HTML**

In `index.html`, replace the content of `#view-reporting` (lines 562-640) with the tabbed structure. Keep all existing chart/table elements but wrap them in tab panes.

```html
<div class="view" id="view-reporting">
  <div class="reporting-header">
    <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.6rem;letter-spacing:0.04em;color:var(--dark-blue);">Client Reporting</h2>
    <div class="reporting-controls">
      <select id="reportingClientSelect" class="reporting-select"></select>
      <div class="date-range-toggle">
        <button class="range-btn active" data-days="30">30d</button>
        <button class="range-btn" data-days="60">60d</button>
        <button class="range-btn" data-days="90">90d</button>
      </div>
      <button class="btn-sync" id="btnSyncNow" onclick="triggerReportingSync()">Sync Now</button>
    </div>
  </div>
  <div class="sync-status-bar" id="syncStatusBar"></div>

  <!-- Tab bar -->
  <div class="dashboard-tabs" id="dashboardTabs">
    <button class="dashboard-tab active" data-tab="overview">Overview</button>
    <button class="dashboard-tab" data-tab="seo">SEO</button>
    <button class="dashboard-tab" data-tab="paid">Paid</button>
    <button class="dashboard-tab" data-tab="leads">Leads</button>
    <button class="dashboard-tab" data-tab="content">Content</button>
    <button class="dashboard-tab" data-tab="tasks">Tasks</button>
  </div>

  <!-- Tab: Overview -->
  <div class="dashboard-tab-pane active" id="tabOverview">
    <div class="hero-kpi-row" id="heroKPIs"></div>
    <div class="reporting-kpi-row" id="overviewSecondaryKPIs"></div>
    <div class="chart-grid">
      <div class="chart-panel"><h4 class="chart-title">Leads Over Time</h4><canvas id="chartOverviewLeads"></canvas></div>
      <div class="chart-panel"><h4 class="chart-title">Revenue vs Ad Spend</h4><canvas id="chartRevenueVsSpend"></canvas></div>
    </div>
    <div class="chart-grid" style="grid-template-columns:1fr;">
      <div class="chart-panel"><h4 class="chart-title">Lead Source Breakdown</h4><canvas id="chartLeadSources"></canvas></div>
    </div>
  </div>

  <!-- Tab: SEO -->
  <div class="dashboard-tab-pane" id="tabSeo">
    <div class="reporting-kpi-row" id="organicKPIs"></div>
    <div class="chart-grid">
      <div class="chart-panel"><h4 class="chart-title">Search Performance</h4><canvas id="chartSearchPerf"></canvas></div>
      <div class="chart-panel"><h4 class="chart-title">Traffic Sources</h4><canvas id="chartTrafficSources"></canvas></div>
    </div>
    <div class="chart-grid">
      <div class="chart-panel"><h4 class="chart-title">Sessions Over Time</h4><canvas id="chartSessions"></canvas></div>
      <div class="chart-panel"><h4 class="chart-title">Top Keywords</h4><canvas id="chartTopKeywords"></canvas></div>
    </div>
    <div class="reporting-table-section">
      <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Keyword Rankings</h3>
      <table id="rankingsTable" class="reporting-table"><thead></thead><tbody></tbody></table>
    </div>
    <div class="reporting-table-section">
      <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Top Pages</h3>
      <table id="topPagesTable" class="reporting-table"><thead></thead><tbody></tbody></table>
    </div>
  </div>

  <!-- Tab: Paid -->
  <div class="dashboard-tab-pane" id="tabPaid">
    <div class="reporting-kpi-row" id="paidKPIs"></div>
    <div class="reporting-subsection" id="subsectionGoogleAds" style="display:none;">
      <h4 class="reporting-subsection-label">Google Ads</h4>
      <div class="reporting-kpi-row" id="googleAdsKPIs"></div>
      <div class="chart-grid">
        <div class="chart-panel"><h4 class="chart-title">Google Ads Spend</h4><canvas id="chartGoogleAdsSpend"></canvas></div>
        <div class="chart-panel"><h4 class="chart-title">Google Ads Conversions</h4><canvas id="chartGoogleAdsConv"></canvas></div>
      </div>
      <div class="reporting-table-section" id="googleAdsCampaignSection" style="display:none;">
        <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Google Ads Campaigns</h3>
        <table id="googleAdsCampaignTable" class="reporting-table"><thead></thead><tbody></tbody></table>
      </div>
    </div>
    <div class="reporting-subsection" id="subsectionMetaAds" style="display:none;">
      <h4 class="reporting-subsection-label">Meta Ads (Facebook &amp; Instagram)</h4>
      <div class="reporting-kpi-row" id="metaAdsKPIs"></div>
      <div class="chart-grid">
        <div class="chart-panel"><h4 class="chart-title">Meta Ads Spend</h4><canvas id="chartMetaAdsSpend"></canvas></div>
        <div class="chart-panel"><h4 class="chart-title">Meta Ads Conversions</h4><canvas id="chartMetaAdsConv"></canvas></div>
      </div>
      <div class="reporting-table-section" id="metaAdsCampaignSection" style="display:none;">
        <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Meta Ads Campaigns</h3>
        <table id="metaAdsCampaignTable" class="reporting-table"><thead></thead><tbody></tbody></table>
      </div>
    </div>
  </div>

  <!-- Tab: Leads -->
  <div class="dashboard-tab-pane" id="tabLeads">
    <div class="reporting-kpi-row" id="leadsKPIs"></div>
    <div class="chart-grid">
      <div class="chart-panel"><h4 class="chart-title">Leads Over Time</h4><canvas id="chartLeadsTimeline"></canvas></div>
      <div class="chart-panel"><h4 class="chart-title">Calls by Source</h4><canvas id="chartCallsBySource"></canvas></div>
    </div>
    <div class="reporting-table-section">
      <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Call Log</h3>
      <table id="callLogTable" class="reporting-table"><thead></thead><tbody></tbody></table>
    </div>
    <div class="reporting-table-section">
      <h3 style="margin-bottom:0.75rem;color:var(--dark-blue);">Form Submissions</h3>
      <table id="formSubmissionsTable" class="reporting-table"><thead></thead><tbody></tbody></table>
    </div>
    <div class="leads-empty" id="leadsEmpty" style="display:none;">
      <p>No lead tracking data yet. Connect CallRail or WhatConverts via Google Sheets in client settings.</p>
    </div>
  </div>

  <!-- Tab: Content -->
  <div class="dashboard-tab-pane" id="tabContent">
    <div class="content-roadmap-header">
      <div class="content-roadmap-stats" id="contentStats"></div>
      <div class="content-roadmap-controls">
        <select id="contentFilterMonth" class="reporting-select" style="width:auto;min-width:120px;">
          <option value="">All Months</option>
        </select>
        <select id="contentFilterType" class="reporting-select" style="width:auto;min-width:120px;">
          <option value="">All Types</option>
        </select>
        <select id="contentFilterStatus" class="reporting-select" style="width:auto;min-width:120px;">
          <option value="">All Statuses</option>
        </select>
        <button class="btn-sync" id="btnUploadContent" style="display:none;">Upload Spreadsheet</button>
      </div>
    </div>
    <div class="chart-grid" style="grid-template-columns: 1fr 300px; margin-bottom: var(--sp-4);">
      <div class="content-roadmap-summary" id="contentSummaryCards"></div>
      <div class="chart-panel"><h4 class="chart-title">Content by Type</h4><canvas id="chartContentTypes"></canvas></div>
    </div>
    <div class="reporting-table-section">
      <table id="contentRoadmapTable" class="reporting-table"><thead></thead><tbody></tbody></table>
    </div>
    <div class="content-empty" id="contentEmpty" style="display:none;">
      <p>No content roadmap data yet. Upload a spreadsheet or connect a Google Sheet in client settings.</p>
    </div>
    <!-- Upload modal (hidden) -->
    <div class="modal-overlay" id="contentUploadModal" style="display:none;">
      <div class="modal-panel" style="max-width:700px;">
        <h3 style="margin-bottom:1rem;color:var(--dark-blue);">Upload Content Roadmap</h3>
        <input type="file" id="contentFileInput" accept=".csv,.xlsx,.xls" style="margin-bottom:1rem;">
        <div id="contentMappingPreview" style="display:none;">
          <h4 style="margin-bottom:0.5rem;">Column Mapping</h4>
          <div id="contentMappingFields"></div>
          <div style="margin-top:1rem;display:flex;gap:0.5rem;">
            <button class="btn-sync" id="btnConfirmMapping">Confirm &amp; Import</button>
            <button class="btn-copy" id="btnCancelMapping" onclick="document.getElementById('contentUploadModal').style.display='none'">Cancel</button>
          </div>
        </div>
        <div id="contentUploadStatus"></div>
      </div>
    </div>
  </div>

  <!-- Tab: Tasks -->
  <div class="dashboard-tab-pane" id="tabTasks">
    <div class="tasks-header">
      <div class="tasks-month-nav">
        <button class="range-btn" id="btnTasksPrev">&larr;</button>
        <span class="tasks-month-label" id="tasksMonthLabel"></span>
        <button class="range-btn" id="btnTasksNext">&rarr;</button>
      </div>
      <button class="btn-sync" id="btnAddTask" style="display:none;">Add Task</button>
    </div>
    <div class="tasks-progress" id="tasksProgress"></div>
    <div class="tasks-list" id="tasksList"></div>
    <div class="tasks-empty" id="tasksEmpty" style="display:none;">
      <p>No tasks for this month yet.</p>
    </div>
  </div>

  <div class="share-link-bar" id="shareLinkBar">
    <button class="btn-share" onclick="generateReportingShareLink()">Generate Share Link</button>
    <input type="text" id="shareLinkInput" readonly class="share-link-input" placeholder="Click 'Generate Share Link' to create a client-facing URL" />
    <button class="btn-copy" id="btnCopyLink" onclick="copyShareLink()" style="display:none;">Copy</button>
  </div>
  <div class="reporting-empty" id="reportingEmpty" style="display:none;">
    <p>No data synced yet. Configure data sources in client settings, then click "Sync Now".</p>
  </div>
</div>
```

**Step 2: Add tab CSS to `style.css`** after existing `.reporting-section` styles (~line 4470). See `docs/plans/2026-03-05-client-dashboard-v2-design.md` for the full CSS block covering: `.dashboard-tabs`, `.dashboard-tab`, `.dashboard-tab-pane`, `.hero-kpi-row`, `.hero-kpi-card`, `.tasks-*`, `.content-*` classes, and responsive breakpoints.

**Step 3: Add tab switching JS** — new functions: `initDashboardTabs()`, `switchDashboardTab()`, `_loadTabData()`, `_renderTab()`. Update `_loadReportingData()` to reset tab state and load active tab.

**Step 4: Update standalone dashboard** to use the tab system, hiding internal-only controls.

**Step 5: Commit**

```bash
git add backend/static/index.html backend/static/style.css backend/static/script.js
git commit -m "feat: add tabbed dashboard infrastructure with 6 tab panes"
```

---

## Task 2: Backend — Tab-Scoped API + New Tables

Modify the dashboard endpoint to accept a `tab` query param and return only the data needed for that tab. Add the new tables.

**Files:**
- Modify: `backend/utils/db.py:128` (add new tables after sync_log)
- Modify: `backend/server.py:742-774` (modify dashboard endpoint)
- Create: `backend/utils/content_db.py` (content roadmap CRUD)
- Create: `backend/utils/tasks_db.py` (client tasks CRUD)

**Step 1: Add new tables to `db.py`**

After the `sync_log` table creation (line ~128), add `content_roadmap` and `client_tasks` tables with indexes on `(client_id, month)`.

```sql
CREATE TABLE IF NOT EXISTS content_roadmap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    month TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    page_type TEXT NOT NULL DEFAULT '',
    content_silo TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned',
    keyword TEXT NOT NULL DEFAULT '',
    volume INTEGER DEFAULT 0,
    difficulty INTEGER DEFAULT 0,
    sheets_source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    status TEXT NOT NULL DEFAULT 'not_started',
    month TEXT NOT NULL DEFAULT '',
    job_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**Step 2: Create `utils/content_db.py`**

Functions: `get_content_roadmap(client_id, month, page_type, status)`, `get_content_stats(client_id)`, `bulk_insert_content(client_id, items, source)`, `clear_content_roadmap(client_id, source)`.

**Step 3: Create `utils/tasks_db.py`**

Functions: `get_client_tasks(client_id, month)`, `create_client_task(client_id, title, category, month, job_id)`, `update_task_status(task_id, status)`, `sync_tasks_from_jobs(client_id, month)`.

The `sync_tasks_from_jobs` function queries the `jobs` table for completed workflows for this client in the given month, and auto-creates task entries with `status='complete'` for any that don't already have a corresponding `client_tasks` row.

**Step 4: Modify dashboard endpoint for tab-scoped data**

Add `_build_tab_data(client_id, tab, days)` that returns only the data needed per tab. Modify the existing `@app.get("/api/clients/{client_id}/dashboard")` to accept `tab` and `month` query params. When `tab` is empty, fall back to `_build_dashboard_data` for backwards compat.

**Step 5: Add new API endpoints**

- `GET /api/clients/{id}/content-roadmap` — list items with optional filters
- `POST /api/clients/{id}/content-roadmap/upload` — CSV upload, Haiku column mapping, return proposed mapping
- `POST /api/clients/{id}/content-roadmap/confirm-mapping` — confirm mapping and bulk import
- `GET /api/clients/{id}/tasks?month=YYYY-MM` — list tasks
- `POST /api/clients/{id}/tasks` — create manual task
- `PATCH /api/clients/{id}/tasks/{task_id}` — update status

Add `from fastapi import UploadFile` to server.py imports.

**Step 6: Commit**

```bash
git add backend/utils/db.py backend/utils/content_db.py backend/utils/tasks_db.py backend/server.py
git commit -m "feat: add tab-scoped dashboard API, content roadmap + tasks tables and CRUD"
```

---

## Task 3: Overview Tab — Hero KPIs + Business Charts

Wire up the Overview tab renderer with hero KPI cards (neon-green accent, sparklines), secondary KPIs, and three business charts.

**Files:**
- Modify: `backend/static/script.js` (add `_renderOverviewTab`)

**Step 1: Implement `_renderOverviewTab(data)`**

- Build 2 hero KPI cards (Total Qualified Leads, Revenue) with sparkline canvases using Chart.js mini line charts
- Build 5 secondary KPIs using existing `_buildKPICards` helper
- Render 3 charts: Leads Over Time (line), Revenue vs Ad Spend (dual-axis line), Lead Source Breakdown (horizontal bar)
- All DOM construction uses `document.createElement` — no innerHTML

**Step 2: Commit**

```bash
git add backend/static/script.js
git commit -m "feat: implement Overview tab with hero KPIs, sparklines, and business charts"
```

---

## Task 4: SEO + Paid Tab Renderers

Migrate existing renderers into tab-aware wrapper functions.

**Files:**
- Modify: `backend/static/script.js`

**Step 1: Add thin wrapper functions**

```javascript
function _renderSeoTab(data) {
  _renderOrganicKPIs(data.summary);
  _renderSearchPerfChart(data.search_clicks, data.search_impressions);
  _renderTrafficSourcesChart(data.traffic_sources);
  _renderSessionsChart(data.sessions, data.users);
  _renderTopKeywordsChart(data.top_keywords);
  _renderRankingsTable(data.rankings);
  _renderTopPagesTable(data.top_pages);
  _renderSyncStatus(data.sync_status);
}

function _renderPaidTab(data) {
  _renderPaidSection(data);
}
```

**Step 2: Commit**

```bash
git add backend/static/script.js
git commit -m "feat: wire SEO and Paid tabs to existing renderers"
```

---

## Task 5: Leads Tab

Wire up the Leads tab with KPIs, charts, and log tables sourced from Sheets data (CallRail/WhatConverts exports).

**Files:**
- Modify: `backend/static/script.js` (add `_renderLeadsTab`, `_renderSimpleTable`)

**Step 1: Implement `_renderLeadsTab(data)`**

- KPIs: Qualified Calls, Missed Calls, Form Submissions, Avg Answer Rate
- Charts: Leads Over Time (line), Calls by Source (horizontal bar)
- Tables: Call Log, Form Submissions (using new `_renderSimpleTable` helper)
- Show empty state if no data

**Step 2: Commit**

```bash
git add backend/static/script.js
git commit -m "feat: implement Leads tab with call/form KPIs, charts, and log tables"
```

---

## Task 6: Content Tab — Roadmap Table + CSV Upload + Sheets Sync

Wire up the Content tab with roadmap table, client-side filtering, summary stats, CSV upload with AI column mapping modal.

**Files:**
- Modify: `backend/static/script.js` (add content tab functions)

**Step 1: Implement content tab functions**

- `_renderContentTab(data)` — summary cards, type pie chart, filter dropdowns, roadmap table with status badges
- `_renderContentTable(items)` — table with Month/Title/Type/Silo/Status/Keyword/Vol/KD columns
- `_filterContentTable(allItems)` — client-side filtering by month/type/status
- `initContentUpload()` — file input handler, calls upload endpoint, shows mapping preview
- `_showMappingPreview(result)` — renders AI-proposed column mapping with dropdowns for override
- `confirmContentMapping()` — sends confirmed mapping + CSV text to import endpoint
- Show Upload button only for internal users (not standalone dashboard)

**Step 2: Commit**

```bash
git add backend/static/script.js
git commit -m "feat: implement Content tab with roadmap table, filters, and CSV upload with AI mapping"
```

---

## Task 7: Tasks Tab — Checklist UI + Auto-Population

Wire up the Tasks tab with month navigation, progress bar, categorized task checklist, and add task functionality.

**Files:**
- Modify: `backend/static/script.js` (add tasks tab functions)
- Modify: `backend/server.py` (add month param to dashboard endpoint)

**Step 1: Implement tasks tab functions**

- `_renderTasksTab(data)` — month label, prev/next navigation, progress bar (DOM-constructed, no innerHTML), categorized task list with checkboxes
- `_navigateTasksMonth(delta)` — month navigation, reloads tab data
- `_cycleTaskStatus(task)` — click checkbox cycles: not_started -> in_progress -> complete
- `_showAddTaskPrompt()` — prompt-based task creation (internal only)
- Progress bar built with DOM: `.tasks-progress-bar` > `.tasks-progress-fill` with width style

**Step 2: Update `_loadTabData`** to pass `&month=` for tasks tab

**Step 3: Update backend** dashboard endpoint to accept `month` query param for tasks tab override

**Step 4: Commit**

```bash
git add backend/static/script.js backend/server.py
git commit -m "feat: implement Tasks tab with checklist UI, month nav, and auto-population from jobs"
```

---

## Summary

| Task | What | Files | Commit |
|------|------|-------|--------|
| 1 | Tab infrastructure (HTML + CSS + JS switching) | index.html, style.css, script.js | `feat: add tabbed dashboard infrastructure` |
| 2 | Backend — tab-scoped API + new tables + CRUD | db.py, server.py, content_db.py, tasks_db.py | `feat: add tab-scoped API, content + tasks tables` |
| 3 | Overview tab — hero KPIs + sparklines + business charts | script.js | `feat: implement Overview tab` |
| 4 | SEO + Paid tabs — migrate existing renderers | script.js | `feat: wire SEO and Paid tabs` |
| 5 | Leads tab — call/form KPIs + charts + log tables | script.js | `feat: implement Leads tab` |
| 6 | Content tab — roadmap table + CSV upload + AI mapping | script.js | `feat: implement Content tab` |
| 7 | Tasks tab — checklist UI + month nav + auto-population | script.js, server.py | `feat: implement Tasks tab` |
