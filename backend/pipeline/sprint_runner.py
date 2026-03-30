"""
Sprint Runner — orchestrates a monthly content sprint for a client.

Takes a list of content items (page_type, keyword, title) and executes
pipeline runs for each item sequentially. Streams SSE progress for the
whole sprint, allowing the frontend to show a unified progress view.

Uses PipelineEngine.create_run() and PipelineEngine.execute() directly,
inheriting all existing stage runners, approval modes, and artifact handling.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from pipeline.engine import PipelineEngine, PipelineRun

logger = logging.getLogger(__name__)


# Default stage lists per page type. These mirror the page_types/ configs
# and act as a fallback when PAGE_TYPE_CONFIGS is not passed in.
DEFAULT_STAGES = {
    "service-page": ["research", "strategy", "copywrite", "design", "images", "qa"],
    "location-page": ["research", "strategy", "copywrite", "design", "images", "qa"],
    "blog-post": ["research", "strategy", "copywrite", "design", "images", "qa"],
}


def _build_inputs(
    item: dict,
    client_name: str,
    domain: str,
) -> dict:
    """Build the inputs dict for a pipeline run from a sprint item.

    Sprint items can provide explicit inputs, or we derive them from
    page_type + keyword + title fields.
    """
    # Start with any explicit inputs the caller provided
    inputs = dict(item.get("inputs", {}))

    # Always inject domain
    inputs.setdefault("domain", domain)

    page_type = item.get("page_type", "service-page")

    keyword = item.get("keyword", "")
    title = item.get("title", "")

    if page_type == "service-page":
        inputs.setdefault("service", keyword or title)
        inputs.setdefault("location", item.get("location", ""))
    elif page_type == "location-page":
        inputs.setdefault("primary_service", item.get("service", keyword))
        inputs.setdefault("target_location", item.get("location", keyword))
    elif page_type == "blog-post":
        inputs.setdefault("keyword", keyword or title)
        inputs.setdefault("business_type", item.get("business_type", ""))
        inputs.setdefault("location", item.get("location", ""))

    return inputs


def _get_stages(page_type: str, page_type_configs: dict | None = None) -> list[str]:
    """Resolve the stage list for a page type."""
    if page_type_configs and page_type in page_type_configs:
        return page_type_configs[page_type]["stages"]
    return DEFAULT_STAGES.get(page_type, DEFAULT_STAGES["service-page"])


def _extract_qa_score(run: PipelineRun) -> int | None:
    """Extract the overall QA score from a completed pipeline run."""
    qa_json = run.artifacts.get("qa")
    if not qa_json:
        return None
    try:
        qa_data = json.loads(qa_json)
        return qa_data.get("overall_score")
    except (json.JSONDecodeError, TypeError):
        return None


async def run_sprint(
    client_id: int,
    client_name: str,
    domain: str,
    items: list[dict],
    pipeline_engine: PipelineEngine,
    stage_runners: dict,
    approval_mode: str = "autopilot",
    page_type_configs: dict | None = None,
    sprint_name: str = "",
) -> AsyncGenerator[str, None]:
    """Execute a monthly content sprint.

    Yields SSE-compatible JSON events:
    - {"type": "sprint_start", "sprint_id": "...", "total_items": N}
    - {"type": "item_start", "index": i, "title": "...", "page_type": "..."}
    - {"type": "token", "text": "...", "stage": "research", "item_index": i}
    - {"type": "stage_start", "stage": "...", "item_index": i, ...}
    - {"type": "stage_complete", "stage": "...", "item_index": i, ...}
    - {"type": "item_complete", "index": i, "pipeline_id": "...", "qa_score": 85}
    - {"type": "item_failed", "index": i, "error": "..."}
    - {"type": "sprint_complete", "sprint_id": "...", "completed": N, "failed": M, "pipeline_ids": [...]}
    """
    sprint_id = f"sprint_{uuid.uuid4().hex[:12]}"
    total = len(items)

    yield json.dumps({
        "type": "sprint_start",
        "sprint_id": sprint_id,
        "total_items": total,
        "client_name": client_name,
        "name": sprint_name,
    })

    completed = 0
    failed = 0
    pipeline_ids: list[str] = []
    results: list[dict] = []

    for i, item in enumerate(items):
        page_type = item.get("page_type", "service-page")
        title = item.get("title", item.get("keyword", f"Item {i + 1}"))

        yield json.dumps({
            "type": "item_start",
            "index": i,
            "title": title,
            "page_type": page_type,
            "total_items": total,
        })

        # Build inputs and stages for this item
        inputs = _build_inputs(item, client_name, domain)
        stages = _get_stages(page_type, page_type_configs)

        # Create pipeline run
        run = pipeline_engine.create_run(
            page_type=page_type,
            client_id=client_id,
            client_name=client_name,
            inputs=inputs,
            stages=stages,
            approval_mode=approval_mode,
        )
        pipeline_ids.append(run.pipeline_id)

        # Execute pipeline, forwarding events with item index annotation
        item_error = None
        try:
            async for chunk in pipeline_engine.execute(run, stage_runners):
                # Parse the engine event and annotate with item_index
                try:
                    event = json.loads(chunk)
                    event["item_index"] = i
                    yield json.dumps(event)
                except (json.JSONDecodeError, TypeError):
                    # Raw text chunk — wrap it
                    yield json.dumps({
                        "type": "token",
                        "text": chunk,
                        "item_index": i,
                    })

        except Exception as e:
            logger.exception(
                "Sprint item %d (%s) failed for client %d",
                i, title, client_id,
            )
            item_error = str(e)
            yield json.dumps({
                "type": "item_failed",
                "index": i,
                "title": title,
                "pipeline_id": run.pipeline_id,
                "error": item_error,
            })

        # Determine outcome
        if item_error or run.status.value == "failed":
            failed += 1
            results.append({
                "index": i,
                "title": title,
                "pipeline_id": run.pipeline_id,
                "status": "failed",
                "error": item_error or run.error,
            })
        else:
            completed += 1
            qa_score = _extract_qa_score(run)
            results.append({
                "index": i,
                "title": title,
                "pipeline_id": run.pipeline_id,
                "page_type": page_type,
                "status": "completed",
                "qa_score": qa_score,
                "clickup_task_id": item.get("clickup_task_id"),
            })

            yield json.dumps({
                "type": "item_complete",
                "index": i,
                "title": title,
                "pipeline_id": run.pipeline_id,
                "qa_score": qa_score,
                "page_type": page_type,
            })

    # Sprint complete
    yield json.dumps({
        "type": "sprint_complete",
        "sprint_id": sprint_id,
        "completed": completed,
        "failed": failed,
        "total_items": total,
        "pipeline_ids": pipeline_ids,
        "results": results,
    })
