# ProofPilot Agency Hub — Feature Roadmap

**Live:** `https://proofpilot-agents.up.railway.app`
**Stack:** Python 3.11 + FastAPI + SSE | Claude Opus 4.6 | Railway | Pure JS frontend

Phases are ordered by dependency and business value. Complete a phase before starting the next unless items are explicitly marked independent.

---

## Phase 1 — Core Platform ✅ COMPLETE

The foundational platform is live and production-ready.

- [x] 7 active AI workflows (SEO Audit, Prospect Audit, Keyword Gap, Blog Post, Service Page, Location Page, Home Service Content)
- [x] Live SSE streaming terminal — tokens stream in real time from Claude
- [x] Branded `.docx` export — every job generates a downloadable Word doc
- [x] SQLite job persistence — jobs survive server restarts via Railway Volume
- [x] Content Library — all completed jobs organized by client
- [x] Per-client hub — activity view per client with quick workflow launch
- [x] Workflow categorization with sample previews in the launch modal
- [x] DataForSEO integration — SERP, Maps, Labs, Keywords, GBP, Difficulty endpoints
- [x] Search Atlas integration — organic data, backlinks, holistic audit scores
- [x] Health check + crash-proof deployment (Dockerfile CMD, no Railway startCommand override)

---

## Phase 2 — Client Data Layer

**Why first:** Clients are currently hardcoded arrays in `script.js`. Every new client requires a code edit and re-deploy. This blocks everything downstream.

### 2.1 — Client CRUD API
- [x] `POST /api/clients` — create client (name, domain, service, location, monthly_revenue, avg_job_value, notes, status)
- [x] `GET /api/clients` — list all clients (replace hardcoded JS array)
- [x] `PATCH /api/clients/{id}` — update client fields
- [x] `DELETE /api/clients/{id}` — soft-delete (status = inactive)
- [x] SQLite `clients` table with all fields + `created_at`, `updated_at`
- [x] Frontend: "Add Client" modal in the Clients view
- [x] Frontend: Edit client inline from client hub

### 2.2 — Strategy Context Persistence
- [x] Save per-client strategy context in DB (currently typed fresh every workflow run)
- [x] Auto-populate strategy context field when client is selected in workflow modal
- [x] Edit strategy context from client hub → persists to DB

### 2.3 — Content Approval Status
- [x] Add `approved`, `approved_at` columns to jobs table
- [x] "Mark as Approved" toggle in Content Library card
- [x] Approved content gets a visual badge (green checkmark)
- [ ] Filter Content Library by: All / Approved / Pending Review

### 2.4 — Input Validation & UX Polish
- [ ] Domain format validation before workflow launch (strip `https://`, `www.`, trailing slash)
- [ ] Required field error states in workflow modal
- [ ] TTL-based cleanup of `temp_docs/` — delete `.docx` files older than 30 days
- [ ] Regenerate missing `.docx` from stored content (if Railway restarted and wiped temp_docs)

---

## Phase 3 — Google Drive Publishing

**The content pipeline:** ProofPilot generates → agency reviews → approves → pushes to Drive → automation publishes to WordPress/Webflow/etc.

### Folder Structure (auto-created by ProofPilot)
```
ProofPilot Clients/               ← shared top-level folder
├── All Thingz Electric/
│   ├── Location Pages/
│   ├── Service Pages/
│   ├── Blog Posts/
│   ├── Home Service Content/
│   ├── SEO Audits/
│   ├── Prospect Analyses/
│   └── Keyword Gap Reports/
├── Steadfast Plumbing/
│   └── ...
└── [New Client]/
    └── ...
```

### Workflow → Drive Folder Mapping
| Workflow ID | Drive Folder |
|-------------|-------------|
| `location-page` | Location Pages |
| `service-page` | Service Pages |
| `seo-blog-post` | Blog Posts |
| `home-service-content` | Home Service Content |
| `website-seo-audit` | SEO Audits |
| `prospect-audit` | Prospect Analyses |
| `keyword-gap` | Keyword Gap Reports |

