# Client Reporting Dashboard — Implementation Plan

## Context

Matthew currently uses Agency Analytics for client reporting dashboards, which costs ~$20/client/month, has unstable integrations, no data blending, and requires manual Google Slide presentations for monthly reports. The goal is to build a custom client-facing reporting dashboard directly into the ProofPilot Agent Hub that connects GSC, GA4, and the existing DataForSEO/Search Atlas data — replacing Agency Analytics entirely.

**Phase 1:** GSC + GA4 integration, per-client dashboard with charts, shareable client-facing URLs.
**Phase 2:** Scheduled auto-sync, Google Sheets lead data, PDF export.
**Phase 3:** Google Ads, Meta Ads, Local Falcon heatmaps, automated email delivery.

---

## Research Summary

### Why Build Custom (vs. Agency Analytics)
- AA costs ~$20/client/month and escalating — at 30 clients that's $600/month in add-ons alone
- Unstable integrations — data can take 2-3 days to fetch, integrations frequently break
- No data blending — can't combine ad spend with CRM lead data for CPL/CPA calculations
- No data warehouse export — data locked in their platform
- Limited custom dimensions on lower tiers
- No API access without top-tier plan

### Architecture Decision: Build Inside the Hub
- Reuses existing FastAPI backend, client data, brand system, and SQLite persistence
- No new infrastructure needed
- Clients access via shareable token URLs (`/dashboard/{token}`) — no login system needed
- Admin sees all clients in a "Reporting" view; clients see only their own data

### Data Sync Strategy
| Data Source | Sync Frequency | Auth Method | Why |
|---|---|---|---|
| GSC | Daily at 3-4 AM | Service account | Data is 2-3 days delayed anyway |
| GA4 | Daily | Service account | Same-day data is incomplete |
| Google Ads | Every 6 hours (Phase 3) | OAuth + developer token | Spend updates throughout the day |
| Meta Ads | Every 6 hours (Phase 3) | System User token | Same reason |
| DataForSEO | Weekly | API key (already have) | Rankings don't change hourly |
| Google Sheets | Every 15-30 min (Phase 2) | Service account | Leads are time-sensitive |

### Google API Authentication
All Google APIs (GSC, GA4, Sheets, Ads) can share **one Google Cloud project** and **one service account**. The service account email gets added as a user/viewer on each client's:
- GSC property (read permissions)
- GA4 property (Viewer role)
- Google Sheets (Editor for read access)

This gives automated access without user-facing OAuth flows.

### GSC API Details
- Data available: clicks, impressions, CTR, position by query/page/date
- Data is 2-3 days behind — never query today/yesterday
- API returns up to 50,000 rows per request (paginate with `startRow`)
- Rate limits: 1,200 queries/min per site, 30M queries/day per project
- Python: `google-api-python-client` with `searchanalytics().query()`

### GA4 Data API Details
- Data available: sessions, users, pageviews, events, conversions, traffic sources, geography
- Uses `BetaAnalyticsDataClient` with `RunReportRequest`
- Rate limits: 10 concurrent requests, 10,000 requests/day per property
- Python: `pip install google-analytics-data`

### Time-Series Storage
Using a flexible EAV (entity-attribute-value) pattern in SQLite:
- Single `metrics` table with `(client_id, source, metric_type, dimension, value, date)`
- UNIQUE constraint enables efficient upserts on re-sync
- Indexed on `(client_id, source, metric_type, date)` for fast dashboard queries
- Trivially extensible — adding Google Ads or Meta just means new `source` values, no schema changes
- Good up to ~10M rows in SQLite; migrate to PostgreSQL + TimescaleDB if needed later

### Frontend Charting
- Chart.js via CDN (no build step, matches existing SPA pattern)
- `chartjs-adapter-date-fns` for time-axis support
- Leaflet.js for GBP heatmaps (Phase 3)

---

## Phase 1: MVP Implementation

### New Files to Create

#### 1. `backend/utils/google_auth.py` — Service account credential loading
- `get_gsc_service()` → builds Search Console API client
- `get_ga4_client()` → builds GA4 Data API client
- Loads creds from `GOOGLE_SERVICE_ACCOUNT_JSON` env var (JSON string) or `GOOGLE_SERVICE_ACCOUNT_PATH` (file path)
- Scopes: `webmasters.readonly` for GSC, `analytics.readonly` for GA4

