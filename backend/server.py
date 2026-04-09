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

import anthropic
from fastapi import FastAPI, HTTPException, UploadFile, Query as QueryParam, WebSocket, WebSocketDisconnect
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
    save_sprint, get_sprint as db_get_sprint, get_client_sprints,
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
from utils.db import _connect as db_connect
from pipeline.engine import PipelineEngine
from pipeline.stages import STAGE_RUNNERS
from pipeline.page_types.service_page import PAGE_CONFIG as SERVICE_PAGE_CONFIG
from pipeline.page_types.location_page import PAGE_CONFIG as LOCATION_PAGE_CONFIG
from pipeline.page_types.blog_post import PAGE_CONFIG as BLOG_POST_CONFIG
from memory.store import ClientMemoryStore
from pipeline.sprint_runner import run_sprint
from clickup_sync import update_task_status as clickup_update_task, add_task_comment as clickup_add_comment
from utils.content_db import (
    get_assignable_items, get_roadmap_item, assign_to_pipeline,
    update_roadmap_status, mark_roadmap_approved,
)
try:
    from scheduler.scheduler import PipelineScheduler
    from scheduler.jobs import (
        create_scheduled_job, get_scheduled_job, list_scheduled_jobs,
        update_scheduled_job, delete_scheduled_job,
    )
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    PipelineScheduler = None

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

# ── Pipeline engine setup ─────────────────────────────────
_anthropic_client = anthropic.AsyncAnthropic()
_memory_store = ClientMemoryStore(db_connect)
_pipeline_engine = PipelineEngine(_anthropic_client, db_connect, _memory_store)

PAGE_TYPE_CONFIGS = {
    "service-page": SERVICE_PAGE_CONFIG,
    "location-page": LOCATION_PAGE_CONFIG,
    "blog-post": BLOG_POST_CONFIG,
}

# ── Scheduler setup ───────────────────────────────────────
_scheduler = PipelineScheduler(_pipeline_engine, db_connect, STAGE_RUNNERS) if SCHEDULER_AVAILABLE else None


@app.on_event("startup")
async def _start_scheduler():
    if _scheduler:
        _scheduler.start()


@app.on_event("shutdown")
async def _stop_scheduler():
    if _scheduler:
        _scheduler.stop()

# ── RedditPilot embedded agent ───────────────────────────
# The RedditPilot package is vendored at backend/redditpilot/.
# reddit_agent.py manages a lazy singleton orchestrator and exposes
# helper functions for the /api/reddit/* routes below.
import reddit_agent


@app.on_event("shutdown")
async def _stop_reddit_agent():
    """Gracefully shut down the RedditPilot orchestrator if it was initialized."""
    try:
        reddit_agent.shutdown()
    except Exception:
        pass


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


class InterviewRequest(BaseModel):
    answer: Optional[str] = None
    session_state: Optional[dict] = None


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


# ── Brand Onboarding routes ────────────────────────────────

class OnboardRequest(BaseModel):
    domain: Optional[str] = None
    force: bool = False


@app.post("/api/clients/{client_id}/onboard")
async def onboard_client_brand(client_id: int, body: OnboardRequest):
    """Extract brand data from client website and save to memory."""
    client_row = await asyncio.to_thread(db_get_client, client_id)
    if not client_row:
        raise HTTPException(status_code=404, detail="Client not found")

    domain = (body.domain or client_row.get("domain", "")).strip()
    if not domain:
        raise HTTPException(status_code=400, detail="No domain provided and none on client record")

    from pipeline.brand_extractor import extract_brand
    from pipeline.brand_memory import save_brand_to_memory

    brand_data = await extract_brand(domain, anthropic.AsyncAnthropic())
    if not brand_data.get("color_palette"):
        raise HTTPException(status_code=422, detail="Brand extraction returned no color data")

    count = save_brand_to_memory(_memory_store, client_id, brand_data)

    return {
        "client_id": client_id,
        "domain": domain,
        "entries_saved": count,
        "color_palette": brand_data.get("color_palette", {}),
        "typography": brand_data.get("typography", {}),
        "photography_style": brand_data.get("photography_style", ""),
        "brand_voice": brand_data.get("brand_voice", ""),
        "value_propositions": brand_data.get("value_propositions", []),
        "logos_found": len(brand_data.get("assets", {}).get("images", {}).get("logos", [])),
        "images_found": len(brand_data.get("assets", {}).get("images", {}).get("all", [])),
    }