### Implementation

**Auth (Service Account — no user login required)**
- [ ] Create Google Cloud project + enable Drive API
- [ ] Create Service Account, download JSON key
- [ ] Share `ProofPilot Clients/` folder with service account email (Editor access)
- [ ] Set `GOOGLE_SERVICE_ACCOUNT_JSON` (base64-encoded) + `GOOGLE_DRIVE_ROOT_FOLDER_ID` in Railway env vars

**Backend**
- [ ] Add `google-api-python-client` + `google-auth` to `requirements.txt`
- [ ] Create `utils/google_drive.py`:
  - `get_or_create_folder(parent_id, name)` — idempotent folder creation
  - `upload_docx(client_name, workflow_id, job_id, docx_path)` → returns `(file_id, web_view_url)`
  - `regenerate_and_upload(job_id)` — rebuild `.docx` from stored content, then upload
- [ ] Add `drive_file_id`, `drive_url`, `approved`, `approved_at` columns to jobs table
- [ ] `POST /api/jobs/{job_id}/approve` — approve job + upload to Drive → returns `{ drive_url }`
- [ ] Handle missing `.docx` gracefully — regenerate from SQLite content before upload

**Frontend**
- [ ] "Approve & Push to Drive" button on each Content Library card (replaces plain "Approve" toggle)
- [ ] Loading state during Drive upload ("Pushing to Drive...")
- [ ] After push: show Google Drive icon + "Open in Drive" link on the card
- [ ] Green "Approved" badge on approved cards
- [ ] Content Library filter: All / Approved / Pending Review

**Future automation (out of scope for this phase — handled externally)**
- Google Drive → WordPress via Zapier/Make trigger on new file in folder
- Google Drive → Webflow CMS via same automation
- ProofPilot generates, agency approves, automation publishes — zero manual copy-paste

---

## Phase 4 — Advanced Workflows

New workflow types that expand what ProofPilot can deliver.

### 4.1 — On-Page Technical Audit
- [ ] `workflows/onpage_audit.py` — uses DataForSEO On-Page API (task-based, 2–10 min)
- [ ] Async task submission → poll pattern: submit crawl task, store `task_id`, poll until done
- [ ] Background task system in `server.py` (task status endpoint)
- [ ] Report: Core Web Vitals, crawl errors, missing meta, duplicate content, internal link health, page speed
- [ ] Requires: async task polling UI in frontend (progress bar with estimated time)

### 4.2 — Monthly Client Report
- [ ] `workflows/monthly_report.py` — aggregates job history + live rank data
- [ ] Pulls: all jobs created this month, current organic rankings vs. last month, keyword volume changes
- [ ] Claude synthesizes into executive summary + recommendations
- [ ] Output: branded `.docx` report card — suitable for client delivery

### 4.3 — GBP Audit Workflow
- [ ] `workflows/gbp_audit.py`
- [ ] Compare client GBP completeness vs. top 3 competitors
- [ ] Check: photos count, categories, attributes, Q&A, review response rate, post frequency
- [ ] Uses `get_competitor_gmb_profiles()` (already built in `utils/dataforseo.py`)
- [ ] Output: GBP Optimization Checklist with specific gaps + competitor benchmarks

### 4.4 — Review Intelligence
- [ ] `workflows/review_intelligence.py`
- [ ] Pull competitor reviews via DataForSEO Business Data API
- [ ] Claude performs sentiment analysis → identifies recurring themes, complaints, praise patterns
- [ ] Output: "What competitors' customers complain about" → client talking points + service differentiators

### 4.5 — Seasonality & Content Calendar
- [ ] `workflows/seasonality_report.py`
- [ ] Google Trends subregion data for the client's primary service keywords
- [ ] Maps seasonal demand peaks to content calendar
- [ ] Output: 12-month content calendar with recommended publish dates tied to search demand

