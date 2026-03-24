"""
ProofPilot Agency Hub — API Backend
FastAPI + SSE streaming → Claude API
Deploy on Railway: set root directory to /backend, add ANTHROPIC_API_KEY env var
"""

import os
import json
import uuid
import asyncio
from pathlib import Path

import yaml
import anthropic
from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional

from workflows.home_service_content import run_home_service_content
from workflows.website_seo_audit import run_website_seo_audit
from workflows.prospect_audit import run_prospect_audit
from workflows.keyword_gap import run_keyword_gap
from workflows.seo_blog_post import run_seo_blog_post
from workflows.service_page import run_service_page
from workflows.location_page import run_location_page
from workflows.programmatic_content import run_programmatic_content
from workflows.ai_search_report import run_ai_search_report
from workflows.backlink_audit import run_backlink_audit
from workflows.onpage_audit import run_onpage_audit
from workflows.seo_research_agent import run_seo_research_agent
from workflows.competitor_intel import run_competitor_intel
from workflows.monthly_report import run_monthly_report
from workflows.proposals import run_proposals
from workflows.google_ads_copy import run_google_ads_copy
from workflows.schema_generator import run_schema_generator
from workflows.content_strategy import run_content_strategy
from workflows.pnl_statement import run_pnl_statement
from workflows.property_mgmt_strategy import run_property_mgmt_strategy
from workflows.page_design import run_page_design
from workflows.geo_content_audit import run_geo_content_audit
from workflows.seo_content_audit import run_seo_content_audit
from workflows.technical_seo_review import run_technical_seo_review
from workflows.programmatic_seo_strategy import run_programmatic_seo_strategy
from workflows.competitor_seo_analysis import run_competitor_seo_analysis
from utils.docx_generator import generate_docx
from utils.db import (
    init_db, save_job, update_docx_path, update_job_content,
    get_job as db_get_job, get_all_jobs,
    create_client, get_client as db_get_client, get_all_clients,
    update_client, delete_client, approve_job, unapprove_job,
)
from utils.metrics_db import (
    get_dashboard_summary, get_metric_timeseries, get_metric_breakdown,
    get_keyword_rankings, get_sync_status,
    create_dashboard_token, get_client_by_token, revoke_dashboard_token,
)
from utils.gsc_sync import sync_gsc_data, sync_gsc_keywords, sync_gsc_pages
from utils.ga4_sync import sync_ga4_data, sync_ga4_sources, sync_ga4_pages
from utils.google_ads_sync import sync_google_ads_data, sync_google_ads_campaigns
from utils.meta_ads_sync import sync_meta_ads_data, sync_meta_ads_campaigns
from utils.sheets_sync import sync_sheets_data
from utils.content_db import get_content_roadmap, get_content_stats, bulk_insert_content, clear_content_roadmap
from utils.tasks_db import get_client_tasks, create_client_task, update_task_status, sync_tasks_from_jobs

