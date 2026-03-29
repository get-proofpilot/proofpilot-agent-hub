/* ═══════════════════════════════════════════════════════
   PROOFPILOT AGENCY HUB — script.js
   Data models, rendering, terminal typewriter, agent toggle
═══════════════════════════════════════════════════════ */

/* ── DATA MODELS ── */

let CLIENTS = [];

function _autoInitials(name) {
  if (!name) return '?';
  return name.split(' ').filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

function mapApiClient(c) {
  return {
    id: c.client_id,
    name: c.name,
    domain: c.domain || '',
    service: c.service || '',
    location: c.location || '',
    plan: c.plan || 'Starter',
    monthly_revenue: c.monthly_revenue || '',
    avg_job_value: c.avg_job_value || '',
    status: c.status || 'active',
    color: c.color || '#0051FF',
    initials: c.initials || _autoInitials(c.name),
    notes: c.notes || '',
    strategy_context: c.strategy_context || '',
    // Display-only placeholders (computed from jobs in a future phase)
    score: 0,
    trend: '→',
    avgRank: '–',
    lastJob: '–',
  };
}

async function loadClients() {
  try {
    const res = await fetch(`${API_BASE}/api/clients`);
    if (!res.ok) return;
    const data = await res.json();
    CLIENTS = data.clients.map(mapApiClient);
    renderClients();
    renderClientSelect();
    renderRoster();
    updateClientsBadge();
  } catch (e) {
    // Server not available — CLIENTS stays empty
  }
}

const WORKFLOWS = [
  /* ── SEO ANALYSIS ── */
  { id: 'prospect-audit', icon: '🎯', title: 'Prospect SEO Market Analysis',
    desc: 'Full sales-pitch analysis — real competitor traffic, per-city keyword tables, service-specific breakdowns, $-value ROI projections, and a 3-phase strategy that closes deals.',
    time: '~8 min', status: 'active', skill: 'prospect-audit', category: 'seo',
    preview: '# SEO Market Opportunity: Steadfast Plumbing — Gilbert, AZ\n\n**3,990 monthly searches. $377K annual ad value. 7 named competitors.**\n\n## Competitor Landscape\n| Competitor | Monthly Traffic | Value |\n|---|---|---|\n| rotorooter.com | 2,340,262/mo | $66M/mo |\n| parkerandsons.com | 307,444/mo | $5.3M/mo |\n| ezflowplumbingaz.com | 8,946/mo | $208K/mo |\n| **Steadfast Plumbing** | **Your opportunity** | |\n\n## High-Value Keywords ($100+ CPC)\n- "emergency plumber" — $313.04/click, 30/mo\n- "emergency plumber gilbert" — $140.71/click, 140/mo\n- "emergency plumber near me" — $108.37/click, 210/mo\n\n**WHY THIS MATTERS:** Every organic click on "emergency plumber" saves $313/click vs. Google Ads. 12 months of rankings = $11,269 in ad spend you keep.\n\n## Per-City Keyword Tables (Gilbert, Chandler, Mesa, Tempe)\n## Service Breakdowns (Water Heater, Water Treatment, Drain, Emergency)\n## ROI: 12–48 new customers/month → $64,800–$259,200/year' },
  { id: 'website-seo-audit', icon: '🔍', title: 'Website & SEO Audit',
    desc: 'Full technical SEO audit — performance, structure, local signals, backlinks, and a ranked action list.',
    time: '~8 min', status: 'active', skill: 'website-seo-audit', category: 'seo',
    preview: '# SEO Audit: All Thingz Electric — Chandler, AZ\n\n**Overall Score: 63/100** — Est. 12–18 leads/month lost to ranking gaps.\n\n## Critical Issues\n- "Panel upgrade Chandler AZ" — Position #23 (first page achievable in 90 days)\n- GBP missing 8 service categories vs. top competitor\n- 0 backlinks from local Chandler business directories\n\n## Top Priority Action\nCreate 3 service pages targeting underranked commercial keywords. Estimated ROI: 8–12 inbound calls/month within 60 days.' },
  { id: 'keyword-gap', icon: '📊', title: 'Keyword Gap Analysis',
    desc: 'Find every keyword competitors rank for that you don\'t — sorted by revenue opportunity.',
    time: '~6 min', status: 'active', skill: 'keyword-gap', category: 'seo',
    preview: '# Keyword Gap Report: All Thingz Electric vs. 3 Competitors\n\n**47 untapped keywords** your top competitors rank for — you rank for 0.\n\nTop Opportunities by Revenue:\n- "electrical panel upgrade chandler" — 210/mo searches, Difficulty 38, Est. $4,200/mo\n- "ev charger installation scottsdale" — 170/mo searches, Difficulty 31, Est. $3,400/mo\n- "electrical inspection chandler az" — 140/mo searches, Difficulty 27, Est. $2,100/mo\n\n**Priority Plan:** 3 service pages + 2 blog posts covers 74% of total opportunity.' },
  { id: 'ai-search-report', icon: '🤖', title: 'AI Search Visibility Report',
    desc: 'See how your brand appears in AI Overviews, featured snippets, and knowledge panels — with a plan to get cited.',
    time: '~6 min', status: 'active', skill: 'ai-search-report', category: 'seo',
    preview: '# AI Search Visibility Report: All Thingz Electric\n\n**AI Visibility Score: 22/100** — Your competitors are being cited by Google AI Overviews. You are not.\n\n## Key Findings\n- 7 of 10 target keywords trigger AI Overviews\n- Competitor "Parker & Sons" cited in 4 AI Overviews\n- You appear in 0 AI Overviews — missing $12K/mo in traffic\n\n## Top Opportunity\nCreate FAQ content answering "how much does a panel upgrade cost in Chandler?" — this query has an AI Overview citing a competitor blog post.' },
  { id: 'backlink-audit', icon: '🔗', title: 'Backlink Audit',
    desc: 'Full backlink health check — referring domains, anchor text, spam score, competitor comparison, and link-building plan.',
    time: '~5 min', status: 'active', skill: 'backlink-audit', category: 'seo',
    preview: '# Backlink Audit: All Thingz Electric\n\n**Backlink Health: 54/100** — 127 backlinks from 43 domains. Competitor average: 312 backlinks from 89 domains.\n\n## Key Issues\n- 68% of anchors are branded or URL-only — need more keyword-rich anchors\n- 12 broken backlinks losing link equity\n- Missing from Chandler Chamber of Commerce, BBB, and 3 local directories\n\n## Top Opportunities\n1. Replicate 14 competitor links from local directories\n2. Fix 12 broken backlinks → instant authority recovery\n3. Guest post on azcentral.com home improvement section' },
  { id: 'onpage-audit', icon: '🔬', title: 'On-Page Technical Audit',
    desc: 'Deep single-page technical audit — Core Web Vitals, meta tags, heading structure, and a prioritized fix list.',
    time: '~4 min', status: 'active', skill: 'onpage-audit', category: 'seo',
    preview: '# On-Page Audit: /panel-upgrade — All Thingz Electric\n\n**Page Health: 47/100** — 6 critical issues found.\n\n## Critical Fixes\n1. Title tag is 13 chars ("Panel Upgrade") — should be 50-60 with location keyword\n2. No H1 tag — the page has no primary heading element\n3. LCP is 4.8s — needs image optimization and lazy loading\n4. Only 2 internal links — competitors average 12+\n\n## vs. Top Competitor\n#1 ranking page has 2,400 words, 8 H2s, FAQ schema, and 14 internal links. This page: 340 words, 1 H2, no schema.' },
  { id: 'seo-research', icon: '🧠', title: 'SEO Research & Content Strategy',
    desc: 'The strategic brain — analyzes your entire keyword universe, clusters by intent, and produces a prioritized content roadmap.',
    time: '~10 min', status: 'active', skill: 'seo-research', category: 'seo',
    preview: '# SEO Content Strategy: All Thingz Electric — Chandler, AZ\n\n**Total Market Opportunity: $47,000/mo in organic traffic value**\n\n## Keyword Universe: 156 keywords discovered\n- Commercial (42): "electrician chandler az" 2,400/mo, "panel upgrade chandler" 210/mo\n- Cost Intent (18): "how much does rewiring cost phoenix" 1,200/mo\n- Comparison (12): "rheem vs carrier water heater" 880/mo\n- Informational (84): "signs you need panel upgrade" 450/mo\n\n## Content Roadmap\n**Week 1:** 3 service pages targeting commercial keywords (est. $4,200/mo value)\n**Month 1:** 8 location pages + 4 cost guides (est. $12,000/mo value)' },
  { id: 'competitor-intel', icon: '🕵️', title: 'Competitor Intelligence Report',
    desc: 'Deep competitive teardown — keyword gaps, backlink gaps, content gaps, and a specific plan to outrank every competitor.',
    time: '~8 min', status: 'active', skill: 'competitor-intel', category: 'seo',
    preview: '# Competitor Intelligence: All Thingz Electric vs. 3 Competitors\n\n**Competitive Position: Outranked** — Top competitor captures 4x your organic traffic.\n\n## Domain Comparison\n| Metric | You | Parker & Sons | Efficient Electric |\n|---|---|---|---|\n| Keywords | 47 | 312 | 189 |\n| Traffic | 280/mo | 4,200/mo | 1,800/mo |\n\n## Biggest Gap\n23 commercial keywords your competitors rank for that you rank for ZERO.\nTotal addressable volume: 8,400/mo searches.' },
  { id: 'schema-generator', icon: '🧩', title: 'Schema Generator',
    desc: 'Auto-generate structured data markup for target pages — local business, FAQ, service, and article schemas.',
    time: '~2 min', status: 'active', skill: 'schema-generator', category: 'seo',
    preview: '# Schema Markup: All Thingz Electric — Chandler, AZ\n\n## Strategy Overview\n3 schema types recommended: LocalBusiness, FAQPage, Service\n\n## LocalBusiness Schema\n```json\n{\n  "@context": "https://schema.org",\n  "@type": "Electrician",\n  "name": "All Thingz Electric",\n  "address": { "@type": "PostalAddress", "addressLocality": "Chandler", "addressRegion": "AZ" },\n  "telephone": "(480) 555-0182"\n}\n```\n\n## FAQPage Schema (5 Q&As)\n## Service Schema (per service)\n## Implementation Guide' },
  { id: 'geo-content-audit', icon: '🎯', title: 'GEO Content Citability Audit',
    desc: 'Score content against the CITE framework — Citable Structure, Information Density, Topical Authority, Entity Clarity. Get specific rewrites to appear in ChatGPT, Perplexity, and Google AI Overviews.',
    time: '~4 min', status: 'active', skill: 'geo-content-audit', category: 'seo',
    preview: '# GEO Citability Audit\n\n## CITE Framework Score\n| Dimension | Score | Status | Primary Issue |\n|---|---|---|---|\n| C — Citable Structure | 2/5 | 🔴 | Headers are vague ("Overview", "Introduction") — not extractable as standalone claims |\n| I — Information Density | 2/5 | 🔴 | No specific numbers, no named examples — every paragraph could appear in any article |\n| T — Topical Authority | 3/5 | 🟡 | 1 article on this topic vs. competitor\'s 12 supporting pieces |\n| E — Entity Clarity | 3/5 | 🟡 | Business name inconsistent — "the company", "we", "All Thingz Electric" used interchangeably |\n| **Overall Citability** | **10/20** | | |\n\n## Target Query Analysis\n| Query | Would AI Cite This? | Why |\n|---|---|---|\n| "how much does a panel upgrade cost in Chandler" | ❌ No | No price data, vague claims, no specific numbers |\n| "electrician chandler az" | ⚠️ Maybe | Topical but competing content has specific pricing tables |\n\n## Prioritized Recommendations\n1. Add "$1,800–$3,200 for a 200-amp panel upgrade" — current: "pricing varies"\n2. Change H2 "Our Services" → "How Electrical Panel Upgrades Work in Chandler, AZ"' },
  { id: 'seo-content-audit', icon: '📝', title: 'SEO Content Audit',
    desc: 'Paste content and target keyword — get a full on-page SEO audit without needing a live URL. Covers title, meta, headers, intent alignment, keyword usage, E-E-A-T, and a prioritized fix list.',
    time: '~3 min', status: 'active', skill: 'seo-content-audit', category: 'seo',
    preview: '# SEO Content Audit\n\n## Page Overview\n- Target keyword: "electrician chandler az"\n- Search intent: Navigational/Commercial — searchers want to hire, not learn\n- Intent match: ⚠️ Partial — content reads as informational blog post, not service page\n\n## On-Page Elements\n| Element | Current | Count | Status | Issue |\n|---|---|---|---|---|\n| Title tag | "Chandler Electrician" | 19 chars | ❌ | Too short, missing brand, keyword buried |\n| Meta description | Missing | 0 chars | ❌ | Auto-generated by WordPress — no CTA |\n| H1 | "Welcome to All Thingz Electric" | — | ❌ | No keyword, not what searchers want to see |\n\n## Prioritized Fix List\n| Priority | Issue | Exact Fix | Time | Impact |\n|---|---|---|---|---|\n| 1 | Missing title keyword | Change to: "Electrician in Chandler, AZ | All Thingz Electric" (52 chars) | 5min | High |' },
  { id: 'technical-seo-review', icon: '⚙️', title: 'Technical SEO Review',
    desc: 'Strategic technical SEO audit + ready-to-paste JSON-LD schema templates. Covers crawlability, Core Web Vitals recommendations, site architecture, and generates LocalBusiness, FAQPage, Service, and Article schemas.',
    time: '~4 min', status: 'active', skill: 'technical-seo-review', category: 'seo',
    preview: '# Technical SEO Review: allthingzelectric.com\n\n## Technical Health Checklist\n| Check | Status | Action for WordPress |\n|---|---|---|\n| robots.txt | ✅ Exists | Verify wp-admin blocked, CSS/JS allowed |\n| XML sitemap | ⚠️ Exists but not submitted | Submit at search.google.com/search-console |\n| Core Web Vitals: LCP | ❌ 4.2s (target <2.5s) | Install WP Rocket, preload hero image |\n| Core Web Vitals: CLS | ⚠️ 0.18 (target <0.1) | Set image dimensions in Media Library |\n\n## LocalBusiness Schema (Ready to Paste)\n```json\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "Electrician",\n  "name": "All Thingz Electric",\n  "telephone": "(480) 555-0182",\n  "address": { "@type": "PostalAddress", "addressLocality": "Chandler", "addressRegion": "AZ" }\n}\n</script>\n```\n## FAQPage Schema — 5 Q&As\n## Service Schema\n## Implementation Guide + 30-Day Plan' },
  { id: 'programmatic-seo-strategy', icon: '🏗️', title: 'Programmatic SEO Strategy',
    desc: 'Build a scalable content system — template design, data sources, quality controls, and a staged launch plan for location pages, comparison pages, or any repeatable content type.',
    time: '~5 min', status: 'active', skill: 'programmatic-seo-strategy', category: 'seo',
    preview: '# Programmatic SEO Strategy\n\n## Opportunity Assessment\n| Factor | Assessment |\n|---|---|\n| Page type | Location pages — "[Service] in [City, State]" |\n| Estimated pages | 87 cities across Phoenix metro |\n| Est. total search volume | 14,200/month across all city variants |\n| Competitor presence | Parker & Sons has 43 city pages — you have 0 |\n| Differentiation opportunity | Pricing specific to each city\'s permit costs |\n\n## Template Design\n**Unique Value Layer (what makes each page genuinely different):**\n- City-specific permit cost data (public record)\n- Local housing stock context (avg home age, common panel sizes)\n- Named local landmarks as geographic anchors\n- City-specific competitors (pulled from Google Maps per city)\n\n## Staged Launch Plan\nPhase 1 (10 pages): Gilbert, Mesa, Tempe, Scottsdale, Queen Creek, Ahwatukee, Maricopa, Apache Junction, Avondale, Peoria\nPhase 2 (30 pages): After 4-6 week validation\nPhase 3: Remaining 47 cities' },
  { id: 'competitor-seo-analysis', icon: '🔭', title: 'Competitor SEO Analysis',
    desc: 'Find out WHY competitors outrank you — not just that they do. Identifies content gaps, SERP feature opportunities, format mismatches, and a 90-day competitive positioning plan.',
    time: '~5 min', status: 'active', skill: 'competitor-seo-analysis', category: 'seo',
    preview: '# SEO Competitive Analysis: All Thingz Electric vs. 3 Competitors\n\n## Why They\'re Winning\n### Parker & Sons\n**Primary advantage:** Topical authority — 47 supporting articles vs. your 3\n**Evidence:** Their "electrical" topic cluster has 47 pieces covering every subtopic. You have 3 blog posts. Google gives them domain-level authority for electrical queries in Phoenix metro.\n**Your fix:** Build 8 supporting articles targeting the highest-volume subtopics they cover.\n\n## SERP Feature Gaps\n| Feature | Your Status | Competitor | Opportunity |\n|---|---|---|---|\n| Featured Snippet | Missing | Parker & Sons owns 3 | High — "how much does a panel upgrade cost" has snippet |\n| People Also Ask | 0 boxes | Competitor in 4 | High — add direct-answer FAQs |\n\n## 90-Day Action Plan\n1. Create "How Much Does a Panel Upgrade Cost in Phoenix?" — targets the featured snippet\n2. Build FAQ sections on all service pages\n3. Publish 4 supporting articles closing the topical authority gap' },
  /* ── CONTENT CREATION ── */
  { id: 'seo-blog-post', icon: '✍️', title: 'SEO Blog Post',
    desc: 'Publish-ready blog post targeting informational keywords — key takeaways, FAQ, local CTA, and meta description.',
    time: '~5 min', status: 'active', skill: 'seo-blog-post', category: 'content',
    preview: 'META: How much does it cost to rewire a house in Phoenix? Real ranges ($8,000–$22,000), what drives price, and when to call a licensed Phoenix electrician.\n\n# How Much Does It Cost to Rewire a House in Phoenix, AZ?\n\n## Key Takeaways\n- Whole-home rewire in Phoenix: **$8,000–$22,000** (1,500–3,000 sq ft)\n- Permit required in Maricopa County — expect $180–$420\n- Timeline: 3–5 days for most homes\n- Summer timing matters: Phoenix heat accelerates insulation degradation\n\nIf your home was built before 1985, there\'s a reasonable chance your wiring has been sending warning signs for months...' },
  { id: 'service-page', icon: '⚡', title: 'Service Page',
    desc: 'Conversion-optimized page targeting high-intent "[service] [city]" keywords — built to rank and convert.',
    time: '~4 min', status: 'active', skill: 'service-page', category: 'content',
    preview: '# Electrical Panel Upgrade in Chandler, AZ\n\nYour circuit breaker tripping again? **A panel upgrade stops the problem at the source** — and in Chandler\'s heat-heavy summers, an undersized panel isn\'t just inconvenient, it\'s a fire risk.\n\n**Call for a free estimate: (480) 555-0182**\n\n## What\'s Included in Every Panel Upgrade\n- 200-amp service upgrade with permits pulled same day\n- All circuits mapped, labeled, and load-balanced\n- City of Chandler inspection coordinated — we handle scheduling\n- Same-day power restoration in most cases\n\n**Price range: $1,800–$3,200** depending on panel size and existing wiring.' },
  { id: 'location-page', icon: '📍', title: 'Location Page',
    desc: 'Geo-targeted page for "[service] [city]" rankings — genuinely local, not templated.',
    time: '~4 min', status: 'active', skill: 'location-page', category: 'content',
    preview: '# Plumbing Repair in Mesa, AZ | Chandler Plumbing Pros\n\nMesa\'s housing stock tells a story. **Homes in the Val Vista Lakes area** were built in the late 1980s — after 35 years, that original copper plumbing is at the stage where pinhole leaks become a Tuesday problem.\n\nBased in Chandler, we\'ve been serving Mesa homeowners for 12 years. Licensed, insured, and familiar with the specific challenges that come with **east Mesa\'s hard water** and the aging PVC systems common in Dobson Ranch.\n\n**Call for same-day service: (480) 555-0182**\n\n## Plumbing Services in Mesa\n- Emergency leak repair (2-hour response for Mesa residents)\n- Water heater replacement and tankless conversion...' },
  { id: 'home-service-content', icon: '🏠', title: 'Home Service SEO Content',
    desc: 'SEO articles for electricians, plumbers, HVAC, and other home service businesses. Built for local rank.',
    time: '~5 min', status: 'active', skill: 'home-service-seo-content', category: 'content',
    preview: '# 7 Signs Your Home Needs an Electrical Panel Upgrade\n\nMost homeowners in Chandler don\'t think about their electrical panel until something goes wrong. By then, the warning signs had been there for months — tripping breakers, flickering lights, outlets that stopped working.\n\nHere\'s what to look for, and when to call a licensed electrician:\n\n**1. Breakers That Keep Tripping**\nA breaker trips once — that\'s it doing its job. If the same breaker trips twice a week, the circuit is consistently overloaded. This is the most common panel issue in Chandler homes built before 2000...' },
  { id: 'content-strategy', icon: '📋', title: 'Content Strategy',
    desc: 'Content ecosystem mapping with buyer personas, topic clusters, funnel stages, 12-month calendar, and distribution plan.',
    time: '~6 min', status: 'active', skill: 'content-strategy', category: 'content',
    preview: '# Content Strategy: Steadfast Plumbing — Gilbert, AZ\n\n## Buyer Personas\n**Persona 1: "Emergency Ed"** — Homeowner, 40-55, pipe burst at 2am. Pain: water damage. Trigger: visible leak.\n**Persona 2: "Renovation Rachel"** — First-time buyer, 30-40, remodeling bathroom. Researches heavily before hiring.\n\n## Content Pillars (6)\n1. Emergency Services (12 cluster topics)\n2. Cost Transparency (8 cluster topics)\n3. Home Maintenance Education (10 topics)\n\n## 12-Month Calendar\nJan: "Winter pipe protection" blog series\nFeb: Cost guide refresh...' },
  { id: 'google-ads-copy', icon: '📣', title: 'Google Ads Copy',
    desc: 'High-converting search ad copy — headlines, descriptions, sitelinks, callouts, and negative keywords.',
    time: '~4 min', status: 'active', skill: 'google-ads-copy', category: 'content',
    preview: '# Google Ads Copy: All Thingz Electric — Chandler, AZ\n\n## Ad Group: Electrician — High Intent\n**Headlines (15):**\n1. Electrician in Chandler AZ (23 chars)\n2. Licensed Master Electrician (27 chars)\n3. Same-Day Service Available (26 chars)\n\n**Descriptions (4):**\n1. Licensed & insured electricians serving Chandler. Same-day appointments. Call for free estimate. (90 chars)\n\n**Keywords:** "electrician chandler az" 2,400/mo $12.50 CPC\n\n## Sitelinks\n## Negative Keywords (47)' },
  { id: 'page-design', icon: '🎨', title: 'Page Design Agent',
    desc: 'Generates a fully designed, self-contained HTML/CSS page — renders in any browser. Service pages, landing pages, location pages, and more.',
    time: '~6 min', status: 'active', skill: 'page-design', category: 'content',
    preview: '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <title>Panel Upgrade in Chandler, AZ | All Thingz Electric</title>\n  <style>\n    :root { --primary: #1a3b5c; --accent: #ff6b00; }\n    /* Full responsive CSS design system */\n  </style>\n</head>\n<body>\n  <header>Sticky nav with mobile hamburger</header>\n  <section class="hero">Customer-problem-first headline + CTA</section>\n  <section class="trust-bar">15 Years · 500+ Reviews · Licensed</section>\n  <section class="services">3-6 service cards with icons</section>\n  <section class="why-us">Differentiators grid</section>\n  <section class="process">Step-by-step timeline</section>\n  <section class="testimonials">3 review cards</section>\n  <section class="faq">CSS-only accordion</section>\n  <section class="cta">Full-width CTA band</section>\n  <footer>Business info + nav + copyright</footer>\n</body>\n</html>' },
  /* ── BUSINESS TOOLS ── */
  { id: 'monthly-report', icon: '📈', title: 'Monthly Client Report',
    desc: 'Data-backed monthly performance report — rankings, traffic, backlinks, wins, and strategic recommendations.',
    time: '~5 min', status: 'active', skill: 'monthly-report', category: 'business',
    preview: '# Monthly SEO Report: All Thingz Electric — January 2026\n\n**SEO Health Score: 72/100** | Direction: Improving\n\n## Rankings Performance\n- 47 total keywords ranked (up from 39)\n- 12 keywords on page 1 (3 new this month)\n- 8 keywords on page 2 — "almost there" opportunities\n\n## Traffic & Visibility\n- Est. organic traffic: 1,240/mo (+18% MoM)\n- Traffic value: $4,200/mo\n\n## Wins This Month\n- "panel upgrade chandler az" moved from #14 to #7\n- New blog post ranking #4 for "ev charger cost phoenix"\n\n## Next Month Strategy\n3 service pages targeting $8,400/mo in opportunity' },
  { id: 'proposals', icon: '📄', title: 'Client Proposals',
    desc: 'Data-backed marketing proposals — competitor data, opportunity sizing, scoped deliverables, and ROI projections.',
    time: '~5 min', status: 'active', skill: 'proposals', category: 'business',
    preview: '# Marketing Proposal: Steadfast Plumbing\nPrepared by ProofPilot\n\n## The Opportunity\nYour top competitor gets 4,200 monthly organic visits worth $18,000/mo in ad value. You currently get 280.\n\n**Total addressable search volume in Gilbert:** 8,900/mo\n**Revenue you\'re leaving on the table:** $47,000/year\n\n## Investment: Growth Strategy — $6,200/mo\n- 8 SEO-optimized pages/month\n- Full keyword gap remediation\n- Monthly backlink acquisition\n- Dedicated strategy calls\n\n## ROI Projection\nConservative (5% capture): 12 new leads/mo → $64,800/year' },
  { id: 'pnl-statement', icon: '💰', title: 'P&L Statement',
    desc: 'Monthly profit & loss statement — itemized revenue/expenses, margins, ratios, and financial recommendations.',
    time: '~2 min', status: 'active', skill: 'pnl-statement', category: 'business',
    preview: '# P&L Statement: ProofPilot — January 2026\n\n## Revenue Summary\n| Client | Amount |\n|---|---|\n| Client A | $6,200 |\n| Client B | $2,000 |\n| Client C | $3,500 |\n| **Total Revenue** | **$11,700** |\n\n## Gross Profit: $9,100 (77.8%)\n## Net Income: $6,200 (53.0%)\n\n## Key Ratios\n| Ratio | Value | Benchmark |\n| Gross Margin | 77.8% | 50-70% |\n| Net Margin | 53.0% | 15-30% |\n\n## Recommendations\n1. Capacity for 3 more clients at current margins' },
  { id: 'property-mgmt-strategy', icon: '🏢', title: 'Property Mgmt Strategy',
    desc: 'Website and SEO strategy for property management companies — owner acquisition, tenant funnels, and local SEO.',
    time: '~6 min', status: 'active', skill: 'property-mgmt-strategy', category: 'business',
    preview: '# Property Management Marketing Strategy: ABC Properties — Phoenix, AZ\n\n## Market Assessment\n- Currently ranking for 12 keywords (vs competitor avg of 89)\n- Missing 47 high-value keywords\n\n## Website Strategy\n- Owner Portal: ROI calculator, management fee transparency, case studies\n- Tenant Portal: Online payments, maintenance requests, community info\n\n## SEO Strategy by Property Type\n- Residential: 24 target keywords, 8 location pages\n- Commercial: 12 target keywords, 4 service pages\n- HOA: 8 target keywords, 3 authority posts\n\n## 90-Day Roadmap\nWeek 1-2: Foundation pages...' },
  /* ── PAGE BUILDER PIPELINES ── */
  { id: 'pipeline-service-page', icon: '🏗️', title: 'Page Builder: Service Page',
    desc: 'Full pipeline — research, strategy, copywriting, HTML/CSS design, and QA review. Produces a production-ready service page.',
    time: '~15 min', status: 'active', skill: 'pipeline-service-page', category: 'pipeline',
    preview: 'Stage 1: RESEARCH — Keyword volumes, competitor analysis, SERP features, content gaps\nStage 2: STRATEGY — Content brief, heading hierarchy, internal links, schema plan\nStage 3: COPYWRITE — Full page copy with anti-AI style, brand voice, E-E-A-T\nStage 4: DESIGN — Production HTML/CSS with responsive layout, schema, OG tags\nStage 5: QA — 100-point quality score, SEO check, AEO readiness, E-E-A-T audit\n\nOutput: Download-ready HTML page + branded .docx' },
  { id: 'pipeline-location-page', icon: '📍', title: 'Page Builder: Location Page',
    desc: 'Full pipeline — research, strategy, copywriting, HTML/CSS design, and QA review. Produces a production-ready location page.',
    time: '~15 min', status: 'active', skill: 'pipeline-location-page', category: 'pipeline',
    preview: 'Stage 1: RESEARCH — Local keyword data, competitor presence, service area analysis\nStage 2: STRATEGY — Location-specific brief, local context requirements, nearby areas\nStage 3: COPYWRITE — City-specific copy with 30-50% unique content, local proof\nStage 4: DESIGN — Production HTML/CSS with service grid, area map, local schema\nStage 5: QA — Quality score, local specificity check, cannibalization review' },
  { id: 'pipeline-blog-post', icon: '📝', title: 'Page Builder: Blog Post',
    desc: 'Full pipeline — research, strategy, copywriting, HTML/CSS design, and QA review. Produces a production-ready blog post.',
    time: '~15 min', status: 'active', skill: 'pipeline-blog-post', category: 'pipeline',
    preview: 'Stage 1: RESEARCH — Informational keyword data, PAA questions, competitor content\nStage 2: STRATEGY — Content brief with outline, snippet targets, internal link plan\nStage 3: COPYWRITE — Long-form content with AEO optimization, featured snippet format\nStage 4: DESIGN — Production HTML/CSS with TOC, author bio, article schema\nStage 5: QA — Quality score, fact-check, AI citation readiness (CITE framework)' },
];

const JOBS = [];
const LOG_ENTRIES = [];
const REPORTS = [];
const CONTENT = [];

// Content Library — persists workflow outputs indexed by client
// Each item: {id, job_id, client_name, client_id, workflow_id, workflow_title, created_at, has_docx, preview}
let CONTENT_ITEMS = [];

/* job progress simulation */
const jobProgresses = {};
JOBS.forEach(j => { jobProgresses[j.id] = j.pct; });

/* ── CONFIG ── */
const API_BASE = '';

/* ── VIEW ROUTING ── */
let currentView = 'dashboard';
let selectedWorkflow = null;
let agentRunning = true;
let activeClientId = null;

/* ── STREAMING STATE ── */
let terminalStreaming = false;
let streamDiv = null;
let sseBuffer = '';
let currentJobId = null;
let activeTerminalEl = null;
let monitorJobId = null;
const activeSSEJobs = new Set();

/* ── CLIENT BRAIN STATE ── */
let clientBrainData = null;
let clientHubTab = 'activity';
let brainBuildAbort = null;

/* ── SPRINT STATE ── */
let sprintItems = [];
let sprintRunning = false;
let sprintHistory = [];  // Module-level cache of past sprint results
let sprintAbort = null;

/* ── DOCUMENT VIEWER STATE ── */
let markdownBuffer = '';          // Accumulates raw markdown during streaming
let docViewMode = 'terminal';     // 'terminal' or 'document'
let currentDocContent = '';       // Full markdown of the current/last completed document

function showView(viewId) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const el = document.getElementById(`view-${viewId}`);
  if (el) el.classList.add('active');

  const nav = document.getElementById(`nav-${viewId}`);
  if (nav) nav.classList.add('active');

  const title = document.getElementById('pageTitle');
  const titles = {
    dashboard: 'Dashboard', workflows: 'Run Workflows', clients: 'Clients',
    jobs: 'Agent Tasks', reporting: 'Reporting', reports: 'Reports', content: 'Content',
    logs: 'Activity Log', ads: 'Ad Studio', campaigns: 'Campaigns', schedules: 'Schedules',
    training: 'Training', 'client-hub': 'Client Hub'
  };
  if (title) title.textContent = titles[viewId] || viewId;

  currentView = viewId;

  if (viewId === 'dashboard') renderDashboard();
  if (viewId === 'workflows') renderWorkflows();
  if (viewId === 'clients') renderClients();
  if (viewId === 'jobs') renderJobs('all');
  if (viewId === 'reporting') renderReportingDashboard();
  if (viewId === 'reports') renderReports();
  if (viewId === 'content') { syncContentLibrary(); }
  if (viewId === 'logs') renderLogs();
  if (viewId === 'ads') renderAds();
  if (viewId === 'client-hub') renderClientHub();
  if (viewId === 'schedules') renderSchedules();
}