### 4.6 — Page Design Agent

**The problem:** Current content workflows (service page, location page, blog post) output copy only — markdown text that still needs a designer and developer to turn into an actual page. That handoff gap costs hours per page and produces inconsistent results across clients. A developer receiving a 1,000-word markdown doc has to make every layout decision from scratch: where the CTA goes, how the trust signals are arranged, what the hero looks like on mobile, where images sit relative to text.

**The solution:** A new workflow that outputs a complete, developer-ready page design — full HTML/CSS with responsive layout, visual hierarchy, section architecture, image art direction, and conversion-optimized component placement. The output is a page a developer can drop into WordPress, Webflow, or any CMS with minimal adaptation. It's also a standalone artifact Matthew can open in a browser to review the design before handing it off.

**Why this matters for growth:** This turns ProofPilot from a copy shop into a full page production system. Instead of delivering a Word doc that needs 2-4 hours of design/dev work per page, we deliver a ready-to-implement design. For programmatic content (bulk location pages, service pages across cities), this is the difference between "here are 30 docs of text" and "here are 30 pages ready to go live."

#### Workflow: `page-design`

**File:** `workflows/page_design.py`

**Inputs:**
```json
{
  "page_type": "service-page | location-page | landing-page | blog-post",
  "domain": "allthingzelectric.com",
  "business_type": "electrician",
  "service": "panel upgrade",
  "location": "Chandler, AZ",
  "brand_colors": "#1a3a5c, #f59e0b, #ffffff",
  "brand_style": "modern and clean | bold and industrial | warm and friendly",
  "differentiators": "same-day service, master electrician, 15 years",
  "price_range": "$1,200–$3,500",
  "phone": "(480) 555-0123",
  "cta_text": "Schedule Your Free Estimate",
  "image_notes": "has hero photo of technician at panel, customer testimonial headshots",
  "reference_url": "optional — URL of a page whose layout/style to reference",
  "notes": "optional"
}
```

#### What the Agent Outputs

A single, self-contained HTML file with embedded CSS that includes:

**1. Full Page Layout (HTML + CSS)**
- Complete semantic HTML5 structure — `<header>`, `<main>`, `<section>`, `<footer>`
- Inline CSS (no external dependencies) so the file renders standalone in any browser
- Responsive design with three breakpoints: mobile (< 768px), tablet (768–1024px), desktop (> 1024px)
- CSS Grid / Flexbox layouts — no frameworks, no Bootstrap, clean modern CSS
- The HTML is clean enough to extract sections and drop into WordPress page builders (Elementor, Divi, Gutenberg blocks) or Webflow

**2. Section-by-Section Design Architecture**

Every page type gets a conversion-optimized section sequence. For service pages:

| Section | Layout | Purpose |
|---------|--------|---------|
| **Hero** | Full-width, split layout (text left / image right on desktop, stacked on mobile) | Headline + subhead + primary CTA + trust badges |
| **Trust Bar** | Horizontal strip with icon + stat pairs | License, insurance, years, review count — visible without scrolling |
| **Problem / Pain** | Centered text block, max-width 720px | Name the customer's problem before pitching the solution |
| **Service Details** | Two-column cards or icon grid | What's included — specific scope items, not vague promises |
| **Pricing Transparency** | Highlighted callout box with range | Real price ranges + what affects cost |
| **Process Steps** | Numbered vertical timeline or horizontal stepper | Step-by-step from call to completion |
| **Social Proof** | Testimonial cards (photo + quote + name + service) | Real reviews, not generic praise |
| **Local Proof** | Map embed placeholder + neighborhood list | Geographic anchors for local SEO |
| **FAQ** | Accordion component (expand/collapse) | Schema-ready Q&A — real Google queries |
| **Final CTA** | Full-width colored band, large button, phone number | Urgency close with contact options |
| **Footer** | Multi-column: nav, contact, service areas, legal | Standard footer with local business info |

