# Client Dashboard v2 — Tabbed Portal Design

**Date:** 2026-03-05
**Status:** Approved
**Context:** Redesign reporting from single scrolling page into Hook Agency-inspired tabbed client portal with business-level metrics, platform drill-downs, content roadmap, and task tracking.

## Design Decisions

- **Client-first portal** — the tabbed dashboard IS the primary client experience. Internal view wraps the same component.
- **Six tabs:** Overview, SEO, Paid, Leads, Content, Tasks
- **Content Roadmap:** CSV/Excel upload with AI column mapping + Google Sheets live sync
- **Leads data (CallRail/WhatConverts):** Via Google Sheets sync (both platforms export to Sheets natively)
- **Tasks:** Auto-generated from ProofPilot jobs + manual additions
- **Hero KPIs:** Total Qualified Leads + Revenue get spotlight treatment on Overview

## Tab Structure

```
┌─────────────────────────────────────────────────────┐
│  Client Name  │  30d  60d  90d  │  Sync  │  Share   │
├──────────┬─────┬──────┬────────┬─────────┬──────────┤
│ Overview │ SEO │ Paid │ Leads  │ Content │  Tasks   │
└──────────┴─────┴──────┴────────┴─────────┴──────────┘
```

### Tab 1: Overview

Two hero KPI cards (large, neon-green accent, sparkline):
- Total Qualified Leads (calls + forms, MoM %)
- Revenue (from Sheets, MoM %)

Secondary KPIs row (smaller, each with sparkline):
- Phone Calls | Form Submissions | Organic Sessions | Total Ad Spend | Avg Position

Charts:
- Leads Over Time (stacked: organic vs paid leads)
- Revenue vs Ad Spend (dual-axis ROI story)
- Lead Source Breakdown (horizontal bar: Google Organic, Google Ads, Meta, Direct)

### Tab 2: SEO

Current organic section reorganized:
- KPIs: Clicks, Impressions, Avg Position, CTR, Sessions
- Search Performance + Traffic Sources
- Sessions Over Time + Top Keywords
- Keyword Rankings table
- Top Pages table

### Tab 3: Paid

Combined KPIs (Total Spend, Total Conversions, ROAS), then subsections:
- Google Ads: KPIs, spend chart, conversions chart, campaigns table
- Meta Ads: Same structure

### Tab 4: Leads

Data from Google Sheets (CallRail/WhatConverts exports):
- KPIs: Qualified Calls, Missed Calls, Form Submissions, Avg Answer Rate
- Calls by Source (horizontal bar)
- Leads Over Time chart
- Call Log table (date, caller, duration, source, qualified)
- Form Submissions table (date, name, source, type)

Sheets config gets `call_tracking` template with pre-mapped fields.

### Tab 5: Content

Content Roadmap table by month:
- Columns: Month | Title | Type | Content Silo | Status | Keyword | Volume | Difficulty
- Filterable by month, type, status
- Status as color-coded badges (Planned/Assigned/Written/Published)

Summary stats: X total | Y published | Z in progress | type breakdown pie

Two data paths:
1. CSV/Excel upload — AI (Haiku) reads headers, proposes column mapping, confirm, import
2. Google Sheets sync — connect Sheet URL, auto-maps columns, syncs on load

### Tab 6: Tasks

This Month's Deliverables — checklist view:
- Auto-populated from ProofPilot jobs (workflow runs)
- Manual task entry (internal only, hidden on share links)
- Status: Not Started / In Progress / Complete
- Grouped by category: Content, SEO, Paid, Reporting, Other
- Add Task button (internal only)

## Data Layer

### New Tables

```sql
CREATE TABLE IF NOT EXISTS content_roadmap (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER NOT NULL,
    month        TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    page_type    TEXT NOT NULL DEFAULT '',
    content_silo TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'planned',
    keyword      TEXT NOT NULL DEFAULT '',
    volume       INTEGER DEFAULT 0,
    difficulty   INTEGER DEFAULT 0,
    sheets_source TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'other',
    status      TEXT NOT NULL DEFAULT 'not_started',
    month       TEXT NOT NULL DEFAULT '',
    job_id      TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

### Sheets Config Expansion

The `sheets_config` JSON field on clients becomes structured:

```json
{
  "metrics": { "sheet_id": "...", "range": "...", "columns": {...} },
  "call_tracking": { "sheet_id": "...", "range": "...", "columns": {...} },
  "content_roadmap": { "sheet_id": "...", "range": "...", "columns": {...} }
}
```

## API Endpoints

### Modified
- `GET /api/clients/{id}/dashboard` — add `tab` query param, return only data for requested tab (lazy load)

### New
- `POST /api/clients/{id}/content-roadmap/upload` — CSV/Excel upload with AI column mapping
- `POST /api/clients/{id}/content-roadmap/confirm-mapping` — confirm AI mapping and import
- `GET /api/clients/{id}/content-roadmap` — list roadmap items (filterable by month, type, status)
- `GET /api/clients/{id}/tasks` — list tasks (filterable by month)
- `POST /api/clients/{id}/tasks` — create manual task
- `PATCH /api/clients/{id}/tasks/{task_id}` — update task status
- `GET /api/clients/{id}/leads` — leads data (calls + forms from Sheets)

## Frontend Architecture

- Pure JS tab switching — no framework change
- Each tab is a `<div>` that lazy-renders on first click
- Tab state in URL hash (`#overview`, `#seo`, `#paid`, `#leads`, `#content`, `#tasks`)
- Share links deep-link to tabs
- CSV upload: file input + FormData POST, AI returns preview, confirm imports
- Charts destroyed/recreated per tab switch to prevent memory leaks

## Implementation Order

1. Tab infrastructure (HTML/CSS/JS tab switching, lazy load)
2. Overview tab (hero KPIs, sparklines, business metrics)
3. SEO tab (migrate existing organic section)
4. Paid tab (migrate existing paid section)
5. Leads tab (Sheets sync for call tracking + new renderers)
6. Content tab (new table, CSV upload, AI mapping, Sheets sync)
7. Tasks tab (new table, auto from jobs, manual entry, checklist UI)