@app.get("/api/clients/{client_id}/brand")
async def get_client_brand(client_id: int):
    """Get current brand data from memory."""
    ds_entries = _memory_store.load_by_type(client_id, "design_system")
    asset_entries = _memory_store.load_by_type(client_id, "asset_catalog")
    voice_entries = _memory_store.load_by_type(client_id, "brand_voice")

    if not ds_entries and not asset_entries and not voice_entries:
        return {"client_id": client_id, "has_brand": False, "message": "No brand data. Run POST /api/clients/{id}/onboard first."}

    return {
        "client_id": client_id,
        "has_brand": True,
        "design_system": {e["key"]: e["value"] for e in ds_entries},
        "asset_catalog": {e["key"]: e["value"] for e in asset_entries},
        "brand_voice": {e["key"]: e["value"] for e in voice_entries},
    }


# ── Client Brain Research routes ──────────────────────────

class ResearchRequest(BaseModel):
    force: bool = False


@app.post("/api/clients/{client_id}/research")
async def research_client(client_id: int, body: ResearchRequest = ResearchRequest()):
    """Build the full client brain: brand + voice + business intelligence.
    Returns SSE stream with progress updates."""
    client_row = await asyncio.to_thread(db_get_client, client_id)
    if not client_row:
        raise HTTPException(status_code=404, detail="Client not found")

    domain = (client_row.get("domain", "")).strip()
    if not domain:
        raise HTTPException(status_code=400, detail="Client has no domain set")

    location = (client_row.get("location", "")).strip()
    service = (client_row.get("service", "")).strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)

    async def research_stream():
        from pipeline.client_research_agent import build_client_brain_streaming
        async for chunk in build_client_brain_streaming(
            client_id=client_id,
            domain=domain,
            location=location,
            anthropic_client=anthropic_client,
            memory_store=_memory_store,
            service=service,
            force=body.force,
        ):
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'client_id': client_id})}\n\n"

    return StreamingResponse(research_stream(), media_type="text/event-stream")


@app.get("/api/clients/{client_id}/brain")
async def get_client_brain(client_id: int):
    """Get the full client brain — all memory entries grouped by section."""
    from memory.store import (
        BRAND_VOICE, DESIGN_SYSTEM, ASSET_CATALOG,
        BUSINESS_INTEL, PAST_CONTENT, LEARNINGS,
    )

    sections = {}
    for memory_type in [DESIGN_SYSTEM, ASSET_CATALOG, BRAND_VOICE, BUSINESS_INTEL, PAST_CONTENT, LEARNINGS]:
        entries = _memory_store.load_by_type(client_id, memory_type)
        sections[memory_type] = {e["key"]: e["value"] for e in entries}

    has_brain = any(bool(v) for v in sections.values())
    return {
        "client_id": client_id,
        "has_brain": has_brain,
        "sections": sections,
        "entry_count": sum(len(v) for v in sections.values()),
    }


# ── Interview & Test Voice routes ─────────────────────────