Location pages, landing pages, and blog posts each get their own section sequence optimized for their conversion goal.

**3. Visual Design System (per page)**
- Typography hierarchy: H1 size/weight, H2, H3, body, caption — using web-safe fonts or Google Fonts `<link>` tags
- Color application: primary for CTAs and headings, secondary for accents and hover states, neutral for body text and backgrounds
- Spacing rhythm: consistent vertical spacing between sections (e.g., 80px desktop, 48px mobile)
- Button styles: primary CTA (filled, bold), secondary CTA (outlined), with hover/active states
- Card and container styles: border-radius, box-shadow, padding patterns
- Image treatment: aspect ratios, object-fit rules, overlay styles for hero images

**4. Image Art Direction**
Since the workflow won't have actual images, it includes:
- Placeholder `<div>`s with exact dimensions and aspect ratios for every image slot
- Background color placeholders that match the brand palette
- Alt text pre-written for SEO
- Detailed comments in the HTML describing what image should go in each slot:
  ```html
  <!-- IMAGE: Hero photo — technician working at electrical panel,
       professional lighting, customer's home visible in background.
       Recommended: 1200x600px, landscape orientation.
       If no real photo: use a high-quality stock photo of electrical work. -->
  <div class="hero-image" style="aspect-ratio: 2/1; background: #e5e7eb;">
    <span class="placeholder-label">Hero Image — 1200×600</span>
  </div>
  ```

**5. Interactive Components**
- FAQ accordion with CSS-only expand/collapse (no JavaScript dependencies)
- Smooth scroll navigation from hero CTA to contact section
- Mobile hamburger menu (CSS-only or minimal vanilla JS)
- Sticky header on scroll (CSS `position: sticky`)
- Optional: before/after image slider placeholder, review carousel placeholder

**6. SEO Built Into the HTML**
- Proper heading hierarchy (single H1, logical H2/H3 nesting)
- Meta title and meta description pre-written in `<head>`
- Open Graph tags for social sharing
- JSON-LD LocalBusiness + Service schema embedded in `<script type="application/ld+json">`
- Canonical URL placeholder
- Image alt text on every image slot
- Semantic HTML elements for accessibility (`<nav>`, `<main>`, `<article>`, `<aside>`)

**7. Developer Handoff Notes**
A comment block at the top of the HTML file with:
- Platform-specific implementation notes (WordPress, Webflow, custom)
- Which sections map to which page builder components
- Font loading instructions (Google Fonts links or self-hosted font files)
- Image specs: exact dimensions, format recommendations (WebP with JPEG fallback)
- Performance notes: lazy loading attributes, critical CSS identification
- Any JavaScript that should be added for enhanced interactivity (form validation, analytics events)

#### Output Formats

| Format | Description |
|--------|-------------|
| **HTML preview** | Self-contained `.html` file — open in browser to see the full design |
| **Branded `.docx`** | Design specification document with section descriptions, layout diagrams (ASCII), color specs, typography specs, and the full copy — for clients or designers who prefer a document |

#### Implementation Plan

**Backend**
- [ ] Create `workflows/page_design.py` with page-type-specific system prompts
- [ ] System prompt includes CSS best practices, responsive patterns, accessibility requirements, conversion layout patterns
- [ ] Separate section prompt templates per page type (service, location, landing, blog)
- [ ] Claude generates the full HTML/CSS in a single streaming pass — the HTML IS the design
- [ ] Post-processing: extract the HTML from Claude's response, validate it's well-formed, save as `.html`
- [ ] Generate `.docx` companion with: design overview, section-by-section specs, copy text, implementation notes
- [ ] Add `/api/preview/{job_id}` endpoint — serves the generated HTML file directly so it renders in-browser
- [ ] Register workflow in `server.py` with `WORKFLOW_TITLES` and `event_stream()` routing