function showJobMonitor(jobId) {
  const job = JOBS.find(j => j.id === jobId);
  if (!job) return;

  monitorJobId = jobId;

  document.getElementById('jmJobId').textContent = job.id;
  document.getElementById('jmWfName').textContent = job.wf;
  document.getElementById('jmClient').textContent = job.client;
  updateMonitorStatus(job.status);

  const doneBar = document.getElementById('jmDoneBar');
  if (doneBar) doneBar.style.display = 'none'; // Reset — will be shown below if completed

  // Switch view manually so we can keep nav-jobs highlighted
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const el = document.getElementById('view-job-monitor');
  if (el) el.classList.add('active');
  document.getElementById('nav-jobs')?.classList.add('active');
  const title = document.getElementById('pageTitle');
  if (title) title.textContent = `${job.id} — ${job.wf}`;
  currentView = 'job-monitor';

  activeTerminalEl = document.getElementById('monitorTerminal');

  // If the job is completed and has cached doc content, show document view
  if (job.status === 'completed' && job.docContent) {
    currentDocContent = job.docContent;
    markdownBuffer = job.docContent;
    toggleDocView('document');

    // Initialize version history and edit bar for completed jobs
    if (job.server_job_id) {
      activeEditJobId = job.server_job_id;
      docVersions = [{ content: job.docContent, instruction: 'Original' }];
      docVersionIndex = 0;
      _updateVersionBar('monitor');
      const editBar = document.getElementById('docEditBar');
      if (editBar) editBar.style.display = 'flex';

      // Show done bar with download or preview link
      const dlLink = document.getElementById('jmDownloadLink');
      const previewLink = document.getElementById('jmPreviewLink');
      const doneMsg = document.getElementById('jmDoneMsg');
      if (doneBar && dlLink && doneMsg) {
        doneMsg.textContent = `Job ${job.server_job_id} complete — output ready`;
        // Detect if this is a page-design job by checking content
        const isPageDesign = _isHtmlContent(job.docContent);
        if (isPageDesign) {
          if (previewLink) {
            previewLink.href = `${API_BASE}/api/preview/${job.server_job_id}`;
            previewLink.style.display = '';
          }
          dlLink.style.display = 'none';
        } else {
          dlLink.href = `${API_BASE}/api/download/${job.server_job_id}`;
          dlLink.style.display = '';
          if (previewLink) previewLink.style.display = 'none';
        }
        doneBar.style.display = 'flex';
      }
    }
  } else if (job.status === 'running') {
    // For running jobs, show terminal view
    toggleDocView('terminal');
  } else {
    // Default: hide edit bar and show terminal
    toggleDocView('terminal');
    const editBar = document.getElementById('docEditBar');
    if (editBar) editBar.style.display = 'none';
  }
}

function updateMonitorStatus(status) {
  const badge = document.getElementById('jmStatusBadge');
  if (!badge) return;
  badge.textContent = status.toUpperCase();
  badge.className = `jm-status-badge ${status}`;
}

/* ── Document View Toggle ── */
function toggleDocView(mode) {
  docViewMode = mode;
  const termWrap = document.getElementById('jmTerminalWrap');
  const docWrap = document.getElementById('jmDocWrap');
  if (!termWrap || !docWrap) return;

  // Toggle visibility
  termWrap.style.display = mode === 'terminal' ? 'flex' : 'none';
  docWrap.style.display = mode === 'document' ? 'flex' : 'none';

  // Toggle button active state
  document.querySelectorAll('.jm-toggle-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // If switching to document view, render current buffer
  if (mode === 'document') {
    renderDocPanel();
  }
}

function _isHtmlContent(content) {
  const t = (content || '').trimStart();
  return t.startsWith('<!DOCTYPE') || t.startsWith('<html') || t.startsWith('<HTML');
}

function renderDocPanel() {
  const panel = document.getElementById('docPanel');
  const iframeWrap = document.getElementById('docIframeWrap');
  const iframe = document.getElementById('docIframe');
  const vpToggle = document.getElementById('viewportToggle');
  if (!panel) return;
  const content = markdownBuffer || currentDocContent;
  if (!content) {
    panel.innerHTML = '<div class="doc-panel-empty">No document content yet</div>';
    if (iframeWrap) iframeWrap.style.display = 'none';
    if (vpToggle) vpToggle.style.display = 'none';
    return;
  }

  if (_isHtmlContent(content)) {
    // HTML mode — render in iframe
    panel.style.display = 'none';
    if (iframeWrap) iframeWrap.style.display = 'flex';
    if (vpToggle) vpToggle.style.display = 'flex';
    if (iframe) iframe.srcdoc = content;
  } else {
    // Markdown mode
    if (iframeWrap) iframeWrap.style.display = 'none';
    if (vpToggle) vpToggle.style.display = 'none';
    panel.style.display = '';
    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
      panel.innerHTML = DOMPurify.sanitize(marked.parse(content));
    } else {
      panel.innerHTML = `<pre style="white-space:pre-wrap;">${content}</pre>`;
    }
    panel.scrollTop = panel.scrollHeight;
  }
}

function renderDocViewerModal(content, title, subtitle, downloadUrl, jobId) {
  const panel = document.getElementById('docViewerPanel');
  const titleEl = document.getElementById('docViewerTitle');
  const subEl = document.getElementById('docViewerSub');
  const dlBtn = document.getElementById('docViewerDownload');
  const overlay = document.getElementById('docViewerModal');
  const modalIframeWrap = document.getElementById('modalIframeWrap');
  const modalIframe = document.getElementById('modalIframe');
  const modalVpToggle = document.getElementById('modalViewportToggle');
  if (!panel || !overlay) return;

  titleEl.textContent = title || 'Document';
  subEl.textContent = subtitle || '';

  const isHtml = _isHtmlContent(content);

  if (isHtml) {
    // HTML mode — show iframe, hide markdown panel
    panel.style.display = 'none';
    if (modalIframeWrap) modalIframeWrap.style.display = 'flex';
    if (modalVpToggle) modalVpToggle.style.display = 'flex';
    if (modalIframe) modalIframe.srcdoc = content;
    // Change download button to "Open Preview" linking to preview endpoint
    if (dlBtn && jobId) {
      dlBtn.href = `${API_BASE}/api/preview/${jobId}`;
      dlBtn.textContent = 'Open in New Tab';
      dlBtn.style.display = '';
    }
  } else {
    // Markdown mode
    if (modalIframeWrap) modalIframeWrap.style.display = 'none';
    if (modalVpToggle) modalVpToggle.style.display = 'none';
    panel.style.display = '';
    if (downloadUrl) {
      dlBtn.href = downloadUrl;
      dlBtn.textContent = '↓ Download .docx';
      dlBtn.style.display = '';
    } else {
      dlBtn.style.display = 'none';
    }

    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
      panel.innerHTML = DOMPurify.sanitize(marked.parse(content));
    } else {
      panel.innerHTML = `<pre style="white-space:pre-wrap;">${content}</pre>`;
    }
  }

  // Initialize modal version history and editing
  modalEditJobId = jobId || null;
  modalVersions = [{ content, instruction: 'Original' }];
  modalVersionIndex = 0;
  _updateVersionBar('modal');

  // Show/hide edit bar based on whether we have a job ID
  const editBar = document.getElementById('modalEditBar');
  if (editBar) editBar.style.display = jobId ? 'flex' : 'none';

  overlay.classList.add('open');
}

function closeDocViewer() {
  const overlay = document.getElementById('docViewerModal');
  if (overlay) overlay.classList.remove('open');
}

