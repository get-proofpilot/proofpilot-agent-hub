"""
QAPilot Engine — 7-layer QA review orchestrator.

Takes a URL or raw content, scrapes the page if needed, and runs all 7 QA layers
through Claude. Produces a structured report with per-layer scores and actionable fixes.

Can run standalone (any URL) or be called from the AutoPilot pipeline as the QA stage.
"""

import json
import logging
import re
from typing import AsyncGenerator, Optional

import anthropic

from agents.qapilot.prompts import QA_SYSTEM, QA_CONTENT_ONLY

logger = logging.getLogger(__name__)


async def run_qa(
    client: anthropic.AsyncAnthropic,
    inputs: dict,
    strategy_context: str = "",
    client_name: str = "",
) -> AsyncGenerator[str, None]:
    """
    Run a full QAPilot 7-layer review.

    inputs:
        url: str — live page URL to review (optional if content provided)
        content: str — raw content to review (optional if url provided)
        keyword: str — target keyword for this page
        client_name: str — the client this page belongs to
        page_type: str — service-page, location-page, blog-post
        notes: str — task brief or additional context
    """
    url = inputs.get("url", "").strip()
    content = inputs.get("content", "").strip()
    keyword = inputs.get("keyword", "").strip()
    page_type = inputs.get("page_type", "service-page")
    notes = inputs.get("notes", "")

    if not url and not content:
        yield "\n\n**Error:** Either a URL or page content is required.\n"
        return

    if not keyword:
        yield "\n\n**Error:** Target keyword is required.\n"
        return

    yield f"# QAPilot Review\n\n"
    yield f"**Client:** {client_name}  \n"
    yield f"**Keyword:** {keyword}  \n"
    yield f"**Page Type:** {page_type}  \n"
    if url:
        yield f"**URL:** {url}  \n"
    yield "\n---\n\n"

    # ── Scrape page if URL provided ─────────────────────────────────
    page_html = ""
    page_markdown = ""
    page_meta = {}

    if url:
        yield "Scraping page for analysis...\n\n"
        try:
            from agents.auditpilot.data_collector import firecrawl_scrape
            page_data = await firecrawl_scrape(url, formats=["markdown", "rawHtml"])
            if page_data:
                page_markdown = page_data.get("markdown", "")
                page_html = page_data.get("rawHtml", "")[:20000]
                page_meta = page_data.get("metadata", {})
                yield f"Page scraped: {len(page_markdown)} chars content, {len(page_html)} chars HTML\n\n"
            else:
                yield "Warning: Could not scrape page. Running content-only review.\n\n"
        except Exception as e:
            yield f"Warning: Scrape failed ({e}). Running content-only review.\n\n"

    # Use provided content as fallback
    if not page_markdown and content:
        page_markdown = content

    if not page_markdown:
        yield "**Error:** No content available for review.\n"
        return

    # ── Build QA prompt ─────────────────────────────────────────────
    has_html = bool(page_html)
    system_prompt = QA_SYSTEM if has_html else QA_CONTENT_ONLY

    qa_prompt = f"""Review this page for {client_name}.

TARGET KEYWORD: {keyword}
PAGE TYPE: {page_type}
{f'URL: {url}' if url else ''}

{'METADATA:' if page_meta else ''}
{f'Title: {page_meta.get("title", "N/A")}' if page_meta else ''}
{f'Description: {page_meta.get("description", "N/A")}' if page_meta else ''}

PAGE CONTENT (Markdown):
{page_markdown[:12000]}

{f'RAW HTML (first 15K chars):' if has_html else ''}
{page_html[:15000] if has_html else ''}

{f'TASK BRIEF / NOTES: {notes}' if notes else ''}
{f'CLIENT CONTEXT: {strategy_context}' if strategy_context else ''}

Run all {7 if has_html else 5} applicable QA layers. Be specific about issues found.
For every issue, include the exact text or element that needs fixing."""

    # ── Run QA analysis ─────────────────────────────────────────────
    yield "Running 7-layer QA review...\n\n"

    qa_result = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=6000,
            system=system_prompt,
            messages=[{"role": "user", "content": qa_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                qa_result += text
    except Exception as e:
        yield f"\n**QA analysis error:** {e}\n"
        return

    # ── Parse and format the report ─────────────────────────────────
    yield "---\n\n## QA Report\n\n"

    # Try to parse JSON from the response
    report = _try_parse_json(qa_result)

    if report and "layers" in report:
        # Structured output — format nicely
        verdict = report.get("verdict", "UNKNOWN")
        score = report.get("overall_score", 0)

        verdict_emoji = {"PASS": "✅", "CONDITIONAL_PASS": "⚠️", "FAIL": "❌"}.get(verdict, "❓")
        yield f"### {verdict_emoji} Verdict: {verdict} — Score: {score}/100\n\n"

        for layer in report.get("layers", []):
            status = layer.get("status", "")
            s_emoji = {"PASS": "✅", "CONDITIONAL_PASS": "⚠️", "FAIL": "❌", "SKIPPED": "⏭️"}.get(status, "")
            yield f"**Layer {layer.get('layer', '?')}: {layer.get('name', '')}** {s_emoji} "
            if layer.get("score") is not None:
                yield f"({layer['score']}/100)\n"
            else:
                yield "(skipped)\n"

            for issue in layer.get("critical_issues", []):
                yield f"  - 🔴 CRITICAL: {issue}\n"
            for warning in layer.get("warnings", []):
                yield f"  - 🟡 {warning}\n"
            for note in layer.get("notes", []):
                yield f"  - {note}\n"
            yield "\n"

        if report.get("top_3_fixes"):
            yield "### Top 3 Fixes\n\n"
            for i, fix in enumerate(report["top_3_fixes"], 1):
                yield f"{i}. {fix}\n"
            yield "\n"

        if report.get("summary"):
            yield f"### Summary\n\n{report['summary']}\n"
    else:
        # Couldn't parse JSON — output the raw analysis
        yield qa_result


def _try_parse_json(text: str) -> Optional[dict]:
    """Try to extract JSON from Claude's response (may be wrapped in markdown)."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the outermost { ... }
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None
