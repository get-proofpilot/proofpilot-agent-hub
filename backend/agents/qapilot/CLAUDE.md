# CLAUDE.md — QAPilot

## What this agent does

QAPilot is ProofPilot's **internal QA specialist**. It reviews SEO
deliverables (service pages, location pages, blog posts) created by the
team or by AutoPilot before they go to the client. It runs a 7-layer
review and produces a structured JSON report with a PASS / CONDITIONAL
PASS / FAIL verdict.

QAPilot is the quality gate between "work done" and "manager approved."

## Entry point

- `POST /api/agents/qa` — SSE stream, `.docx` at the end

## The 7 layers (prompt-encoded, do not drift)

1. **Information Accuracy** (2x weight) — NAP, copy-paste errors, placeholders
2. **On-Page SEO** (2x weight) — headings, meta tags, URL, alt, internal links, schema
3. **Content Quality** — word count, uniqueness, local signals, FAQs, CTAs
4. **AI Detection & Voice** — tell words, em dashes, semicolons, sentence variety
5. **Visual / UX** — hierarchy, image quality, CTA prominence, mobile
6. **Strategy Alignment** — right keyword, no cannibalization, competitive
7. **Cross-Page Consistency** — NAP, branding, internal linking

Scoring: each layer 0-100; overall is weighted avg (Layers 1-2 double).
Any critical issue in Layer 1 = automatic FAIL.

## Folder map

- `engine.py` — orchestration (calls Claude, formats report)
- `prompts/qa_system.md` — full 7-layer prompt
- `prompts/qa_content_only.md` — fallback when no HTML is available
- `prompts/__init__.py` — loads .md files → `QA_SYSTEM`, `QA_CONTENT_ONLY`

## Hard rules

- Layer definitions live in prompts, NOT in Python. Updating a layer =
  editing a `.md` file. Do NOT re-encode layer rules in code.
- AI tell word list is also in the prompt — add new words there, not in
  engine.py.
- QAPilot talks to Firecrawl to scrape live URLs when `url` is provided.
  The scraper lives in `agents.auditpilot.data_collector` — this is the
  ONE legitimate cross-agent import (it's a shared utility by history).
  When `backend/integrations/firecrawl.py` exists, move the import.