/* ── Viewport Toggle (HTML preview) ── */
function setViewport(width, btn) {
  const iframe = document.getElementById('docIframe');
  if (iframe) iframe.style.width = width;
  document.querySelectorAll('#viewportToggle .vp-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

function setModalViewport(width, btn) {
  const iframe = document.getElementById('modalIframe');
  if (iframe) iframe.style.width = width;
  document.querySelectorAll('#modalViewportToggle .vp-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

/* ── Document Version History ── */
let docVersions = [];       // Array of {content, instruction} — version history
let docVersionIndex = -1;   // Current version being viewed
let activeEditJobId = null; // Job ID being edited

// Modal version state (separate from job monitor)
let modalVersions = [];
let modalVersionIndex = -1;
let modalEditJobId = null;

function _pushVersion(content, instruction, target) {
  const versions = target === 'modal' ? modalVersions : docVersions;
  versions.push({ content, instruction: instruction || 'Original' });
  if (target === 'modal') {
    modalVersionIndex = versions.length - 1;
    _updateVersionBar('modal');
  } else {
    docVersionIndex = versions.length - 1;
    _updateVersionBar('monitor');
  }
}

function _updateVersionBar(target) {
  const isModal = target === 'modal';
  const versions = isModal ? modalVersions : docVersions;
  const index = isModal ? modalVersionIndex : docVersionIndex;
  const bar = document.getElementById(isModal ? 'modalVersionBar' : 'docVersionBar');
  const label = document.getElementById(isModal ? 'modalVerLabel' : 'docVerLabel');
  const prev = document.getElementById(isModal ? 'modalVerPrev' : 'docVerPrev');
  const next = document.getElementById(isModal ? 'modalVerNext' : 'docVerNext');
  if (!bar) return;

  if (versions.length <= 1) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  label.textContent = `Version ${index + 1} of ${versions.length}`;
  prev.disabled = index <= 0;
  next.disabled = index >= versions.length - 1;
}

function docVersionNav(dir) {
  const newIndex = docVersionIndex + dir;
  if (newIndex < 0 || newIndex >= docVersions.length) return;
  docVersionIndex = newIndex;
  currentDocContent = docVersions[newIndex].content;
  markdownBuffer = currentDocContent;
  renderDocPanel();
  _updateVersionBar('monitor');
}

function modalVersionNav(dir) {
  const newIndex = modalVersionIndex + dir;
  if (newIndex < 0 || newIndex >= modalVersions.length) return;
  modalVersionIndex = newIndex;
  const vContent = modalVersions[newIndex].content;
  if (_isHtmlContent(vContent)) {
    const iframe = document.getElementById('modalIframe');
    const panel = document.getElementById('docViewerPanel');
    const iframeWrap = document.getElementById('modalIframeWrap');
    const vpToggle = document.getElementById('modalViewportToggle');
    if (panel) panel.style.display = 'none';
    if (iframeWrap) iframeWrap.style.display = 'flex';
    if (vpToggle) vpToggle.style.display = 'flex';
    if (iframe) iframe.srcdoc = vContent;
  } else {
    const panel = document.getElementById('docViewerPanel');
    const iframeWrap = document.getElementById('modalIframeWrap');
    const vpToggle = document.getElementById('modalViewportToggle');
    if (iframeWrap) iframeWrap.style.display = 'none';
    if (vpToggle) vpToggle.style.display = 'none';
    if (panel) {
      panel.style.display = '';
      if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
        panel.innerHTML = DOMPurify.sanitize(marked.parse(vContent));
      }
    }
  }
  _updateVersionBar('modal');
}

/* ── Submit Document Edits ── */
async function submitDocEdit() {
  const input = document.getElementById('docEditInput');
  const btn = document.getElementById('docEditSubmit');
  if (!input || !input.value.trim()) return;

  const instruction = input.value.trim();
  const jobId = activeEditJobId || currentJobId;
  if (!jobId || !currentDocContent) return;

  input.value = '';
  btn.disabled = true;
  btn.textContent = 'Editing...';

  try {
    const newContent = await _streamDocEdit(jobId, instruction, currentDocContent, 'docPanel');
    if (newContent) {
      currentDocContent = newContent;
      markdownBuffer = newContent;
      // Cache on job object
      const job = JOBS.find(j => j.server_job_id === jobId);
      if (job) job.docContent = newContent;
      _pushVersion(newContent, instruction, 'monitor');
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Apply Edit';
  }
}

async function submitModalEdit() {
  const input = document.getElementById('modalEditInput');
  const btn = document.getElementById('modalEditSubmit');
  if (!input || !input.value.trim()) return;

  const instruction = input.value.trim();
  const jobId = modalEditJobId;
  if (!jobId) return;

  const currentContent = modalVersions.length > 0
    ? modalVersions[modalVersionIndex].content
    : '';
  if (!currentContent) return;

  input.value = '';
  btn.disabled = true;
  btn.textContent = 'Editing...';

  try {
    const newContent = await _streamDocEdit(jobId, instruction, currentContent, 'docViewerPanel');
    if (newContent) {
      _pushVersion(newContent, instruction, 'modal');
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Apply Edit';
  }
}

async function _streamDocEdit(jobId, instruction, currentContent, panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return null;

  let editBuffer = '';
  let editRenderTimer = null;
  const isHtml = _isHtmlContent(currentContent);
  const EDIT_RENDER_INTERVAL = isHtml ? 500 : 120; // slower for HTML to prevent iframe reload flicker

  function renderEdit() {
    if (isHtml) {
      // HTML edit — render to iframe
      const iframeId = panelId === 'docPanel' ? 'docIframe' : 'modalIframe';
      const iframe = document.getElementById(iframeId);
      if (iframe) iframe.srcdoc = editBuffer;
    } else if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
      panel.innerHTML = DOMPurify.sanitize(marked.parse(editBuffer));
      panel.scrollTop = panel.scrollHeight;
    }
  }

  try {
    const response = await fetch(`${API_BASE}/api/edit-document`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: jobId,
        instruction,
        current_content: currentContent,
      }),
    });

    if (!response.ok) throw new Error(`Server returned ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let sseEditBuffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseEditBuffer += decoder.decode(value, { stream: true });
      const lines = sseEditBuffer.split('\n');
      sseEditBuffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'token') {
            editBuffer += data.text;
            // Throttled render
            if (!editRenderTimer) {
              editRenderTimer = setTimeout(() => { editRenderTimer = null; renderEdit(); }, EDIT_RENDER_INTERVAL);
            }
          } else if (data.type === 'done') {
            // Final render — clear throttle timer and do immediate render
            if (editRenderTimer) { clearTimeout(editRenderTimer); editRenderTimer = null; }
            renderEdit();
            showToast('Document updated');
          } else if (data.type === 'error') {
            showToast(`Edit failed: ${data.message}`);
            return null;
          }
        } catch (e) { /* skip malformed */ }
      }
    }

    return editBuffer || null;
  } catch (err) {
    showToast(`Edit error: ${err.message}`);
    return null;
  }
}

function updateClientsBadge() {
  const badge = document.getElementById('navBadgeClients');
  if (badge) badge.textContent = CLIENTS.filter(c => c.status === 'active').length;
}

function updateJobsBadge() {
  const running = JOBS.filter(j => j.status === 'running').length;
  const badge = document.getElementById('navBadgeJobs');
  if (!badge) return;
  if (running > 0) {
    badge.textContent = `${running} LIVE`;
    badge.classList.add('nav-badge-live');
  } else {
    badge.textContent = JOBS.length;
    badge.classList.remove('nav-badge-live');
  }
}

/* ── DASHBOARD ── */
function renderDashboard() {
  // KPIs
  const activeClients = CLIENTS.filter(c => c.status === 'active').length;
  const activeTasks   = JOBS.filter(j => j.status === 'running').length;
  const workflowsRun  = JOBS.length;
  const docsGenerated = JOBS.filter(j => j.status === 'completed').length;

  const kpiEl = id => document.getElementById(id);
  if (kpiEl('kpiActiveClients')) kpiEl('kpiActiveClients').textContent = activeClients;
  if (kpiEl('kpiActiveTasks'))   kpiEl('kpiActiveTasks').textContent   = activeTasks;
  if (kpiEl('kpiWorkflowsRun'))  kpiEl('kpiWorkflowsRun').textContent  = workflowsRun;
  if (kpiEl('kpiDocsGenerated')) kpiEl('kpiDocsGenerated').textContent = docsGenerated;

  renderTaskQueue();
  renderCompletions();
  renderRoster();
  renderAlerts();
  renderAdPreview();
}

function renderTaskQueue() {
  const el = document.getElementById('dashTaskQueue');
  if (!el) return;
  const running = JOBS.filter(j => j.status === 'running');
  if (!running.length) {
    el.innerHTML = '<div class="empty-state">No active tasks — run a workflow to start</div>';
    return;
  }
  el.innerHTML = running.map(j => `
    <div class="task-item" onclick="showJobMonitor('${j.id}')" style="cursor:pointer;">
      <div class="task-dot td-running"></div>
      <div class="task-info">
        <div class="task-name">${j.wf}</div>
        <div class="task-client">${j.client}</div>
      </div>
      <div class="task-right">
        <span class="task-tag tt-running">Running</span>
        <span class="task-time">${j.started}</span>
      </div>
    </div>
  `).join('');
}

function dotClass(s) {
  return { running: 'td-running', queued: 'td-queued', done: 'td-done', warn: 'td-warn', blocked: 'td-blocked' }[s] || 'td-queued';
}

function tagLabel(s) {
  return { running: 'Running', queued: 'Queued', done: 'Done', warn: 'Review', blocked: 'Blocked' }[s] || s;
}

function renderCompletions() {
  const el = document.getElementById('completionsTbody');
  if (!el) return;
  const completed = JOBS.filter(j => j.status === 'completed');
  if (!completed.length) {
    el.innerHTML = '<tr><td colspan="5" class="empty-state" style="text-align:center;padding:24px;">No completed tasks yet</td></tr>';
    return;
  }
  el.innerHTML = completed.map(j => `
    <tr onclick="openJobModal('${j.id}')" style="cursor:pointer;">
      <td>${j.wf}</td>
      <td style="color:var(--text3);font-family:var(--mono);font-size:10px;">${j.client}</td>
      <td><span class="c-pill cp-kw">Workflow</span></td>
      <td class="c-outcome">Complete</td>
      <td style="color:var(--text3);font-family:var(--mono);font-size:10px;">${j.started}</td>
    </tr>
  `).join('');
}

function renderRoster() {
  const el = document.getElementById('clientRoster');
  if (!el) return;
  el.innerHTML = CLIENTS.map((c, i) => {
    const scoreClass = c.score >= 80 ? 'score-hi' : c.score >= 65 ? 'score-md' : 'score-lo';
    const trendClass = c.trend.startsWith('+') ? 'tr-up' : c.trend.startsWith('-') ? 'tr-down' : '';
    return `
      <div class="roster-item ${i === 0 ? 'selected' : ''} ${c.status === 'inactive' ? 'inactive' : ''}" onclick="selectRosterItem(this)">
        <div class="roster-avatar" style="color:${c.color};">${c.initials}</div>
        <div class="roster-info">
          <div class="roster-name client-name-link" onclick="event.stopPropagation();showClientHub(${c.id})">${c.name}</div>
          <div class="roster-domain">${c.domain}</div>
        </div>
        <div class="roster-right">
          <span class="roster-score ${scoreClass}">${c.score}</span>
          <span class="roster-trend ${trendClass}">${c.trend}</span>
        </div>
      </div>
    `;
  }).join('');
}

function selectRosterItem(el) {
  document.querySelectorAll('.roster-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
}

function renderAlerts() {
  const el = document.getElementById('dashAlerts');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">No alerts — system healthy</div>';
}

function renderAdPreview() {
  const el = document.getElementById('dashAdList');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">No ads yet — use Ad Studio to create</div>';
}

/* ── WORKFLOWS ── */
function renderWorkflows() {
  renderClientSelect();
  renderWorkflowCards();
}

function renderClientSelect() {
  const sel = document.getElementById('wfClientSelect');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— Choose client —</option>' +
    CLIENTS.filter(c => c.status === 'active')
           .map(c => `<option value="${c.id}">${c.name}</option>`).join('');
  if (current) sel.value = current;
}

function renderWorkflowCards() {
  const el = document.getElementById('workflowCardsGrid');
  if (!el) return;

  const categories = [
    { key: 'pipeline', label: 'Page Builders',      desc: 'Full pipeline: research → strategy → copy → design → QA' },
    { key: 'seo',      label: 'SEO Analysis',      desc: 'Audits, gap reports, and competitive intelligence' },
    { key: 'content',  label: 'Content Creation',   desc: 'Blog posts, service pages, and location pages' },
    { key: 'business', label: 'Business Tools',     desc: 'Reports, proposals, and agency operations' },
    { key: 'dev',      label: 'Dev & Creative',     desc: 'Frontend builds, app prompting, and design' },
  ];

  let html = '';
  categories.forEach(cat => {
    const activeInCat = WORKFLOWS.filter(w => w.category === cat.key && w.status === 'active');
    const soonInCat   = WORKFLOWS.filter(w => w.category === cat.key && w.status === 'soon');
    if (!activeInCat.length && !soonInCat.length) return;

    html += `<div class="wf-category-header">
      <div class="wf-category-name">${cat.label}</div>
      <div class="wf-category-desc">${cat.desc}${activeInCat.length ? ` · <span class="wf-cat-active">${activeInCat.length} active</span>` : ''}${soonInCat.length ? ` · ${soonInCat.length} coming` : ''}</div>
    </div>`;

    activeInCat.forEach(wf => {
      html += `<div class="wf-card" data-id="${wf.id}" onclick="selectWorkflow('${wf.id}')">
        <div class="wf-card-header">
          <span class="wf-card-icon">${wf.icon}</span>
        </div>
        <div class="wf-card-title">${wf.title}</div>
        <div class="wf-card-desc">${wf.desc}</div>
        <div class="wf-card-time">⏱ ${wf.time} · <span class="wf-preview-hint">click to preview</span></div>
      </div>`;
    });

    soonInCat.forEach(wf => {
      html += `<div class="wf-card soon">
        <div class="wf-card-header">
          <span class="wf-card-icon">${wf.icon}</span>
          <span class="wf-soon-badge">SOON</span>
        </div>
        <div class="wf-card-title">${wf.title}</div>
        <div class="wf-card-desc">${wf.desc}</div>
        <div class="wf-card-time">⏱ ${wf.time}</div>
      </div>`;
    });
  });

  el.innerHTML = html;
}

function selectWorkflow(id) {
  const wf = WORKFLOWS.find(w => w.id === id);
  if (!wf || wf.status === 'soon') return;

  selectedWorkflow = id;

  // Populate modal header
  document.getElementById('modalWfIcon').textContent = wf.icon;
  document.getElementById('modalWfTitle').textContent = wf.title;
  document.getElementById('modalWfDesc').textContent = wf.desc;

  // Populate preview panel
  const previewEl = document.getElementById('wfOutputPreview');
  const previewText = document.getElementById('wfPreviewText');
  if (previewEl && previewText) {
    if (wf.preview) {
      previewText.textContent = wf.preview;
      previewEl.style.display = 'block';
    } else {
      previewEl.style.display = 'none';
    }
  }

  // Show/hide workflow-specific inputs
  const panels = {
    'modalInputsHomeService':   id === 'home-service-content',
    'modalInputsWebsiteAudit':  id === 'website-seo-audit',
    'modalInputsProspectAudit': id === 'prospect-audit',
    'modalInputsKeywordGap':    id === 'keyword-gap',
    'modalInputsSEOBlogPost':   id === 'seo-blog-post',
    'modalInputsServicePage':   id === 'service-page',
    'modalInputsLocationPage':  id === 'location-page',
    'modalInputsProgrammatic':  id === 'programmatic-content',
    'modalInputsAISearch':      id === 'ai-search-report',
    'modalInputsBacklinkAudit': id === 'backlink-audit',
    'modalInputsOnpageAudit':   id === 'onpage-audit',
    'modalInputsSEOResearch':   id === 'seo-research',
    'modalInputsCompIntel':     id === 'competitor-intel',
    'modalInputsMonthlyReport': id === 'monthly-report',
    'modalInputsProposals':     id === 'proposals',
    'modalInputsGoogleAds':     id === 'google-ads-copy',
    'modalInputsSchema':        id === 'schema-generator',
    'modalInputsContentStrategy': id === 'content-strategy',
    'modalInputsPnl':           id === 'pnl-statement',
    'modalInputsPropertyMgmt':  id === 'property-mgmt-strategy',
    'modalInputsPageDesign':      id === 'page-design',
    'modalInputsGeoAudit':        id === 'geo-content-audit',
    'modalInputsSEOContentAudit': id === 'seo-content-audit',
    'modalInputsTechSEO':         id === 'technical-seo-review',
    'modalInputsProgSEOStrategy': id === 'programmatic-seo-strategy',
    'modalInputsCompSEOAnalysis': id === 'competitor-seo-analysis',
    'modalInputsPipeline':          id.startsWith('pipeline-'),
  };
  Object.entries(panels).forEach(([panelId, show]) => {
    const panel = document.getElementById(panelId);
    if (panel) panel.style.display = show ? 'flex' : 'none';
  });

  // Hide client dropdown and strategy context for prospect-audit (prospects aren't clients yet)
  const clientFieldWrap = document.getElementById('wfClientFieldWrap');
  if (clientFieldWrap) clientFieldWrap.style.display = id === 'prospect-audit' ? 'none' : '';
  const strategyWrap = document.getElementById('wfStrategyCtxWrap');
  if (strategyWrap) strategyWrap.style.display = id === 'prospect-audit' ? 'none' : '';

  // Reset form fields
  const clientSel = document.getElementById('wfClientSelect');
  if (clientSel) clientSel.value = '';
  ['wfBusinessType','wfLocation','wfKeyword','wfServiceFocus','wfStrategyCtx',
   'wfAuditDomain','wfAuditService','wfAuditLocation','wfAuditNotes',
   'wfProspectName','wfProspectDomain','wfProspectService','wfProspectLocation','wfProspectRevenue','wfProspectJobValue','wfProspectNotes',
   'wfGapDomain','wfGapService','wfGapLocation','wfGapCompetitors','wfGapNotes',
   'wfBlogBusinessType','wfBlogLocation','wfBlogKeyword','wfBlogAudience','wfBlogTone','wfBlogInternalLinks','wfBlogNotes',
   'wfSvcBusinessType','wfSvcService','wfSvcLocation','wfSvcDifferentiators','wfSvcPriceRange','wfSvcNotes',
   'wfLocBusinessType','wfLocPrimaryService','wfLocTargetLocation','wfLocHomeBase','wfLocLocalDetails','wfLocServicesList','wfLocNotes',
   'wfProgContentType','wfProgBusinessType','wfProgPrimaryService','wfProgLocation','wfProgHomeBase','wfProgItemsList','wfProgServicesList','wfProgDifferentiators','wfProgNotes',
   'wfAIDomain','wfAIService','wfAILocation','wfAINotes',
   'wfBLDomain','wfBLService','wfBLLocation','wfBLCompetitors','wfBLNotes',
   'wfOPUrl','wfOPKeyword','wfOPLocation','wfOPNotes',
   'wfSRDomain','wfSRService','wfSRLocation','wfSRCompetitors','wfSRNotes',
   'wfCIDomain','wfCICompetitors','wfCIService','wfCILocation','wfCINotes',
   'wfMRDomain','wfMRService','wfMRLocation','wfMRPeriod','wfMRHighlights','wfMRNotes',
   'wfPRDomain','wfPRService','wfPRLocation','wfPRPackage','wfPRCompetitors','wfPRNotes',
   'wfGAService','wfGALocation','wfGABusinessName','wfGAUsp','wfGALandingUrl','wfGABudget','wfGANotes',
   'wfSCBusinessName','wfSCBusinessType','wfSCLocation','wfSCSchemaTypes','wfSCPhone','wfSCAddress','wfSCWebsite','wfSCServicesList','wfSCHours','wfSCNotes',
   'wfCSBusinessType','wfCSService','wfCSLocation','wfCSAudience','wfCSGoals','wfCSNotes',
   'wfPLPeriod','wfPLRevenue','wfPLExpenses','wfPLEntity','wfPLNotes',
   'wfPMDomain','wfPMCompany','wfPMLocation','wfPMPropertyTypes','wfPMPortfolioSize','wfPMNotes',
   'wfPDPageType','wfPDBusinessType','wfPDService','wfPDLocation','wfPDDomain','wfPDBusinessName','wfPDPhone','wfPDBrandColors','wfPDStyle','wfPDExistingCopy','wfPDNotes',
   'wfGEOContent','wfGEOQueries','wfGEOBizType','wfGEOLocation','wfGEOCompUrls','wfGEONotes',
   'wfSCAContent','wfSCAKeyword','wfSCATitleTag','wfSCAMetaDesc','wfSCAUrl','wfSCABizType','wfSCANotes',
   'wfTSRDomain','wfTSRPlatform','wfTSRBizType','wfTSRLocation','wfTSRPageTypes','wfTSRKnownIssues','wfTSRNotes',
   'wfPSSBizType','wfPSSService','wfPSSLocation','wfPSSPageType','wfPSSScale','wfPSSCompetitors','wfPSSDataAssets','wfPSSNotes',
   'wfCSADomain','wfCSACompetitors','wfCSAService','wfCSALocation','wfCSAKeywords','wfCSANotes',
   'wfPipeDomain','wfPipeService','wfPipeLocation','wfPipeKeyword','wfPipeDifferentiators','wfPipePriceRange','wfPipeCompetitors','wfPipeNotes'].forEach(fid => {
    const el = document.getElementById(fid);
    if (el) el.value = '';
  });

  // Reset programmatic content conditional fields
  ['progLocFields', 'progSvcBlogFields', 'progAutoDiscover'].forEach(elId => {
    const el = document.getElementById(elId);
    if (el) el.style.display = 'none';
  });
  const progItemCount = document.getElementById('progItemCount');
  if (progItemCount) progItemCount.style.display = 'none';
  // Reset discover city fields
  const discoverCity = document.getElementById('wfProgDiscoverCity');
  if (discoverCity) discoverCity.value = '';
  const discoverRadius = document.getElementById('wfProgDiscoverRadius');
  if (discoverRadius) discoverRadius.value = '15';

  checkRunReady();

  // Open modal
  document.getElementById('wfModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeWorkflowModal(e) {
  if (e && e.target !== document.getElementById('wfModal')) return;
  document.getElementById('wfModal').classList.remove('open');
  document.body.style.overflow = '';
}

function checkRunReady() {
  const btn = document.getElementById('wfRunBtn');
  if (!btn) return;

  let ready = !!selectedWorkflow;

  if (selectedWorkflow === 'prospect-audit') {
    // Prospect-audit uses its own name field — no client dropdown needed
    const name     = document.getElementById('wfProspectName')?.value.trim();
    const domain   = document.getElementById('wfProspectDomain')?.value.trim();
    const service  = document.getElementById('wfProspectService')?.value.trim();
    const location = document.getElementById('wfProspectLocation')?.value.trim();
    ready = !!(name && domain && service && location);
  } else {
    // All other workflows require a client to be selected
    const clientVal = document.getElementById('wfClientSelect')?.value;
    ready = !!(clientVal && selectedWorkflow);

    if (selectedWorkflow === 'home-service-content' && ready) {
      const businessType = document.getElementById('wfBusinessType')?.value.trim();
      const location     = document.getElementById('wfLocation')?.value.trim();
      const keyword      = document.getElementById('wfKeyword')?.value.trim();
      ready = !!(businessType && location && keyword);
    }

    if (selectedWorkflow === 'website-seo-audit' && ready) {
      const domain   = document.getElementById('wfAuditDomain')?.value.trim();
      const service  = document.getElementById('wfAuditService')?.value.trim();
      const location = document.getElementById('wfAuditLocation')?.value.trim();
      ready = !!(domain && service && location);
    }

    if (selectedWorkflow === 'keyword-gap' && ready) {
      const domain   = document.getElementById('wfGapDomain')?.value.trim();
      const service  = document.getElementById('wfGapService')?.value.trim();
      const location = document.getElementById('wfGapLocation')?.value.trim();
      ready = !!(domain && service && location);
    }

    if (selectedWorkflow === 'seo-blog-post' && ready) {
      const businessType = document.getElementById('wfBlogBusinessType')?.value.trim();
      const location     = document.getElementById('wfBlogLocation')?.value.trim();
      const keyword      = document.getElementById('wfBlogKeyword')?.value.trim();
      ready = !!(businessType && location && keyword);
    }

    if (selectedWorkflow === 'service-page' && ready) {
      const businessType = document.getElementById('wfSvcBusinessType')?.value.trim();
      const service      = document.getElementById('wfSvcService')?.value.trim();
      const location     = document.getElementById('wfSvcLocation')?.value.trim();
      ready = !!(businessType && service && location);
    }

    if (selectedWorkflow === 'location-page' && ready) {
      const businessType     = document.getElementById('wfLocBusinessType')?.value.trim();
      const primaryService   = document.getElementById('wfLocPrimaryService')?.value.trim();
      const targetLocation   = document.getElementById('wfLocTargetLocation')?.value.trim();
      const homeBase         = document.getElementById('wfLocHomeBase')?.value.trim();
      ready = !!(businessType && primaryService && targetLocation && homeBase);
    }

    if (selectedWorkflow === 'ai-search-report' && ready) {
      const domain   = document.getElementById('wfAIDomain')?.value.trim();
      const service  = document.getElementById('wfAIService')?.value.trim();
      const location = document.getElementById('wfAILocation')?.value.trim();
      ready = !!(domain && service && location);
    }

    if (selectedWorkflow === 'backlink-audit' && ready) {
      const domain = document.getElementById('wfBLDomain')?.value.trim();
      ready = !!domain;
    }

    if (selectedWorkflow === 'onpage-audit' && ready) {
      const url = document.getElementById('wfOPUrl')?.value.trim();
      ready = !!url;
    }

    if (selectedWorkflow === 'seo-research' && ready) {
      const domain   = document.getElementById('wfSRDomain')?.value.trim();
      const service  = document.getElementById('wfSRService')?.value.trim();
      const location = document.getElementById('wfSRLocation')?.value.trim();
      ready = !!(domain && service && location);
    }

    if (selectedWorkflow === 'competitor-intel' && ready) {
      const domain = document.getElementById('wfCIDomain')?.value.trim();
      ready = !!domain;
    }

    if (selectedWorkflow === 'monthly-report' && ready) {
      const domain = document.getElementById('wfMRDomain')?.value.trim();
      ready = !!domain;
    }

    if (selectedWorkflow === 'proposals' && ready) {
      const domain   = document.getElementById('wfPRDomain')?.value.trim();
      const service  = document.getElementById('wfPRService')?.value.trim();
      const location = document.getElementById('wfPRLocation')?.value.trim();
      ready = !!(domain && service && location);
    }

    if (selectedWorkflow === 'google-ads-copy' && ready) {
      const service  = document.getElementById('wfGAService')?.value.trim();
      const location = document.getElementById('wfGALocation')?.value.trim();
      ready = !!(service && location);
    }

    if (selectedWorkflow === 'schema-generator' && ready) {
      const businessType = document.getElementById('wfSCBusinessType')?.value.trim();
      const location     = document.getElementById('wfSCLocation')?.value.trim();
      ready = !!(businessType && location);
    }

    if (selectedWorkflow === 'content-strategy' && ready) {
      const businessType = document.getElementById('wfCSBusinessType')?.value.trim();
      const service      = document.getElementById('wfCSService')?.value.trim();
      const location     = document.getElementById('wfCSLocation')?.value.trim();
      ready = !!(businessType && service && location);
    }

    if (selectedWorkflow === 'pnl-statement' && ready) {
      const period  = document.getElementById('wfPLPeriod')?.value.trim();
      const revenue = document.getElementById('wfPLRevenue')?.value.trim();
      const expenses = document.getElementById('wfPLExpenses')?.value.trim();
      ready = !!(period && revenue && expenses);
    }

    if (selectedWorkflow === 'property-mgmt-strategy' && ready) {
      const domain   = document.getElementById('wfPMDomain')?.value.trim();
      const location = document.getElementById('wfPMLocation')?.value.trim();
      ready = !!(domain && location);
    }

    if (selectedWorkflow === 'page-design' && ready) {
      const pageType     = document.getElementById('wfPDPageType')?.value;
      const businessType = document.getElementById('wfPDBusinessType')?.value.trim();
      const service      = document.getElementById('wfPDService')?.value.trim();
      const location     = document.getElementById('wfPDLocation')?.value.trim();
      ready = !!(pageType && businessType && service && location);
    }

    if (selectedWorkflow === 'programmatic-content' && ready) {
      const contentType  = document.getElementById('wfProgContentType')?.value;
      const businessType = document.getElementById('wfProgBusinessType')?.value.trim();
      const itemsList    = document.getElementById('wfProgItemsList')?.value.trim();

      if (!contentType || !businessType || !itemsList) {
        ready = false;
      } else if (contentType === 'location-pages') {
        const primaryService = document.getElementById('wfProgPrimaryService')?.value.trim();
        const homeBase       = document.getElementById('wfProgHomeBase')?.value.trim();
        ready = !!(primaryService && homeBase);
      } else if (contentType === 'service-pages' || contentType === 'blog-posts' || contentType === 'comparison-posts' || contentType === 'cost-guides' || contentType === 'best-in-city') {
        const location = document.getElementById('wfProgLocation')?.value.trim();
        ready = !!location;
      }
      // Enforce 50-page batch limit
      if (ready && itemsList) {
        let lines = itemsList.split('\n');
        if (lines.length === 1 && lines[0].includes(',')) lines = lines[0].split(',');
        if (lines.filter(l => l.trim()).length > 50) ready = false;
      }
      updateProgItemCount();
    }

    if (selectedWorkflow === 'geo-content-audit' && ready) {
      const content  = document.getElementById('wfGEOContent')?.value.trim();
      const queries  = document.getElementById('wfGEOQueries')?.value.trim();
      ready = !!(content && queries);
    }

    if (selectedWorkflow === 'seo-content-audit' && ready) {
      const content  = document.getElementById('wfSCAContent')?.value.trim();
      const keyword  = document.getElementById('wfSCAKeyword')?.value.trim();
      ready = !!(content && keyword);
    }

    if (selectedWorkflow === 'technical-seo-review' && ready) {
      const domain   = document.getElementById('wfTSRDomain')?.value.trim();
      const platform = document.getElementById('wfTSRPlatform')?.value.trim();
      const bizType  = document.getElementById('wfTSRBizType')?.value.trim();
      const location = document.getElementById('wfTSRLocation')?.value.trim();
      ready = !!(domain && platform && bizType && location);
    }

    if (selectedWorkflow === 'programmatic-seo-strategy' && ready) {
      const bizType  = document.getElementById('wfPSSBizType')?.value.trim();
      const service  = document.getElementById('wfPSSService')?.value.trim();
      const location = document.getElementById('wfPSSLocation')?.value.trim();
      const pageType = document.getElementById('wfPSSPageType')?.value;
      ready = !!(bizType && service && location && pageType);
    }

    if (selectedWorkflow === 'competitor-seo-analysis' && ready) {
      const domain      = document.getElementById('wfCSADomain')?.value.trim();
      const competitors = document.getElementById('wfCSACompetitors')?.value.trim();
      const service     = document.getElementById('wfCSAService')?.value.trim();
      const location    = document.getElementById('wfCSALocation')?.value.trim();
      ready = !!(domain && competitors && service && location);
    }

    // Pipeline workflows
    if (selectedWorkflow === 'pipeline-service-page' && ready) {
      const domain   = document.getElementById('wfPipeDomain')?.value.trim();
      const service  = document.getElementById('wfPipeService')?.value.trim();
      const location = document.getElementById('wfPipeLocation')?.value.trim();
      ready = !!(domain && service && location);
    }
    if (selectedWorkflow === 'pipeline-location-page' && ready) {
      const domain   = document.getElementById('wfPipeDomain')?.value.trim();
      const service  = document.getElementById('wfPipeService')?.value.trim();
      const location = document.getElementById('wfPipeLocation')?.value.trim();
      ready = !!(domain && service && location);
    }
    if (selectedWorkflow === 'pipeline-blog-post' && ready) {
      const domain   = document.getElementById('wfPipeDomain')?.value.trim();
      const keyword  = document.getElementById('wfPipeKeyword')?.value.trim();
      const location = document.getElementById('wfPipeLocation')?.value.trim();
      ready = !!(domain && keyword && location);
    }
  }

  btn.disabled = !ready;
}

function onClientSelectChange() {
  const id = parseInt(document.getElementById('wfClientSelect')?.value);
  const client = CLIENTS.find(c => c.id === id);
  const ta = document.getElementById('wfStrategyCtx');
  if (ta && client) ta.value = client.strategy_context || '';
  checkRunReady();
  onAuditClientChange();
}

function onAuditClientChange() {
  // Auto-fill domain from CLIENTS when client is selected in the audit or prospect modal
  const clientSel = document.getElementById('wfClientSelect');
  if (!clientSel) return;
  const clientId = parseInt(clientSel.value);
  const client = CLIENTS.find(c => c.id === clientId);
  if (!client) return;

  if (selectedWorkflow === 'website-seo-audit') {
    const domainEl = document.getElementById('wfAuditDomain');
    if (domainEl) domainEl.value = client.domain;
  } else if (selectedWorkflow === 'prospect-audit') {
    const domainEl = document.getElementById('wfProspectDomain');
    if (domainEl) domainEl.value = client.domain;
  } else if (selectedWorkflow === 'keyword-gap') {
    const domainEl = document.getElementById('wfGapDomain');
    if (domainEl) domainEl.value = client.domain;
  } else if (selectedWorkflow === 'seo-blog-post') {
    const locationEl = document.getElementById('wfBlogLocation');
    if (locationEl && client.location) locationEl.value = client.location;
  } else if (selectedWorkflow === 'service-page') {
    const locationEl = document.getElementById('wfSvcLocation');
    if (locationEl && client.location) locationEl.value = client.location;
  } else if (selectedWorkflow === 'location-page') {
    const homeBaseEl = document.getElementById('wfLocHomeBase');
    if (homeBaseEl && client.location) homeBaseEl.value = client.location;
  } else if (selectedWorkflow === 'ai-search-report') {
    const domainEl = document.getElementById('wfAIDomain');
    if (domainEl && client.domain) domainEl.value = client.domain;
    const locationEl = document.getElementById('wfAILocation');
    if (locationEl && client.location) locationEl.value = client.location;
    const serviceEl = document.getElementById('wfAIService');
    if (serviceEl && client.service) serviceEl.value = client.service;
  } else if (selectedWorkflow === 'backlink-audit') {
    const domainEl = document.getElementById('wfBLDomain');
    if (domainEl && client.domain) domainEl.value = client.domain;
    const locationEl = document.getElementById('wfBLLocation');
    if (locationEl && client.location) locationEl.value = client.location;
    const serviceEl = document.getElementById('wfBLService');
    if (serviceEl && client.service) serviceEl.value = client.service;
  } else if (selectedWorkflow === 'onpage-audit') {
    const urlEl = document.getElementById('wfOPUrl');
    if (urlEl && client.domain) urlEl.value = client.domain;
    const locationEl = document.getElementById('wfOPLocation');
    if (locationEl && client.location) locationEl.value = client.location;
  } else if (selectedWorkflow === 'seo-research') {
    const domainEl = document.getElementById('wfSRDomain');
    if (domainEl && client.domain) domainEl.value = client.domain;
    const serviceEl = document.getElementById('wfSRService');
    if (serviceEl && client.service) serviceEl.value = client.service;
    const locationEl = document.getElementById('wfSRLocation');
    if (locationEl && client.location) locationEl.value = client.location;
  } else if (selectedWorkflow === 'competitor-intel') {
    const domainEl = document.getElementById('wfCIDomain');
    if (domainEl && client.domain) domainEl.value = client.domain;
    const serviceEl = document.getElementById('wfCIService');
    if (serviceEl && client.service) serviceEl.value = client.service;
    const locationEl = document.getElementById('wfCILocation');
    if (locationEl && client.location) locationEl.value = client.location;
  } else if (selectedWorkflow === 'monthly-report') {
    if (client.domain) document.getElementById('wfMRDomain').value = client.domain;
    if (client.service) document.getElementById('wfMRService').value = client.service;
    if (client.location) document.getElementById('wfMRLocation').value = client.location;
  } else if (selectedWorkflow === 'proposals') {
    if (client.domain) document.getElementById('wfPRDomain').value = client.domain;
    if (client.service) document.getElementById('wfPRService').value = client.service;
    if (client.location) document.getElementById('wfPRLocation').value = client.location;
  } else if (selectedWorkflow === 'google-ads-copy') {
    if (client.service) document.getElementById('wfGAService').value = client.service;
    if (client.location) document.getElementById('wfGALocation').value = client.location;
  } else if (selectedWorkflow === 'schema-generator') {
    if (client.service) document.getElementById('wfSCBusinessType').value = client.service;
    if (client.location) document.getElementById('wfSCLocation').value = client.location;
    if (client.domain) document.getElementById('wfSCWebsite').value = client.domain;
  } else if (selectedWorkflow === 'content-strategy') {
    if (client.service) document.getElementById('wfCSBusinessType').value = client.service;
    if (client.service) document.getElementById('wfCSService').value = client.service;
    if (client.location) document.getElementById('wfCSLocation').value = client.location;
  } else if (selectedWorkflow === 'property-mgmt-strategy') {
    if (client.domain) document.getElementById('wfPMDomain').value = client.domain;
    if (client.location) document.getElementById('wfPMLocation').value = client.location;
  } else if (selectedWorkflow && selectedWorkflow.startsWith('pipeline-')) {
    // Auto-fill pipeline inputs from client record
    const domainEl = document.getElementById('wfPipeDomain');
    const serviceEl = document.getElementById('wfPipeService');
    const locationEl = document.getElementById('wfPipeLocation');
    if (domainEl && client.domain) domainEl.value = client.domain;
    if (serviceEl && client.service) serviceEl.value = client.service;
    if (locationEl && client.location) locationEl.value = client.location;
  }
  checkRunReady();
}

function selectProgrammatic(contentType) {
  selectWorkflow('programmatic-content');
  // After modal opens, pre-select the content type
  setTimeout(() => {
    const sel = document.getElementById('wfProgContentType');
    if (sel) {
      sel.value = contentType;
      onProgContentTypeChange();
      checkRunReady();
    }
  }, 50);
}

function updateProgItemCount() {
  const el = document.getElementById('progItemCount');
  const textarea = document.getElementById('wfProgItemsList');
  if (!el || !textarea) return;

  const text = textarea.value.trim();
  if (!text) {
    el.style.display = 'none';
    return;
  }

  let lines = text.split('\n');
  if (lines.length === 1 && lines[0].includes(',')) {
    lines = lines[0].split(',');
  }
  const count = lines.filter(l => l.trim()).length;
  const max = 50;

  el.style.display = 'block';
  if (count > max) {
    el.innerHTML = `<span style="color:#FF4444;">${count} items — exceeds limit of ${max}</span>`;
  } else {
    el.innerHTML = `<span style="color:var(--text3);">${count} item${count !== 1 ? 's' : ''} · max ${max} per batch</span>`;
  }
}

async function discoverCities() {
  const cityInput = document.getElementById('wfProgDiscoverCity');
  const city = cityInput?.value.trim();
  const radius = document.getElementById('wfProgDiscoverRadius')?.value || '15';
  const btn = document.getElementById('btnDiscoverCities');

  if (!city) {
    showToast('Enter a center city first');
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = 'Searching...'; }

  try {
    const resp = await fetch('/api/discover-cities', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ city, radius: parseInt(radius) }),
    });

    if (!resp.ok) throw new Error('Server returned ' + resp.status);

    const data = await resp.json();
    const textarea = document.getElementById('wfProgItemsList');
    if (textarea && data.cities && data.cities.length > 0) {
      textarea.value = data.cities.join('\n');
      updateProgItemCount();
      checkRunReady();
      showToast('Found ' + data.cities.length + ' cities near ' + city);
    } else {
      showToast('No cities found — try a larger radius');
    }
  } catch (err) {
    showToast('Error: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Find Cities'; }
  }
}

function onProgContentTypeChange() {
  const contentType = document.getElementById('wfProgContentType')?.value;
  const locFields = document.getElementById('progLocFields');
  const svcBlogFields = document.getElementById('progSvcBlogFields');
  const itemsLabel = document.getElementById('progItemsLabel');
  const itemsTextarea = document.getElementById('wfProgItemsList');
  const itemsHint = document.getElementById('progItemsHint');
  const servicesWrap = document.getElementById('progServicesWrap');

  const autoDiscover = document.getElementById('progAutoDiscover');

  if (contentType === 'location-pages') {
    if (locFields) locFields.style.display = 'block';
    if (svcBlogFields) svcBlogFields.style.display = 'none';
    if (autoDiscover) autoDiscover.style.display = 'block';
    if (itemsLabel) itemsLabel.innerHTML = 'Locations <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One city per line, e.g.:\nMesa, AZ\nGilbert, AZ\nTempe, AZ\nScottsdale, AZ\nPhoenix, AZ';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a unique location page with its own DataForSEO research';
    if (servicesWrap) servicesWrap.style.display = '';
  } else if (contentType === 'service-pages') {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'block';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Services <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One service per line, e.g.:\npanel upgrade\nEV charger installation\nwhole-house rewiring\nelectrical inspection\ngenerator installation';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a unique service page with competitor research';
    if (servicesWrap) servicesWrap.style.display = 'none';
  } else if (contentType === 'blog-posts') {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'block';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Keywords <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One target keyword per line, e.g.:\nhow much does a panel upgrade cost\nsigns you need to rewire your house\nwhen to call an emergency electrician\nEV charger installation guide';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a unique blog post with keyword research data';
    if (servicesWrap) servicesWrap.style.display = 'none';
  } else if (contentType === 'comparison-posts') {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'block';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Comparisons <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One comparison per line, e.g.:\ntankless vs tank water heater\n100 amp vs 200 amp panel\ncopper vs PEX piping\nductless mini split vs central air';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a unique "X vs Y" comparison post with SERP research';
    if (servicesWrap) servicesWrap.style.display = 'none';
  } else if (contentType === 'cost-guides') {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'block';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Services to Price <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One service per line, e.g.:\npanel upgrade\nwhole house rewiring\nEV charger installation\nelectrical inspection\ngenerator installation';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a "How Much Does X Cost in [City]" pricing guide';
    if (servicesWrap) servicesWrap.style.display = 'none';
  } else if (contentType === 'best-in-city') {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'block';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Service Types <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'One service type per line, e.g.:\nelectrician\nresidential electrician\ncommercial electrician\nemergency electrician';
    if (itemsHint) itemsHint.textContent = 'Each line becomes a "Best [Service] in [City]" post with real Maps competitor data';
    if (servicesWrap) servicesWrap.style.display = 'none';
  } else {
    if (locFields) locFields.style.display = 'none';
    if (svcBlogFields) svcBlogFields.style.display = 'none';
    if (autoDiscover) autoDiscover.style.display = 'none';
    if (itemsLabel) itemsLabel.innerHTML = 'Items <span class="req">*</span>';
    if (itemsTextarea) itemsTextarea.placeholder = 'Select a content type above to see format...';
    if (itemsHint) itemsHint.textContent = 'Enter one item per line — each becomes a unique page with its own DataForSEO research';
    if (servicesWrap) servicesWrap.style.display = 'none';
  }
  updateProgItemCount();
}

async function launchWorkflow() {
  if (!selectedWorkflow) return;

  const wf = WORKFLOWS.find(w => w.id === selectedWorkflow);
  let clientName, clientVal;

  if (selectedWorkflow === 'prospect-audit') {
    // Prospect-audit: name comes from the prospect name field, no client_id
    clientName = document.getElementById('wfProspectName')?.value.trim();
    if (!clientName) return;
    clientVal = '0';
  } else {
    const clientSel = document.getElementById('wfClientSelect');
    clientVal = clientSel?.value;
    if (!clientVal) return;
    clientName = clientSel.options[clientSel.selectedIndex].text;
  }
  const now = new Date();
  const timeStr = now.toTimeString().slice(0, 8);

  const newJob = {
    id: `JOB-${4822 + JOBS.length}`,
    wf: wf.title,
    client: clientName,
    started: 'just now',
    duration: '–',
    status: 'running',
    pct: 0,
    output: 'Streaming...'
  };
  JOBS.unshift(newJob);
  jobProgresses[newJob.id] = 0;
  LOG_ENTRIES.unshift({ time: timeStr, level: 'info', msg: `${newJob.id} started — ${wf.title} for ${clientName}` });

  // Close modal and open job monitor
  document.getElementById('wfModal').classList.remove('open');
  document.body.style.overflow = '';
  updateJobsBadge();
  showJobMonitor(newJob.id);
  startStreamingTerminal(newJob.id, wf.title, clientName);

  // Build inputs + strategy context per workflow
  let inputs = {};
  const strategyContext = document.getElementById('wfStrategyCtx')?.value.trim() || '';

  if (selectedWorkflow === 'home-service-content') {
    inputs = {
      business_type: document.getElementById('wfBusinessType')?.value.trim() || '',
      location:      document.getElementById('wfLocation')?.value.trim() || '',
      keyword:       document.getElementById('wfKeyword')?.value.trim() || '',
      service_focus: document.getElementById('wfServiceFocus')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'website-seo-audit') {
    inputs = {
      domain:   document.getElementById('wfAuditDomain')?.value.trim() || '',
      service:  document.getElementById('wfAuditService')?.value.trim() || '',
      location: document.getElementById('wfAuditLocation')?.value.trim() || '',
      notes:    document.getElementById('wfAuditNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'prospect-audit') {
    inputs = {
      domain:          document.getElementById('wfProspectDomain')?.value.trim() || '',
      service:         document.getElementById('wfProspectService')?.value.trim() || '',
      location:        document.getElementById('wfProspectLocation')?.value.trim() || '',
      monthly_revenue: document.getElementById('wfProspectRevenue')?.value.trim() || '',
      avg_job_value:   document.getElementById('wfProspectJobValue')?.value.trim() || '',
      notes:           document.getElementById('wfProspectNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'keyword-gap') {
    inputs = {
      domain:             document.getElementById('wfGapDomain')?.value.trim() || '',
      service:            document.getElementById('wfGapService')?.value.trim() || '',
      location:           document.getElementById('wfGapLocation')?.value.trim() || '',
      competitor_domains: document.getElementById('wfGapCompetitors')?.value.trim() || '',
      notes:              document.getElementById('wfGapNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'seo-blog-post') {
    inputs = {
      business_type:  document.getElementById('wfBlogBusinessType')?.value.trim() || '',
      location:       document.getElementById('wfBlogLocation')?.value.trim() || '',
      keyword:        document.getElementById('wfBlogKeyword')?.value.trim() || '',
      audience:       document.getElementById('wfBlogAudience')?.value.trim() || '',
      tone:           document.getElementById('wfBlogTone')?.value.trim() || '',
      internal_links: document.getElementById('wfBlogInternalLinks')?.value.trim() || '',
      notes:          document.getElementById('wfBlogNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'service-page') {
    inputs = {
      business_type:   document.getElementById('wfSvcBusinessType')?.value.trim() || '',
      service:         document.getElementById('wfSvcService')?.value.trim() || '',
      location:        document.getElementById('wfSvcLocation')?.value.trim() || '',
      differentiators: document.getElementById('wfSvcDifferentiators')?.value.trim() || '',
      price_range:     document.getElementById('wfSvcPriceRange')?.value.trim() || '',
      notes:           document.getElementById('wfSvcNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'location-page') {
    inputs = {
      business_type:    document.getElementById('wfLocBusinessType')?.value.trim() || '',
      primary_service:  document.getElementById('wfLocPrimaryService')?.value.trim() || '',
      target_location:  document.getElementById('wfLocTargetLocation')?.value.trim() || '',
      home_base:        document.getElementById('wfLocHomeBase')?.value.trim() || '',
      local_details:    document.getElementById('wfLocLocalDetails')?.value.trim() || '',
      services_list:    document.getElementById('wfLocServicesList')?.value.trim() || '',
      notes:            document.getElementById('wfLocNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'ai-search-report') {
    inputs = {
      domain:   document.getElementById('wfAIDomain')?.value.trim() || '',
      service:  document.getElementById('wfAIService')?.value.trim() || '',
      location: document.getElementById('wfAILocation')?.value.trim() || '',
      notes:    document.getElementById('wfAINotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'backlink-audit') {
    inputs = {
      domain:      document.getElementById('wfBLDomain')?.value.trim() || '',
      service:     document.getElementById('wfBLService')?.value.trim() || '',
      location:    document.getElementById('wfBLLocation')?.value.trim() || '',
      competitors: document.getElementById('wfBLCompetitors')?.value.trim() || '',
      notes:       document.getElementById('wfBLNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'onpage-audit') {
    inputs = {
      url:      document.getElementById('wfOPUrl')?.value.trim() || '',
      keyword:  document.getElementById('wfOPKeyword')?.value.trim() || '',
      location: document.getElementById('wfOPLocation')?.value.trim() || '',
      notes:    document.getElementById('wfOPNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'seo-research') {
    inputs = {
      domain:      document.getElementById('wfSRDomain')?.value.trim() || '',
      service:     document.getElementById('wfSRService')?.value.trim() || '',
      location:    document.getElementById('wfSRLocation')?.value.trim() || '',
      competitors: document.getElementById('wfSRCompetitors')?.value.trim() || '',
      notes:       document.getElementById('wfSRNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'competitor-intel') {
    inputs = {
      domain:      document.getElementById('wfCIDomain')?.value.trim() || '',
      competitors: document.getElementById('wfCICompetitors')?.value.trim() || '',
      service:     document.getElementById('wfCIService')?.value.trim() || '',
      location:    document.getElementById('wfCILocation')?.value.trim() || '',
      notes:       document.getElementById('wfCINotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'monthly-report') {
    inputs = {
      domain:           document.getElementById('wfMRDomain')?.value.trim() || '',
      service:          document.getElementById('wfMRService')?.value.trim() || '',
      location:         document.getElementById('wfMRLocation')?.value.trim() || '',
      reporting_period: document.getElementById('wfMRPeriod')?.value.trim() || '',
      highlights:       document.getElementById('wfMRHighlights')?.value.trim() || '',
      notes:            document.getElementById('wfMRNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'proposals') {
    inputs = {
      domain:       document.getElementById('wfPRDomain')?.value.trim() || '',
      service:      document.getElementById('wfPRService')?.value.trim() || '',
      location:     document.getElementById('wfPRLocation')?.value.trim() || '',
      package_tier: document.getElementById('wfPRPackage')?.value.trim() || 'growth-strategy',
      competitors:  document.getElementById('wfPRCompetitors')?.value.trim() || '',
      notes:        document.getElementById('wfPRNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'google-ads-copy') {
    inputs = {
      service:       document.getElementById('wfGAService')?.value.trim() || '',
      location:      document.getElementById('wfGALocation')?.value.trim() || '',
      business_name: document.getElementById('wfGABusinessName')?.value.trim() || '',
      usp:           document.getElementById('wfGAUsp')?.value.trim() || '',
      landing_url:   document.getElementById('wfGALandingUrl')?.value.trim() || '',
      budget:        document.getElementById('wfGABudget')?.value.trim() || '',
      notes:         document.getElementById('wfGANotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'schema-generator') {
    inputs = {
      business_name:  document.getElementById('wfSCBusinessName')?.value.trim() || '',
      business_type:  document.getElementById('wfSCBusinessType')?.value.trim() || '',
      location:       document.getElementById('wfSCLocation')?.value.trim() || '',
      schema_types:   document.getElementById('wfSCSchemaTypes')?.value.trim() || 'LocalBusiness, FAQPage, Service',
      phone:          document.getElementById('wfSCPhone')?.value.trim() || '',
      address:        document.getElementById('wfSCAddress')?.value.trim() || '',
      website:        document.getElementById('wfSCWebsite')?.value.trim() || '',
      services_list:  document.getElementById('wfSCServicesList')?.value.trim() || '',
      hours:          document.getElementById('wfSCHours')?.value.trim() || '',
      notes:          document.getElementById('wfSCNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'content-strategy') {
    inputs = {
      business_type:   document.getElementById('wfCSBusinessType')?.value.trim() || '',
      service:         document.getElementById('wfCSService')?.value.trim() || '',
      location:        document.getElementById('wfCSLocation')?.value.trim() || '',
      target_audience: document.getElementById('wfCSAudience')?.value.trim() || '',
      content_goals:   document.getElementById('wfCSGoals')?.value.trim() || '',
      notes:           document.getElementById('wfCSNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'pnl-statement') {
    inputs = {
      period:          document.getElementById('wfPLPeriod')?.value.trim() || '',
      revenue_items:   document.getElementById('wfPLRevenue')?.value.trim() || '',
      expense_items:   document.getElementById('wfPLExpenses')?.value.trim() || '',
      business_entity: document.getElementById('wfPLEntity')?.value.trim() || 'ProofPilot',
      notes:           document.getElementById('wfPLNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'property-mgmt-strategy') {
    inputs = {
      domain:         document.getElementById('wfPMDomain')?.value.trim() || '',
      company_name:   document.getElementById('wfPMCompany')?.value.trim() || '',
      location:       document.getElementById('wfPMLocation')?.value.trim() || '',
      property_types: document.getElementById('wfPMPropertyTypes')?.value.trim() || '',
      portfolio_size: document.getElementById('wfPMPortfolioSize')?.value.trim() || '',
      notes:          document.getElementById('wfPMNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'page-design') {
    inputs = {
      page_type:       document.getElementById('wfPDPageType')?.value || '',
      business_type:   document.getElementById('wfPDBusinessType')?.value.trim() || '',
      service:         document.getElementById('wfPDService')?.value.trim() || '',
      location:        document.getElementById('wfPDLocation')?.value.trim() || '',
      domain:          document.getElementById('wfPDDomain')?.value.trim() || '',
      business_name:   document.getElementById('wfPDBusinessName')?.value.trim() || '',
      phone:           document.getElementById('wfPDPhone')?.value.trim() || '',
      brand_colors:    document.getElementById('wfPDBrandColors')?.value.trim() || '',
      style_direction: document.getElementById('wfPDStyle')?.value.trim() || '',
      existing_copy:   document.getElementById('wfPDExistingCopy')?.value.trim() || '',
      notes:           document.getElementById('wfPDNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'programmatic-content') {
    inputs = {
      content_type:     document.getElementById('wfProgContentType')?.value || '',
      business_type:    document.getElementById('wfProgBusinessType')?.value.trim() || '',
      primary_service:  document.getElementById('wfProgPrimaryService')?.value.trim() || '',
      location:         document.getElementById('wfProgLocation')?.value.trim() || '',
      home_base:        document.getElementById('wfProgHomeBase')?.value.trim() || '',
      items_list:       document.getElementById('wfProgItemsList')?.value.trim() || '',
      services_list:    document.getElementById('wfProgServicesList')?.value.trim() || '',
      differentiators:  document.getElementById('wfProgDifferentiators')?.value.trim() || '',
      notes:            document.getElementById('wfProgNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'geo-content-audit') {
    inputs = {
      content:          document.getElementById('wfGEOContent')?.value.trim() || '',
      target_queries:   document.getElementById('wfGEOQueries')?.value.trim() || '',
      business_type:    document.getElementById('wfGEOBizType')?.value.trim() || '',
      location:         document.getElementById('wfGEOLocation')?.value.trim() || '',
      competitor_urls:  document.getElementById('wfGEOCompUrls')?.value.trim() || '',
      notes:            document.getElementById('wfGEONotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'seo-content-audit') {
    inputs = {
      content:          document.getElementById('wfSCAContent')?.value.trim() || '',
      keyword:          document.getElementById('wfSCAKeyword')?.value.trim() || '',
      title_tag:        document.getElementById('wfSCATitleTag')?.value.trim() || '',
      meta_description: document.getElementById('wfSCAMetaDesc')?.value.trim() || '',
      url:              document.getElementById('wfSCAUrl')?.value.trim() || '',
      business_type:    document.getElementById('wfSCABizType')?.value.trim() || '',
      notes:            document.getElementById('wfSCANotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'technical-seo-review') {
    inputs = {
      domain:         document.getElementById('wfTSRDomain')?.value.trim() || '',
      platform:       document.getElementById('wfTSRPlatform')?.value.trim() || '',
      business_type:  document.getElementById('wfTSRBizType')?.value.trim() || '',
      location:       document.getElementById('wfTSRLocation')?.value.trim() || '',
      page_types:     document.getElementById('wfTSRPageTypes')?.value.trim() || '',
      known_issues:   document.getElementById('wfTSRKnownIssues')?.value.trim() || '',
      notes:          document.getElementById('wfTSRNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'programmatic-seo-strategy') {
    inputs = {
      business_type:  document.getElementById('wfPSSBizType')?.value.trim() || '',
      service:        document.getElementById('wfPSSService')?.value.trim() || '',
      location:       document.getElementById('wfPSSLocation')?.value.trim() || '',
      page_type:      document.getElementById('wfPSSPageType')?.value || '',
      scale:          document.getElementById('wfPSSScale')?.value.trim() || '',
      competitors:    document.getElementById('wfPSSCompetitors')?.value.trim() || '',
      data_assets:    document.getElementById('wfPSSDataAssets')?.value.trim() || '',
      notes:          document.getElementById('wfPSSNotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow === 'competitor-seo-analysis') {
    inputs = {
      domain:       document.getElementById('wfCSADomain')?.value.trim() || '',
      competitors:  document.getElementById('wfCSACompetitors')?.value.trim() || '',
      service:      document.getElementById('wfCSAService')?.value.trim() || '',
      location:     document.getElementById('wfCSALocation')?.value.trim() || '',
      keywords:     document.getElementById('wfCSAKeywords')?.value.trim() || '',
      notes:        document.getElementById('wfCSANotes')?.value.trim() || '',
    };
  } else if (selectedWorkflow.startsWith('pipeline-')) {
    inputs = {
      domain:          document.getElementById('wfPipeDomain')?.value.trim() || '',
      service:         document.getElementById('wfPipeService')?.value.trim() || '',
      location:        document.getElementById('wfPipeLocation')?.value.trim() || '',
      keyword:         document.getElementById('wfPipeKeyword')?.value.trim() || '',
      differentiators: document.getElementById('wfPipeDifferentiators')?.value.trim() || '',
      price_range:     document.getElementById('wfPipePriceRange')?.value.trim() || '',
      competitors:     document.getElementById('wfPipeCompetitors')?.value.trim() || '',
      notes:           document.getElementById('wfPipeNotes')?.value.trim() || '',
      // Map pipeline-specific fields
      primary_service:  document.getElementById('wfPipeService')?.value.trim() || '',
      target_location:  document.getElementById('wfPipeLocation')?.value.trim() || '',
      business_type:    document.getElementById('wfPipeService')?.value.trim() || '',
    };
  }

  // Pipeline workflows use a different API endpoint
  const pipelineTypes = {
    'pipeline-service-page': 'service-page',
    'pipeline-location-page': 'location-page',
    'pipeline-blog-post': 'blog-post',
  };

  if (pipelineTypes[selectedWorkflow]) {
    const pipePayload = {
      page_type: pipelineTypes[selectedWorkflow],
      client_id: parseInt(clientVal),
      client_name: clientName,
      inputs,
      approval_mode: 'autopilot',
    };

    try {
      const response = await fetch(`${API_BASE}/api/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pipePayload),
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      sseBuffer = '';

      activeSSEJobs.add(newJob.id);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          processSSEChunk(decoder.decode(value, { stream: true }), newJob);
        }
      } finally {
        activeSSEJobs.delete(newJob.id);
      }
    } catch (err) {
      activeSSEJobs.delete(newJob.id);
      appendErrorLineToTerminal(`Connection error: ${err.message}`);
      newJob.status = 'failed';
      newJob.output = err.message;
      terminalStreaming = false;
      streamDiv = null;
    }
    return;
  }

  const liveWorkflows = ['home-service-content', 'website-seo-audit', 'prospect-audit', 'keyword-gap', 'seo-blog-post', 'service-page', 'location-page', 'programmatic-content', 'ai-search-report', 'backlink-audit', 'onpage-audit', 'seo-research', 'competitor-intel', 'monthly-report', 'proposals', 'google-ads-copy', 'schema-generator', 'content-strategy', 'pnl-statement', 'property-mgmt-strategy', 'page-design', 'geo-content-audit', 'seo-content-audit', 'technical-seo-review', 'programmatic-seo-strategy', 'competitor-seo-analysis'];

  if (liveWorkflows.includes(selectedWorkflow)) {
    const payload = {
      workflow_id: selectedWorkflow,
      client_id: parseInt(clientVal),
      client_name: clientName,
      inputs,
      strategy_context: strategyContext,
    };

    try {
      const response = await fetch(`${API_BASE}/api/run-workflow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      sseBuffer = '';

      activeSSEJobs.add(newJob.id);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          processSSEChunk(decoder.decode(value, { stream: true }), newJob);
        }
      } finally {
        activeSSEJobs.delete(newJob.id);
      }
    } catch (err) {
      activeSSEJobs.delete(newJob.id);
      appendErrorLineToTerminal(`Connection error: ${err.message}`);
      newJob.status = 'failed';
      newJob.output = err.message;
      terminalStreaming = false;
      streamDiv = null;
    }
  } else {
    // Mock for workflows without a live backend yet
    showToast(`▷ ${wf.title} launched for ${clientName} (mock)`);
    setTimeout(() => {
      const tb = document.getElementById('terminal');
      if (tb) {
        const mockDiv = document.createElement('div');
        mockDiv.className = 'tl-w';
        mockDiv.textContent = `  ⚠ ${wf.title} backend not yet connected — coming in a future session`;
        tb.appendChild(mockDiv);
        tb.scrollTop = tb.scrollHeight;
      }
      newJob.status = 'completed';
      newJob.output = 'Mock complete';
      terminalStreaming = false;
      streamDiv = null;
    }, 1500);
  }
}

function startStreamingTerminal(jobId, wfTitle, clientName) {
  terminalStreaming = true;
  streamDiv = null;
  markdownBuffer = '';
  currentDocContent = '';
  // Reset document panel and start in terminal view
  const docPanel = document.getElementById('docPanel');
  if (docPanel) docPanel.innerHTML = '<div class="doc-panel-empty">Generating document...</div>';
  toggleDocView('terminal');
  sseBuffer = '';

  const tb = activeTerminalEl || document.getElementById('terminal');
  if (!tb) return;

  tb.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'tl-d';
  header.textContent = `# ProofPilot Claude Agent — ${new Date().toISOString().slice(0, 10)}`;
  tb.appendChild(header);
  tb.appendChild(document.createElement('br'));

  const jobLine = document.createElement('div');
  jobLine.className = 'tl-inf';
  jobLine.textContent = `▷ ${jobId} — ${wfTitle} for ${clientName}`;
  tb.appendChild(jobLine);
  tb.appendChild(document.createElement('br'));

  const callingLine = document.createElement('div');
  callingLine.className = 'tl-p';
  callingLine.innerHTML = '<span class="t-prompt">$ </span>Calling Claude Opus · streaming output...';
  tb.appendChild(callingLine);
  tb.appendChild(document.createElement('br'));
}

function appendTokenToTerminal(text) {
  // Always accumulate into markdown buffer (for document view)
  markdownBuffer += text;

  // Terminal view: raw text append
  const tb = activeTerminalEl || document.getElementById('terminal');
  if (tb) {
    if (!streamDiv) {
      streamDiv = document.createElement('div');
      streamDiv.className = 'tl-stream';
      tb.appendChild(streamDiv);
    }
    streamDiv.textContent += text;
    tb.scrollTop = tb.scrollHeight;
  }

  // Document view: re-render markdown (throttled)
  if (docViewMode === 'document') {
    _scheduleDocRender();
  }
}

/* Throttle document re-renders — 500ms for HTML (iframe reload is expensive), 120ms for markdown */
let _docRenderTimer = null;
function _scheduleDocRender() {
  if (_docRenderTimer) return;
  const content = markdownBuffer || currentDocContent;
  const interval = _isHtmlContent(content) ? 500 : 120;
  _docRenderTimer = setTimeout(() => {
    _docRenderTimer = null;
    renderDocPanel();
  }, interval);
}

function appendErrorLineToTerminal(msg) {
  const tb = activeTerminalEl || document.getElementById('terminal');
  if (!tb) return;
  const errDiv = document.createElement('div');
  errDiv.className = 'tl-err';
  errDiv.textContent = `✗ ${msg}`;
  tb.appendChild(errDiv);
  tb.scrollTop = tb.scrollHeight;
}

function appendStatusLineToTerminal(msg) {
  const tb = activeTerminalEl || document.getElementById('terminal');
  if (!tb) return;
  streamDiv = null; // force new div for stage markers
  const statusDiv = document.createElement('div');
  statusDiv.className = 'tl-status';
  statusDiv.textContent = msg;
  tb.appendChild(statusDiv);
  tb.scrollTop = tb.scrollHeight;
}

function processSSEChunk(chunk, job) {
  sseBuffer += chunk;
  const lines = sseBuffer.split('\n');
  sseBuffer = lines.pop(); // keep last (possibly incomplete) line

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    try {
      const data = JSON.parse(line.slice(6));
      if (data.type === 'token') {
        appendTokenToTerminal(data.text);
        if (job) jobProgresses[job.id] = Math.min(95, (jobProgresses[job.id] || 0) + 0.25);

      } else if (data.type === 'stage_start') {
        const stageLabel = (data.stage || '').toUpperCase();
        const stageNum = (data.stage_index || 0) + 1;
        const total = data.total_stages || 5;
        appendStatusLineToTerminal(`\n▸ Stage ${stageNum}/${total}: ${stageLabel}`);
        if (job) jobProgresses[job.id] = Math.min(90, (stageNum / total) * 80);

      } else if (data.type === 'stage_complete') {
        const stageLabel = (data.stage || '').toUpperCase();
        appendStatusLineToTerminal(`  ✓ ${stageLabel} complete`);

      } else if (data.type === 'awaiting_approval') {
        appendStatusLineToTerminal(`\n⏸ Paused — awaiting approval for "${data.stage}"`);
        if (job) { job.status = 'paused'; job.pipelineId = data.pipeline_id; }

      } else if (data.type === 'pipeline_complete') {
        appendStatusLineToTerminal(`\n✅ Pipeline complete — ${data.stages_completed} stages finished`);
        if (data.pipeline_id && job) job.pipelineId = data.pipeline_id;
        // Fall through to done-like handling below

      } else if (data.type === 'done') {
        currentJobId = data.job_id;
        terminalStreaming = false;
        streamDiv = null;

        // Save final document content and render
        currentDocContent = markdownBuffer;
        renderDocPanel();
        // Auto-switch to document view on completion
        toggleDocView('document');

        // Initialize version history and show edit bar
        activeEditJobId = data.job_id;
        docVersions = [{ content: currentDocContent, instruction: 'Original' }];
        docVersionIndex = 0;
        _updateVersionBar('monitor');
        const editBar = document.getElementById('docEditBar');
        if (editBar) editBar.style.display = 'flex';

        if (job) {
          job.status = 'completed';
          job.output = 'Complete — ready to download';
          job.server_job_id = data.job_id; // store server UUID for later lookup
          job.docContent = currentDocContent; // cache for later viewing
          jobProgresses[job.id] = 100;
        }

        const tb = activeTerminalEl || document.getElementById('terminal');
        if (tb) {
          tb.appendChild(document.createElement('br'));
          const doneDiv = document.createElement('div');
          doneDiv.className = 'tl-ok';
          doneDiv.textContent = `✓ Complete — Job ${data.job_id}`;
          tb.appendChild(doneDiv);
          tb.scrollTop = tb.scrollHeight;
        }

        // Update job monitor done bar
        if (monitorJobId === job?.id) {
          updateMonitorStatus('completed');
          const doneBar = document.getElementById('jmDoneBar');
          const dlLink = document.getElementById('jmDownloadLink');
          const previewLink = document.getElementById('jmPreviewLink');
          const doneMsg = document.getElementById('jmDoneMsg');
          if (doneBar && dlLink && doneMsg) {
            doneMsg.textContent = `Job ${data.job_id} complete — output ready`;
            if (data.workflow_id === 'page-design') {
              // Show preview link, hide download
              if (previewLink) {
                previewLink.href = `${API_BASE}/api/preview/${data.job_id}`;
                previewLink.style.display = '';
              }
              dlLink.style.display = 'none';
            } else {
              dlLink.href = `${API_BASE}/api/download/${data.job_id}`;
              dlLink.style.display = '';
              if (previewLink) previewLink.style.display = 'none';
            }
            doneBar.style.display = 'flex';
          }
        }

        // Add to content library
        addToContentLibrary(
          data.job_id,
          data.client_name || job?.client || '',
          0,
          data.workflow_id || selectedWorkflow || '',
          data.workflow_title || job?.wf || ''
        );

        updateJobsBadge();
        showToast(`✓ ${job?.wf || 'Workflow'} complete`);
        LOG_ENTRIES.unshift({ time: new Date().toTimeString().slice(0, 8), level: 'ok', msg: `${job?.id} completed — ${job?.wf} for ${job?.client}` });

      } else if (data.type === 'error') {
        appendErrorLineToTerminal(data.message || 'Workflow error');
        terminalStreaming = false;
        streamDiv = null;
        if (job) { job.status = 'failed'; job.output = data.message || 'Error'; }
      }
    } catch (e) { /* skip malformed lines */ }
  }
}

/* ── CLIENTS ── */
function renderClients(filter = '') {
  const el = document.getElementById('clientsTbody');
  if (!el) return;

  const filtered = filter
    ? CLIENTS.filter(c => c.name.toLowerCase().includes(filter) || c.domain.toLowerCase().includes(filter))
    : CLIENTS;

  el.innerHTML = filtered.map(c => {
    const scoreClass = c.score >= 80 ? 'score-hi' : c.score >= 65 ? 'score-md' : 'score-lo';
    const isActive = c.status === 'active';
    return `
      <tr class="${isActive ? '' : 'row-inactive'}">
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:26px;height:26px;background:var(--dark-blue);border:1px solid rgba(0,81,255,0.3);
                        display:flex;align-items:center;justify-content:center;
                        font-family:var(--display);font-size:10px;color:${c.color};">${c.initials}</div>
            <span class="client-name-link" onclick="showClientHub(${c.id})">${c.name}</span>
          </div>
        </td>
        <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">${c.domain}</td>
        <td style="color:var(--text3);">${c.plan}</td>
        <td><span class="seo-score ${scoreClass}">${c.score || '–'}</span></td>
        <td style="font-family:var(--mono);color:var(--text3);">${c.avgRank !== '–' ? '#' + c.avgRank : '–'}</td>
        <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">${c.lastJob}</td>
        <td>
          <span class="pill ${isActive ? 'pill-act' : 'pill-inactive'} pill-toggle"
                onclick="toggleClientStatus(${c.id})"
                title="${isActive ? 'Click to deactivate' : 'Click to activate'}">
            ${isActive ? 'Active' : 'Inactive'}
          </span>
        </td>
        <td style="display:flex;gap:6px;">
          <button class="tbl-btn" onclick="showClientHub(${c.id})">Hub</button>
          <button class="tbl-btn" onclick="showEditClientModal(${c.id})">Edit</button>
          <button class="tbl-btn" onclick="selectWorkflowForClient(${c.id})" ${isActive ? '' : 'disabled'}>Run</button>
        </td>
      </tr>
    `;
  }).join('');
}

/* ── CLIENT HUB ── */

function showClientHub(clientId) {
  // Reset brain + sprint state when switching to a different client
  if (activeClientId !== clientId) {
    clientHubTab = 'activity';
    clientBrainData = null;
    sprintItems = [];
    sprintRunning = false;
  }
  activeClientId = clientId;
  // Keep the Clients nav item highlighted when viewing the hub
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const el = document.getElementById('view-client-hub');
  if (el) el.classList.add('active');

  const navClients = document.getElementById('nav-clients');
  if (navClients) navClients.classList.add('active');

  const title = document.getElementById('pageTitle');
  const client = CLIENTS.find(c => c.id === clientId);
  if (title && client) title.textContent = client.name;

  currentView = 'client-hub';
  renderClientHub();
}

function showClientHubByName(clientName) {
  const client = CLIENTS.find(c => c.name === clientName);
  if (client) showClientHub(client.id);
}

function renderClientHub() {
  const el = document.getElementById('clientHubContent');
  if (!el) return;

  const client = CLIENTS.find(c => c.id === activeClientId);
  if (!client) {
    el.innerHTML = '<div class="empty-state">Client not found.</div>';
    return;
  }

  const clientJobs = JOBS.filter(j => j.client === client.name);
  const runningJobs = clientJobs.filter(j => j.status === 'running');
  const completedJobs = clientJobs.filter(j => j.status === 'completed' || j.status === 'complete');

  const scoreClass = client.score >= 80 ? 'score-hi' : client.score >= 65 ? 'score-md' : 'score-lo';
  const trendUp = client.trend && client.trend.startsWith('+');
  const trendDown = client.trend && client.trend.startsWith('-');

  // Plan badge class
  const planKey = (client.plan || '').toLowerCase();
  const planClass = `ch-plan-${planKey}`;

  // Stats
  const totalRun = clientJobs.length;
  const lastJobDate = clientJobs.length ? clientJobs[0].started : '—';
  const avgScore = client.score;

  // Needs Attention recommendations based on score
  let attentionTasks = [];
  if (client.score < 60) {
    attentionTasks = [
      { name: 'Technical SEO Audit overdue', desc: 'Core Web Vitals and crawl errors need immediate review.', priority: 'high' },
      { name: 'GBP optimization needed', desc: 'Google Business Profile is incomplete or out of date.', priority: 'high' },
      { name: 'Page speed issues detected', desc: 'LCP score above threshold on mobile — impacts local rankings.', priority: 'medium' },
    ];
  } else if (client.score < 76) {
    attentionTasks = [
      { name: 'Content gaps identified', desc: '12+ keywords competitors rank for that this site does not.', priority: 'medium' },
      { name: 'Link building opportunity', desc: '3 high-authority local directories have unclaimed listings.', priority: 'medium' },
      { name: 'Schema markup missing', desc: 'LocalBusiness and Service schemas not implemented.', priority: 'low' },
    ];
  } else {
    attentionTasks = [
      { name: 'Competitor monitoring active', desc: 'Top 3 competitors gained rankings in past 30 days — review now.', priority: 'low' },
      { name: 'Content calendar update due', desc: 'Next content batch should be scheduled for next month.', priority: 'low' },
      { name: 'Review acquisition momentum', desc: 'GBP review velocity slowing — consider review outreach campaign.', priority: 'medium' },
    ];
  }

  // WF icon map for content strip
  const wfIconMap = {
    'Website & SEO Audit': '🔍',
    'Prospect SEO Market Analysis': '🎯',
    'Keyword Gap Analysis': '🔍',
    'Home Service SEO Content': '🏠',
    'SEO Blog Generator': '✍️',
  };

  // ── In Progress column ──
  const inProgressHTML = runningJobs.length
    ? runningJobs.map(j => {
        const pct = Math.round(jobProgresses[j.id] || j.pct || 0);
        return `
          <div class="ch-job-card">
            <div class="ch-job-type">${j.wf}</div>
            <div class="ch-job-meta">Started ${j.started}</div>
            <div class="ch-job-progress">
              <div class="ch-job-progress-fill" style="width:${pct}%"></div>
            </div>
            <button class="ch-view-live-btn" onclick="showJobMonitor('${j.id}')">View Live</button>
          </div>
        `;
      }).join('')
    : `<div class="empty-state" style="padding:24px 16px;">No active tasks running for this client.</div>`;

  // ── Recently Completed column ──
  const completedHTML = completedJobs.length
    ? completedJobs.slice(0, 10).map(j => {
        const icon = wfIconMap[j.wf] || '📄';
        const dlBtn = j.server_job_id
          ? `<a class="ch-dl-btn" href="${API_BASE}/api/download/${j.server_job_id}" target="_blank" onclick="event.stopPropagation()">↓ .docx</a>`
          : `<span class="ch-dl-btn" style="opacity:0.4;cursor:default;">↓ .docx</span>`;
        return `
          <div class="ch-done-card" onclick="${j.server_job_id ? `viewContentItem('${j.server_job_id}')` : `showJobMonitor('${j.id}')`}" style="cursor:pointer;">
            <div class="ch-done-icon">${icon}</div>
            <div class="ch-done-info">
              <div class="ch-done-title">${j.wf}</div>
              <div class="ch-done-date">${j.started}</div>
            </div>
            ${dlBtn}
          </div>
        `;
      }).join('')
    : `<div class="empty-state" style="padding:24px 16px;">No completed workflows yet — run one above.</div>`;

  // ── Needs Attention column ──
  const attentionHTML = attentionTasks.map(t => `
    <div class="ch-task-card priority-${t.priority}">
      <div class="ch-task-header">
        <span class="ch-task-name">${t.name}</span>
        <span class="ch-priority-badge">${t.priority}</span>
      </div>
      <div class="ch-task-desc">${t.desc}</div>
    </div>
  `).join('');

  // ── Content library strip items ──
  const stripHTML = completedJobs.length
    ? completedJobs.slice(0, 12).map(j => {
        const icon = wfIconMap[j.wf] || '📄';
        const hasDocx = !!j.server_job_id;
        return `
          <div class="ch-content-item" onclick="${j.server_job_id ? `viewContentItem('${j.server_job_id}')` : ''}" style="cursor:pointer;">
            <div class="ch-content-item-header">
              <span class="ch-content-wf-icon">${icon}</span>
              <span class="ch-content-wf-type">${j.wf.split(' ').slice(0, 2).join(' ')}</span>
            </div>
            <div class="ch-content-title">${j.wf} — ${client.name}</div>
            <div class="ch-content-footer">
              <span class="ch-content-date">${j.started}</span>
              ${hasDocx
                ? `<a class="ch-content-dl" href="${API_BASE}/api/download/${j.server_job_id}" target="_blank" onclick="event.stopPropagation()">↓ .docx</a>`
                : `<span class="ch-content-dl" style="opacity:0.35;cursor:default;">↓ .docx</span>`}
            </div>
          </div>
        `;
      }).join('')
    : `<div class="ch-strip-empty">No content generated for this client yet — run a workflow to create your first piece.</div>`;

  el.innerHTML = `
    <!-- Client Header Bar -->
    <div class="ch-header">
      <button class="ch-back-btn" onclick="showView('clients')">← Clients</button>
      <div class="ch-identity">
        <div class="ch-client-name">${client.name}</div>
        <a class="ch-domain-link" href="https://${client.domain}" target="_blank" rel="noopener">${client.domain} ↗</a>
      </div>
      <div class="ch-badges">
        <span class="ch-plan-badge ${planClass}">${client.plan}</span>
        <div class="ch-score-badge ${scoreClass}">
          <span style="font-size:10px;opacity:0.6;letter-spacing:.08em;text-transform:uppercase;">SEO</span>
          <span class="ch-score-val">${client.score}</span>
          <span class="ch-score-trend ${trendUp ? 'tr-up' : trendDown ? 'tr-down' : ''}">${client.trend || '→0'}</span>
        </div>
      </div>
      <div class="ch-header-actions">
        <button class="ch-run-btn" onclick="selectWorkflowForClient(${client.id})">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          Run Workflow
        </button>
      </div>
    </div>

    <!-- Client Stats Bar -->
    <div class="ch-stats-bar">
      <div class="ch-stat">
        <div class="ch-stat-label">Workflows Run</div>
        <div class="ch-stat-value">${totalRun}</div>
        <div class="ch-stat-sub">total for this client</div>
      </div>
      <div class="ch-stat">
        <div class="ch-stat-label">Last Workflow</div>
        <div class="ch-stat-value" style="font-size:14px;padding-top:4px;">${lastJobDate}</div>
        <div class="ch-stat-sub">${completedJobs.length} completed</div>
      </div>
      <div class="ch-stat">
        <div class="ch-stat-label">SEO Score</div>
        <div class="ch-stat-value ${scoreClass}">${avgScore}</div>
        <div class="ch-stat-sub">avg rank #${client.avgRank}</div>
      </div>
      <div class="ch-stat">
        <div class="ch-stat-label">Active Since</div>
        <div class="ch-stat-value" style="font-size:16px;padding-top:4px;">2024</div>
        <div class="ch-stat-sub">${client.status === 'active' ? 'Active client' : 'Inactive'}</div>
      </div>
    </div>

    <!-- Tab Bar -->
    <div class="ch-tab-bar">
      <button class="ch-tab ${clientHubTab === 'activity' ? 'active' : ''}" onclick="switchClientHubTab('activity')">Activity</button>
      <button class="ch-tab ${clientHubTab === 'brain' ? 'active' : ''}" onclick="switchClientHubTab('brain')">Brain</button>
      <button class="ch-tab ${clientHubTab === 'sprint' ? 'active' : ''}" onclick="switchClientHubTab('sprint')">Sprint</button>
      <button class="ch-tab" onclick="showView('content')">Content</button>
    </div>

    <!-- Tab Content Container -->
    <div id="chTabContent"></div>
  `;

  // Render the active tab content
  renderClientHubTabContent(client, {
    runningJobs, completedJobs, attentionTasks,
    inProgressHTML, completedHTML, attentionHTML, stripHTML
  });
}

/* ══════════════════════════════════════════════════════════
   CLIENT HUB — TAB ROUTING + BRAIN VIEW (US-008, US-009)
   ══════════════════════════════════════════════════════════ */

function switchClientHubTab(tab) {
  clientHubTab = tab;
  // Update tab bar active state without full re-render
  document.querySelectorAll('.ch-tab-bar .ch-tab').forEach(t => t.classList.remove('active'));
  const tabs = document.querySelectorAll('.ch-tab-bar .ch-tab');
  const tabMap = { activity: 0, brain: 1, sprint: 2 };
  if (tabMap[tab] !== undefined && tabs[tabMap[tab]]) tabs[tabMap[tab]].classList.add('active');

  if (tab === 'brain') {
    loadAndRenderBrain();
  } else if (tab === 'sprint') {
    renderSprintView();
  } else {
    renderClientHub();
  }
}

function renderClientHubTabContent(client, data) {
  const container = document.getElementById('chTabContent');
  if (!container) return;

  if (clientHubTab === 'brain') {
    loadAndRenderBrain();
    return;
  }

  if (clientHubTab === 'sprint') {
    renderSprintView();
    return;
  }

  // Activity tab — original four-column layout + content strip
  // Note: all values are escaped via escapeHtml() before insertion
  const activityHtml = buildActivityTabHtml(data);
  container.innerHTML = activityHtml;
}

function buildActivityTabHtml(data) {
  return `
    <div class="ch-columns">
      <div class="ch-col ch-col-inprogress">
        <div class="ch-col-header">
          <div class="ch-col-title"><span class="ch-col-dot"></span> In Progress</div>
          <span class="ch-col-count">${data.runningJobs.length}</span>
        </div>
        <div class="ch-col-body">${data.inProgressHTML}</div>
      </div>
      <div class="ch-col ch-col-completed">
        <div class="ch-col-header">
          <div class="ch-col-title"><span class="ch-col-dot"></span> Recently Completed</div>
          <span class="ch-col-count">${data.completedJobs.length}</span>
        </div>
        <div class="ch-col-body">${data.completedHTML}</div>
      </div>
      <div class="ch-col ch-col-attention">
        <div class="ch-col-header">
          <div class="ch-col-title"><span class="ch-col-dot"></span> Needs Attention</div>
          <span class="ch-col-count">${data.attentionTasks.length}</span>
        </div>
        <div class="ch-col-body">${data.attentionHTML}</div>
      </div>
      <div class="ch-col ch-col-upcoming">
        <div class="ch-col-header">
          <div class="ch-col-title"><span class="ch-col-dot"></span> Upcoming Automations</div>
          <span class="ch-col-count">0</span>
        </div>
        <div class="ch-col-body">
          <div class="ch-upcoming-empty">
            <div class="ch-upcoming-icon">🗓</div>
            <div class="ch-upcoming-text">No automations scheduled yet.<br>Schedule recurring workflows to run automatically.</div>
            <button class="ch-schedule-btn" onclick="showToast('Coming soon — scheduling is on the roadmap')">+ Schedule Automation</button>
          </div>
        </div>
      </div>
    </div>
    <div class="ch-content-strip">
      <div class="ch-strip-header">
        <div class="ch-strip-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          Content Library
        </div>
        <button class="ch-view-all-link" onclick="showView('content')">View All &rarr;</button>
      </div>
      <div class="ch-strip-scroll">${data.stripHTML}</div>
    </div>
  `;
}

/* ── Brain Data Loading ── */

async function loadAndRenderBrain() {
  const container = document.getElementById('chTabContent');
  if (!container) return;

  container.innerHTML = '<div class="ch-brain-loading">Loading brain data...</div>';

  try {
    const res = await fetch(`${API_BASE}/api/clients/${activeClientId}/brain`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    clientBrainData = await res.json();
    renderBrainView();
  } catch (err) {
    // Brain endpoint may not exist yet — show empty state gracefully
    clientBrainData = { client_id: activeClientId, has_brain: false, sections: {}, entry_count: 0 };
    renderBrainView();
  }
}

/* ── Brain View Renderer ── */

const BRAIN_SECTION_META = {
  design_system:  { label: 'Brand Identity',         icon: '🎨' },
  asset_catalog:  { label: 'Asset Catalog',           icon: '📁' },
  brand_voice:    { label: 'Writing Voice',            icon: '✍️' },
  business_intel: { label: 'Business Intelligence',    icon: '📊' },
  past_content:   { label: 'Content History',          icon: '📄' },
  learnings:      { label: 'Learnings',                icon: '🧠' },
};

function renderBrainView() {
  const container = document.getElementById('chTabContent');
  if (!container) return;

  const data = clientBrainData || { has_brain: false, sections: {}, entry_count: 0 };
  const hasBrain = data.has_brain && data.entry_count > 0;
  const buildBtnLabel = hasBrain ? 'Rebuild Brain' : 'Build Brain';
  const buildBtnClass = hasBrain ? 'ch-build-brain-btn rebuild' : 'ch-build-brain-btn';

  const parts = [];

  // Toolbar
  parts.push('<div class="ch-brain-toolbar">');
  parts.push('  <div class="ch-brain-toolbar-info">');
  parts.push('    <span class="ch-brain-entry-count">' + (data.entry_count || 0) + ' entries</span>');
  parts.push('  </div>');
  parts.push('  <button class="' + buildBtnClass + '" onclick="startBuildBrain()">');
  parts.push('    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">');
  parts.push('      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>');
  parts.push('    </svg>');
  parts.push('    ' + buildBtnLabel);
  parts.push('  </button>');
  parts.push('</div>');

  // Progress panel (hidden)
  parts.push('<div id="chBrainProgress" class="ch-brain-progress" style="display:none;">');
  parts.push('  <div class="ch-brain-progress-header">');
  parts.push('    <span>Building client brain...</span>');
  parts.push('    <button class="ch-brain-progress-close" onclick="closeBrainProgress()">x</button>');
  parts.push('  </div>');
  parts.push('  <div id="chBrainProgressLog" class="ch-brain-progress-log"></div>');
  parts.push('</div>');

  if (!hasBrain) {
    // Full empty state
    parts.push('<div class="ch-brain-empty-hero">');
    parts.push('  <div class="ch-brain-empty-icon">🧠</div>');
    parts.push('  <div class="ch-brain-empty-title">No Brain Data Yet</div>');
    parts.push('  <div class="ch-brain-empty-desc">');
    parts.push('    The client brain captures brand identity, writing voice, business intelligence,');
    parts.push('    and content patterns. Click <strong>' + buildBtnLabel + '</strong> above to auto-populate');
    parts.push('    by researching this client\'s website and online presence.');
    parts.push('  </div>');
    parts.push('</div>');
  } else {
    // Render each section
    const sectionOrder = ['design_system', 'asset_catalog', 'brand_voice', 'business_intel', 'past_content', 'learnings'];
    for (const sectionKey of sectionOrder) {
      const meta = BRAIN_SECTION_META[sectionKey] || { label: formatBrainKey(sectionKey), icon: '📋' };
      const entries = data.sections[sectionKey] || {};
      const entryKeys = Object.keys(entries);

      parts.push('<div class="ch-brain-section" data-section="' + sectionKey + '">');
      parts.push('  <div class="ch-brain-section-header" onclick="toggleBrainSection(this)">');
      parts.push('    <span class="ch-brain-section-icon">' + meta.icon + '</span>');
      parts.push('    <span class="ch-brain-section-label">' + meta.label + '</span>');
      parts.push('    <span class="ch-brain-section-count">' + entryKeys.length + '</span>');
      parts.push('    <span class="ch-brain-section-chevron">&#9662;</span>');
      parts.push('  </div>');
      parts.push('  <div class="ch-brain-section-body">');

      if (entryKeys.length === 0) {
        parts.push('    <div class="ch-brain-empty-section">Not yet populated. Build the client brain to auto-populate.</div>');
      } else {
        for (const key of entryKeys) {
          const val = entries[key];
          const displayVal = formatBrainValue(val);
          const rawVal = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
          const isTruncated = displayVal.length > 200;
          const truncated = isTruncated ? displayVal.slice(0, 200) + '...' : displayVal;

          parts.push('    <div class="ch-brain-entry" data-section="' + sectionKey + '" data-key="' + escapeAttr(key) + '">');
          parts.push('      <div class="ch-brain-entry-display">');
          parts.push('        <div class="ch-brain-entry-key">' + formatBrainKey(key) + '</div>');
          parts.push('        <div class="ch-brain-entry-val">');
          parts.push('          <span class="ch-brain-val-text">' + escapeHtml(truncated) + '</span>');
          if (isTruncated) {
            parts.push('          <button class="ch-brain-show-more" onclick="toggleBrainEntryFull(this)">Show more</button>');
          }
          parts.push('        </div>');
          parts.push('        <button class="ch-brain-edit-btn" onclick="startEditBrainEntry(this)" title="Edit entry">');
          parts.push('          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>');
          parts.push('        </button>');
          parts.push('      </div>');
          parts.push('      <div class="ch-brain-entry-edit" style="display:none;">');
          parts.push('        <textarea class="ch-brain-edit-textarea">' + escapeHtml(rawVal) + '</textarea>');
          parts.push('        <div class="ch-brain-edit-actions">');
          parts.push('          <button class="ch-brain-save-btn" onclick="saveBrainEntry(this, \'' + sectionKey + '\', \'' + escapeAttr(key) + '\')">Save</button>');
          parts.push('          <button class="ch-brain-cancel-btn" onclick="cancelEditBrainEntry(this)">Cancel</button>');
          parts.push('        </div>');
          parts.push('      </div>');
          parts.push('    </div>');
        }
      }

      // Add Entry row
      parts.push('    <div class="ch-brain-add-row" data-section="' + sectionKey + '">');
      parts.push('      <button class="ch-brain-add-btn" onclick="showAddBrainEntry(this, \'' + sectionKey + '\')">+ Add Entry</button>');
      parts.push('      <div class="ch-brain-add-form" style="display:none;">');
      parts.push('        <input type="text" class="ch-brain-add-key" placeholder="Key (e.g. color_palette)">');
      parts.push('        <textarea class="ch-brain-add-value" placeholder="Value"></textarea>');
      parts.push('        <div class="ch-brain-edit-actions">');
      parts.push('          <button class="ch-brain-save-btn" onclick="saveNewBrainEntry(this, \'' + sectionKey + '\')">Save</button>');
      parts.push('          <button class="ch-brain-cancel-btn" onclick="cancelAddBrainEntry(this)">Cancel</button>');
      parts.push('        </div>');
      parts.push('      </div>');
      parts.push('    </div>');

      parts.push('  </div>');
      parts.push('</div>');
    }
  }

  container.innerHTML = parts.join('\n');

  // Store full display values on entry elements for show more/less toggle
  if (hasBrain) {
    const sectionOrder = ['design_system', 'asset_catalog', 'brand_voice', 'business_intel', 'past_content', 'learnings'];
    for (const sectionKey of sectionOrder) {
      const entries = data.sections[sectionKey] || {};
      for (const key of Object.keys(entries)) {
        const fullVal = formatBrainValue(entries[key]);
        if (fullVal.length > 200) {
          const entryEl = container.querySelector('.ch-brain-entry[data-section="' + sectionKey + '"][data-key="' + escapeAttr(key) + '"]');
          if (entryEl) entryEl.dataset.fullVal = fullVal;
        }
      }
    }
  }
}

/* ── Brain Helpers ── */

function formatBrainKey(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

function formatBrainValue(val) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) {
    return val.map(function(item) {
      if (typeof item === 'object') return JSON.stringify(item);
      return String(item);
    }).join(', ');
  }
  if (typeof val === 'object') {
    return Object.entries(val).map(function(pair) {
      return formatBrainKey(pair[0]) + ': ' + (typeof pair[1] === 'object' ? JSON.stringify(pair[1]) : pair[1]);
    }).join('\n');
  }
  return String(val);
}

function escapeHtml(str) {
  var d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function escapeAttr(str) {
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ── Brain Section Toggle ── */

function toggleBrainSection(headerEl) {
  var section = headerEl.closest('.ch-brain-section');
  if (section) section.classList.toggle('collapsed');
}

/* ── Show More / Show Less ── */

function toggleBrainEntryFull(btn) {
  var entry = btn.closest('.ch-brain-entry');
  var textEl = entry.querySelector('.ch-brain-val-text');
  var fullVal = entry.dataset.fullVal || '';
  if (btn.textContent === 'Show more') {
    textEl.textContent = fullVal;
    btn.textContent = 'Show less';
  } else {
    textEl.textContent = fullVal.slice(0, 200) + '...';
    btn.textContent = 'Show more';
  }
}

/* ── Inline Editing ── */

function startEditBrainEntry(btn) {
  var entry = btn.closest('.ch-brain-entry');
  entry.querySelector('.ch-brain-entry-display').style.display = 'none';
  entry.querySelector('.ch-brain-entry-edit').style.display = 'block';
}

function cancelEditBrainEntry(btn) {
  var entry = btn.closest('.ch-brain-entry');
  entry.querySelector('.ch-brain-entry-display').style.display = '';
  entry.querySelector('.ch-brain-entry-edit').style.display = 'none';
}

async function saveBrainEntry(btn, memoryType, key) {
  var entry = btn.closest('.ch-brain-entry');
  var textarea = entry.querySelector('.ch-brain-edit-textarea');
  var value = textarea.value;

  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    var res = await fetch(API_BASE + '/api/memory/' + activeClientId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory_type: memoryType, key: key, value: value }),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    showToast('Entry saved');
    loadAndRenderBrain();
  } catch (err) {
    showToast('Failed to save: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Save';
  }
}

/* ── Add New Entry ── */

function showAddBrainEntry(btn, sectionKey) {
  var row = btn.closest('.ch-brain-add-row');
  btn.style.display = 'none';
  row.querySelector('.ch-brain-add-form').style.display = 'block';
}

function cancelAddBrainEntry(btn) {
  var row = btn.closest('.ch-brain-add-row');
  row.querySelector('.ch-brain-add-btn').style.display = '';
  row.querySelector('.ch-brain-add-form').style.display = 'none';
  row.querySelector('.ch-brain-add-key').value = '';
  row.querySelector('.ch-brain-add-value').value = '';
}

async function saveNewBrainEntry(btn, sectionKey) {
  var row = btn.closest('.ch-brain-add-row');
  var key = row.querySelector('.ch-brain-add-key').value.trim();
  var value = row.querySelector('.ch-brain-add-value').value;

  if (!key) {
    showToast('Key is required');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    var res = await fetch(API_BASE + '/api/memory/' + activeClientId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory_type: sectionKey, key: key, value: value }),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    showToast('Entry added');
    loadAndRenderBrain();
  } catch (err) {
    showToast('Failed to save: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Save';
  }
}

/* ── Build Brain (SSE Stream) ── */

async function startBuildBrain() {
  var data = clientBrainData || {};
  var hasBrain = data.has_brain && data.entry_count > 0;

  if (hasBrain) {
    if (!confirm('This will rebuild the client brain from scratch. Existing entries will be replaced. Continue?')) return;
  }

  var progressPanel = document.getElementById('chBrainProgress');
  var progressLog = document.getElementById('chBrainProgressLog');
  if (!progressPanel || !progressLog) return;

  progressPanel.style.display = 'block';
  progressLog.textContent = '';

  var buildBtn = document.querySelector('.ch-build-brain-btn');
  if (buildBtn) {
    buildBtn.disabled = true;
    buildBtn.textContent = 'Building...';
  }

  try {
    var res = await fetch(API_BASE + '/api/clients/' + activeClientId + '/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) throw new Error('HTTP ' + res.status);

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;

      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (!line.startsWith('data: ')) continue;
        var payload = line.slice(6).trim();
        if (!payload) continue;

        try {
          var evt = JSON.parse(payload);
          if (evt.type === 'token' && evt.text) {
            var span = document.createElement('span');
            span.textContent = evt.text;
            progressLog.appendChild(span);
            progressLog.scrollTop = progressLog.scrollHeight;
          } else if (evt.type === 'done') {
            var doneMsg = document.createElement('div');
            doneMsg.className = 'ch-brain-progress-done';
            doneMsg.textContent = 'Brain build complete.';
            progressLog.appendChild(doneMsg);
            progressLog.scrollTop = progressLog.scrollHeight;
            loadAndRenderBrain();
          } else if (evt.type === 'error') {
            var errDiv = document.createElement('div');
            errDiv.className = 'ch-brain-progress-error';
            errDiv.textContent = 'Error: ' + (evt.message || 'Unknown error');
            progressLog.appendChild(errDiv);
          }
        } catch (parseErr) {
          var txt = document.createElement('span');
          txt.textContent = payload;
          progressLog.appendChild(txt);
        }
      }
    }
  } catch (err) {
    var errMsg = document.createElement('div');
    errMsg.className = 'ch-brain-progress-error';
    errMsg.textContent = 'Build failed: ' + err.message;
    if (progressLog) progressLog.appendChild(errMsg);
  } finally {
    if (buildBtn) {
      buildBtn.disabled = false;
      buildBtn.textContent = hasBrain ? 'Rebuild Brain' : 'Build Brain';
    }
  }
}

function closeBrainProgress() {
  var panel = document.getElementById('chBrainProgress');
  if (panel) panel.style.display = 'none';
}

/* ══════════════════════════════════════════════════════════
   CLIENT HUB — MONTHLY SPRINT VIEW (Phase 3)
   ══════════════════════════════════════════════════════════ */

const SPRINT_PAGE_TYPES = [
  { value: 'service_page', label: 'Service Page' },
  { value: 'location_page', label: 'Location Page' },
  { value: 'blog_post', label: 'Blog Post' },
];

function sprintTypeLabel(val) {
  const t = SPRINT_PAGE_TYPES.find(p => p.value === val);
  return t ? t.label : val;
}

function renderSprintView() {
  const container = document.getElementById('chTabContent');
  if (!container) return;

  const parts = [];

  // Toolbar: Add Item + Run Sprint
  parts.push('<div class="ch-sprint-toolbar">');
  parts.push('  <button class="ch-sprint-add-btn" onclick="showSprintAddForm()" ' + (sprintRunning ? 'disabled' : '') + '>+ Add Item</button>');
  parts.push('  <button class="ch-sprint-run-btn" onclick="runSprint()" ' + (sprintRunning || sprintItems.length === 0 ? 'disabled' : '') + '>');
  parts.push('    Run Sprint &#9654;');
  parts.push('  </button>');
  parts.push('</div>');

  // Inline add form (hidden by default)
  parts.push('<div id="sprintAddForm" class="ch-sprint-add-form" style="display:none;">');
  parts.push('  <div class="ch-sprint-add-row">');
  parts.push('    <select id="sprintAddType" class="ch-sprint-input ch-sprint-select">');
  for (const pt of SPRINT_PAGE_TYPES) {
    parts.push('      <option value="' + pt.value + '">' + escapeHtml(pt.label) + '</option>');
  }
  parts.push('    </select>');
  parts.push('    <input id="sprintAddTitle" class="ch-sprint-input ch-sprint-text" type="text" placeholder="Title (e.g. Panel Upgrade)" />');
  parts.push('    <input id="sprintAddKeyword" class="ch-sprint-input ch-sprint-text" type="text" placeholder="Keyword (e.g. panel upgrade chandler az)" />');
  parts.push('    <button class="ch-sprint-confirm-btn" onclick="addSprintItem()">Add</button>');
  parts.push('    <button class="ch-sprint-cancel-btn" onclick="hideSprintAddForm()">Cancel</button>');
  parts.push('  </div>');
  parts.push('</div>');

  // Items table
  if (sprintItems.length > 0) {
    parts.push('<div class="ch-sprint-table-wrap">');
    parts.push('<table class="ch-sprint-table">');
    parts.push('  <thead><tr>');
    parts.push('    <th class="ch-sprint-th-num">#</th>');
    parts.push('    <th>Type</th>');
    parts.push('    <th>Title</th>');
    parts.push('    <th>Keyword</th>');
    parts.push('    <th class="ch-sprint-th-action"></th>');
    parts.push('  </tr></thead>');
    parts.push('  <tbody>');
    for (let i = 0; i < sprintItems.length; i++) {
      const item = sprintItems[i];
      parts.push('  <tr>');
      parts.push('    <td class="ch-sprint-num">' + (i + 1) + '</td>');
      parts.push('    <td>' + escapeHtml(sprintTypeLabel(item.page_type)) + '</td>');
      parts.push('    <td>' + escapeHtml(item.title) + '</td>');
      parts.push('    <td class="ch-sprint-kw">' + escapeHtml(item.keyword) + '</td>');
      parts.push('    <td class="ch-sprint-remove">');
      if (!sprintRunning) {
        parts.push('      <button class="ch-sprint-remove-btn" onclick="removeSprintItem(' + i + ')" title="Remove">&times;</button>');
      }
      parts.push('    </td>');
      parts.push('  </tr>');
    }
    parts.push('  </tbody>');
    parts.push('</table>');
    parts.push('</div>');
  } else {
    parts.push('<div class="ch-sprint-empty">');
    parts.push('  <div class="ch-sprint-empty-icon">&#128640;</div>');
    parts.push('  <div class="ch-sprint-empty-title">No sprint items yet</div>');
    parts.push('  <div class="ch-sprint-empty-desc">Click <strong>+ Add Item</strong> to add service pages, location pages, and blog posts for this month\'s sprint.</div>');
    parts.push('</div>');
  }

  // Approval mode selector
  if (sprintItems.length > 0) {
    parts.push('<div class="ch-sprint-options">');
    parts.push('  <label class="ch-sprint-label">Approval Mode:</label>');
    parts.push('  <select id="sprintApprovalMode" class="ch-sprint-input ch-sprint-select">');
    parts.push('    <option value="autopilot">Autopilot</option>');
    parts.push('    <option value="review_each">Review Each</option>');
    parts.push('    <option value="review_final">Review Final</option>');
    parts.push('  </select>');
    parts.push('</div>');
  }

  // Progress panel (always in DOM, toggled via display)
  parts.push('<div id="sprintProgress" class="ch-sprint-progress" style="display:none;"></div>');

  // Sprint history
  if (sprintHistory.length > 0) {
    parts.push('<div class="ch-sprint-history">');
    parts.push('  <div class="ch-sprint-history-title">Recent Sprints</div>');
    for (let h = sprintHistory.length - 1; h >= 0; h--) {
      const run = sprintHistory[h];
      parts.push('  <div class="ch-sprint-history-item">');
      parts.push('    <span class="ch-sprint-history-date">' + escapeHtml(run.date) + '</span>');
      parts.push('    <span class="ch-sprint-history-count">' + run.completed + '/' + run.total + ' items</span>');
      if (run.failed > 0) {
        parts.push('    <span class="ch-sprint-history-fail">' + run.failed + ' failed</span>');
      }
      parts.push('  </div>');
    }
    parts.push('</div>');
  }

  // Use safe DOM insertion: all dynamic values passed through escapeHtml above
  container.innerHTML = parts.join('\n');
}

function showSprintAddForm() {
  var form = document.getElementById('sprintAddForm');
  if (form) form.style.display = 'block';
}

function hideSprintAddForm() {
  var form = document.getElementById('sprintAddForm');
  if (form) form.style.display = 'none';
}

function addSprintItem() {
  var typeEl = document.getElementById('sprintAddType');
  var titleEl = document.getElementById('sprintAddTitle');
  var kwEl = document.getElementById('sprintAddKeyword');
  if (!typeEl || !titleEl || !kwEl) return;

  var title = titleEl.value.trim();
  var keyword = kwEl.value.trim();

  if (!title) {
    showToast('Title is required');
    return;
  }
  if (!keyword) {
    showToast('Keyword is required');
    return;
  }

  sprintItems.push({
    page_type: typeEl.value,
    title: title,
    keyword: keyword,
  });

  // Reset form inputs
  titleEl.value = '';
  kwEl.value = '';
  hideSprintAddForm();
  renderSprintView();
}

function removeSprintItem(index) {
  if (index >= 0 && index < sprintItems.length) {
    sprintItems.splice(index, 1);
    renderSprintView();
  }
}

async function runSprint() {
  if (sprintItems.length === 0) {
    showToast('Add at least one item before running');
    return;
  }
  if (sprintRunning) return;

  sprintRunning = true;
  renderSprintView(); // Re-render to disable buttons

  var progressEl = document.getElementById('sprintProgress');
  if (!progressEl) return;
  progressEl.style.display = 'block';

  // Build initial progress UI
  var totalItems = sprintItems.length;
  var itemStates = sprintItems.map(function(item, idx) {
    return { index: idx, title: item.title, page_type: item.page_type, status: 'queued', stage: '', stageIndex: 0, qaScore: null };
  });

  var stages = ['research', 'strategy', 'copywrite', 'design', 'qa'];

  function renderProgress(currentItem, streamContent) {
    var parts = [];
    parts.push('<div class="ch-sprint-progress-header">');
    parts.push('  <span>Sprint Progress</span>');
    parts.push('</div>');

    // Current item info
    if (currentItem !== null && currentItem < totalItems) {
      var cur = itemStates[currentItem];
      parts.push('<div class="ch-sprint-progress-current">');
      parts.push('  <div class="ch-sprint-progress-item-label">Item ' + (currentItem + 1) + '/' + totalItems + ': ' + escapeHtml(cur.title) + ' (' + escapeHtml(sprintTypeLabel(cur.page_type)) + ')</div>');

      // Stage progress bar
      var completedStages = cur.stageIndex;
      parts.push('  <div class="ch-sprint-progress-stages">');
      parts.push('    <div class="ch-sprint-stage-label">Stage: ');
      for (var s = 0; s < stages.length; s++) {
        if (s > 0) parts.push(' &rarr; ');
        var cls = '';
        if (s < completedStages) cls = 'done';
        else if (s === completedStages && cur.status === 'running') cls = 'active';
        parts.push('<span class="ch-sprint-stage ' + cls + '">' + stages[s] + '</span>');
      }
      parts.push('    </div>');

      // Progress bar
      var pct = Math.round((completedStages / stages.length) * 100);
      parts.push('    <div class="ch-sprint-bar-track">');
      parts.push('      <div class="ch-sprint-bar-fill" style="width:' + pct + '%"></div>');
      parts.push('    </div>');
      parts.push('    <div class="ch-sprint-bar-text">' + completedStages + '/' + stages.length + ' stages</div>');
      parts.push('  </div>');
      parts.push('</div>');
    }

    // SSE stream output
    if (streamContent) {
      parts.push('<div class="ch-sprint-stream">' + escapeHtml(streamContent) + '</div>');
    }

    // Results list
    parts.push('<div class="ch-sprint-results">');
    parts.push('  <div class="ch-sprint-results-title">Results:</div>');
    for (var r = 0; r < itemStates.length; r++) {
      var st = itemStates[r];
      var icon = '';
      var detail = '';
      if (st.status === 'complete') {
        icon = '<span class="ch-sprint-icon-done">&#10003;</span>';
        detail = ' -- QA Score: ' + (st.qaScore !== null ? st.qaScore + '/100' : '--');
      } else if (st.status === 'running') {
        icon = '<span class="ch-sprint-icon-running">&#9203;</span>';
        detail = ' -- Running...';
      } else if (st.status === 'failed') {
        icon = '<span class="ch-sprint-icon-fail">&#10007;</span>';
        detail = ' -- Failed';
      } else {
        icon = '<span class="ch-sprint-icon-queued">&#9675;</span>';
        detail = ' -- Queued';
      }
      parts.push('  <div class="ch-sprint-result-row">' + icon + ' ' + escapeHtml(st.title) + detail + '</div>');
    }
    parts.push('</div>');

    // All values escaped above; safe for innerHTML
    progressEl.innerHTML = parts.join('\n');
  }

  renderProgress(null, '');

  // Collect approval mode
  var approvalEl = document.getElementById('sprintApprovalMode');
  var approvalMode = approvalEl ? approvalEl.value : 'autopilot';

  // Build payload
  var payload = {
    items: sprintItems.map(function(item) {
      return { page_type: item.page_type, keyword: item.keyword, title: item.title };
    }),
    approval_mode: approvalMode,
  };

  var streamText = '';
  var currentItemIdx = null;

  try {
    var res = await fetch(API_BASE + '/api/clients/' + activeClientId + '/sprint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error('HTTP ' + res.status);

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;

      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (var li = 0; li < lines.length; li++) {
        var line = lines[li];
        if (!line.startsWith('data: ')) continue;
        var raw = line.slice(6).trim();
        if (!raw) continue;

        try {
          var evt = JSON.parse(raw);

          if (evt.type === 'sprint_start') {
            // Sprint started
            renderProgress(null, '');
          } else if (evt.type === 'item_start') {
            currentItemIdx = evt.index;
            streamText = '';
            if (itemStates[evt.index]) {
              itemStates[evt.index].status = 'running';
              itemStates[evt.index].stage = '';
              itemStates[evt.index].stageIndex = 0;
            }
            renderProgress(currentItemIdx, streamText);
          } else if (evt.type === 'stage_start') {
            var si = stages.indexOf(evt.stage);
            if (evt.item_index !== undefined && itemStates[evt.item_index]) {
              itemStates[evt.item_index].stage = evt.stage;
              itemStates[evt.item_index].stageIndex = si >= 0 ? si : 0;
            }
            renderProgress(currentItemIdx, streamText);
          } else if (evt.type === 'token') {
            streamText += evt.text || '';
            // Only keep last 500 chars for the stream window
            if (streamText.length > 500) {
              streamText = streamText.slice(streamText.length - 500);
            }
            if (evt.item_index !== undefined) currentItemIdx = evt.item_index;
            renderProgress(currentItemIdx, streamText);
          } else if (evt.type === 'item_complete') {
            if (itemStates[evt.index]) {
              itemStates[evt.index].status = 'complete';
              itemStates[evt.index].qaScore = evt.qa_score || null;
              itemStates[evt.index].stageIndex = stages.length;
            }
            streamText = '';
            renderProgress(currentItemIdx, '');
          } else if (evt.type === 'item_error') {
            if (itemStates[evt.index]) {
              itemStates[evt.index].status = 'failed';
            }
            renderProgress(currentItemIdx, '');
          } else if (evt.type === 'sprint_complete') {
            // Store in history
            sprintHistory.push({
              date: new Date().toLocaleDateString(),
              total: evt.completed + (evt.failed || 0),
              completed: evt.completed,
              failed: evt.failed || 0,
            });
            renderProgress(null, '');
          } else if (evt.type === 'error') {
            showToast('Sprint error: ' + (evt.message || 'Unknown'));
          }
        } catch (parseErr) {
          // Non-JSON SSE line — ignore
        }
      }
    }
  } catch (err) {
    showToast('Sprint failed: ' + err.message);
    // Render final state for completed items
    renderProgress(currentItemIdx, '');
  } finally {
    sprintRunning = false;
    renderSprintView();
  }
}

/* ══════════════════════════════════════════════════════════ */

function selectWorkflowForClient(clientId) {
  // Pre-select the client in the workflow modal and open the workflows view
  activeClientId = clientId;
  showView('workflows');
  // After a short tick so the modal client select is populated
  setTimeout(() => {
    const sel = document.getElementById('wfClientSelect');
    if (sel) {
      sel.value = clientId;
      checkRunReady();
    }
  }, 80);
}

async function toggleClientStatus(id) {
  const client = CLIENTS.find(c => c.id === id);
  if (!client) return;
  const newStatus = client.status === 'active' ? 'inactive' : 'active';
  try {
    await fetch(`${API_BASE}/api/clients/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
  } catch (e) { /* ignore network errors */ }
  await loadClients();
}

/* ── Add / Edit Client modals ── */

function showAddClientModal() {
  ['acName','acDomain','acService','acLocation','acRevenue','acJobValue','acNotes','acStrategyCtx'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const planEl = document.getElementById('acPlan');
  if (planEl) planEl.value = 'Starter';
  document.getElementById('addClientModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function hideAddClientModal(e) {
  if (e && e.target !== document.getElementById('addClientModal')) return;
  document.getElementById('addClientModal').classList.remove('open');
  document.body.style.overflow = '';
}

async function submitAddClient() {
  const name = document.getElementById('acName')?.value.trim();
  const domain = document.getElementById('acDomain')?.value.trim();
  if (!name || !domain) {
    showToast('Client Name and Domain are required');
    return;
  }
  const payload = {
    name,
    domain,
    service:          document.getElementById('acService')?.value.trim() || '',
    location:         document.getElementById('acLocation')?.value.trim() || '',
    plan:             document.getElementById('acPlan')?.value || 'Starter',
    monthly_revenue:  document.getElementById('acRevenue')?.value.trim() || '',
    avg_job_value:    document.getElementById('acJobValue')?.value.trim() || '',
    notes:            document.getElementById('acNotes')?.value.trim() || '',
    strategy_context: document.getElementById('acStrategyCtx')?.value.trim() || '',
  };
  try {
    const res = await fetch(`${API_BASE}/api/clients`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to create client');
    document.getElementById('addClientModal').classList.remove('open');
    document.body.style.overflow = '';
    await loadClients();
    showToast(`✓ ${name} added`);
  } catch (e) {
    showToast('Error adding client — please try again');
  }
}

function showEditClientModal(clientId) {
  const client = CLIENTS.find(c => c.id === clientId);
  if (!client) return;

  document.getElementById('ecId').value = clientId;
  document.getElementById('ecName').value = client.name || '';
  document.getElementById('ecDomain').value = client.domain || '';
  document.getElementById('ecService').value = client.service || '';
  document.getElementById('ecLocation').value = client.location || '';
  document.getElementById('ecPlan').value = client.plan || 'Starter';
  document.getElementById('ecRevenue').value = client.monthly_revenue || '';
  document.getElementById('ecJobValue').value = client.avg_job_value || '';
  document.getElementById('ecNotes').value = client.notes || '';
  document.getElementById('ecStrategyCtx').value = client.strategy_context || '';
  document.getElementById('ecGscProperty').value = client.gsc_property || '';
  document.getElementById('ecGa4PropertyId').value = client.ga4_property_id || '';
  document.getElementById('ecGoogleAdsCustomerId').value = client.google_ads_customer_id || '';
  document.getElementById('ecMetaAdAccountId').value = client.meta_ad_account_id || '';
  document.getElementById('ecSheetsConfig').value = client.sheets_config || '';

  const descEl = document.getElementById('editClientModalDesc');
  if (descEl) descEl.textContent = `Editing: ${client.name}`;

  document.getElementById('editClientModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function hideEditClientModal(e) {
  if (e && e.target !== document.getElementById('editClientModal')) return;
  document.getElementById('editClientModal').classList.remove('open');
  document.body.style.overflow = '';
}

async function submitEditClient() {
  const clientId = parseInt(document.getElementById('ecId')?.value);
  const name = document.getElementById('ecName')?.value.trim();
  const domain = document.getElementById('ecDomain')?.value.trim();
  if (!clientId || !name || !domain) {
    showToast('Client Name and Domain are required');
    return;
  }
  const payload = {
    name,
    domain,
    service:          document.getElementById('ecService')?.value.trim() || '',
    location:         document.getElementById('ecLocation')?.value.trim() || '',
    plan:             document.getElementById('ecPlan')?.value || 'Starter',
    monthly_revenue:  document.getElementById('ecRevenue')?.value.trim() || '',
    avg_job_value:    document.getElementById('ecJobValue')?.value.trim() || '',
    notes:            document.getElementById('ecNotes')?.value.trim() || '',
    strategy_context: document.getElementById('ecStrategyCtx')?.value.trim() || '',
    gsc_property:     document.getElementById('ecGscProperty')?.value.trim() || '',
    ga4_property_id:  document.getElementById('ecGa4PropertyId')?.value.trim() || '',
    google_ads_customer_id: document.getElementById('ecGoogleAdsCustomerId')?.value.trim().replace(/-/g, '') || '',
    meta_ad_account_id:     document.getElementById('ecMetaAdAccountId')?.value.trim().replace(/^act_/, '') || '',
    sheets_config:          document.getElementById('ecSheetsConfig')?.value.trim() || '',
  };
  try {
    const res = await fetch(`${API_BASE}/api/clients/${clientId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to update client');
    document.getElementById('editClientModal').classList.remove('open');
    document.body.style.overflow = '';
    await loadClients();
    showToast(`✓ ${name} updated`);
  } catch (e) {
    showToast('Error saving changes — please try again');
  }
}

async function deleteClientFromModal() {
  const clientId = parseInt(document.getElementById('ecId')?.value);
  const name = document.getElementById('ecName')?.value.trim();
  if (!clientId) return;
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    const res = await fetch(`${API_BASE}/api/clients/${clientId}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 204) throw new Error('Failed to delete client');
    document.getElementById('editClientModal').classList.remove('open');
    document.body.style.overflow = '';
    await loadClients();
    showToast(`${name} deleted`);
  } catch (e) {
    showToast('Error deleting client — please try again');
  }
}

/* ── JOBS ── */
let jobFilter = 'all';

function renderJobs(filter) {
  jobFilter = filter;
  document.querySelectorAll('#jobFilterTabs .filter-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });

  const el = document.getElementById('jobsTbody');
  if (!el) return;

  const filtered = filter === 'all' ? JOBS : JOBS.filter(j => j.status === filter);

  if (!filtered.length) {
    el.innerHTML = `<tr><td colspan="7" class="empty-state" style="text-align:center;padding:32px;">No ${filter === 'all' ? '' : filter + ' '}tasks yet — run a workflow to create one</td></tr>`;
    return;
  }

  el.innerHTML = filtered.map(j => {
    const pillClass = { running: 'pill-run', completed: 'pill-ok', failed: 'pill-fail' }[j.status] || 'pill-warn';
    const pct = Math.round(jobProgresses[j.id] || j.pct);
    const progressHTML = j.status === 'running'
      ? `<div class="prog-bar" id="pb-${j.id}"><div class="prog-fill" style="width:${pct}%" id="pf-${j.id}"></div></div>`
      : '';
    return `
      <tr onclick="openJobModal('${j.id}')" style="cursor:pointer;">
        <td style="font-family:var(--mono);font-size:10px;color:var(--elec-blue);">${j.id}</td>
        <td style="color:var(--text);font-weight:600;">${j.wf}</td>
        <td><span class="client-name-link" onclick="event.stopPropagation();showClientHubByName('${j.client.replace(/'/g, "\\'")}')">${j.client}</span></td>
        <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">${j.started}</td>
        <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">${j.duration}</td>
        <td><span class="pill ${pillClass}">${j.status}</span></td>
        <td>${progressHTML}<span style="font-size:10px;color:var(--text3);font-family:var(--mono);">${j.output}</span></td>
      </tr>
    `;
  }).join('');
}

/* ── REPORTS ── */
function renderReports() {
  const el = document.getElementById('reportsGrid');
  if (!el) return;
  if (!REPORTS.length) {
    el.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No reports yet — completed workflows will appear here</div>';
    return;
  }
  el.innerHTML = REPORTS.map(r => `
    <div class="report-card">
      <div class="rc-type">${r.type}</div>
      <div class="rc-title">${r.title}</div>
      <div class="rc-client">${r.client} · ${r.date}</div>
      <div class="rc-actions">
        <button class="rc-btn rc-btn-primary">Preview</button>
        <button class="rc-btn rc-btn-ghost">Download</button>
      </div>
    </div>
  `).join('');
}

/* ── CONTENT LIBRARY ── */

const WF_ICONS = {
  'website-seo-audit':    '🔍',
  'prospect-audit':       '🎯',
  'home-service-content': '🏠',
  'keyword-gap':          '📊',
  'seo-blog-generator':   '✍️',
  'seo-blog-post':        '✍️',
  'service-page':         '⚡',
  'location-page':        '📍',
  'programmatic-content': '🚀',
  'seo-strategy-sheet':   '📋',
};

const WF_TYPE_LABELS = {
  'website-seo-audit':    'SEO Audit',
  'prospect-audit':       'Prospect Analysis',
  'home-service-content': 'SEO Content',
  'keyword-gap':          'Keyword Gap',
  'seo-blog-generator':   'Blog Post',
  'seo-blog-post':        'Blog Post',
  'service-page':         'Service Page',
  'location-page':        'Location Page',
  'programmatic-content': 'Programmatic Content',
  'seo-strategy-sheet':   'Strategy',
};

function wfIcon(workflowId) {
  return WF_ICONS[workflowId] || '📄';
}

function wfTypeLabel(workflowId) {
  return WF_TYPE_LABELS[workflowId] || 'Document';
}

function getClientInitials(name) {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

function getClientColor(name) {
  // Deterministic color from client name — cycles through brand palette
  const palette = ['#0051FF', '#7C3AED', '#0D9488', '#EA580C', '#D97706', '#28A745'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xFFFFFF;
  return palette[Math.abs(hash) % palette.length];
}

function addToContentLibrary(jobId, clientName, clientId, workflowId, workflowTitle) {
  // Prevent duplicates
  if (CONTENT_ITEMS.find(c => c.job_id === jobId)) return;

  const now = new Date();
  CONTENT_ITEMS.unshift({
    id: jobId,
    job_id: jobId,
    client_name: clientName || 'Unknown Client',
    client_id: clientId || 0,
    workflow_id: workflowId || '',
    workflow_title: workflowTitle || 'Document',
    created_at: now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
    has_docx: true,
    preview: '',
  });

  // Refresh client filter dropdown if content view is active
  _populateContentClientFilter();
  renderContentLibrary();
}

function _populateContentClientFilter() {
  const sel = document.getElementById('contentClientFilter');
  if (!sel) return;
  const current = sel.value;
  const clientNames = [...new Set(CONTENT_ITEMS.map(c => c.client_name))].sort();
  sel.innerHTML = '<option value="">All Clients</option>' +
    clientNames.map(n => `<option value="${n}">${n}</option>`).join('');
  if (current) sel.value = current;
}

function renderContentLibrary(items) {
  const el = document.getElementById('contentLibraryGrid');
  if (!el) return;

  const list = items !== undefined ? items : CONTENT_ITEMS;

  if (!list.length) {
    el.innerHTML = `
      <div class="cl-empty-state">
        <div class="cl-empty-icon">📂</div>
        <div class="cl-empty-title">No content yet</div>
        <div class="cl-empty-sub">Run a workflow to generate your first document — it will appear here automatically.</div>
        <button class="btn-primary-top" onclick="showView('workflows')" style="margin-top:16px;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          Run a Workflow
        </button>
      </div>`;
    return;
  }

  // Group by client_name
  const byClient = {};
  list.forEach(item => {
    const key = item.client_name || 'Unknown Client';
    if (!byClient[key]) byClient[key] = [];
    byClient[key].push(item);
  });

  el.innerHTML = Object.entries(byClient).map(([clientName, clientItems]) => {
    const initials = getClientInitials(clientName);
    const color = getClientColor(clientName);
    const count = clientItems.length;
    const cards = clientItems.map(item => _contentCard(item)).join('');

    return `
      <div class="cl-client-section">
        <div class="cl-client-header">
          <div class="cl-client-avatar" style="background:${color}20;border-color:${color}40;color:${color};">${initials}</div>
          <span class="cl-client-name">${clientName}</span>
          <span class="cl-client-count">${count} document${count !== 1 ? 's' : ''}</span>
        </div>
        <div class="cl-cards-row">
          ${cards}
        </div>
      </div>`;
  }).join('');
}

async function approveContentItem(jobId) {
  await fetch(`${API_BASE}/api/jobs/${jobId}/approve`, { method: 'POST' });
  await syncContentLibrary();
}

function _contentCard(item) {
  const icon = wfIcon(item.workflow_id);
  const typeLabel = wfTypeLabel(item.workflow_id);
  const downloadBtn = item.has_docx
    ? `<button class="cl-card-btn cl-card-btn-dl" onclick="event.stopPropagation(); downloadContentItem('${item.job_id}')" title="Download .docx">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
         .docx
       </button>`
    : '';

  const approvalEl = item.approved
    ? `<span class="cl-approved-badge">✓ Approved</span>`
    : `<button class="cl-card-btn cl-card-btn-approve" onclick="event.stopPropagation(); approveContentItem('${item.job_id}')">✓ Approve</button>`;

  const previewBtn = item.workflow_id === 'page-design'
    ? `<button class="cl-card-btn cl-card-btn-preview" onclick="event.stopPropagation(); window.open('${API_BASE}/api/preview/${item.job_id}', '_blank')" title="Open HTML preview">
         Preview
       </button>`
    : '';

  return `
    <div class="cl-card" onclick="viewContentItem('${item.job_id}')">
      <div class="cl-card-top">
        <span class="cl-card-icon">${icon}</span>
        <span class="cl-card-type-badge">${typeLabel}</span>
      </div>
      <div class="cl-card-title">${item.workflow_title}</div>
      <div class="cl-card-meta">${item.client_name} · ${item.created_at}</div>
      ${item.preview ? `<div class="cl-card-preview">${item.preview.slice(0, 120)}${item.preview.length > 120 ? '...' : ''}</div>` : ''}
      <div class="cl-card-actions">
        <button class="cl-card-btn cl-card-btn-view" onclick="event.stopPropagation(); viewContentItem('${item.job_id}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          View
        </button>
        ${previewBtn}
        ${downloadBtn}
        ${approvalEl}
      </div>
    </div>`;
}

function filterContentLibrary() {
  const search = (document.getElementById('contentSearch')?.value || '').toLowerCase().trim();
  const clientFilter = document.getElementById('contentClientFilter')?.value || '';
  const typeFilter = document.getElementById('contentTypeFilter')?.value || '';

  let filtered = CONTENT_ITEMS;

  if (clientFilter) {
    filtered = filtered.filter(c => c.client_name === clientFilter);
  }

  if (typeFilter) {
    filtered = filtered.filter(c => c.workflow_id === typeFilter);
  }

  if (search) {
    filtered = filtered.filter(c =>
      c.workflow_title.toLowerCase().includes(search) ||
      c.client_name.toLowerCase().includes(search) ||
      (c.preview || '').toLowerCase().includes(search)
    );
  }

  renderContentLibrary(filtered);
}

function downloadContentItem(jobId) {
  window.open(`${API_BASE}/api/download/${jobId}`, '_blank');
}

async function viewContentItem(jobId) {
  // JOBS entries use "JOB-NNNN" local IDs; content library uses 8-char server UUIDs.
  // Match via server_job_id which is stored on the job object when the done SSE event fires.
  const job = JOBS.find(j => j.server_job_id === jobId);
  const item = CONTENT_ITEMS.find(c => c.job_id === jobId);

  // If we have cached doc content from this session, show it immediately
  if (job && job.docContent) {
    const title = item ? `${item.workflow_title}` : job.wf || 'Document';
    const subtitle = item ? item.client_name : job.client || '';
    const dlUrl = `${API_BASE}/api/download/${jobId}`;
    renderDocViewerModal(job.docContent, title, subtitle, dlUrl, jobId);
    return;
  }

  // Fetch full content from server API
  try {
    const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();

    if (data.content) {
      const title = data.workflow_title || (item ? item.workflow_title : 'Document');
      const subtitle = data.client_name || (item ? item.client_name : '');
      const dlUrl = data.has_docx ? `${API_BASE}/api/download/${jobId}` : null;
      renderDocViewerModal(data.content, title, subtitle, dlUrl, jobId);
    } else {
      // Fallback: content not available, show basic info modal
      _showBasicJobModal(jobId, item);
    }
  } catch (e) {
    // Server error — fallback to basic modal
    _showBasicJobModal(jobId, item);
  }
}

function _showBasicJobModal(jobId, item) {
  const modalTitle = document.getElementById('modalTitle');
  const modalBody = document.getElementById('modalBody');
  const overlay = document.getElementById('jobModal');
  if (!modalTitle || !modalBody || !overlay) return;

  modalTitle.textContent = item ? `${item.workflow_title} — ${item.client_name}` : `Job ${jobId}`;
  modalBody.innerHTML = `
    <div class="modal-row"><span class="modal-label">Job ID</span><span class="modal-val" style="font-family:var(--mono);color:var(--elec-blue);">${jobId}</span></div>
    ${item ? `<div class="modal-row"><span class="modal-label">Client</span><span class="modal-val">${item.client_name}</span></div>` : ''}
    ${item ? `<div class="modal-row"><span class="modal-label">Workflow</span><span class="modal-val">${item.workflow_title}</span></div>` : ''}
    ${item ? `<div class="modal-row"><span class="modal-label">Created</span><span class="modal-val">${item.created_at}</span></div>` : ''}
    ${item?.has_docx ? `<div class="modal-row"><span class="modal-label">Document</span><span class="modal-val"><a href="${API_BASE}/api/download/${jobId}" target="_blank" style="color:var(--neon-green);text-decoration:none;">Download .docx</a></span></div>` : ''}
    ${item?.preview ? `<div style="margin-top:14px;padding:14px;background:rgba(0,0,0,0.3);border-radius:4px;font-family:var(--mono);font-size:11px;color:var(--text3);line-height:1.7;white-space:pre-wrap;">${item.preview}</div>` : ''}
  `;
  overlay.classList.add('open');
}

async function syncContentLibrary() {
  // Populate the client filter with any items already in memory
  _populateContentClientFilter();

  try {
    const res = await fetch(`${API_BASE}/api/content`);
    if (!res.ok) return;
    const data = await res.json();
    data.items.forEach(item => {
      const existing = CONTENT_ITEMS.find(c => c.job_id === item.job_id);
      if (existing) {
        // Update approval status on existing entries
        existing.approved = !!item.approved;
        existing.approved_at = item.approved_at || null;
      } else {
        // Parse created_at from ISO string or fall back to now
        let displayDate;
        if (item.created_at) {
          const d = new Date(item.created_at);
          displayDate = isNaN(d) ? item.created_at : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } else {
          displayDate = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }
        CONTENT_ITEMS.push({
          id: item.job_id,
          job_id: item.job_id,
          client_name: item.client_name || 'Unknown Client',
          client_id: 0,
          workflow_id: item.workflow_id,
          workflow_title: item.workflow_title,
          has_docx: item.has_docx,
          preview: item.content_preview || '',
          created_at: displayDate,
          approved: !!item.approved,
          approved_at: item.approved_at || null,
        });
      }
    });
    _populateContentClientFilter();
  } catch (e) {
    // Server may not have the endpoint yet — render with whatever is in memory
  }

  renderContentLibrary();
}

/* ── LOGS ── */
let activeLogFilter = 'all';

function setLogFilter(filter) {
  activeLogFilter = filter;
  renderLogs();
}

function renderLogs() {
  const el = document.getElementById('logStream');
  if (!el) return;

  // Update active tab highlight
  document.querySelectorAll('.log-filter-tabs .filter-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.logFilter === activeLogFilter);
  });

  let entries = LOG_ENTRIES;

  if (activeLogFilter === 'agent') {
    entries = LOG_ENTRIES.filter(e => /JOB-\d+/.test(e.msg));
  } else if (activeLogFilter === 'system') {
    entries = LOG_ENTRIES.filter(e => !/JOB-\d+/.test(e.msg) && e.level !== 'err' && e.level !== 'error');
  } else if (activeLogFilter === 'errors') {
    entries = LOG_ENTRIES.filter(e => e.level === 'err' || e.level === 'error');
  }

  if (!entries.length) {
    el.innerHTML = '<div class="empty-state">No activity yet — workflow runs will be logged here</div>';
    return;
  }
  el.innerHTML = entries.map(entry => `
    <div class="log-entry">
      <span class="log-time">${entry.time}</span>
      <span class="log-level-${entry.level}">${entry.level.toUpperCase().padEnd(4)}</span>
      <span class="log-msg">${entry.msg}</span>
    </div>
  `).join('');
}

function clearLogs() {
  LOG_ENTRIES.length = 0;
  renderLogs();
  showToast('Activity log cleared');
}

/* ── AD STUDIO VIEW ── */
function renderAds() {
  const el = document.getElementById('adsGrid');
  if (!el) return;
  el.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">No ad creatives yet — Ad Studio coming soon</div>';
}

/* ── SCHEDULE MANAGER ── */

let SCHEDULES = [];

async function loadSchedules() {
  try {
    const res = await fetch(`${API_BASE}/api/schedule`);
    if (!res.ok) return;
    const data = await res.json();
    SCHEDULES = data.schedules || [];
  } catch (e) { /* server not available */ }
}

function renderSchedules() {
  const el = document.getElementById('schedulesGrid');
  if (!el) return;
  // Clear existing content
  while (el.firstChild) el.removeChild(el.firstChild);

  if (!SCHEDULES.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.style.cssText = 'grid-column:1/-1; text-align:center; padding: 60px 20px;';
    const title = document.createElement('div');
    title.style.cssText = 'font-size:2rem; margin-bottom:12px;';
    title.textContent = 'Automated Content Production';
    const desc = document.createElement('p');
    desc.style.cssText = 'color:var(--text-muted); max-width:500px; margin:0 auto 24px;';
    desc.textContent = 'Schedule pipelines to run automatically \u2014 blog posts every Monday, location pages on the 1st of each month.';
    const btn = document.createElement('button');
    btn.className = 'btn-primary';
    btn.textContent = 'Create Schedule';
    btn.onclick = openCreateScheduleModal;
    empty.appendChild(title);
    empty.appendChild(desc);
    empty.appendChild(btn);
    el.appendChild(empty);
    return;
  }

  // Header row
  const header = document.createElement('div');
  header.style.cssText = 'display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; grid-column:1/-1;';
  const h3 = document.createElement('h3');
  h3.style.margin = '0';
  h3.textContent = 'Scheduled Pipelines';
  const addBtn = document.createElement('button');
  addBtn.className = 'btn-primary';
  addBtn.textContent = '+ New Schedule';
  addBtn.onclick = openCreateScheduleModal;
  header.appendChild(h3);
  header.appendChild(addBtn);
  el.appendChild(header);

  const typeLabels = { 'service-page': 'Service Page', 'location-page': 'Location Page', 'blog-post': 'Blog Post' };

  for (const s of SCHEDULES) {
    const client = CLIENTS.find(c => c.id === s.client_id);
    const clientName = client ? client.name : `Client #${s.client_id}`;
    const typeLabel = typeLabels[s.pipeline_type] || s.pipeline_type;
    const lastRun = s.last_run_at ? new Date(s.last_run_at).toLocaleDateString() : 'Never';

    const card = document.createElement('div');
    card.className = 'schedule-card';
    card.style.cssText = 'grid-column:1/-1; background:var(--panel-bg,#fff); border:1px solid var(--border,#e5e7eb); border-radius:8px; padding:20px; display:flex; justify-content:space-between; align-items:center;';

    const info = document.createElement('div');
    const nameEl = document.createElement('div');
    nameEl.style.cssText = 'font-weight:600; font-size:1.05rem;';
    nameEl.textContent = s.name;
    const meta = document.createElement('div');
    meta.style.cssText = 'color:var(--text-muted); font-size:0.9rem; margin-top:4px;';
    meta.textContent = `${typeLabel} for ${clientName} \u00B7 ${s.schedule}`;
    const last = document.createElement('div');
    last.style.cssText = 'color:var(--text-muted); font-size:0.85rem; margin-top:4px;';
    last.textContent = `Last run: ${lastRun} \u00B7 Status: ${s.last_status || '\u2014'}`;
    info.appendChild(nameEl);
    info.appendChild(meta);
    info.appendChild(last);

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; gap:8px; align-items:center;';
    const badge = document.createElement('span');
    badge.className = s.enabled ? 'badge badge-active' : 'badge badge-inactive';
    badge.style.cssText = 'font-size:0.8rem; padding:4px 10px; border-radius:99px;';
    badge.textContent = s.enabled ? 'Active' : 'Paused';
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'btn-sm';
    toggleBtn.textContent = s.enabled ? 'Pause' : 'Resume';
    toggleBtn.onclick = () => toggleSchedule(s.id, !s.enabled);
    const delBtn = document.createElement('button');
    delBtn.className = 'btn-sm btn-danger';
    delBtn.textContent = 'Delete';
    delBtn.onclick = () => deleteSchedule(s.id);
    actions.appendChild(badge);
    actions.appendChild(toggleBtn);
    actions.appendChild(delBtn);

    card.appendChild(info);
    card.appendChild(actions);
    el.appendChild(card);
  }
}

async function toggleSchedule(jobId, enabled) {
  await fetch(`${API_BASE}/api/schedule/${jobId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  await loadSchedules();
  renderSchedules();
}

async function deleteSchedule(jobId) {
  if (!confirm('Delete this scheduled pipeline?')) return;
  await fetch(`${API_BASE}/api/schedule/${jobId}`, { method: 'DELETE' });
  await loadSchedules();
  renderSchedules();
}

function openCreateScheduleModal() {
  const pipeType = prompt('Pipeline type (service-page, location-page, blog-post):');
  if (!pipeType) return;
  const clientId = prompt('Client ID:');
  if (!clientId) return;
  const schedule = prompt('Schedule (e.g. "every 7d", "0 9 * * 1"):');
  if (!schedule) return;
  const name = prompt('Schedule name:', `Scheduled ${pipeType}`);

  fetch(`${API_BASE}/api/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name || `Scheduled ${pipeType}`,
      client_id: parseInt(clientId),
      pipeline_type: pipeType,
      schedule: schedule,
      inputs: {},
    }),
  }).then(() => { loadSchedules().then(() => renderSchedules()); });
}