**Frontend**
- [ ] Add `page-design` to `WORKFLOWS` array in `script.js` (category: `content`)
- [ ] New modal panel `#modalInputsPageDesign` with fields: page_type dropdown, domain, business_type, service, location, brand_colors (color picker or text), brand_style dropdown, differentiators, price_range, phone, cta_text, image_notes, reference_url, notes
- [ ] Wire into `selectWorkflow()`, `checkRunReady()`, `launchWorkflow()`
- [ ] After job completion: "Preview Design" button alongside "Download .docx" — opens the HTML preview in a new tab via `/api/preview/{job_id}`
- [ ] In Content Library: page design jobs show a thumbnail preview or "View Design" link

**Preview System**
- [ ] `POST /api/run-workflow` returns the streaming copy as usual (the HTML source)
- [ ] On completion, save the HTML file to `temp_docs/{job_id}.html`
- [ ] `GET /api/preview/{job_id}` serves the HTML with `Content-Type: text/html` — browser renders the full design
- [ ] Preview opens in a new tab so Matthew can review the design at full width, test responsive behavior by resizing
- [ ] Optional: add a simple toolbar at the top of the preview (injected via JS) with "Desktop / Tablet / Mobile" viewport toggles using iframe resizing

**Prompt Engineering (the hard part)**
- [ ] Build a master system prompt that teaches Claude modern frontend design: CSS Grid, Flexbox, custom properties, responsive units (clamp, min/max), accessible patterns
- [ ] Include a "design library" of proven section patterns in the system prompt — hero layouts, trust bars, testimonial cards, FAQ accordions, CTA bands — so Claude assembles from proven components rather than inventing from scratch
- [ ] Page-type-specific conversion architecture: service pages optimize for phone calls, location pages optimize for "near me" intent, landing pages optimize for form fills, blog posts optimize for time-on-page and internal link clicks
- [ ] Brand adaptation instructions: how to apply provided brand colors to the design system (primary → CTAs and headings, secondary → accents, neutral → backgrounds)
- [ ] Test with 5+ real client scenarios, iterate the prompt until output quality is consistent
- [ ] Consider a two-pass approach if single-pass quality isn't sufficient: Pass 1 generates the design architecture + copy, Pass 2 generates the full HTML/CSS implementation

#### Quality Bar

A page design output should meet these criteria before we consider the workflow production-ready:

- [ ] Opens in Chrome, Firefox, Safari and renders correctly without errors
- [ ] Looks good at 375px (mobile), 768px (tablet), and 1440px (desktop) — not just "doesn't break" but actually looks designed for each
- [ ] Every section has a clear visual purpose — no "wall of text" sections
- [ ] CTA buttons are prominent, above the fold, and repeated throughout
- [ ] Page loads instantly (no external dependencies except Google Fonts)
- [ ] A developer can read the HTML and understand the intended structure in under 5 minutes
- [ ] Copy quality matches or exceeds the existing service-page workflow output
- [ ] JSON-LD schema is valid (test with Google Rich Results tester)

#### Stretch Goals (post-launch)
- [ ] **Style variants:** Generate 2-3 design variants per request (e.g., "minimal," "bold," "editorial") — Matthew picks the one that fits the client
- [ ] **Component library:** Build a reusable component library over time from the best sections Claude generates — feed it back into the prompt as examples
- [ ] **Figma export:** Generate a Figma-compatible design file (via Figma API or `.fig` format) for clients who want pixel-perfect handoff
- [ ] **WordPress theme snippet:** Output a WordPress-specific version with proper theme function calls, Elementor widget mappings, or Gutenberg block markup
- [ ] **A/B variant generation:** Generate two hero/CTA variants for split testing with conversion tracking recommendations
- [ ] **Chain with existing workflows:** Run the service-page copy workflow first, then feed its output into page-design as the copy layer — separating content strategy from visual design