# ── App setup ─────────────────────────────────────────────
app = FastAPI(title="ProofPilot Agency Hub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Initialise SQLite on startup ───────────────────────────
init_db()

WORKFLOW_TITLES = {
    "home-service-content":      "Home Service SEO Content",
    "seo-blog-post":             "SEO Blog Post",
    "service-page":              "Service Page",
    "location-page":             "Location Page",
    "website-seo-audit":         "Website & SEO Audit",
    "prospect-audit":            "Prospect SEO Market Analysis",
    "keyword-gap":               "Keyword Gap Analysis",
    "programmatic-content":      "Programmatic Content Agent",
    "ai-search-report":          "AI Search Visibility Report",
    "backlink-audit":            "Backlink Audit",
    "onpage-audit":              "On-Page Technical Audit",
    "seo-research":              "SEO Research & Content Strategy",
    "competitor-intel":          "Competitor Intelligence Report",
    "monthly-report":            "Monthly Client Report",
    "proposals":                 "Client Proposals",
    "google-ads-copy":           "Google Ads Copy",
    "schema-generator":          "Schema Generator",
    "content-strategy":          "Content Strategy",
    "pnl-statement":             "P&L Statement",
    "property-mgmt-strategy":    "Property Mgmt Strategy",
    "page-design":               "Page Design Agent",
    "geo-content-audit":         "GEO Content Citability Audit",
    "seo-content-audit":         "SEO Content Audit",
    "technical-seo-review":      "Technical SEO Review",
    "programmatic-seo-strategy": "Programmatic SEO Strategy",
    "competitor-seo-analysis":   "Competitor SEO Analysis",
}


# ── Request / response schemas ─────────────────────────────
class WorkflowRequest(BaseModel):
    workflow_id: str
    client_id: int
    client_name: str
    inputs: dict
    strategy_context: Optional[str] = ""


class EditDocumentRequest(BaseModel):
    job_id: str
    instruction: str
    current_content: str


class DiscoverCitiesRequest(BaseModel):
    city: str
    radius: int = 15


class ClientCreate(BaseModel):
    name: str
    domain: str = ""
    service: str = ""
    location: str = ""
    plan: str = "Starter"
    monthly_revenue: str = ""
    avg_job_value: str = ""
    notes: str = ""
    strategy_context: str = ""


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    service: Optional[str] = None
    location: Optional[str] = None
    plan: Optional[str] = None
    monthly_revenue: Optional[str] = None
    avg_job_value: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    strategy_context: Optional[str] = None
    gsc_property: Optional[str] = None
    ga4_property_id: Optional[str] = None
    google_ads_customer_id: Optional[str] = None
    meta_ad_account_id: Optional[str] = None
    sheets_config: Optional[str] = None


class DashboardTokenRequest(BaseModel):
    expires_days: Optional[int] = None


# ── Client routes ──────────────────────────────────────────

@app.get("/api/clients")
async def list_clients():
    """Return all active/inactive clients (excludes soft-deleted)."""
    clients = await asyncio.to_thread(get_all_clients)
    return {"clients": clients}


@app.post("/api/clients", status_code=201)
async def add_client(body: ClientCreate):
    """Create a new client and return the full row."""
    client = await asyncio.to_thread(create_client, body.model_dump())
    return client


@app.get("/api/clients/{client_id}")
async def get_client_detail(client_id: int):
    client = await asyncio.to_thread(db_get_client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.patch("/api/clients/{client_id}")
async def patch_client(client_id: int, body: ClientUpdate):
    """Partial update — only supplied non-null fields are written."""
    updated = await asyncio.to_thread(
        update_client, client_id, body.model_dump(exclude_none=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated


@app.delete("/api/clients/{client_id}", status_code=204)
async def remove_client(client_id: int):
    """Soft-delete: marks status='deleted'."""
    ok = await asyncio.to_thread(delete_client, client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Client not found")


# ── Job approval routes ────────────────────────────────────

@app.post("/api/jobs/{job_id}/approve")
async def approve_content(job_id: str):
    ok = await asyncio.to_thread(approve_job, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"approved": True}


@app.delete("/api/jobs/{job_id}/approve")
async def unapprove_content(job_id: str):
    ok = await asyncio.to_thread(unapprove_job, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"approved": False}


# ── Routes ────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "ProofPilot Agency Hub API", "version": "v22"}


@app.post("/api/discover-cities")
async def discover_cities(req: DiscoverCitiesRequest):
    """Use Claude Haiku to find nearby cities for programmatic content."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    city_name = req.city.split(",")[0].strip()
    client = anthropic.AsyncAnthropic(api_key=api_key)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"List all real, incorporated cities and towns within approximately "
                f"{req.radius} miles of {req.city}. Do NOT include {city_name} itself. "
                f"Format each as 'City, ST' (2-letter state code). One per line. "
                f"No numbering, no bullets, no other text. Just the city list. "
                f"Maximum 50 cities. If fewer than 50 exist within that radius, list all of them."
            ),
        }],
    )

    import re
    text = response.content[0].text.strip()
    cities = []
    for line in text.split("\n"):
        line = line.strip().lstrip("- ").lstrip("• ").lstrip("* ")
        line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
        if line and "," in line:
            cities.append(line)

    return {"cities": cities[:50]}


@app.post("/api/run-workflow")
async def run_workflow(req: WorkflowRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    if req.workflow_id not in WORKFLOW_TITLES:
        raise HTTPException(status_code=400, detail=f"Unknown workflow: {req.workflow_id}")

    job_id = str(uuid.uuid4())[:8]
    client = anthropic.AsyncAnthropic(api_key=api_key)

    async def event_stream():
        full_content: list[str] = []

        try:
            # ── Route to the correct workflow ──
            if req.workflow_id == "home-service-content":
                generator = run_home_service_content(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "website-seo-audit":
                sa_key = os.environ.get("SEARCHATLAS_API_KEY")
                if not sa_key:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'SEARCHATLAS_API_KEY is not configured on the server.'})}\n\n"
                    return
                generator = run_website_seo_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "prospect-audit":
                sa_key = os.environ.get("SEARCHATLAS_API_KEY")
                if not sa_key:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'SEARCHATLAS_API_KEY is not configured on the server.'})}\n\n"
                    return
                generator = run_prospect_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "keyword-gap":
                generator = run_keyword_gap(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-blog-post":
                generator = run_seo_blog_post(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "service-page":
                generator = run_service_page(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "location-page":
                generator = run_location_page(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "programmatic-content":
                generator = run_programmatic_content(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "ai-search-report":
                generator = run_ai_search_report(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "backlink-audit":
                generator = run_backlink_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "onpage-audit":
                generator = run_onpage_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-research":
                generator = run_seo_research_agent(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "competitor-intel":
                generator = run_competitor_intel(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "monthly-report":
                generator = run_monthly_report(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "proposals":
                generator = run_proposals(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "google-ads-copy":
                generator = run_google_ads_copy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "schema-generator":
                generator = run_schema_generator(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "content-strategy":
                generator = run_content_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "pnl-statement":
                generator = run_pnl_statement(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "property-mgmt-strategy":
                generator = run_property_mgmt_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "page-design":
                generator = run_page_design(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "geo-content-audit":
                generator = run_geo_content_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-content-audit":
                generator = run_seo_content_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "technical-seo-review":
                generator = run_technical_seo_review(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "programmatic-seo-strategy":
                generator = run_programmatic_seo_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            elif req.workflow_id == "competitor-seo-analysis":
                generator = run_competitor_seo_analysis(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=req.strategy_context or "",
                    client_name=req.client_name,
                )
            else:
                msg = f'Workflow "{req.workflow_id}" is not yet wired up.'
                yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"
                return

            # ── Stream tokens to the browser ──
            async for token in generator:
                full_content.append(token)
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            # ── Stream complete — persist job + generate .docx ──
            content_str = "".join(full_content)
            job_data = {
                "content": content_str,
                "client_name": req.client_name,
                "workflow_title": WORKFLOW_TITLES[req.workflow_id],
                "workflow_id": req.workflow_id,
                "inputs": req.inputs,
                "client_id": req.client_id,
            }

            # Persist to SQLite and generate docx (both run off the event loop)
            await asyncio.to_thread(save_job, job_id, job_data)
            if req.workflow_id != "page-design":
                docx_path = await asyncio.to_thread(generate_docx, job_id, job_data)
                await asyncio.to_thread(update_docx_path, job_id, str(docx_path))

            yield f"data: {json.dumps({'type': 'done', 'job_id': job_id, 'client_name': req.client_name, 'workflow_title': WORKFLOW_TITLES[req.workflow_id], 'workflow_id': req.workflow_id})}\n\n"

        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid Anthropic API key.'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Rate limited — please wait a moment and try again.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # prevents nginx from buffering SSE
            "Connection": "keep-alive",
        },
    )


@app.get("/api/preview/{job_id}")
def preview_html(job_id: str):
    """Serve page-design HTML output as a rendered page."""
    job = db_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("workflow_id") != "page-design":
        raise HTTPException(status_code=400, detail="Preview only available for page-design workflows")
    content = job.get("content", "")
    if not content:
        raise HTTPException(status_code=404, detail="No content available")
    return HTMLResponse(content=content)


@app.get("/api/download/{job_id}")
def download_docx(job_id: str):
    job = db_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.get("docx_path"):
        raise HTTPException(status_code=404, detail="Document not ready yet")

    docx_path = Path(job["docx_path"])
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="Document file missing — server may have restarted")

    client_slug = job["client_name"].replace(" ", "_")
    wf_slug = job["workflow_id"].replace("-", "_")
    filename = f"ProofPilot_{client_slug}_{wf_slug}_{job_id}.docx"

    return FileResponse(
        path=docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


def _strip_markdown(text: str, max_len: int = 200) -> str:
    """Strip markdown or HTML formatting for clean plain-text previews."""
    import re
    t = text.strip()
    # HTML detection — strip tags for preview
    if t.startswith('<!DOCTYPE') or t.startswith('<html') or t.startswith('<HTML'):
        t = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', t, flags=re.IGNORECASE)
        t = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', t, flags=re.IGNORECASE)
        t = re.sub(r'<!--[\s\S]*?-->', '', t)
        t = re.sub(r'<[^>]+>', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t[:max_len] + "..." if len(t) > max_len else t
    t = text
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)  # headings
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)                 # bold
    t = re.sub(r'\*(.+?)\*', r'\1', t)                      # italic
    t = re.sub(r'__(.+?)__', r'\1', t)                      # bold alt
    t = re.sub(r'_(.+?)_', r'\1', t)                        # italic alt
    t = re.sub(r'`(.+?)`', r'\1', t)                        # inline code
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)          # links
    t = re.sub(r'^[-*+]\s+', '', t, flags=re.MULTILINE)     # list markers
    t = re.sub(r'^\d+\.\s+', '', t, flags=re.MULTILINE)     # numbered lists
    t = re.sub(r'^>\s*', '', t, flags=re.MULTILINE)          # blockquotes
    t = re.sub(r'---+|===+|\*\*\*+', '', t)                 # hr
    t = re.sub(r'\|', ' ', t)                                # table pipes
    t = re.sub(r'\n{2,}', ' ', t)                            # collapse newlines
    t = re.sub(r'\s+', ' ', t).strip()                       # normalize spaces
    return t[:max_len] + "..." if len(t) > max_len else t


@app.get("/api/content")
def list_content():
    """Return all completed jobs as content library items."""
    all_jobs = get_all_jobs()
    items = []
    for job in all_jobs:
        content_str = job.get("content", "")
        if not content_str:
            continue
        items.append({
            "job_id": job["job_id"],
            "client_name": job.get("client_name", ""),
            "workflow_title": job.get("workflow_title", ""),
            "workflow_id": job.get("workflow_id", ""),
            "has_docx": bool(job.get("docx_path")),
            "content_preview": _strip_markdown(content_str, 200),
            "created_at": job.get("created_at", ""),
            "approved": bool(job.get("approved", 0)),
            "approved_at": job.get("approved_at"),
        })
    return {"items": items}  # already sorted newest-first by get_all_jobs()


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str):
    job = db_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    content = job.get("content", "")
    return {
        "job_id": job_id,
        "client_name": job["client_name"],
        "workflow_title": job["workflow_title"],
        "workflow_id": job.get("workflow_id", ""),
        "has_docx": bool(job.get("docx_path")),
        "content": content,
        "content_preview": _strip_markdown(content, 300),
        "approved": bool(job.get("approved", 0)),
        "approved_at": job.get("approved_at"),
    }


# ── Document editing (conversational) ─────────────────────────────

EDIT_SYSTEM_PROMPT = """You are a document editor for a digital marketing agency called ProofPilot.

When given a document and an edit instruction, return the COMPLETE updated document with the requested changes applied.

Rules:
- Preserve ALL existing formatting (markdown headings, bold, bullets, tables, etc.)
- Only change what the instruction asks for — leave everything else intact
- Maintain the same professional tone and style throughout
- Do NOT include any preamble, explanation, or commentary — return ONLY the document content
- Start your response immediately with the document content
- If the document is HTML, return valid HTML. If markdown, return markdown. Never change the format."""


@app.post("/api/edit-document")
async def edit_document(req: EditDocumentRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    async def event_stream():
        edited_content: list[str] = []

        try:
            user_prompt = (
                f"Here is the current document:\n\n"
                f"<document>\n{req.current_content}\n</document>\n\n"
                f"Edit instruction: {req.instruction}\n\n"
                f"Return the COMPLETE updated document with the requested changes applied."
            )

            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=EDIT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    edited_content.append(text)
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # Save the edited content back to the job
        new_content = "".join(edited_content)
        try:
            job = db_get_job(req.job_id)
            if job:
                await asyncio.to_thread(update_job_content, req.job_id, new_content)
                # Regenerate the docx with updated content (skip for HTML workflows)
                if job.get("workflow_id") != "page-design":
                    job_data = {
                        "client_name": job["client_name"],
                        "workflow_title": job["workflow_title"],
                        "workflow_id": job.get("workflow_id", ""),
                        "inputs": job["inputs"],
                        "content": new_content,
                        "created_at": job.get("created_at", ""),
                        "client_id": job.get("client_id", 0),
                    }
                    docx_path = await asyncio.to_thread(generate_docx, req.job_id, job_data)
                    await asyncio.to_thread(update_docx_path, req.job_id, str(docx_path))
        except Exception:
            pass  # Non-fatal — the streamed edit still worked

        yield f"data: {json.dumps({'type': 'done', 'job_id': req.job_id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Dashboard / Reporting routes ──────────────────────────────────

async def _run_sync(client_id: int, client_data: dict):
    """Run all syncs for a client in background threads."""
    domain = (client_data.get("gsc_property") or "").replace("sc-domain:", "")
    ga4_id = client_data.get("ga4_property_id") or ""
    results = {}
    if domain:
        results["gsc"] = await asyncio.to_thread(sync_gsc_data, client_id, domain)
        results["gsc_keywords"] = await asyncio.to_thread(sync_gsc_keywords, client_id, domain)
        results["gsc_pages"] = await asyncio.to_thread(sync_gsc_pages, client_id, domain)
    if ga4_id:
        results["ga4"] = await asyncio.to_thread(sync_ga4_data, client_id, ga4_id)
        results["ga4_sources"] = await asyncio.to_thread(sync_ga4_sources, client_id, ga4_id)
        results["ga4_pages"] = await asyncio.to_thread(sync_ga4_pages, client_id, ga4_id)
    # Google Ads sync
    gads_id = (client_data.get("google_ads_customer_id") or "").strip()
    if gads_id:
        results["google_ads"] = await asyncio.to_thread(sync_google_ads_data, client_id, gads_id)
        results["google_ads_campaigns"] = await asyncio.to_thread(sync_google_ads_campaigns, client_id, gads_id)
    # Meta Ads sync
    meta_id = (client_data.get("meta_ad_account_id") or "").strip()
    if meta_id:
        results["meta_ads"] = await asyncio.to_thread(sync_meta_ads_data, client_id, meta_id)
        results["meta_ads_campaigns"] = await asyncio.to_thread(sync_meta_ads_campaigns, client_id, meta_id)
    # Google Sheets sync
    sheets_config_str = (client_data.get("sheets_config") or "").strip()
    if sheets_config_str:
        import json as _json
        try:
            sheets_cfg = _json.loads(sheets_config_str)
            results["sheets"] = await asyncio.to_thread(sync_sheets_data, client_id, sheets_cfg)
        except _json.JSONDecodeError:
            pass
    return results


def _build_tab_data(client_id: int, tab: str, days: int = 30, month: str = "") -> dict:
    """Build data for a single dashboard tab."""
    if tab == "overview":
        return {
            "summary": get_dashboard_summary(client_id, days),
            "search_clicks": get_metric_timeseries(client_id, "gsc", "clicks", "total", days),
            "sessions": get_metric_timeseries(client_id, "ga4", "sessions", "total", days),
            "google_ads_spend": get_metric_timeseries(client_id, "google_ads", "cost", "total", days),
            "meta_ads_spend": get_metric_timeseries(client_id, "meta_ads", "spend", "total", days),
            "google_ads_conversions": get_metric_timeseries(client_id, "google_ads", "conversions", "total", days),
            "meta_ads_conversions": get_metric_timeseries(client_id, "meta_ads", "conversions", "total", days),
            "sheets_leads": get_metric_timeseries(client_id, "sheets", "leads", "total", days),
            "sheets_calls": get_metric_timeseries(client_id, "sheets", "calls", "total", days),
            "sheets_revenue": get_metric_timeseries(client_id, "sheets", "revenue", "total", days),
            "sync_status": get_sync_status(client_id),
        }
    elif tab == "seo":
        return {
            "summary": get_dashboard_summary(client_id, days),
            "search_clicks": get_metric_timeseries(client_id, "gsc", "clicks", "total", days),
            "search_impressions": get_metric_timeseries(client_id, "gsc", "impressions", "total", days),
            "sessions": get_metric_timeseries(client_id, "ga4", "sessions", "total", days),
            "users": get_metric_timeseries(client_id, "ga4", "totalUsers", "total", days),
            "traffic_sources": get_metric_breakdown(client_id, "ga4", "sessions", days),
            "top_keywords": get_metric_breakdown(client_id, "gsc", "clicks", days, limit=10),
            "top_pages": get_metric_breakdown(client_id, "gsc", "clicks", days, limit=20),
            "rankings": get_keyword_rankings(client_id, days),
            "sync_status": get_sync_status(client_id),
        }
    elif tab == "paid":
        return {
            "summary": get_dashboard_summary(client_id, days),
            "google_ads_spend": get_metric_timeseries(client_id, "google_ads", "cost", "total", days),
            "meta_ads_spend": get_metric_timeseries(client_id, "meta_ads", "spend", "total", days),
            "google_ads_conversions": get_metric_timeseries(client_id, "google_ads", "conversions", "total", days),
            "meta_ads_conversions": get_metric_timeseries(client_id, "meta_ads", "conversions", "total", days),
            "google_ads_campaigns": get_metric_breakdown(client_id, "google_ads", "cost", days, 10),
            "meta_ads_campaigns": get_metric_breakdown(client_id, "meta_ads", "spend", days, 10),
        }
    elif tab == "leads":
        return {
            "summary": get_dashboard_summary(client_id, days),
            "sheets_leads": get_metric_timeseries(client_id, "sheets", "leads", "total", days),
            "sheets_calls": get_metric_timeseries(client_id, "sheets", "calls", "total", days),
            "sheets_revenue": get_metric_timeseries(client_id, "sheets", "revenue", "total", days),
        }
    elif tab == "content":
        return {
            "roadmap": get_content_roadmap(client_id),
            "stats": get_content_stats(client_id),
        }
    elif tab == "tasks":
        if not month:
            from datetime import datetime as _dt
            month = _dt.now().strftime("%Y-%m")
        sync_tasks_from_jobs(client_id, month)
        return {
            "tasks": get_client_tasks(client_id, month),
            "month": month,
        }
    return _build_dashboard_data(client_id, days)


def _build_dashboard_data(client_id: int, days: int = 30) -> dict:
    """Build the full dashboard data bundle."""
    return {
        "summary": get_dashboard_summary(client_id, days),
        "search_clicks": get_metric_timeseries(client_id, "gsc", "clicks", "total", days),
        "search_impressions": get_metric_timeseries(client_id, "gsc", "impressions", "total", days),
        "search_ctr": get_metric_timeseries(client_id, "gsc", "ctr", "total", days),
        "search_position": get_metric_timeseries(client_id, "gsc", "position", "total", days),
        "sessions": get_metric_timeseries(client_id, "ga4", "sessions", "total", days),
        "users": get_metric_timeseries(client_id, "ga4", "totalUsers", "total", days),
        "traffic_sources": get_metric_breakdown(client_id, "ga4", "sessions", days),
        "top_keywords": get_metric_breakdown(client_id, "gsc", "clicks", days, limit=10),
        "top_pages": get_metric_breakdown(client_id, "gsc", "clicks", days, limit=20),
        "rankings": get_keyword_rankings(client_id, days),
        "sync_status": get_sync_status(client_id),
        # Ads data
        "google_ads_spend": get_metric_timeseries(client_id, "google_ads", "cost", "total", days),
        "meta_ads_spend": get_metric_timeseries(client_id, "meta_ads", "spend", "total", days),
        "google_ads_conversions": get_metric_timeseries(client_id, "google_ads", "conversions", "total", days),
        "meta_ads_conversions": get_metric_timeseries(client_id, "meta_ads", "conversions", "total", days),
        "google_ads_campaigns": get_metric_breakdown(client_id, "google_ads", "cost", days, 10),
        "meta_ads_campaigns": get_metric_breakdown(client_id, "meta_ads", "spend", days, 10),
        # Sheets metrics
        "sheets_leads": get_metric_timeseries(client_id, "sheets", "leads", "total", days),
        "sheets_calls": get_metric_timeseries(client_id, "sheets", "calls", "total", days),
        "sheets_revenue": get_metric_timeseries(client_id, "sheets", "revenue", "total", days),
    }


@app.get("/api/clients/{client_id}/dashboard")
async def get_client_dashboard(client_id: int, days: int = 30, tab: str = "", month: str = ""):
    if tab:
        data = await asyncio.to_thread(_build_tab_data, client_id, tab, days, month)
    else:
        data = await asyncio.to_thread(_build_dashboard_data, client_id, days)
    return data


@app.get("/api/clients/{client_id}/dashboard/traffic")
async def get_client_traffic(client_id: int, days: int = 30):
    return {
        "sessions": await asyncio.to_thread(get_metric_timeseries, client_id, "ga4", "sessions", "total", days),
        "users": await asyncio.to_thread(get_metric_timeseries, client_id, "ga4", "totalUsers", "total", days),
        "sources": await asyncio.to_thread(get_metric_breakdown, client_id, "ga4", "sessions", days),
    }


@app.get("/api/clients/{client_id}/dashboard/rankings")
async def get_client_rankings(client_id: int, days: int = 30):
    rankings = await asyncio.to_thread(get_keyword_rankings, client_id, days)
    return {"rankings": rankings}


@app.get("/api/clients/{client_id}/dashboard/search")
async def get_client_search(client_id: int, days: int = 30):
    return {
        "clicks": await asyncio.to_thread(get_metric_timeseries, client_id, "gsc", "clicks", "total", days),
        "impressions": await asyncio.to_thread(get_metric_timeseries, client_id, "gsc", "impressions", "total", days),
        "ctr": await asyncio.to_thread(get_metric_timeseries, client_id, "gsc", "ctr", "total", days),
        "position": await asyncio.to_thread(get_metric_timeseries, client_id, "gsc", "position", "total", days),
    }


@app.post("/api/clients/{client_id}/sync")
async def trigger_sync(client_id: int):
    client_data = await asyncio.to_thread(db_get_client, client_id)
    if not client_data:
        raise HTTPException(status_code=404, detail="Client not found")
    gsc = (client_data.get("gsc_property") or "").strip()
    ga4 = (client_data.get("ga4_property_id") or "").strip()
    gads = (client_data.get("google_ads_customer_id") or "").strip()
    meta = (client_data.get("meta_ad_account_id") or "").strip()
    sheets = (client_data.get("sheets_config") or "").strip()
    if not any([gsc, ga4, gads, meta, sheets]):
        raise HTTPException(status_code=400, detail="No data sources configured for this client")
    asyncio.create_task(_run_sync(client_id, client_data))
    return {"status": "syncing", "message": "Sync started"}


@app.get("/api/clients/{client_id}/sync/status")
async def get_client_sync_status(client_id: int):
    status = await asyncio.to_thread(get_sync_status, client_id)
    return {"sync_status": status}


@app.post("/api/clients/{client_id}/dashboard-token")
async def create_client_dashboard_token(client_id: int, body: DashboardTokenRequest):
    client_data = await asyncio.to_thread(db_get_client, client_id)
    if not client_data:
        raise HTTPException(status_code=404, detail="Client not found")
    token = await asyncio.to_thread(create_dashboard_token, client_id, body.expires_days)
    return {"token": token, "url": f"/dashboard/{token}"}


@app.delete("/api/clients/{client_id}/dashboard-token/{token}")
async def revoke_client_dashboard_token(client_id: int, token: str):
    ok = await asyncio.to_thread(revoke_dashboard_token, token)
    if not ok:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


@app.get("/api/dashboard/{token}")
async def get_public_dashboard(token: str, days: int = 30):
    client_id = await asyncio.to_thread(get_client_by_token, token)
    if client_id is None:
        raise HTTPException(status_code=404, detail="Dashboard not found or link expired")
    client_data = await asyncio.to_thread(db_get_client, client_id)
    data = await asyncio.to_thread(_build_dashboard_data, client_id, days)
    data["client_name"] = client_data["name"] if client_data else "Unknown"
    return data


# ── Content Roadmap endpoints ─────────────────────────────────────

@app.get("/api/clients/{client_id}/content-roadmap")
async def list_content_roadmap(client_id: int, month: str = "", page_type: str = "", status: str = ""):
    items = await asyncio.to_thread(get_content_roadmap, client_id, month or None, page_type or None, status or None)
    stats = await asyncio.to_thread(get_content_stats, client_id)
    return {"items": items, "stats": stats}


@app.post("/api/clients/{client_id}/content-roadmap/upload")
async def upload_content_roadmap(client_id: int, file: UploadFile):
    import csv
    import io
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="CSV must have headers and at least one data row")
    headers = rows[0]
    sample_rows = rows[1:min(4, len(rows))]

    # Use Claude Haiku to propose column mapping
    client = anthropic.Anthropic()
    mapping_prompt = f"""You are a data mapping assistant. Given these CSV headers and sample rows, propose a mapping to these target fields:
- month (e.g. "2026-03", "March 2026", etc.)
- title (content title or page name)
- page_type (blog, service page, location page, landing page, etc.)
- content_silo (topic cluster or category)
- status (planned, assigned, written, published)
- keyword (target keyword)
- volume (search volume, integer)
- difficulty (keyword difficulty, integer 0-100)

CSV Headers: {headers}
Sample rows: {sample_rows}

Return ONLY a JSON object mapping target field names to CSV column indices (0-based). If a field has no match, set it to -1.
Example: {{"month": 0, "title": 1, "page_type": 2, "content_silo": -1, "status": 3, "keyword": 4, "volume": 5, "difficulty": 6}}"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": mapping_prompt}]
    )
    mapping_text = resp.content[0].text.strip()
    # Parse JSON from response
    import re
    json_match = re.search(r'\{[^}]+\}', mapping_text)
    if not json_match:
        raise HTTPException(status_code=500, detail="AI could not determine column mapping")
    proposed_mapping = json.loads(json_match.group())

    return {
        "headers": headers,
        "sample_rows": sample_rows,
        "proposed_mapping": proposed_mapping,
        "total_rows": len(rows) - 1,
        "csv_text": text,
    }


class ConfirmMappingRequest(BaseModel):
    mapping: dict
    csv_text: str


@app.post("/api/clients/{client_id}/content-roadmap/confirm-mapping")
async def confirm_content_mapping(client_id: int, body: ConfirmMappingRequest):
    import csv
    import io
    reader = csv.reader(io.StringIO(body.csv_text))
    rows = list(reader)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="No data rows")
    headers = rows[0]
    data_rows = rows[1:]
    mapping = body.mapping
    items = []
    for row in data_rows:
        item = {}
        for field, col_idx in mapping.items():
            idx = int(col_idx)
            if idx >= 0 and idx < len(row):
                item[field] = row[idx]
            else:
                item[field] = ""
        items.append(item)
    count = await asyncio.to_thread(bulk_insert_content, client_id, items, "csv")
    return {"imported": count}


# ── Tasks endpoints ───────────────────────────────────────────────

@app.get("/api/clients/{client_id}/tasks")
async def list_client_tasks(client_id: int, month: str = ""):
    if not month:
        from datetime import datetime as _dt
        month = _dt.now().strftime("%Y-%m")
    await asyncio.to_thread(sync_tasks_from_jobs, client_id, month)
    tasks = await asyncio.to_thread(get_client_tasks, client_id, month)
    return {"tasks": tasks, "month": month}


class CreateTaskRequest(BaseModel):
    title: str
    category: str = "other"
    month: str = ""


@app.post("/api/clients/{client_id}/tasks")
async def create_task(client_id: int, body: CreateTaskRequest):
    if not body.month:
        from datetime import datetime as _dt
        body.month = _dt.now().strftime("%Y-%m")
    task_id = await asyncio.to_thread(create_client_task, client_id, body.title, body.category, body.month)
    return {"id": task_id, "status": "created"}


class UpdateTaskRequest(BaseModel):
    status: str


@app.patch("/api/clients/{client_id}/tasks/{task_id}")
async def update_task(client_id: int, task_id: int, body: UpdateTaskRequest):
    if body.status not in ("not_started", "in_progress", "complete"):
        raise HTTPException(status_code=400, detail="Invalid status")
    await asyncio.to_thread(update_task_status, task_id, body.status)
    return {"id": task_id, "status": body.status}


# ── Serve frontend ────────────────────────────────────────────────
# Explicit routes instead of StaticFiles mount — prevents the mount from
# intercepting /api/* routes (known FastAPI/Starlette issue with root mounts).
static_dir = Path(__file__).parent / "static"

@app.get("/")
async def serve_index():
    f = static_dir / "index.html"
    if f.exists():
        return FileResponse(f)
    return {"status": "frontend not found"}

@app.get("/script.js")
async def serve_script():
    return FileResponse(static_dir / "script.js", media_type="application/javascript")

@app.get("/style.css")
async def serve_style():
    return FileResponse(static_dir / "style.css", media_type="text/css")

# ── SEO Playbook API ──────────────────────────────────────────────────────────

VAULT_DATA_DIR = Path(__file__).parent / 'data' / 'vault'
from datetime import datetime as _dt


def _parse_yaml(filepath: Path):
    if not filepath.exists():
        return None
    try:
        return yaml.safe_load(filepath.read_text())
    except Exception:
        return None


def _build_playbook_data():
    index_data = _parse_yaml(VAULT_DATA_DIR / '_clients-index.yaml')
    if not index_data or 'clients' not in index_data:
        return {'generated': _dt.utcnow().strftime('%Y-%m-%d'), 'month': '', 'clients': []}
    now = _dt.utcnow()
    mn = ['January','February','March','April','May','June',
          'July','August','September','October','November','December']
    tm = now.month + 1 if now.day > 15 else now.month
    ty = now.year + 1 if tm > 12 else now.year
    if tm > 12:
        tm = 1
    month_label = f"{mn[tm - 1]} {ty}"
    clients = []
    for c in index_data['clients']:
        if c.get('status') != 'active':
            continue
        folder = c.get('folder', '')
        recurring = _parse_yaml(VAULT_DATA_DIR / 'clients' / folder / 'recurring.yaml')
        roadmap = _parse_yaml(VAULT_DATA_DIR / 'clients' / folder / 'roadmap.yaml')
        tasks = {'content': [], 'gbp': [], 'offpage': [], 'technical': [], 'reporting': []}
        if recurring:
            for item in recurring.get('content', []):
                tasks['content'].append({'task': item.get('task', ''), 'time': str(item.get('time', 'varies'))})
            for item in recurring.get('gbp', []):
                tasks['gbp'].append({'task': item.get('task', ''), 'time': str(item.get('time', 'varies'))})
            for item in recurring.get('off_page', []):
                tv = 'outsource' if item.get('owner') == 'outsource' else str(item.get('time', 'varies'))
                tasks['offpage'].append({'task': item.get('task', ''), 'time': tv})
            for item in recurring.get('technical', []):
                tasks['technical'].append({'task': item.get('task', ''), 'time': str(item.get('time', 'varies'))})
            for item in recurring.get('reporting', []):
                tasks['reporting'].append({'task': item.get('task', ''), 'time': str(item.get('time', 'varies'))})
        next_pages = []
        if roadmap and isinstance(roadmap, dict) and 'pages_pipeline' in roadmap:
            high = [p for p in roadmap['pages_pipeline']
                    if isinstance(p, dict) and p.get('priority') == 'HIGH' and p.get('status') != 'done']
            for p in high[:3]:
                next_pages.append({'url': p.get('url', ''), 'keyword': p.get('keyword', '')})
        services = c.get('services', [])
        if isinstance(services, str):
            services = [s.strip() for s in services.split(',')]
        clients.append({
            'name': c.get('client', ''), 'folder': folder, 'tier': c.get('tier', 3),
            'mrr': c.get('mrr', 0), 'manager': c.get('manager', ''),
            'cadence': c.get('cadence', 'monthly'), 'contact': c.get('contact', ''),
            'location': c.get('location', ''), 'services': services,
            'tasks': tasks, 'nextPages': next_pages
        })
    return {'generated': _dt.utcnow().strftime('%Y-%m-%d'), 'month': month_label, 'clients': clients}


@app.get("/api/seo/playbook-data")
async def seo_playbook_data():
    return _build_playbook_data()


@app.get("/api/seo/clients")
async def seo_clients():
    data = _parse_yaml(VAULT_DATA_DIR / '_clients-index.yaml')
    return data if data else {'clients': []}


# ── SPA fallback (must be last) ──────────────────────────────────────────────

@app.get("/{spa_path:path}")
async def serve_spa(spa_path: str):
    """Serve standalone agent pages if they exist, otherwise fall back to SPA."""
    if spa_path and not spa_path.startswith("api/"):
        candidate = static_dir / f"{spa_path}.html"
        if candidate.exists():
            return FileResponse(candidate)
    return FileResponse(static_dir / "index.html")