/* ── JOB MODAL ── */
function openJobModal(jobId) {
  // Navigate to the job monitor view for all jobs
  showJobMonitor(jobId);

  // If job is completed and has a docx (server_job_id was set), show the done bar immediately
  const job = JOBS.find(j => j.id === jobId);
  if (job && job.status === 'completed' && job.server_job_id) {
    updateMonitorStatus('completed');
    const doneBar = document.getElementById('jmDoneBar');
    const dlLink = document.getElementById('jmDownloadLink');
    const doneMsg = document.getElementById('jmDoneMsg');
    if (doneBar && dlLink && doneMsg) {
      doneMsg.textContent = `Job ${job.server_job_id} complete — output ready`;
      dlLink.href = `${API_BASE}/api/download/${job.server_job_id}`;
      doneBar.style.display = 'flex';
    }
  }
}

function closeModal() {
  document.getElementById('jobModal').classList.remove('open');
}

/* ── TOAST ── */
function showToast(msg, duration = 3000) {
  const t = document.getElementById('runToast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

/* ── AGENT TOGGLE ── */
function toggleAgent() {
  agentRunning = !agentRunning;
  const btn = document.getElementById('agentToggleBtn');
  const dot = document.getElementById('agentDot');
  const state = document.getElementById('agentState');

  if (agentRunning) {
    btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Pause Agent`;
    dot.style.background = 'var(--neon-green)';
    dot.style.boxShadow = '0 0 8px var(--neon-green)';
    state.textContent = `Running · ${JOBS.filter(j => j.status === 'running').length} tasks active`;
    state.style.color = 'var(--neon-green)';
  } else {
    btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Resume Agent`;
    dot.style.background = 'var(--amber)';
    dot.style.boxShadow = 'none';
    state.textContent = 'Paused · tasks held';
    state.style.color = 'var(--amber)';
  }
}

/* ── LIVE CLOCK ── */
function updateClock() {
  const now = new Date();
  const t = now.toTimeString().slice(0, 8);
  const el = document.getElementById('clock');
  if (el) el.textContent = t + ' UTC';
}
updateClock();
setInterval(updateClock, 1000);

/* ── TERMINAL TYPEWRITER ── */
const TERMINAL_LINES = [
  { cls: 'tl-d', text: `# ProofPilot Claude Agent — ${new Date().toISOString().slice(0, 10)}` },
  { blank: true },
  { cls: 'tl-p', text: 'proofpilot init --env production', isPrompt: true },
  { cls: 'tl-d', text: '  → Connecting to Railway backend...', d: 700 },
  { cls: 'tl-ok', text: '  ✓ Backend connected · claude-opus-4-6 ready', d: 1300 },
  { blank: true, d: 1700 },
  { cls: 'tl-p', text: 'proofpilot status --clients', d: 2100, isPrompt: true },
  { cls: 'tl-inf', text: `  ${CLIENTS.length} clients loaded · ${CLIENTS.filter(c => c.status === 'active').length} active · ${CLIENTS.filter(c => c.status === 'inactive').length} inactive`, d: 2700 },
  { blank: true, d: 3200 },
  { cls: 'tl-p', text: 'proofpilot workflows --list-active', d: 3600, isPrompt: true },
  { cls: 'tl-d', text: `  ${WORKFLOWS.filter(w => w.status === 'active').length} active workflows · ${WORKFLOWS.filter(w => w.status === 'soon').length} in pipeline`, d: 4200 },
  { blank: true, d: 4700 },
  { cls: 'tl-inf', text: '  ✓ Agent standing by — select a workflow above to run', d: 5200 },
];

function startTerminal() {
  const tb = document.getElementById('terminal');
  if (!tb) return;

  let li = 0, ci = 0, curDiv = null;

  function tick() {
    if (terminalStreaming) { setTimeout(tick, 1000); return; }
    if (!agentRunning) { setTimeout(tick, 500); return; }
    if (li >= TERMINAL_LINES.length) {
      setTimeout(() => {
        if (tb) tb.innerHTML = `<div class="tl-d"># ProofPilot Claude Agent — ${new Date().toISOString().slice(0, 10)}</div><br>`;
        li = 0; ci = 0; curDiv = null;
        setTimeout(tick, 1500);
      }, 4000);
      return;
    }
    const l = TERMINAL_LINES[li];
    if (l.blank) {
      if (tb) tb.appendChild(document.createElement('br'));
      li++; ci = 0; curDiv = null;
      setTimeout(tick, 80);
      return;
    }
    if (!curDiv) {
      curDiv = document.createElement('div');
      curDiv.className = l.cls;
      if (l.isPrompt) {
        const pfx = document.createElement('span');
        pfx.className = 't-prompt';
        pfx.textContent = '$ ';
        curDiv.appendChild(pfx);
      }
      if (tb) tb.appendChild(curDiv);
    }
    const old = curDiv.querySelector('.t-cursor');
    if (old) old.remove();
    if (ci < l.text.length) {
      curDiv.appendChild(document.createTextNode(l.text[ci]));
      ci++;
      const cur = document.createElement('span');
      cur.className = 't-cursor';
      curDiv.appendChild(cur);
      if (tb) tb.scrollTop = tb.scrollHeight;
      setTimeout(tick, l.isPrompt ? 34 : 10);
    } else {
      li++; ci = 0; curDiv = null;
      setTimeout(tick, l.isPrompt ? 220 : 70);
    }
  }
  setTimeout(tick, 600);
}

function clearTerminal() {
  const tb = document.getElementById('terminal');
  if (tb) tb.innerHTML = '<div class="tl-d"># ProofPilot terminal cleared</div><br>';
}

/* ── JOB PROGRESS SIMULATION ── */
setInterval(() => {
  JOBS.filter(j => j.status === 'running').forEach(job => {
    // Skip jobs that have an active SSE stream — real progress updates come from processSSEChunk()
    if (activeSSEJobs.has(job.id)) return;

    const inc = Math.random() * 2.5 + 0.5;
    jobProgresses[job.id] = Math.min(100, (jobProgresses[job.id] || 0) + inc);

    const pf = document.getElementById(`pf-${job.id}`);
    if (pf) pf.style.width = jobProgresses[job.id] + '%';

    if (jobProgresses[job.id] >= 100) {
      job.status = 'completed';
      job.duration = '8m 14s';
      job.output = 'Complete';
      if (currentView === 'jobs') renderJobs(jobFilter);
      if (currentView === 'dashboard') renderTaskQueue();
    }
  });
}, 2000);

/* ── EVENT LISTENERS ── */

// Nav clicks
document.querySelectorAll('.nav-item[data-view]').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    showView(item.dataset.view);
  });
});