#### 2. `backend/utils/gsc_sync.py` — GSC data fetcher
- `sync_gsc_data(client_id, domain, days_back=90)` → pulls daily clicks, impressions, CTR, avg position
- `sync_gsc_keywords(client_id, domain, days_back=90)` → pulls per-keyword daily positions for ranking tracking
- Also fetches top pages by clicks/impressions
- Uses `searchanalytics().query()` with `sc-domain:{domain}` format
- UPSERT into metrics table (handles re-syncing without duplicates)

#### 3. `backend/utils/ga4_sync.py` — GA4 data fetcher
- `sync_ga4_data(client_id, property_id, days_back=90)` → pulls sessions, users, new users, bounce rate by date
- Also fetches sessions by source/medium, top landing pages, conversions
- Uses `BetaAnalyticsDataClient` with `RunReportRequest`

#### 4. `backend/utils/metrics_db.py` — Metrics storage layer (separate from db.py)
- **Write:** `upsert_metrics()`, `bulk_upsert_metrics()`, `save_sync_log()`
- **Read:** `get_metric_timeseries()`, `get_metric_breakdown()`, `get_keyword_rankings()`, `get_dashboard_summary()` (KPIs with MoM deltas)
- **Tokens:** `create_dashboard_token()`, `get_client_by_token()`, `revoke_dashboard_token()`

### Database Schema

**New tables** (created via `init_metrics_db()` called after existing `init_db()`):

```sql
-- Flexible EAV-style metrics table for all data sources
CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     INTEGER NOT NULL,
    source        TEXT NOT NULL,           -- 'gsc', 'ga4', 'gads', 'meta', 'dfs', 'sheets'
    metric_type   TEXT NOT NULL,           -- 'clicks', 'sessions', 'position', etc.
    dimension     TEXT NOT NULL DEFAULT '', -- 'total', 'query:panel upgrade', 'source:google'
    value         REAL NOT NULL,
    date          TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    synced_at     TEXT NOT NULL,
    UNIQUE(client_id, source, metric_type, dimension, date)
);
CREATE INDEX IF NOT EXISTS idx_metrics_client_source ON metrics(client_id, source, metric_type, date);
CREATE INDEX IF NOT EXISTS idx_metrics_dimension ON metrics(client_id, source, metric_type, dimension);

-- Sync tracking
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_synced INTEGER DEFAULT 0,
    error_msg TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT
);

-- Client dashboard access tokens (shareable URLs)
CREATE TABLE IF NOT EXISTS dashboard_tokens (
    token TEXT PRIMARY KEY,
    client_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tokens_client ON dashboard_tokens(client_id);
```

**Client table migrations:** Add `gsc_property` and `ga4_property_id` TEXT columns to existing `clients` table.

### API Endpoints to Add (server.py)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/clients/{id}/dashboard` | GET | Full dashboard data bundle (KPIs + timeseries + breakdowns) |
| `/api/clients/{id}/dashboard/traffic` | GET | GA4 sessions/users over time + source breakdown |
| `/api/clients/{id}/dashboard/rankings` | GET | GSC keyword positions + distribution |
| `/api/clients/{id}/dashboard/search` | GET | GSC clicks/impressions/CTR over time |
| `/api/clients/{id}/sync` | POST | Trigger data sync (runs as background task) |
| `/api/clients/{id}/sync/status` | GET | Last sync time + status per source |
| `/api/clients/{id}/dashboard-token` | POST | Generate shareable URL token |
| `/api/dashboard/{token}` | GET | Public dashboard data (token auth) |
| `/dashboard/{token}` | GET | Serve dashboard page for clients |

### Frontend Changes

**index.html:**
- Add Chart.js CDN + `chartjs-adapter-date-fns` (after DOMPurify script tag)
- Add "Reporting" nav item in sidebar
- Add `<div id="view-reporting">` view container
- Add GSC property + GA4 property ID fields to client edit modal

**script.js:**
- Add `'reporting'` to view routing in `showView()`
- `renderReportingDashboard()` with:
  - Client selector + date range picker (30d/60d/90d)
  - KPI row: Total Clicks, Total Sessions, Avg Position, Impressions, CTR (with MoM arrows)
  - Chart grid (2-col): Search Performance line, Traffic by Source doughnut, Sessions Over Time line, Top Keywords bar
  - Rankings table (sortable): keyword, position, change, clicks, impressions
  - Top Pages table
  - Sync status + manual trigger
  - Share link generator