@app.post("/api/clients/{client_id}/interview")
async def client_interview(client_id: int, body: InterviewRequest = InterviewRequest()):
    """Run one step of the client brain interview.
    Body: { answer: str | null, session_state: dict | null }
    Returns SSE stream with the next question + updated session_state.
    """
    client_row = await asyncio.to_thread(db_get_client, client_id)
    if not client_row:
        raise HTTPException(status_code=404, detail="Client not found")

    async def interview_stream():
        from pipeline.interview_agent import run_interview
        async for event in run_interview(
            client_id=client_id,
            memory_store=_memory_store,
            anthropic_client=_anthropic_client,
            user_answer=body.answer,
            session_state=body.session_state,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(interview_stream(), media_type="text/event-stream")


@app.post("/api/clients/{client_id}/test-voice")
async def test_client_voice(client_id: int):
    """Generate a sample paragraph using the client's brain to validate voice quality.
    Returns SSE stream with a sample service intro paragraph + the brain context used.
    """
    client_row = await asyncio.to_thread(db_get_client, client_id)
    if not client_row:
        raise HTTPException(status_code=404, detail="Client not found")

    client_name = client_row.get("name", "this business")

    from pipeline.brain_formatter import format_brain_for_workflow
    brain_ctx = format_brain_for_workflow(_memory_store, client_id, "service-page")
    if not brain_ctx:
        raise HTTPException(
            status_code=400,
            detail="Client has no brain data yet. Run research or the interview first.",
        )

    async def voice_stream():
        # Send brain context first so the UI can show what informed the output
        yield f"data: {json.dumps({'type': 'brain_context', 'text': brain_ctx})}\n\n"

        prompt = (
            f"Write a 3-4 sentence intro paragraph for a service page for {client_name}. "
            "Use the brand voice and business context provided in the system prompt. "
            "Write as if this is the opening of a real service page on their website -- "
            "warm, confident, and specific to their business. Do NOT use placeholder text. "
            "Include a natural call-to-action."
        )

        async with _anthropic_client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=f"You are a marketing copywriter. Use this client brain to write in the client's authentic voice:\n\n{brain_ctx}",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(voice_stream(), media_type="text/event-stream")


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

        # ── Inject client brain context if available ──
        strategy_ctx = req.strategy_context or ""
        if req.client_id:
            try:
                from pipeline.brain_formatter import format_brain_for_workflow
                from memory.store import ClientMemoryStore
                _mem = ClientMemoryStore(db_connect)
                brain_ctx = format_brain_for_workflow(_mem, req.client_id, req.workflow_id)
                if brain_ctx:
                    strategy_ctx = brain_ctx + "\n\n" + strategy_ctx
            except Exception:
                pass  # Brain not available yet — use manual strategy_context

        try:
            # ── Route to the correct workflow ──
            if req.workflow_id == "home-service-content":
                generator = run_home_service_content(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
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
                    strategy_context=strategy_ctx,
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
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "keyword-gap":
                generator = run_keyword_gap(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-blog-post":
                generator = run_seo_blog_post(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "service-page":
                generator = run_service_page(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "location-page":
                generator = run_location_page(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "programmatic-content":
                generator = run_programmatic_content(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "ai-search-report":
                generator = run_ai_search_report(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "backlink-audit":
                generator = run_backlink_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "onpage-audit":
                generator = run_onpage_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-research":
                generator = run_seo_research_agent(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "competitor-intel":
                generator = run_competitor_intel(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "monthly-report":
                generator = run_monthly_report(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "proposals":
                generator = run_proposals(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "google-ads-copy":
                generator = run_google_ads_copy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "schema-generator":
                generator = run_schema_generator(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "content-strategy":
                generator = run_content_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "pnl-statement":
                generator = run_pnl_statement(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "property-mgmt-strategy":
                generator = run_property_mgmt_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "page-design":
                generator = run_page_design(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "geo-content-audit":
                generator = run_geo_content_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "seo-content-audit":
                generator = run_seo_content_audit(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "technical-seo-review":
                generator = run_technical_seo_review(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "programmatic-seo-strategy":
                generator = run_programmatic_seo_strategy(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
                    client_name=req.client_name,
                )
            elif req.workflow_id == "competitor-seo-analysis":
                generator = run_competitor_seo_analysis(
                    client=client,
                    inputs=req.inputs,
                    strategy_context=strategy_ctx,
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


# ── Pipeline API ──────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    page_type: str              # "service-page", "location-page", "blog-post"
    client_id: int
    client_name: str = ""
    inputs: dict = {}
    approval_mode: str = "autopilot"  # "autopilot", "milestone", "output_only"


class PipelineApproveRequest(BaseModel):
    feedback: str = ""


@app.get("/api/pipeline/templates")
async def get_pipeline_templates():
    """Return available page type configurations for the pipeline builder UI."""
    return {"templates": list(PAGE_TYPE_CONFIGS.values())}


@app.post("/api/pipeline/run")
async def run_pipeline(body: PipelineRunRequest):
    """Start a pipeline run, returning SSE stream of progress + tokens."""
    config = PAGE_TYPE_CONFIGS.get(body.page_type)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown page type: {body.page_type}")

    # Resolve client name if not provided
    client_name = body.client_name
    if not client_name and body.client_id:
        client_row = await asyncio.to_thread(db_get_client, body.client_id)
        if client_row:
            client_name = client_row.get("name", "")

    run = _pipeline_engine.create_run(
        page_type=body.page_type,
        client_id=body.client_id,
        client_name=client_name,
        inputs=body.inputs,
        stages=config["stages"],
        approval_mode=body.approval_mode,
    )

    async def event_stream():
        full_content: list[str] = []
        pipeline_id_ref = run.pipeline_id
        try:
            async for chunk in _pipeline_engine.execute(run, STAGE_RUNNERS):
                # Capture text tokens for job persistence / docx
                try:
                    parsed = json.loads(chunk)
                    if parsed.get("type") == "token":
                        full_content.append(parsed.get("text", ""))
                except Exception:
                    pass
                yield f"data: {chunk}\n\n"

            # Pipeline finished — persist job + generate docx (blog only)
            content_str = "".join(full_content)
            job_id = str(uuid.uuid4())[:8]
            wf_title = f"AutoPilot: {config['title']}"
            wf_id = f"pipeline-{body.page_type}"
            job_data = {
                "content": content_str,
                "client_name": client_name,
                "workflow_title": wf_title,
                "workflow_id": wf_id,
                "inputs": body.inputs,
                "client_id": body.client_id,
            }
            await asyncio.to_thread(save_job, job_id, job_data)
            # Only blog posts get a .docx — pages get a shareable HTML preview URL
            if body.page_type == "blog-post":
                docx_path = await asyncio.to_thread(generate_docx, job_id, job_data)
                await asyncio.to_thread(update_docx_path, job_id, str(docx_path))

            yield f"data: {json.dumps({'type': 'done', 'job_id': job_id, 'client_name': client_name, 'workflow_title': wf_title, 'workflow_id': wf_id, 'pipeline_id': pipeline_id_ref})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/pipeline/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str):
    """Get current status and artifacts for a pipeline run."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    result = run.to_dict()
    # Include stage outputs for completed stages
    result["stage_outputs"] = {
        k: v[:500] + "..." if len(v) > 500 else v
        for k, v in run.stage_outputs.items()
    }
    return result


@app.get("/api/pipeline/{pipeline_id}/artifact/{stage}")
async def get_pipeline_artifact(pipeline_id: str, stage: str):
    """Get the full artifact for a specific stage."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    artifact_json = run.artifacts.get(stage)
    if not artifact_json:
        raise HTTPException(status_code=404, detail=f"No artifact for stage: {stage}")
    return {"stage": stage, "artifact": json.loads(artifact_json)}


@app.get("/api/pipeline/{pipeline_id}/output/{stage}")
async def get_pipeline_stage_output(pipeline_id: str, stage: str):
    """Get the full text output for a specific stage."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    output = run.stage_outputs.get(stage)
    if output is None:
        raise HTTPException(status_code=404, detail=f"No output for stage: {stage}")
    return {"stage": stage, "output": output}


@app.post("/api/pipeline/{pipeline_id}/approve")
async def approve_pipeline_stage(pipeline_id: str, body: PipelineApproveRequest):
    """Approve the current stage and continue the pipeline. Returns SSE stream."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    async def event_stream():
        try:
            async for chunk in _pipeline_engine.approve_and_continue(
                pipeline_id, STAGE_RUNNERS, body.feedback
            ):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/pipeline/{pipeline_id}/reject")
async def reject_pipeline_stage(pipeline_id: str, body: PipelineApproveRequest):
    """Reject the current stage with feedback. Stores feedback as a learning."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if body.feedback and _memory_store:
        stage = run.current_stage or "unknown"
        _memory_store.save_learning(
            run.client_id,
            f"rejection-{stage}-{run.pipeline_id[:8]}",
            f"Stage '{stage}' rejected: {body.feedback}",
        )
    return {"pipeline_id": pipeline_id, "status": "rejected", "feedback": body.feedback}


class BatchPipelineRequest(BaseModel):
    page_type: str
    client_id: int
    client_name: str = ""
    items: list[dict]  # list of input dicts, one per page
    approval_mode: str = "autopilot"


@app.post("/api/pipeline/batch")
async def batch_pipeline(body: BatchPipelineRequest):
    """Queue a batch of pipelines (e.g., 12 location pages for 12 cities).
    Returns the list of created pipeline IDs. Each runs sequentially to avoid
    overwhelming the Claude API.
    """
    config = PAGE_TYPE_CONFIGS.get(body.page_type)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown page type: {body.page_type}")
    if not body.items:
        raise HTTPException(status_code=400, detail="No items in batch")

    client_name = body.client_name
    if not client_name and body.client_id:
        client_row = await asyncio.to_thread(db_get_client, body.client_id)
        if client_row:
            client_name = client_row.get("name", "")

    pipeline_ids = []
    for item_inputs in body.items:
        run = _pipeline_engine.create_run(
            page_type=body.page_type,
            client_id=body.client_id,
            client_name=client_name,
            inputs=item_inputs,
            stages=config["stages"],
            approval_mode=body.approval_mode,
        )
        pipeline_ids.append(run.pipeline_id)

    return {"batch_size": len(pipeline_ids), "pipeline_ids": pipeline_ids}


@app.post("/api/pipeline/batch/{pipeline_id}/start")
async def start_batch_pipeline(pipeline_id: str):
    """Start a specific pipeline from a batch. Returns SSE stream."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    async def event_stream():
        try:
            async for chunk in _pipeline_engine.execute(run, STAGE_RUNNERS):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Monthly Sprint endpoints ──────────────────────────────────────────

class SprintRequest(BaseModel):
    client_id: int
    items: list[dict]  # [{page_type, keyword, title, clickup_task_id?, location?, ...}]
    approval_mode: str = "autopilot"
    name: str = ""


@app.post("/api/clients/{client_id}/sprint")
async def run_client_sprint(client_id: int, body: SprintRequest):
    """Execute a monthly content sprint for a client.

    Creates a pipeline run for each item, executes them sequentially, and
    streams SSE progress for the whole sprint.
    """
    if body.client_id != client_id:
        body.client_id = client_id

    client_row = await asyncio.to_thread(db_get_client, client_id)
    if not client_row:
        raise HTTPException(status_code=404, detail="Client not found")
    if not body.items:
        raise HTTPException(status_code=400, detail="No items in sprint")

    client_name = client_row.get("name", "")
    domain = client_row.get("domain", "")
    sprint_name = body.name or f"{client_name} Sprint"

    # Persist sprint record as pending
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc).isoformat()

    async def event_stream():
        sprint_id = None
        pipeline_ids = []
        results = []

        try:
            async for chunk in run_sprint(
                client_id=client_id,
                client_name=client_name,
                domain=domain,
                items=body.items,
                pipeline_engine=_pipeline_engine,
                stage_runners=STAGE_RUNNERS,
                approval_mode=body.approval_mode,
                page_type_configs=PAGE_TYPE_CONFIGS,
                sprint_name=sprint_name,
            ):
                # Capture sprint_id and results from events for DB persistence
                try:
                    event = json.loads(chunk)
                    if event.get("type") == "sprint_start":
                        sprint_id = event.get("sprint_id")
                        # Save initial sprint record
                        await asyncio.to_thread(save_sprint, sprint_id, {
                            "client_id": client_id,
                            "name": sprint_name,
                            "status": "running",
                            "items": body.items,
                            "pipeline_ids": [],
                            "results": {},
                            "created_at": now,
                        })
                    elif event.get("type") == "sprint_complete":
                        pipeline_ids = event.get("pipeline_ids", [])
                        results = event.get("results", [])
                        if sprint_id:
                            await asyncio.to_thread(save_sprint, sprint_id, {
                                "client_id": client_id,
                                "name": sprint_name,
                                "status": "completed",
                                "items": body.items,
                                "pipeline_ids": pipeline_ids,
                                "results": {"items": results},
                                "created_at": now,
                                "completed_at": datetime.now(tz.utc).isoformat(),
                            })
                except (json.JSONDecodeError, TypeError):
                    pass

                yield f"data: {chunk}\n\n"

        except Exception as e:
            error_event = json.dumps({"type": "error", "message": str(e)})
            if sprint_id:
                await asyncio.to_thread(save_sprint, sprint_id, {
                    "client_id": client_id,
                    "name": sprint_name,
                    "status": "failed",
                    "items": body.items,
                    "pipeline_ids": pipeline_ids,
                    "results": {"error": str(e)},
                    "created_at": now,
                })
            yield f"data: {error_event}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/clients/{client_id}/sprints")
async def list_client_sprints(client_id: int):
    """List all sprint runs for a client."""
    sprints = await asyncio.to_thread(get_client_sprints, client_id)
    return {"client_id": client_id, "sprints": sprints}


@app.get("/api/sprints/{sprint_id}")
async def get_sprint_detail(sprint_id: str):
    """Get details for a specific sprint run."""
    sprint = await asyncio.to_thread(db_get_sprint, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


class ApproveAndSyncRequest(BaseModel):
    clickup_task_id: str = ""
    comment: str = "Content generated and approved via ProofPilot Agent Hub"


@app.post("/api/jobs/{job_id}/approve-and-sync")
async def approve_and_sync_clickup(job_id: str, body: ApproveAndSyncRequest):
    """Approve content AND update ClickUp task status to complete.

    1. Marks the job as approved in the local DB
    2. If a clickup_task_id is provided, updates the task status to 'complete'
    3. Optionally adds a comment to the ClickUp task
    """
    # Approve in local DB
    ok = await asyncio.to_thread(approve_job, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")

    clickup_synced = False
    clickup_commented = False

    if body.clickup_task_id:
        clickup_synced = await clickup_update_task(body.clickup_task_id, "complete")
        if body.comment:
            clickup_commented = await clickup_add_comment(body.clickup_task_id, body.comment)

    return {
        "job_id": job_id,
        "approved": True,
        "clickup_task_id": body.clickup_task_id or None,
        "clickup_synced": clickup_synced,
        "clickup_commented": clickup_commented,
    }


@app.get("/api/pipeline/{pipeline_id}/download/html")
async def download_pipeline_html(pipeline_id: str):
    """Download the design stage output as an HTML file."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    design_json = run.artifacts.get("design")
    if not design_json:
        raise HTTPException(status_code=404, detail="No design artifact — pipeline may not have reached the design stage")

    import json as _json
    design = _json.loads(design_json)
    html_content = design.get("full_page", "")
    if not html_content:
        html_content = run.stage_outputs.get("design", "")

    # Build a descriptive filename
    inputs = run.inputs
    service = inputs.get("service", inputs.get("primary_service", inputs.get("keyword", "page")))
    location = inputs.get("location", inputs.get("target_location", ""))
    slug = f"{service}-{location}".lower().replace(" ", "-").replace(",", "").replace(".", "")[:50]
    filename = f"{run.page_type}-{slug}.html"

    from fastapi.responses import Response
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/pipeline/{pipeline_id}/preview")
async def preview_pipeline_html(pipeline_id: str):
    """Preview the design stage output as rendered HTML (no download)."""
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    design_json = run.artifacts.get("design")
    if not design_json:
        raise HTTPException(status_code=404, detail="No design artifact")
    design = json.loads(design_json)
    html_content = design.get("full_page", "")
    if not html_content:
        html_content = run.stage_outputs.get("design", "")
    return HTMLResponse(content=html_content)


# ── Client Memory API ────────────────────────────────────────────

@app.get("/api/memory/{client_id_param}")
async def get_client_memory(client_id_param: int):
    """Get all memory entries for a client."""
    entries = await asyncio.to_thread(_memory_store.load_all, client_id_param)
    return {"client_id": client_id_param, "entries": entries}


class MemoryEntryRequest(BaseModel):
    memory_type: str  # brand_voice, style_preferences, past_content, learnings
    key: str
    value: str


@app.post("/api/memory/{client_id_param}")
async def save_client_memory(client_id_param: int, body: MemoryEntryRequest):
    """Save or update a client memory entry."""
    await asyncio.to_thread(
        _memory_store.save, client_id_param, body.memory_type, body.key, body.value
    )
    return {"client_id": client_id_param, "memory_type": body.memory_type, "key": body.key, "saved": True}


@app.delete("/api/memory/{client_id_param}/{memory_type}/{key}")
async def delete_client_memory(client_id_param: int, memory_type: str, key: str):
    """Delete a specific memory entry."""
    deleted = await asyncio.to_thread(_memory_store.delete, client_id_param, memory_type, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"deleted": True}


# ── Roadmap Assignment API ────────────────────────────────────────

@app.get("/api/roadmap/{client_id_param}/assignable")
async def get_assignable_roadmap_items(client_id_param: int, month: Optional[str] = None):
    """Get roadmap items that can be assigned to the pipeline agent (status=planned)."""
    items = await asyncio.to_thread(get_assignable_items, client_id_param, month)
    return {"items": items, "count": len(items)}


class RoadmapAssignRequest(BaseModel):
    roadmap_ids: list[int]  # IDs from content_roadmap table
    approval_mode: str = "autopilot"


@app.post("/api/pipeline/from-roadmap")
async def create_pipelines_from_roadmap(body: RoadmapAssignRequest):
    """Assign roadmap items to the pipeline agent. Creates one pipeline per item.

    This is the main way to tell the agent: 'go build these pages from the monthly plan.'
    Each roadmap item becomes a pipeline run. Status auto-updates as stages complete.
    """
    created = []
    for roadmap_id in body.roadmap_ids:
        item = await asyncio.to_thread(get_roadmap_item, roadmap_id)
        if not item:
            continue
        if item.get("status") not in ("planned", "assigned"):
            continue  # Skip items already in progress

        # Map roadmap page_type to pipeline page_type
        page_type_map = {
            "service-page": "service-page",
            "service_page": "service-page",
            "location-page": "location-page",
            "location_page": "location-page",
            "blog-post": "blog-post",
            "blog_post": "blog-post",
            "blog": "blog-post",
        }
        pipeline_type = page_type_map.get(item.get("page_type", "").lower(), "service-page")
        config = PAGE_TYPE_CONFIGS.get(pipeline_type)
        if not config:
            continue

        # Resolve client info
        client = await asyncio.to_thread(db_get_client, item["client_id"])
        client_name = client.get("name", "") if client else ""
        domain = client.get("domain", "") if client else ""
        service = client.get("service", "") if client else ""
        location = client.get("location", "") if client else ""

        # Build pipeline inputs from roadmap item + client record
        inputs = {
            "domain": domain,
            "service": service or item.get("content_silo", ""),
            "location": location,
            "keyword": item.get("keyword", ""),
            "notes": f"From content roadmap: {item.get('title', '')}. Target keyword: {item.get('keyword', '')}.",
        }

        run = _pipeline_engine.create_run(
            page_type=pipeline_type,
            client_id=item["client_id"],
            client_name=client_name,
            inputs=inputs,
            stages=config["stages"],
            approval_mode=body.approval_mode,
        )

        # Link roadmap item to pipeline run
        await asyncio.to_thread(assign_to_pipeline, roadmap_id, run.pipeline_id)

        created.append({
            "roadmap_id": roadmap_id,
            "pipeline_id": run.pipeline_id,
            "title": item.get("title", ""),
            "page_type": pipeline_type,
            "keyword": item.get("keyword", ""),
        })

    return {"assigned": len(created), "pipelines": created}


class RoadmapBulkStartRequest(BaseModel):
    pipeline_ids: list[str]


@app.post("/api/pipeline/start-assigned")
async def start_assigned_pipelines(body: RoadmapBulkStartRequest):
    """Start multiple assigned pipelines. Returns SSE stream for the first one.

    Remaining pipelines are queued — call this endpoint again for each,
    or use the scheduler to run them sequentially.
    """
    if not body.pipeline_ids:
        raise HTTPException(status_code=400, detail="No pipeline IDs provided")

    pipeline_id = body.pipeline_ids[0]
    run = _pipeline_engine.get_run(pipeline_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")

    async def event_stream():
        try:
            async for chunk in _pipeline_engine.execute(run, STAGE_RUNNERS):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/roadmap/{roadmap_id}/approve")
async def approve_roadmap_item(roadmap_id: int):
    """Mark a roadmap item as approved (after reviewing pipeline output)."""
    await asyncio.to_thread(mark_roadmap_approved, "")  # need pipeline_id
    item = await asyncio.to_thread(get_roadmap_item, roadmap_id)
    if not item:
        raise HTTPException(status_code=404, detail="Roadmap item not found")
    await asyncio.to_thread(update_roadmap_status, roadmap_id, "approved")
    return {"roadmap_id": roadmap_id, "status": "approved"}


# ── Schedule API ──────────────────────────────────────────────────

class ScheduleCreateRequest(BaseModel):
    name: str = ""
    client_id: int
    pipeline_type: str
    inputs: dict = {}
    approval_mode: str = "autopilot"
    schedule: str  # "every 7d", "0 9 * * 1", etc.


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = None
    inputs: Optional[dict] = None
    schedule: Optional[str] = None
    approval_mode: Optional[str] = None
    enabled: Optional[bool] = None


@app.get("/api/schedule")
async def list_schedules(client_id: Optional[int] = None):
    """List all scheduled pipeline jobs."""
    if not SCHEDULER_AVAILABLE:
        return {"schedules": [], "warning": "Scheduler not available (apscheduler not installed)"}
    with db_connect() as conn:
        jobs = list_scheduled_jobs(conn, client_id)
    return {"schedules": jobs}


@app.post("/api/schedule")
async def create_schedule(body: ScheduleCreateRequest):
    """Create a new scheduled pipeline job."""
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    if body.pipeline_type not in PAGE_TYPE_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline type: {body.pipeline_type}")
    with db_connect() as conn:
        job = create_scheduled_job(conn, body.dict())
    _scheduler.add_job_from_db(job["id"])
    return job


@app.get("/api/schedule/{job_id}")
async def get_schedule(job_id: str):
    """Get a specific scheduled job."""
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    with db_connect() as conn:
        job = get_scheduled_job(conn, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return job


@app.patch("/api/schedule/{job_id}")
async def update_schedule(job_id: str, body: ScheduleUpdateRequest):
    """Update a scheduled job."""
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    with db_connect() as conn:
        job = update_scheduled_job(conn, job_id, {k: v for k, v in body.dict().items() if v is not None})
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    _scheduler.add_job_from_db(job_id)  # Re-sync with APScheduler
    return job


@app.delete("/api/schedule/{job_id}")
async def delete_schedule(job_id: str):
    """Delete a scheduled job."""
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    _scheduler.remove_job(job_id)
    with db_connect() as conn:
        deleted = delete_scheduled_job(conn, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return {"deleted": True}


# ── RedditPilot routes (embedded agent) ──────────────────────────
# RedditPilot runs in-process via the vendored `redditpilot` package.
# reddit_agent.py manages a lazy singleton orchestrator. These routes
# expose JSON endpoints that the frontend calls directly — no proxy,
# no separate service, no external auth.

@app.get("/api/reddit/health")
async def rp_health():
    """Report RedditPilot agent health and configuration status."""
    configured = reddit_agent.is_configured()
    if not configured:
        return {
            "connected": False,
            "configured": False,
            "reason": f"No config file at {reddit_agent.config_path()}",
        }
    try:
        status = reddit_agent.get_status()
        return {"connected": status.get("connected", False), "configured": True, "status": status}
    except Exception as e:
        return {"connected": False, "configured": True, "reason": str(e)}


@app.get("/api/reddit/status")
async def rp_status():
    return reddit_agent.get_status()


@app.get("/api/reddit/stats")
async def rp_stats(hours: int = QueryParam(24, le=168)):
    return reddit_agent.get_stats(hours=hours)


@app.get("/api/reddit/clients")
async def rp_clients():
    return {"clients": reddit_agent.get_clients()}


@app.get("/api/reddit/clients/{slug}")
async def rp_client_detail(slug: str):
    return reddit_agent.get_client_detail(slug)


@app.get("/api/reddit/accounts")
async def rp_accounts():
    return {"accounts": reddit_agent.get_accounts()}


@app.get("/api/reddit/opportunities")
async def rp_opportunities(limit: int = QueryParam(50, le=200)):
    return {"opportunities": reddit_agent.get_opportunities(limit=limit)}


@app.get("/api/reddit/actions")
async def rp_actions(hours: int = QueryParam(24, le=168), limit: int = QueryParam(50, le=200)):
    return {"actions": reddit_agent.get_actions(hours=hours, limit=limit)}


@app.get("/api/reddit/schedule")
async def rp_schedule():
    return reddit_agent.get_schedule()


@app.get("/api/reddit/insights")
async def rp_insights():
    return reddit_agent.get_insights()


@app.get("/api/reddit/performance")
async def rp_performance(days: int = QueryParam(7, le=30)):
    return reddit_agent.get_performance(days=days)


@app.get("/api/reddit/heatmap")
async def rp_heatmap():
    return reddit_agent.get_heatmap()


@app.get("/api/reddit/funnel")
async def rp_funnel():
    return reddit_agent.get_funnel()


@app.get("/api/reddit/history")
async def rp_history(days: int = QueryParam(7, le=30), limit: int = QueryParam(50, le=200)):
    return {"history": reddit_agent.get_history(days=days, limit=limit)}


@app.get("/api/reddit/decisions")
async def rp_decisions(hours: int = QueryParam(24, le=168), limit: int = QueryParam(50, le=200)):
    return reddit_agent.get_decisions(hours=hours, limit=limit)


@app.get("/api/reddit/summary")
async def rp_summary():
    return reddit_agent.get_summary()


@app.get("/api/reddit/alerts")
async def rp_alerts(limit: int = QueryParam(20, le=100)):
    return {"alerts": reddit_agent.get_alerts(limit=limit)}


@app.get("/api/reddit/comments")
async def rp_comments(hours: int = QueryParam(168, le=720), limit: int = QueryParam(50, le=200)):
    return {"comments": reddit_agent.get_comments(hours=hours, limit=limit)}


@app.get("/api/reddit/failures")
async def rp_failures(days: int = QueryParam(7, le=30), limit: int = QueryParam(20, le=100)):
    return reddit_agent.get_failures(days=days, limit=limit)


@app.get("/api/reddit/subreddit-intel")
async def rp_subreddit_intel(limit: int = QueryParam(20, le=100)):
    return {"subreddits": reddit_agent.get_subreddit_intel(limit=limit)}


@app.get("/api/reddit/config-template")
async def rp_config_template():
    """Return the config template so the frontend can show a setup helper."""
    tpl_path = Path(__file__).parent / "redditpilot" / "config.example.yaml"
    if tpl_path.exists():
        return {"template": tpl_path.read_text(), "target_path": str(reddit_agent.config_path())}
    return {"template": "", "target_path": str(reddit_agent.config_path())}


@app.post("/api/reddit/control/{action}")
async def rp_control(action: str):
    """Execute control commands: scan, learn, pause, resume, emergency_stop,
    cycle, discover, generate, post, start_scheduler, stop_scheduler."""
    return reddit_agent.control(action)


@app.get("/api/reddit/logs")
async def rp_logs(since: int = QueryParam(0)):
    """Poll recent log records (fallback when WebSocket not available)."""
    cap = reddit_agent.log_capture()
    if cap is None:
        return {"logs": [], "seq": 0}
    records = cap.since(since) if since > 0 else cap.snapshot()
    last_seq = records[-1]["seq"] if records else since
    return {"logs": records, "seq": last_seq}


@app.websocket("/ws/reddit/logs")
async def rp_ws_logs(websocket: WebSocket):
    """Stream RedditPilot log records over WebSocket."""
    await websocket.accept()
    # Ensure orchestrator is initialized so the log capture handler exists
    reddit_agent.get_orch()
    cap = reddit_agent.log_capture()
    last_seq = 0
    try:
        # Send snapshot on connect
        if cap is not None:
            snapshot = cap.snapshot()
            for rec in snapshot:
                await websocket.send_json(rec)
                last_seq = rec["seq"]
        # Stream new records
        while True:
            await asyncio.sleep(1.0)
            if cap is None:
                cap = reddit_agent.log_capture()
                continue
            new_records = cap.since(last_seq)
            for rec in new_records:
                await websocket.send_json(rec)
                last_seq = rec["seq"]
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger_rp = __import__("logging").getLogger("proofpilot.reddit_ws")
        logger_rp.warning(f"RedditPilot WS error: {e}")


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

@app.get("/{spa_path:path}")
async def serve_spa(spa_path: str):
    """Serve standalone agent pages if they exist, otherwise fall back to SPA."""
    # Check for standalone agent pages (e.g. /page-design → page-design.html)
    if spa_path and not spa_path.startswith("api/"):
        candidate = static_dir / f"{spa_path}.html"
        if candidate.exists():
            return FileResponse(candidate)
    return FileResponse(static_dir / "index.html")