// Job filter tabs
document.getElementById('jobFilterTabs')?.addEventListener('click', e => {
  if (e.target.classList.contains('filter-tab')) {
    renderJobs(e.target.dataset.filter);
  }
});

// Client search
document.getElementById('clientSearch')?.addEventListener('input', e => {
  renderClients(e.target.value.toLowerCase());
});

// Workflow client select
document.getElementById('wfClientSelect')?.addEventListener('change', () => {
  onClientSelectChange();
});

// Workflow input fields — re-validate run button as user types
['wfBusinessType', 'wfLocation', 'wfKeyword', 'wfServiceFocus',
 'wfAuditDomain', 'wfAuditService', 'wfAuditLocation',
 'wfProspectName', 'wfProspectDomain', 'wfProspectService', 'wfProspectLocation',
 'wfGapDomain', 'wfGapService', 'wfGapLocation',
 'wfBlogBusinessType', 'wfBlogLocation', 'wfBlogKeyword',
 'wfSvcBusinessType', 'wfSvcService', 'wfSvcLocation',
 'wfLocBusinessType', 'wfLocPrimaryService', 'wfLocTargetLocation', 'wfLocHomeBase',
 'wfProgContentType', 'wfProgBusinessType', 'wfProgPrimaryService', 'wfProgLocation', 'wfProgHomeBase', 'wfProgItemsList'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', checkRunReady);
});

