# CLAUDE.md — AuditPilot

## What this agent does

AuditPilot is the **sales audit agent**. Given a prospect's domain,
service vertical, and location, it runs a 4-stage audit and produces a
branded "Sales Audit v2" document that Matthew uses to close new
clients.

## Entry point

- `POST /api/agents/audit` — SSE stream, `.docx` at the end

## The 4 stages (prompt-encoded)

1. **Site Analysis** (`site_analysis_system.md`) — Firecrawl crawl +
   LLM analysis. Produces JSON: company info, page inventory, content
   quality, technical basics, trust signals, conversion architecture.
2. **Ranking Reality Check** (`ranking_reality_system.md`) —
   DataForSEO SERP + ranked keywords. Produces the "RANKING FOR 0 OF 10
   KEYWORDS" headline stat that makes the pain visceral.
3. **Strategic Brain** (`strategic_brain_system.md`) — 8-dimension
   analysis NO automated tool can produce: content authenticity, robot-
   vs-human design, UX as ranking signal, trust depth, conversion
   architecture, content strategy coherence, competitive context, and
   the final verdict story.
4. **Synthesis** (`synthesis_system.md`) — assembles the 8-section
   Sales Audit v2 markdown document. Opus writes. `docx_generator.py`
   renders branded Word.

## Folder map

- `engine.py` — 4-stage orchestrator, SSE streaming
- `data_collector.py` — Firecrawl scrape + DataForSEO calls
- `prompts/` — one `.md` per stage
- `prompts/__init__.py` — loads .md files → named constants

## Cross-agent reach

`data_collector.firecrawl_scrape` is imported by QAPilot (the only
legitimate cross-agent import today). When `backend/integrations/
firecrawl.py` exists, both agents should import from there instead.

## Hard rules

- This is a SALES document, NOT a technical audit. Make the prospect
  feel invisible before explaining why. Fifth-grade reading level.
- NO em dashes, NO semicolons in body copy, NO "comprehensive" / "leverage".
  Enforced by the synthesis prompt — don't override in code.
- Copy-paste contamination (wrong city, wrong company name) is a
  CRITICAL finding. Surface it prominently.
- The 8 Strategic Brain dimensions are load-bearing sales narrative, not
  just a checklist. Changing them requires Matthew's sign-off.