- Client-facing mode: detect `/dashboard/{token}` on page load → hide sidebar → standalone branded view

**style.css:**
- `.reporting-header`, `.reporting-kpi-row`, `.chart-panel`, `.chart-grid`
- `.ranking-table`, `.position-badge`, `.sync-status`, `.share-link-bar`
- `.dashboard-standalone` for client-facing mode

### Dependencies (requirements.txt)
```
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-analytics-data>=0.18.0
apscheduler>=3.10.0
```

### Client-Facing Access
- Admin generates share token → URL like `/dashboard/abc123xyz...`
- Client opens URL → SPA detects `/dashboard/` path → fetches from `/api/dashboard/{token}` → renders without sidebar/admin controls
- ProofPilot-branded header + "Powered by ProofPilot" footer
- Tokens revocable anytime

### Environment Variables (new)
| Variable | Description |
|----------|-------------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON string of service account credentials |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Alternative: file path to service account JSON |

---

## Phase 2: Auto-Sync + Leads + PDF (Next Session)

- `backend/utils/scheduler.py` — APScheduler daily sync (4 AM) for all configured clients
- `backend/utils/sheets_sync.py` — Google Sheets API for lead/job tracking → CPL, CPA, CAC, revenue
- `backend/utils/dashboard_pdf.py` — Branded PDF export (reportlab or weasyprint)
- Endpoint: `GET /api/clients/{id}/dashboard/pdf`
- Frontend: "Export PDF" button, leads section with CPL/CPA/CAC cards
- DB: Add `sheets_id`, `sheets_tab` columns to clients

## Phase 3: Ads + Heatmaps + Email (Future)

- `backend/utils/gads_sync.py` — Google Ads API (spend, conversions, CPC, ROAS by campaign)
- `backend/utils/meta_sync.py` — Meta Marketing API (spend, impressions, CPM, ROAS)
- `backend/utils/local_falcon.py` — Local Falcon API for GBP geo-grid rankings → Leaflet.js heatmap
- `backend/utils/email_delivery.py` — Monthly email with dashboard link + PDF attachment
- DB: Add `gads_customer_id`, `meta_ad_account_id`, `report_email`, `report_frequency` columns

---

## Key Design Decisions

1. **EAV metrics table** — flexible schema lets us add new data sources without migrations
2. **Token-based auth** — zero-friction client access via URL, no login system, revocable
3. **Sync-then-serve** — data cached in SQLite for instant loads + MoM comparisons (no live API proxying)
4. **Separate metrics_db.py** — keeps new metrics code out of the 295-line db.py
5. **Chart.js via CDN** — matches no-build-step SPA constraint, supports all chart types needed
6. **One service account for all Google APIs** — single credential manages GSC, GA4, Sheets

---

## Build Order (Phase 1)

1. Dependencies + schema (requirements.txt, metrics tables, client column migrations)
2. Google auth module (google_auth.py)
3. GSC sync (gsc_sync.py) — test with one real client
4. GA4 sync (ga4_sync.py) — test with one real client
5. Metrics DB layer (metrics_db.py)
6. Backend API endpoints (server.py)
7. Frontend: CDN + nav item + view container (index.html)
8. Dashboard rendering + charts (script.js)
9. Client-facing mode + token auth (script.js + server.py)
10. CSS styling (style.css)

## Verification Checklist

- [ ] Service account loads and can list GSC properties / GA4 accounts
- [ ] `POST /api/clients/{id}/sync` syncs data → verify rows in metrics table
- [ ] Reporting view renders all 4 charts with real data for a synced client
- [ ] Share token generates → `/dashboard/{token}` loads in incognito without admin controls
- [ ] Date range toggle (30d/60d/90d) updates charts correctly
- [ ] Un-synced client shows graceful empty state
- [ ] Local dev works: `uvicorn server:app --reload` at `http://localhost:8000`

## GCP Setup Checklist (Manual Steps)

- [ ] Enable Search Console API in Google Cloud Console
- [ ] Enable Google Analytics Data API in Google Cloud Console
- [ ] Create a service account (or use existing one)
- [ ] Download service account JSON credentials
- [ ] For each client: add service account email as user on their GSC property (read-only)
- [ ] For each client: add service account email as Viewer on their GA4 property
- [ ] Set `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_ACCOUNT_PATH` env var in Railway