/* ══════════════════════════════════════════════════════
   REPORTING DASHBOARD
   ══════════════════════════════════════════════════════ */

let _reportingCharts = {};
let _reportingDays = 30;
let _reportingClientId = null;
let _activeTab = 'overview';
let _tabDataLoaded = {};
let _isStandalone = false;

function initDashboardTabs() {
  const tabBar = document.getElementById('dashboardTabs');
  if (!tabBar) return;
  tabBar.querySelectorAll('.dashboard-tab').forEach(btn => {
    btn.onclick = () => switchDashboardTab(btn.dataset.tab);
  });
  // Check URL hash
  const hash = window.location.hash.replace('#', '');
  if (hash && document.getElementById('tab' + hash.charAt(0).toUpperCase() + hash.slice(1))) {
    switchDashboardTab(hash);
  }
}

function switchDashboardTab(tab) {
  _activeTab = tab;
  // Update tab bar
  document.querySelectorAll('.dashboard-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  // Update panes
  document.querySelectorAll('.dashboard-tab-pane').forEach(pane => {
    pane.classList.remove('active');
  });
  const paneId = 'tab' + tab.charAt(0).toUpperCase() + tab.slice(1);
  const pane = document.getElementById(paneId);
  if (pane) pane.classList.add('active');
  // Update URL hash
  if (!_isStandalone) window.location.hash = tab;
  // Load data for this tab if not already loaded
  _loadTabData(tab);
}

async function _loadTabData(tab) {
  if (!_reportingClientId) return;
  if (_tabDataLoaded[tab]) return; // already loaded
  _tabDataLoaded[tab] = true;
  try {
    const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/dashboard?days=${_reportingDays}&tab=${tab}`);
    if (!res.ok) throw new Error('Failed to load tab data');
    const data = await res.json();
    _renderTab(tab, data);
  } catch (e) {
    console.error('Tab load error:', tab, e);
    _tabDataLoaded[tab] = false; // allow retry
  }
}

function _renderTab(tab, data) {
  switch (tab) {
    case 'overview': _renderOverviewTab(data); break;
    case 'seo': _renderSeoTab(data); break;
    case 'paid': _renderPaidTab(data); break;
    case 'leads': _renderLeadsTab(data); break;
    case 'content': _renderContentTab(data); break;
    case 'tasks': _renderTasksTab(data); break;
  }
}

/* ── Tab Renderers ── */

function _renderOverviewTab(data) {
  const s = data.summary || {};
  // Hero KPIs
  const heroRow = document.getElementById('heroKPIs');
  if (heroRow) {
    heroRow.textContent = '';
    const leadsTotal = (s.total_leads?.current || 0) + (data.sheets_calls || []).reduce((sum, d) => sum + d.value, 0);
    const leadsPrev = s.total_leads?.previous || 0;
    const revCurrent = s.total_revenue?.current || 0;
    const revPrev = s.total_revenue?.previous || 0;

    // Build sparkline data arrays
    const leadsData = (data.sheets_leads || data.search_clicks || []).map(d => d.value);
    const revenueData = (data.sheets_revenue || []).map(d => d.value);

    [
      { label: 'Total Qualified Leads', value: leadsTotal, prev: leadsPrev, fmt: v => Math.round(v).toLocaleString(), sparkData: leadsData },
      { label: 'Revenue', value: revCurrent, prev: revPrev, fmt: v => '$' + Math.round(v).toLocaleString(), sparkData: revenueData },
    ].forEach(kpi => {
      const card = document.createElement('div');
      card.className = 'hero-kpi-card';
      const lbl = document.createElement('div'); lbl.className = 'hero-kpi-label'; lbl.textContent = kpi.label;
      const val = document.createElement('div'); val.className = 'hero-kpi-value'; val.textContent = kpi.fmt(kpi.value);
      const delta = kpi.prev > 0 ? ((kpi.value - kpi.prev) / kpi.prev * 100) : 0;
      const delEl = document.createElement('div');
      delEl.className = 'hero-kpi-delta ' + (delta >= 0 ? 'positive' : 'negative');
      delEl.textContent = (delta >= 0 ? '\u25B2 ' : '\u25BC ') + Math.abs(delta).toFixed(1) + '% MoM';
      card.append(lbl, val, delEl);
      // Sparkline canvas
      if (kpi.sparkData && kpi.sparkData.length > 1) {
        const sparkWrap = document.createElement('div'); sparkWrap.className = 'hero-kpi-sparkline';
        const canvas = document.createElement('canvas');
        canvas.width = 200; canvas.height = 40;
        sparkWrap.appendChild(canvas);
        card.appendChild(sparkWrap);
        // Draw sparkline after DOM attach
        setTimeout(() => {
          new Chart(canvas, {
            type: 'line',
            data: { labels: kpi.sparkData.map((_, i) => i), datasets: [{ data: kpi.sparkData, borderColor: '#C8FF00', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }] },
            options: { responsive: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } }, animation: false }
          });
        }, 0);
      }
      heroRow.appendChild(card);
    });
  }

  // Secondary KPIs
  const calls = (data.sheets_calls || []).reduce((sum, d) => sum + d.value, 0);
  const forms = (s.total_leads?.current || 0);
  const sessions = s.total_sessions?.current || 0;
  const totalSpend = (s.total_ad_spend_google?.current || 0) + (s.total_ad_spend_meta?.current || 0);
  const avgPos = s.avg_position?.current || 0;
  _buildKPICards(document.getElementById('overviewSecondaryKPIs'), [
    { label: 'Phone Calls', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '', _custom: calls, _delta: 0 },
    { label: 'Form Submissions', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '', _custom: forms, _delta: 0 },
    { label: 'Organic Sessions', key: 'total_sessions', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
    { label: 'Total Ad Spend', key: '_', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '', _custom: totalSpend, _delta: 0 },
    { label: 'Avg Position', key: 'avg_position', fmt: v => v.toFixed(1), unit: '', invert: true },
  ], s);

  // Leads Over Time chart
  const orgLeads = (data.sheets_leads || []).map(d => ({ date: d.date, value: d.value }));
  const paidLeads = (data.google_ads_conversions || []).map(d => ({ date: d.date, value: d.value }));
  if (orgLeads.length > 0 || paidLeads.length > 0) {
    const allDates = [...new Set([...orgLeads.map(d => d.date), ...paidLeads.map(d => d.date)])].sort();
    const orgMap = Object.fromEntries(orgLeads.map(d => [d.date, d.value]));
    const paidMap = Object.fromEntries(paidLeads.map(d => [d.date, d.value]));
    _getChart('chartOverviewLeads', {
      type: 'line',
      data: {
        labels: allDates,
        datasets: [
          { label: 'Organic Leads', data: allDates.map(d => orgMap[d] || 0), borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.08)', fill: true, tension: 0.3 },
          { label: 'Paid Leads', data: allDates.map(d => paidMap[d] || 0), borderColor: '#0051FF', backgroundColor: 'rgba(0,81,255,0.08)', fill: true, tension: 0.3 },
        ]
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { x: { type: 'time', time: { unit: 'day' } }, y: { beginAtZero: true } } }
    });
  }

  // Revenue vs Ad Spend chart
  const revTs = data.sheets_revenue || [];
  const gAdsSpend = data.google_ads_spend || [];
  const mAdsSpend = data.meta_ads_spend || [];
  if (revTs.length > 0 || gAdsSpend.length > 0) {
    const allDates2 = [...new Set([...revTs.map(d => d.date), ...gAdsSpend.map(d => d.date), ...mAdsSpend.map(d => d.date)])].sort();
    const revMap = Object.fromEntries(revTs.map(d => [d.date, d.value]));
    const spendMap = {};
    gAdsSpend.forEach(d => { spendMap[d.date] = (spendMap[d.date] || 0) + d.value; });
    mAdsSpend.forEach(d => { spendMap[d.date] = (spendMap[d.date] || 0) + d.value; });
    _getChart('chartRevenueVsSpend', {
      type: 'line',
      data: {
        labels: allDates2,
        datasets: [
          { label: 'Revenue', data: allDates2.map(d => revMap[d] || 0), borderColor: '#0D9488', yAxisID: 'y', tension: 0.3 },
          { label: 'Ad Spend', data: allDates2.map(d => spendMap[d] || 0), borderColor: '#DC3545', borderDash: [5, 5], yAxisID: 'y1', tension: 0.3 },
        ]
      },
      options: {
        responsive: true, plugins: { legend: { position: 'bottom' } },
        scales: {
          x: { type: 'time', time: { unit: 'day' } },
          y: { position: 'left', title: { display: true, text: 'Revenue' }, ticks: { callback: v => '$' + v.toLocaleString() } },
          y1: { position: 'right', title: { display: true, text: 'Ad Spend' }, grid: { drawOnChartArea: false }, ticks: { callback: v => '$' + v.toLocaleString() } }
        }
      }
    });
  }

  // Lead Source Breakdown chart
  const sources = [];
  if (s.total_clicks?.current > 0) sources.push({ label: 'Google Organic', value: s.total_clicks.current });
  if (s.total_conversions_google?.current > 0) sources.push({ label: 'Google Ads', value: s.total_conversions_google.current });
  if (s.total_conversions_meta?.current > 0) sources.push({ label: 'Meta Ads', value: s.total_conversions_meta.current });
  if (calls > 0) sources.push({ label: 'Direct/Calls', value: calls });
  if (sources.length > 0) {
    _getChart('chartLeadSources', {
      type: 'bar',
      data: {
        labels: sources.map(s => s.label),
        datasets: [{ data: sources.map(s => s.value), backgroundColor: ['#16a34a', '#4285F4', '#1877F2', '#D97706'] }]
      },
      options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
    });
  }
}

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

function _renderLeadsTab(data) {
  const leads = data.sheets_leads || [];
  const calls = data.sheets_calls || [];
  const revenue = data.sheets_revenue || [];
  const emptyEl = document.getElementById('leadsEmpty');

  if (leads.length === 0 && calls.length === 0 && revenue.length === 0) {
    if (emptyEl) emptyEl.style.display = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  // KPIs
  const s = data.summary || {};
  const totalCalls = calls.reduce((sum, d) => sum + d.value, 0);
  const totalLeads = leads.reduce((sum, d) => sum + d.value, 0);
  _buildKPICards(document.getElementById('leadsKPIs'), [
    { label: 'Qualified Calls', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '', _custom: totalCalls, _delta: 0 },
    { label: 'Form Submissions', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '', _custom: totalLeads, _delta: 0 },
    { label: 'Total Revenue', key: 'total_revenue', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '%' },
  ], s);

  // Leads Over Time chart
  if (leads.length > 0 || calls.length > 0) {
    const allDates = [...new Set([...leads.map(d => d.date), ...calls.map(d => d.date)])].sort();
    const leadsMap = Object.fromEntries(leads.map(d => [d.date, d.value]));
    const callsMap = Object.fromEntries(calls.map(d => [d.date, d.value]));
    _getChart('chartLeadsTimeline', {
      type: 'line',
      data: {
        labels: allDates,
        datasets: [
          { label: 'Form Leads', data: allDates.map(d => leadsMap[d] || 0), borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.08)', fill: true, tension: 0.3 },
          { label: 'Phone Calls', data: allDates.map(d => callsMap[d] || 0), borderColor: '#0051FF', backgroundColor: 'rgba(0,81,255,0.08)', fill: true, tension: 0.3 },
        ]
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { x: { type: 'time', time: { unit: 'day' } }, y: { beginAtZero: true } } }
    });
  }

  // Calls by Source (placeholder — real data would come from call tracking detail)
  if (calls.length > 0) {
    _getChart('chartCallsBySource', {
      type: 'bar',
      data: {
        labels: ['Google Organic', 'Google Ads', 'Direct', 'Other'],
        datasets: [{ data: [Math.round(totalCalls * 0.4), Math.round(totalCalls * 0.3), Math.round(totalCalls * 0.2), Math.round(totalCalls * 0.1)], backgroundColor: ['#16a34a', '#4285F4', '#D97706', '#6B7280'] }]
      },
      options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
    });
  }
}

function _renderContentTab(data) {
  const items = data.roadmap || [];
  const stats = data.stats || {};
  const emptyEl = document.getElementById('contentEmpty');
  const uploadBtn = document.getElementById('btnUploadContent');

  // Show upload button for internal users
  if (uploadBtn && !_isStandalone) uploadBtn.style.display = '';

  if (items.length === 0 && stats.total === 0) {
    if (emptyEl) emptyEl.style.display = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  // Summary cards
  const summaryEl = document.getElementById('contentSummaryCards');
  if (summaryEl) {
    summaryEl.textContent = '';
    [
      { label: 'Total', value: stats.total || 0, color: 'var(--text)' },
      { label: 'Published', value: stats.published || 0, color: '#4ADE80' },
      { label: 'In Progress', value: stats.in_progress || 0, color: '#FBBF24' },
      { label: 'Planned', value: stats.planned || 0, color: '#9CA3AF' },
    ].forEach(s => {
      const card = document.createElement('div');
      card.className = 'kpi-card';
      const lbl = document.createElement('div'); lbl.className = 'kpi-label'; lbl.textContent = s.label;
      const val = document.createElement('div'); val.className = 'kpi-value'; val.textContent = s.value; val.style.color = s.color;
      card.append(lbl, val);
      summaryEl.appendChild(card);
    });
  }

  // Type pie chart
  if (stats.types && Object.keys(stats.types).length > 0) {
    const typeLabels = Object.keys(stats.types);
    const typeValues = Object.values(stats.types);
    const colors = ['#0051FF', '#D97706', '#7C3AED', '#DC3545', '#28A745', '#0D9488', '#EA580C', '#6B7280'];
    _getChart('chartContentTypes', {
      type: 'doughnut',
      data: { labels: typeLabels, datasets: [{ data: typeValues, backgroundColor: colors.slice(0, typeLabels.length) }] },
      options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
    });
  }

  // Populate filter dropdowns
  _populateContentFilters(items);

  // Roadmap table
  _renderContentTable(items);

  // Wire up filters
  ['contentFilterMonth', 'contentFilterType', 'contentFilterStatus'].forEach(id => {
    const sel = document.getElementById(id);
    if (sel) sel.onchange = () => _filterContentTable(items);
  });

  // Wire up upload button
  if (uploadBtn) {
    uploadBtn.onclick = () => {
      const modal = document.getElementById('contentUploadModal');
      if (modal) modal.style.display = '';
      _initContentUpload();
    };
  }
}

function _populateContentFilters(items) {
  const months = [...new Set(items.map(i => i.month).filter(Boolean))].sort();
  const types = [...new Set(items.map(i => i.page_type).filter(Boolean))].sort();
  const statuses = [...new Set(items.map(i => i.status).filter(Boolean))].sort();

  const monthSel = document.getElementById('contentFilterMonth');
  const typeSel = document.getElementById('contentFilterType');
  const statusSel = document.getElementById('contentFilterStatus');

  if (monthSel) {
    const current = monthSel.value;
    monthSel.textContent = '';
    const all = document.createElement('option'); all.value = ''; all.textContent = 'All Months'; monthSel.appendChild(all);
    months.forEach(m => { const opt = document.createElement('option'); opt.value = m; opt.textContent = m; monthSel.appendChild(opt); });
    monthSel.value = current;
  }
  if (typeSel) {
    const current = typeSel.value;
    typeSel.textContent = '';
    const all = document.createElement('option'); all.value = ''; all.textContent = 'All Types'; typeSel.appendChild(all);
    types.forEach(t => { const opt = document.createElement('option'); opt.value = t; opt.textContent = t; typeSel.appendChild(opt); });
    typeSel.value = current;
  }
  if (statusSel) {
    const current = statusSel.value;
    statusSel.textContent = '';
    const all = document.createElement('option'); all.value = ''; all.textContent = 'All Statuses'; statusSel.appendChild(all);
    statuses.forEach(s => { const opt = document.createElement('option'); opt.value = s; opt.textContent = s; statusSel.appendChild(opt); });
    statusSel.value = current;
  }
}

function _filterContentTable(allItems) {
  const month = document.getElementById('contentFilterMonth')?.value || '';
  const type = document.getElementById('contentFilterType')?.value || '';
  const status = document.getElementById('contentFilterStatus')?.value || '';
  let filtered = allItems;
  if (month) filtered = filtered.filter(i => i.month === month);
  if (type) filtered = filtered.filter(i => i.page_type === type);
  if (status) filtered = filtered.filter(i => i.status === status);
  _renderContentTable(filtered);
}

function _renderContentTable(items) {
  const table = document.getElementById('contentRoadmapTable');
  if (!table) return;
  table.textContent = '';
  const thead = document.createElement('thead');
  thead.appendChild(_tr(['Month', 'Title', 'Type', 'Silo', 'Status', 'Keyword', 'Vol', 'KD'], true));
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  items.forEach(item => {
    const tr = document.createElement('tr');
    const tdMonth = document.createElement('td'); tdMonth.textContent = item.month || ''; tr.appendChild(tdMonth);
    const tdTitle = document.createElement('td'); tdTitle.textContent = item.title || ''; tr.appendChild(tdTitle);
    const tdType = document.createElement('td'); tdType.textContent = item.page_type || ''; tr.appendChild(tdType);
    const tdSilo = document.createElement('td'); tdSilo.textContent = item.content_silo || ''; tr.appendChild(tdSilo);
    const tdStatus = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'content-status-badge ' + (item.status || 'planned');
    badge.textContent = (item.status || 'planned').charAt(0).toUpperCase() + (item.status || 'planned').slice(1);
    tdStatus.appendChild(badge);
    tr.appendChild(tdStatus);
    const tdKw = document.createElement('td'); tdKw.textContent = item.keyword || ''; tr.appendChild(tdKw);
    const tdVol = document.createElement('td'); tdVol.textContent = item.volume ? Number(item.volume).toLocaleString() : ''; tr.appendChild(tdVol);
    const tdKD = document.createElement('td'); tdKD.textContent = item.difficulty || ''; tr.appendChild(tdKD);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function _initContentUpload() {
  const fileInput = document.getElementById('contentFileInput');
  if (!fileInput) return;
  fileInput.value = '';
  const preview = document.getElementById('contentMappingPreview');
  if (preview) preview.style.display = 'none';
  const statusEl = document.getElementById('contentUploadStatus');
  if (statusEl) statusEl.textContent = '';

  fileInput.onchange = async () => {
    if (!fileInput.files || !fileInput.files[0]) return;
    if (statusEl) statusEl.textContent = 'Uploading and analyzing columns...';
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    try {
      const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/content-roadmap/upload`, {
        method: 'POST', body: formData
      });
      if (!res.ok) throw new Error('Upload failed');
      const result = await res.json();
      _showMappingPreview(result);
      if (statusEl) statusEl.textContent = '';
    } catch (e) {
      if (statusEl) statusEl.textContent = 'Error: ' + e.message;
    }
  };
}