---

## Phase 5 — Publishing & Distribution

Direct content publishing from ProofPilot to client websites.

### 5.1 — WordPress Direct Publish
- [ ] `POST /api/jobs/{job_id}/publish/wordpress` — push approved content to WordPress REST API
- [ ] Client configuration: store WP site URL + Application Password in clients table
- [ ] Content type routing: blog post → `wp/v2/posts`, service/location page → `wp/v2/pages`
- [ ] Set status to `draft` initially — agency reviews in WP before going live
- [ ] Return WP post URL, store in job record

### 5.2 — Webflow CMS Push
- [ ] Similar to WordPress but uses Webflow Data API
- [ ] Map ProofPilot workflow types to Webflow Collection IDs (configured per client)
- [ ] Push as draft CMS items

### 5.3 — Scheduled Automations
- [ ] Cron-triggered monthly report generation (first of each month, per active client)
- [ ] Configurable per client: which workflows to run automatically, on what schedule
- [ ] Notification system: email/Slack webhook when automated run completes
- [ ] Railway Cron service or background task queue (APScheduler)

### 5.4 — Bulk Content Generation
- [ ] Run the same workflow across multiple clients in sequence (overnight batch)
- [ ] Run location-page workflow for a list of 10 cities for one client
- [ ] Progress tracking, per-item status, bulk download as ZIP

---

## Phase 6 — Agency Intelligence & Scale

Analytics, client-facing access, and white-labeling.

### 6.1 — Performance Tracking
- [ ] GA4 integration: connect client GA4 properties, pull organic traffic metrics
- [ ] Track which ProofPilot-generated pages are ranking and driving traffic
- [ ] Rank change tracking: compare current DataForSEO rankings vs. baseline from first audit

### 6.2 — Cross-Client Dashboard
- [ ] Agency-level KPIs: total content pieces generated, total approved, total published
- [ ] Industry benchmarks by service type (average audit score, average keyword gap size)
- [ ] "Most active clients" and "clients needing attention" widgets

### 6.3 — Client-Facing Report Portal
- [ ] Read-only client login (separate from agency login)
- [ ] Clients can view their approved content, download reports, see what's in progress
- [ ] No workflow launch access — view only

### 6.4 — White-Label & Agency Settings
- [ ] Agency branding on `.docx` reports (upload logo, set agency name/colors)
- [ ] Custom subdomain support (`clients.youragency.com`)
- [ ] Per-agency configuration: which workflows are visible, default strategy contexts

---

## Tech Debt Backlog

Items that don't fit a phase but should be resolved as bandwidth allows.

| Issue | Priority | Notes |
|-------|----------|-------|
| Hardcoded CLIENTS in `script.js` | High | Resolved in Phase 2.1 |
| US-only location parsing | Medium | Add international format support via DFS Appendix API |
| No domain format validation | Medium | Resolved in Phase 2.4 |
| `temp_docs/` not cleaned up | Low | TTL cleanup in Phase 2.4 |
| No test coverage | Medium | At minimum: unit tests for keyword gap computation, docx generation |
| No request logging | Low | Add structured logging for all workflow runs |
| Missing `.env.example` file | Low | Create with all required env var keys documented |

---

## Google Drive Setup Guide (for Phase 3)

When ready to implement, here's what's needed from your side:

1. **Google Cloud Console** — create project, enable Drive API
2. **Service Account** — create, download JSON key file
3. **Share folder** — create `ProofPilot Clients/` in your Google Drive, share it with the service account email (it looks like `proofpilot@your-project.iam.gserviceaccount.com`)
4. **Railway env vars** to add:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — base64-encoded contents of the JSON key file
   - `GOOGLE_DRIVE_ROOT_FOLDER_ID` — the folder ID from the Drive URL of `ProofPilot Clients/`

Once those are in Railway, Phase 3 can be implemented in a single session.