let _pendingCsvText = '';
function _showMappingPreview(result) {
  _pendingCsvText = result.csv_text;
  const preview = document.getElementById('contentMappingPreview');
  if (!preview) return;
  preview.style.display = '';
  const fieldsEl = document.getElementById('contentMappingFields');
  if (!fieldsEl) return;
  fieldsEl.textContent = '';

  const headers = result.headers || [];
  const mapping = result.proposed_mapping || {};
  const targetFields = ['month', 'title', 'page_type', 'content_silo', 'status', 'keyword', 'volume', 'difficulty'];

  targetFields.forEach(field => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;';
    const label = document.createElement('span');
    label.style.cssText = 'min-width:120px;font-weight:600;font-size:13px;';
    label.textContent = field;
    const sel = document.createElement('select');
    sel.className = 'reporting-select';
    sel.style.cssText = 'width:auto;min-width:160px;';
    sel.dataset.field = field;
    const noneOpt = document.createElement('option'); noneOpt.value = '-1'; noneOpt.textContent = '(none)'; sel.appendChild(noneOpt);
    headers.forEach((h, i) => {
      const opt = document.createElement('option'); opt.value = String(i); opt.textContent = h; sel.appendChild(opt);
    });
    sel.value = String(mapping[field] !== undefined ? mapping[field] : -1);
    row.append(label, sel);
    fieldsEl.appendChild(row);
  });

  // Sample data preview
  if (result.sample_rows && result.sample_rows.length > 0) {
    const sampleLabel = document.createElement('p');
    sampleLabel.style.cssText = 'margin-top:0.75rem;font-size:12px;color:var(--muted);';
    sampleLabel.textContent = 'Sample: ' + result.sample_rows[0].join(' | ');
    fieldsEl.appendChild(sampleLabel);
  }

  const totalLabel = document.createElement('p');
  totalLabel.style.cssText = 'margin-top:0.25rem;font-size:12px;color:var(--muted);';
  totalLabel.textContent = result.total_rows + ' rows to import';
  fieldsEl.appendChild(totalLabel);

  // Wire confirm button
  const confirmBtn = document.getElementById('btnConfirmMapping');
  if (confirmBtn) confirmBtn.onclick = () => _confirmContentMapping();
}

async function _confirmContentMapping() {
  const fieldsEl = document.getElementById('contentMappingFields');
  if (!fieldsEl) return;
  const mapping = {};
  fieldsEl.querySelectorAll('select').forEach(sel => {
    mapping[sel.dataset.field] = parseInt(sel.value);
  });
  const statusEl = document.getElementById('contentUploadStatus');
  if (statusEl) statusEl.textContent = 'Importing...';
  try {
    const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/content-roadmap/confirm-mapping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mapping, csv_text: _pendingCsvText })
    });
    if (!res.ok) throw new Error('Import failed');
    const result = await res.json();
    if (statusEl) statusEl.textContent = 'Imported ' + result.imported + ' items!';
    const modal = document.getElementById('contentUploadModal');
    setTimeout(() => { if (modal) modal.style.display = 'none'; }, 1500);
    // Reload content tab
    _tabDataLoaded['content'] = false;
    _loadTabData('content');
  } catch (e) {
    if (statusEl) statusEl.textContent = 'Error: ' + e.message;
  }
}

let _tasksMonth = '';
function _renderTasksTab(data) {
  const tasks = data.tasks || [];
  const month = data.month || '';
  _tasksMonth = month;

  // Month label
  const monthLabel = document.getElementById('tasksMonthLabel');
  if (monthLabel) {
    const [y, m] = month.split('-');
    const monthNames = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    monthLabel.textContent = (monthNames[parseInt(m)] || m) + ' ' + y;
  }

  // Month navigation
  const prevBtn = document.getElementById('btnTasksPrev');
  const nextBtn = document.getElementById('btnTasksNext');
  if (prevBtn) prevBtn.onclick = () => _navigateTasksMonth(-1);
  if (nextBtn) nextBtn.onclick = () => _navigateTasksMonth(1);

  // Add task button (internal only)
  const addBtn = document.getElementById('btnAddTask');
  if (addBtn && !_isStandalone) {
    addBtn.style.display = '';
    addBtn.onclick = () => _showAddTaskPrompt();
  }

  // Empty state
  const emptyEl = document.getElementById('tasksEmpty');
  if (tasks.length === 0) {
    if (emptyEl) emptyEl.style.display = '';
    document.getElementById('tasksProgress').textContent = '';
    document.getElementById('tasksList').textContent = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  // Progress bar
  const progressEl = document.getElementById('tasksProgress');
  if (progressEl) {
    progressEl.textContent = '';
    const total = tasks.length;
    const complete = tasks.filter(t => t.status === 'complete').length;
    const pct = total > 0 ? Math.round(complete / total * 100) : 0;

    const bar = document.createElement('div'); bar.className = 'tasks-progress-bar';
    const fill = document.createElement('div'); fill.className = 'tasks-progress-fill'; fill.style.width = pct + '%';
    bar.appendChild(fill);
    const label = document.createElement('div'); label.className = 'tasks-progress-label';
    label.textContent = complete + ' of ' + total + ' complete (' + pct + '%)';
    progressEl.append(bar, label);
  }

  // Task list grouped by category
  const listEl = document.getElementById('tasksList');
  if (listEl) {
    listEl.textContent = '';
    const grouped = {};
    tasks.forEach(t => {
      const cat = t.category || 'other';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(t);
    });
    const catOrder = ['content', 'seo', 'paid', 'reporting', 'other'];
    catOrder.forEach(cat => {
      if (!grouped[cat]) return;
      const catLabel = document.createElement('div');
      catLabel.className = 'tasks-category-label';
      catLabel.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
      listEl.appendChild(catLabel);

      grouped[cat].forEach(task => {
        const item = document.createElement('div');
        item.className = 'task-item ' + (task.status || 'not_started');

        const checkbox = document.createElement('div');
        checkbox.className = 'task-checkbox';
        if (task.status === 'complete') checkbox.textContent = '\u2713';
        if (task.status === 'in_progress') checkbox.textContent = '\u2022';

        const title = document.createElement('div');
        title.className = 'task-title';
        title.textContent = task.title || '';

        const catTag = document.createElement('span');
        catTag.className = 'task-category-tag';
        catTag.textContent = cat;

        item.append(checkbox, title, catTag);
        item.onclick = () => _cycleTaskStatus(task, item);
        listEl.appendChild(item);
      });
    });
  }
}

async function _navigateTasksMonth(delta) {
  const [y, m] = _tasksMonth.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  const newMonth = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  _tasksMonth = newMonth;
  try {
    const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/dashboard?days=${_reportingDays}&tab=tasks&month=${newMonth}`);
    if (!res.ok) throw new Error('Failed');
    const data = await res.json();
    _renderTasksTab(data);
  } catch (e) {
    console.error('Tasks month nav error:', e);
  }
}

async function _cycleTaskStatus(task, itemEl) {
  const order = ['not_started', 'in_progress', 'complete'];
  const idx = order.indexOf(task.status || 'not_started');
  const newStatus = order[(idx + 1) % order.length];
  try {
    await fetch(`${API_BASE}/api/clients/${_reportingClientId}/tasks/${task.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    task.status = newStatus;
    // Update UI
    itemEl.className = 'task-item ' + newStatus;
    const cb = itemEl.querySelector('.task-checkbox');
    if (cb) {
      cb.textContent = newStatus === 'complete' ? '\u2713' : newStatus === 'in_progress' ? '\u2022' : '';
    }
    // Refresh progress bar
    _tabDataLoaded['tasks'] = false;
    _loadTabData('tasks');
  } catch (e) {
    console.error('Status update error:', e);
  }
}

function _showAddTaskPrompt() {
  const title = prompt('Task title:');
  if (!title) return;
  const category = prompt('Category (content/seo/paid/reporting/other):', 'other') || 'other';
  fetch(`${API_BASE}/api/clients/${_reportingClientId}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, category, month: _tasksMonth })
  }).then(() => {
    _tabDataLoaded['tasks'] = false;
    _loadTabData('tasks');
  });
}

function _esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

async function renderReportingDashboard() {
  const sel = document.getElementById('reportingClientSelect');
  if (!sel) return;

  if (sel.options.length <= 1) {
    sel.textContent = '';
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = 'Select a client...';
    sel.appendChild(opt0);
    CLIENTS.filter(c => c.status === 'active').forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      sel.appendChild(opt);
    });
    sel.onchange = () => { _reportingClientId = parseInt(sel.value) || null; _loadReportingData(); };
  }

  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _reportingDays = parseInt(btn.dataset.days);
      _loadReportingData();
    };
  });

  if (_reportingClientId) _loadReportingData();
  initDashboardTabs();
}

async function _loadReportingData() {
  if (!_reportingClientId) return;
  const emptyEl = document.getElementById('reportingEmpty');
  // Reset tab data cache so tabs reload
  _tabDataLoaded = {};
  // Destroy all existing charts
  _destroyCharts();
  // Load data for the active tab
  _loadTabData(_activeTab);
}

/* ── KPI card builder helper ── */
function _buildKPICards(container, kpis, summary) {
  if (!container) return;
  container.textContent = '';
  kpis.forEach(kpi => {
    const d = kpi._custom !== undefined
      ? { current: kpi._custom, previous: kpi._prevCustom || 0, delta: kpi._delta || 0 }
      : (summary[kpi.key] || { current: 0, previous: 0, delta: 0 });
    const delta = d.delta;
    const isPositive = kpi.invert ? delta < 0 : delta > 0;
    const cls = isPositive ? 'positive' : delta === 0 ? '' : 'negative';
    const arrow = delta > 0 ? '\u25B2' : delta < 0 ? '\u25BC' : '\u2013';
    const deltaStr = kpi.unit === '%' ? `${Math.abs(delta).toFixed(1)}%` : Math.abs(delta).toFixed(1);

    const card = document.createElement('div');
    card.className = 'kpi-card';
    const lbl = document.createElement('div'); lbl.className = 'kpi-label'; lbl.textContent = kpi.label;
    const val = document.createElement('div'); val.className = 'kpi-value'; val.textContent = kpi.fmt(d.current);
    const del = document.createElement('div'); del.className = `kpi-delta ${cls}`; del.textContent = `${arrow} ${deltaStr}`;
    card.append(lbl, val, del);
    container.appendChild(card);
  });
}

function _renderOrganicKPIs(summary) {
  _buildKPICards(document.getElementById('organicKPIs'), [
    { label: 'Total Clicks', key: 'total_clicks', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
    { label: 'Impressions', key: 'total_impressions', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
    { label: 'Avg Position', key: 'avg_position', fmt: v => v.toFixed(1), unit: '', invert: true },
    { label: 'Avg CTR', key: 'avg_ctr', fmt: v => (v * 100).toFixed(1) + '%', unit: '' },
    { label: 'Sessions', key: 'total_sessions', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
  ], summary);
}

function _destroyCharts() {
  Object.values(_reportingCharts).forEach(c => c?.destroy());
  _reportingCharts = {};
}

function _getChart(canvasId, config) {
  if (_reportingCharts[canvasId]) _reportingCharts[canvasId].destroy();
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  const chart = new Chart(ctx, config);
  _reportingCharts[canvasId] = chart;
  return chart;
}

function _renderSearchPerfChart(clicks, impressions) {
  _getChart('chartSearchPerf', {
    type: 'line',
    data: {
      labels: (clicks || []).map(d => d.date),
      datasets: [
        { label: 'Clicks', data: (clicks || []).map(d => d.value), borderColor: '#0051FF', backgroundColor: 'rgba(0,81,255,0.08)', fill: true, yAxisID: 'y', tension: 0.3 },
        { label: 'Impressions', data: (impressions || []).map(d => d.value), borderColor: '#D97706', backgroundColor: 'transparent', borderDash: [5, 5], yAxisID: 'y1', tension: 0.3 },
      ]
    },
    options: {
      responsive: true, plugins: { legend: { position: 'bottom' } },
      scales: {
        x: { type: 'time', time: { unit: 'day' } },
        y: { position: 'left', title: { display: true, text: 'Clicks' } },
        y1: { position: 'right', title: { display: true, text: 'Impressions' }, grid: { drawOnChartArea: false } }
      }
    }
  });
}

function _renderTrafficSourcesChart(sources) {
  const labels = (sources || []).map(d => d.dimension.replace('source:', ''));
  const values = (sources || []).map(d => d.value);
  const colors = ['#0051FF', '#D97706', '#7C3AED', '#DC3545', '#28A745', '#0D9488', '#EA580C', '#6B7280'];
  _getChart('chartTrafficSources', {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors.slice(0, labels.length) }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
  });
}

function _renderSessionsChart(sessions, users) {
  _getChart('chartSessions', {
    type: 'line',
    data: {
      labels: (sessions || []).map(d => d.date),
      datasets: [
        { label: 'Sessions', data: (sessions || []).map(d => d.value), borderColor: '#0051FF', tension: 0.3, fill: true, backgroundColor: 'rgba(0,81,255,0.08)' },
        { label: 'Users', data: (users || []).map(d => d.value), borderColor: '#7C3AED', tension: 0.3, fill: false },
      ]
    },
    options: {
      responsive: true, plugins: { legend: { position: 'bottom' } },
      scales: { x: { type: 'time', time: { unit: 'day' } } }
    }
  });
}

function _renderTopKeywordsChart(keywords) {
  const top = (keywords || []).slice(0, 10);
  _getChart('chartTopKeywords', {
    type: 'bar',
    data: {
      labels: top.map(d => d.dimension.replace('query:', '')),
      datasets: [{ label: 'Clicks', data: top.map(d => d.value), backgroundColor: '#0051FF' }]
    },
    options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
  });
}

function _renderRankingsTable(rankings) {
  const table = document.getElementById('rankingsTable');
  if (!table || !rankings) return;
  const posClass = p => p <= 3 ? 'top3' : p <= 10 ? 'top10' : p <= 20 ? 'top20' : 'beyond';
  table.textContent = '';
  const thead = document.createElement('thead');
  thead.appendChild(_tr(['Keyword', 'Position', 'Change', 'Clicks', 'Impressions'], true));
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  (rankings || []).forEach(r => {
    const tr = document.createElement('tr');
    const tdKw = document.createElement('td'); tdKw.textContent = r.keyword; tr.appendChild(tdKw);
    const tdPos = document.createElement('td');
    const badge = document.createElement('span'); badge.className = `position-badge ${posClass(r.position)}`; badge.textContent = r.position;
    tdPos.appendChild(badge); tr.appendChild(tdPos);
    const tdChg = document.createElement('td'); tdChg.textContent = (r.change > 0 ? '+' : '') + r.change;
    tdChg.style.color = r.change > 0 ? '#28A745' : r.change < 0 ? '#DC3545' : '#6B7280'; tr.appendChild(tdChg);
    const tdClk = document.createElement('td'); tdClk.textContent = r.clicks.toLocaleString(); tr.appendChild(tdClk);
    const tdImp = document.createElement('td'); tdImp.textContent = r.impressions.toLocaleString(); tr.appendChild(tdImp);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function _renderTopPagesTable(pages) {
  const table = document.getElementById('topPagesTable');
  if (!table || !pages) return;
  table.textContent = '';
  const thead = document.createElement('thead');
  thead.appendChild(_tr(['Page', 'Clicks'], true));
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  (pages || []).slice(0, 20).forEach(p => {
    const path = p.dimension.replace('page:', '');
    const tr = document.createElement('tr');
    const tdPage = document.createElement('td'); tdPage.textContent = path.length > 60 ? path.slice(0, 57) + '...' : path; tdPage.title = path; tr.appendChild(tdPage);
    const tdClk = document.createElement('td'); tdClk.textContent = Math.round(p.value).toLocaleString(); tr.appendChild(tdClk);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function _tr(cells, isHeader) {
  const tr = document.createElement('tr');
  cells.forEach(text => {
    const td = document.createElement(isHeader ? 'th' : 'td');
    td.textContent = text;
    tr.appendChild(td);
  });
  return tr;
}

/* ── Paid Section ── */
function _renderPaidSection(data) {
  const section = document.getElementById('sectionPaid');
  if (!section) return;

  const gSpend = data.google_ads_spend || [];
  const mSpend = data.meta_ads_spend || [];
  const gConv = data.google_ads_conversions || [];
  const mConv = data.meta_ads_conversions || [];
  const hasGoogle = gSpend.length > 0;
  const hasMeta = mSpend.length > 0;

  if (!hasGoogle && !hasMeta) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Combined paid KPIs
  const s = data.summary || {};
  const totalSpendG = s.total_ad_spend_google?.current || 0;
  const totalSpendM = s.total_ad_spend_meta?.current || 0;
  const totalConvG = s.total_conversions_google?.current || 0;
  const totalConvM = s.total_conversions_meta?.current || 0;
  _buildKPICards(document.getElementById('paidKPIs'), [
    { label: 'Total Ad Spend', key: '_', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '%', _custom: totalSpendG + totalSpendM, _delta: 0 },
    { label: 'Total Conversions', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '%', _custom: totalConvG + totalConvM, _delta: 0 },
  ], s);

  // ── Google Ads subsection ──
  const gSub = document.getElementById('subsectionGoogleAds');
  if (gSub) {
    if (!hasGoogle) { gSub.style.display = 'none'; }
    else {
      gSub.style.display = '';
      _buildKPICards(document.getElementById('googleAdsKPIs'), [
        { label: 'Spend', key: 'total_ad_spend_google', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '%' },
        { label: 'Conversions', key: 'total_conversions_google', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
      ], s);
      _getChart('chartGoogleAdsSpend', {
        type: 'line',
        data: { labels: gSpend.map(d => d.date), datasets: [{ label: 'Spend', data: gSpend.map(d => d.value), borderColor: '#4285F4', backgroundColor: 'rgba(66,133,244,0.08)', fill: true, tension: 0.3 }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => '$' + v.toLocaleString() } } } }
      });
      _getChart('chartGoogleAdsConv', {
        type: 'bar',
        data: { labels: gConv.map(d => d.date), datasets: [{ label: 'Conversions', data: gConv.map(d => d.value), backgroundColor: 'rgba(66,133,244,0.7)' }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
      _renderPlatformCampaignTable('googleAdsCampaignSection', 'googleAdsCampaignTable', data.google_ads_campaigns || []);
    }
  }

  // ── Meta Ads subsection ──
  const mSub = document.getElementById('subsectionMetaAds');
  if (mSub) {
    if (!hasMeta) { mSub.style.display = 'none'; }
    else {
      mSub.style.display = '';
      _buildKPICards(document.getElementById('metaAdsKPIs'), [
        { label: 'Spend', key: 'total_ad_spend_meta', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '%' },
        { label: 'Conversions', key: 'total_conversions_meta', fmt: v => Math.round(v).toLocaleString(), unit: '%' },
      ], s);
      _getChart('chartMetaAdsSpend', {
        type: 'line',
        data: { labels: mSpend.map(d => d.date), datasets: [{ label: 'Spend', data: mSpend.map(d => d.value), borderColor: '#1877F2', backgroundColor: 'rgba(24,119,242,0.08)', fill: true, tension: 0.3 }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => '$' + v.toLocaleString() } } } }
      });
      _getChart('chartMetaAdsConv', {
        type: 'bar',
        data: { labels: mConv.map(d => d.date), datasets: [{ label: 'Conversions', data: mConv.map(d => d.value), backgroundColor: 'rgba(24,119,242,0.7)' }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
      _renderPlatformCampaignTable('metaAdsCampaignSection', 'metaAdsCampaignTable', data.meta_ads_campaigns || []);
    }
  }
}

function _renderPlatformCampaignTable(sectionId, tableId, campaigns) {
  const section = document.getElementById(sectionId);
  const table = document.getElementById(tableId);
  if (!section || !table) return;
  if (campaigns.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  table.querySelector('thead').textContent = '';
  table.querySelector('tbody').textContent = '';

  const hr = document.createElement('tr');
  ['Campaign', 'Spend'].forEach(h => { const th = document.createElement('th'); th.textContent = h; hr.appendChild(th); });
  table.querySelector('thead').appendChild(hr);

  campaigns.forEach(c => {
    const tr = document.createElement('tr');
    const name = (c.dimension || '').replace(/^campaign:/, '');
    const tdName = document.createElement('td'); tdName.textContent = name;
    const tdSpend = document.createElement('td'); tdSpend.textContent = '$' + Math.round(c.value || 0).toLocaleString();
    tr.append(tdName, tdSpend);
    table.querySelector('tbody').appendChild(tr);
  });
}

/* ── Leads / Business Metrics Section ── */
function _renderLeadsSection(data) {
  const section = document.getElementById('sectionLeads');
  if (!section) return;
  const leads = data.sheets_leads || [];
  const calls = data.sheets_calls || [];
  const revenue = data.sheets_revenue || [];

  if (leads.length === 0 && calls.length === 0 && revenue.length === 0) {
    section.style.display = 'none'; return;
  }
  section.style.display = '';

  const s = data.summary || {};
  const kpis = [];
  if (s.total_leads?.current > 0) kpis.push({ label: 'Total Leads', key: 'total_leads', fmt: v => Math.round(v).toLocaleString(), unit: '%' });
  if (calls.length > 0) {
    const totalCalls = calls.reduce((sum, d) => sum + d.value, 0);
    kpis.push({ label: 'Total Calls', key: '_', fmt: v => Math.round(v).toLocaleString(), unit: '', _custom: totalCalls, _delta: 0 });
  }
  if (s.total_revenue?.current > 0) kpis.push({ label: 'Revenue', key: 'total_revenue', fmt: v => '$' + Math.round(v).toLocaleString(), unit: '%' });
  _buildKPICards(document.getElementById('sheetsKPIs'), kpis, s);

  if (leads.length > 0) {
    _getChart('chartLeads', {
      type: 'line',
      data: { labels: leads.map(d => d.date), datasets: [{ label: 'Leads', data: leads.map(d => d.value), borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.08)', fill: true, tension: 0.3 }] },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    });
  }
  if (revenue.length > 0) {
    _getChart('chartRevenue', {
      type: 'line',
      data: { labels: revenue.map(d => d.date), datasets: [{ label: 'Revenue', data: revenue.map(d => d.value), borderColor: '#0D9488', backgroundColor: 'rgba(13,148,136,0.08)', fill: true, tension: 0.3 }] },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => '$' + v.toLocaleString() } } } }
    });
  }
}

function _renderSyncStatus(status) {
  const bar = document.getElementById('syncStatusBar');
  if (!bar) return;
  bar.textContent = '';
  if (!status || Object.keys(status).length === 0) {
    bar.textContent = 'No sync data yet';
    bar.style.opacity = '0.5';
    return;
  }
  bar.style.opacity = '1';
  Object.entries(status).forEach(([src, s], i) => {
    if (i > 0) { const sep = document.createTextNode(' | '); bar.appendChild(sep); }
    const icon = document.createElement('span');
    icon.textContent = s.status === 'success' ? '\u2713 ' : '\u2717 ';
    icon.style.color = s.status === 'success' ? '#28A745' : '#DC3545';
    const label = document.createElement('strong'); label.textContent = src;
    const info = document.createTextNode(`: ${s.rows_synced} rows \u00B7 ${s.completed_at ? new Date(s.completed_at).toLocaleString() : 'never'}`);
    bar.append(icon, label, info);
  });
}

async function triggerReportingSync() {
  if (!_reportingClientId) { showToast('Select a client first'); return; }
  const btn = document.getElementById('btnSyncNow');
  if (btn) { btn.disabled = true; btn.textContent = 'Syncing...'; }
  try {
    const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/sync`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || 'Sync failed');
    } else {
      showToast('Sync started — data will appear shortly');
      setTimeout(() => _loadReportingData(), 5000);
    }
  } catch (e) { showToast('Sync error'); }
  if (btn) { btn.disabled = false; btn.textContent = 'Sync Now'; }
}

async function generateReportingShareLink() {
  if (!_reportingClientId) { showToast('Select a client first'); return; }
  try {
    const res = await fetch(`${API_BASE}/api/clients/${_reportingClientId}/dashboard-token`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
    });
    if (!res.ok) throw new Error('Failed');
    const data = await res.json();
    const fullUrl = `${window.location.origin}${data.url}`;
    const input = document.getElementById('shareLinkInput');
    const copyBtn = document.getElementById('btnCopyLink');
    if (input) input.value = fullUrl;
    if (copyBtn) copyBtn.style.display = '';
    showToast('Share link generated');
  } catch (e) { showToast('Error generating share link'); }
}

function copyShareLink() {
  const input = document.getElementById('shareLinkInput');
  if (!input || !input.value) return;
  navigator.clipboard.writeText(input.value).then(() => showToast('Link copied to clipboard'));
}

/* ── Client-facing standalone dashboard ── */
function initClientDashboard(token) {
  _isStandalone = true;
  document.body.classList.add('dashboard-standalone');
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) sidebar.style.display = 'none';
  const topBar = document.querySelector('.top-bar');
  if (topBar) topBar.style.display = 'none';
  const mainContent = document.querySelector('.main-content');
  if (mainContent) { mainContent.style.marginLeft = '0'; mainContent.style.paddingTop = '0'; }

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const reportingView = document.getElementById('view-reporting');
  if (reportingView) reportingView.classList.add('active');

  document.getElementById('dashboardStandaloneHeader').style.display = 'flex';
  document.getElementById('dashboardStandaloneFooter').style.display = '';
  const shareBar = document.querySelector('.share-link-bar');
  if (shareBar) shareBar.style.display = 'none';
  const syncBar = document.querySelector('.sync-status-bar');
  if (syncBar) syncBar.style.display = 'none';
  const repHeader = document.querySelector('.reporting-header');
  if (repHeader) repHeader.style.display = 'none';
  // Hide internal-only controls on standalone
  const btnAddTask = document.getElementById('btnAddTask');
  if (btnAddTask) btnAddTask.style.display = 'none';
  const btnUploadContent = document.getElementById('btnUploadContent');
  if (btnUploadContent) btnUploadContent.style.display = 'none';

  // Add date range toggle to standalone header
  const header = document.getElementById('dashboardStandaloneHeader');
  const rangeDiv = document.createElement('div');
  rangeDiv.className = 'date-range-toggle';
  rangeDiv.style.marginLeft = 'auto';
  rangeDiv.style.marginRight = '1rem';
  [30, 60, 90].forEach(d => {
    const btn = document.createElement('button');
    btn.className = 'range-btn' + (d === 30 ? ' active' : '');
    btn.dataset.days = d;
    btn.textContent = d + 'd';
    btn.onclick = () => {
      rangeDiv.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _reportingDays = d;
      _loadPublicDashboard(token);
    };
    rangeDiv.appendChild(btn);
  });
  header.appendChild(rangeDiv);

  initDashboardTabs();
  _loadPublicDashboard(token);
}

async function _loadPublicDashboard(token) {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/${token}?days=${_reportingDays}`);
    if (!res.ok) {
      document.getElementById('view-reporting').style.display = 'none';
      document.getElementById('dashboardError').style.display = 'flex';
      return;
    }
    const data = await res.json();
    document.getElementById('dashboardClientName').textContent = data.client_name || '';

    const hasData = data.search_clicks?.length > 0 || data.sessions?.length > 0;
    if (!hasData) {
      document.getElementById('reportingEmpty').style.display = '';
      return;
    }
    document.getElementById('reportingEmpty').style.display = 'none';
    _renderOrganicKPIs(data.summary);
    _renderSearchPerfChart(data.search_clicks, data.search_impressions);
    _renderTrafficSourcesChart(data.traffic_sources);
    _renderSessionsChart(data.sessions, data.users);
    _renderTopKeywordsChart(data.top_keywords);
    _renderRankingsTable(data.rankings);
    _renderTopPagesTable(data.top_pages);
    _renderPaidSection(data);
    _renderLeadsSection(data);
  } catch (e) {
    document.getElementById('view-reporting').style.display = 'none';
    document.getElementById('dashboardError').style.display = 'flex';
  }
}

/* ── INIT ── */
const dashboardMatch = window.location.pathname.match(/^\/dashboard\/([a-f0-9-]+)$/);
if (dashboardMatch) {
  initClientDashboard(dashboardMatch[1]);
} else {
  updateJobsBadge();
  showView('dashboard');
  startTerminal();
}
loadClients();
loadSchedules();
