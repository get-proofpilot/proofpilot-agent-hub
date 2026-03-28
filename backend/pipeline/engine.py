"""
Pipeline Engine — orchestrates multi-stage SEO page builds.

Each pipeline chains stages (research → strategy → copywrite → design → qa),
passing typed artifacts between them. Stages are async generators that stream
SSE tokens to the frontend, matching the existing workflow pattern.

Key features:
- Sequential stage execution with artifact passing
- Configurable approval gates (autopilot, milestone, output-only)
- SQLite persistence for pause/resume across approval gates
- SSE streaming from each active stage
- Client memory injection into agent prompts
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

import anthropic

from pipeline.artifacts import ARTIFACT_TYPES
from pipeline.skill_loader import build_stage_prompt

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalMode(str, Enum):
    AUTOPILOT = "autopilot"         # Run all stages without stopping
    MILESTONE = "milestone"         # Pause after each stage for approval
    OUTPUT_ONLY = "output_only"     # Pause only after the final QA stage


# Stages that trigger an approval gate in milestone mode
MILESTONE_STAGES = {"research", "copywrite", "qa"}


class PipelineRun:
    """Represents a single pipeline execution."""

    def __init__(
        self,
        pipeline_id: str,
        page_type: str,
        client_id: int,
        client_name: str,
        inputs: dict,
        stages: list[str],
        approval_mode: str = "autopilot",
    ):
        self.pipeline_id = pipeline_id
        self.page_type = page_type
        self.client_id = client_id
        self.client_name = client_name
        self.inputs = inputs
        self.stages = stages
        self.approval_mode = ApprovalMode(approval_mode)

        self.status = PipelineStatus.PENDING
        self.current_stage_index = 0
        self.artifacts: dict[str, str] = {}  # stage_name → artifact JSON
        self.stage_outputs: dict[str, str] = {}  # stage_name → raw text output
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def current_stage(self) -> Optional[str]:
        if self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_stage_index >= len(self.stages)

    def should_pause_after(self, stage: str) -> bool:
        """Check if pipeline should pause for approval after this stage."""
        if self.approval_mode == ApprovalMode.AUTOPILOT:
            return False
        if self.approval_mode == ApprovalMode.OUTPUT_ONLY:
            return stage == "qa"
        if self.approval_mode == ApprovalMode.MILESTONE:
            return stage in MILESTONE_STAGES
        return False

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "page_type": self.page_type,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "inputs": self.inputs,
            "stages": self.stages,
            "approval_mode": self.approval_mode.value,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "current_stage_index": self.current_stage_index,
            "completed_stages": self.stages[:self.current_stage_index],
            "artifacts": {k: "(stored)" for k in self.artifacts},
            "error": self.error,
            "created_at": self.created_at,
        }


class PipelineEngine:
    """Runs pipeline stages sequentially, streaming output via SSE."""

    def __init__(self, anthropic_client: anthropic.AsyncAnthropic, db_connect_fn, memory_store=None):
        self.client = anthropic_client
        self._connect = db_connect_fn
        self.memory_store = memory_store
        self._active_runs: dict[str, PipelineRun] = {}

    def create_run(
        self,
        page_type: str,
        client_id: int,
        client_name: str,
        inputs: dict,
        stages: list[str],
        approval_mode: str = "autopilot",
    ) -> PipelineRun:
        """Create a new pipeline run and persist it."""
        pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
        run = PipelineRun(
            pipeline_id=pipeline_id,
            page_type=page_type,
            client_id=client_id,
            client_name=client_name,
            inputs=inputs,
            stages=stages,
            approval_mode=approval_mode,
        )
        self._active_runs[pipeline_id] = run
        self._persist_run(run)
        return run

    def get_run(self, pipeline_id: str) -> Optional[PipelineRun]:
        """Get an active or persisted run."""
        if pipeline_id in self._active_runs:
            return self._active_runs[pipeline_id]
        return self._load_run(pipeline_id)

    async def execute(
        self,
        run: PipelineRun,
        stage_runners: dict,
    ) -> AsyncGenerator[str, None]:
        """Execute pipeline stages, yielding SSE-compatible text chunks.

        stage_runners: dict mapping stage names to async generator functions.
        Each function signature: async def run_stage(client, run, prev_artifacts, memory) -> AsyncGenerator[str, None]
        """
        run.status = PipelineStatus.RUNNING
        self._persist_run(run)

        # Load client memory snapshot once at start (frozen, Hermes pattern)
        client_memory = ""
        if self.memory_store:
            # Auto-extract brand if design_system memory is missing
            domain = run.inputs.get("domain", "")
            if domain and not self.memory_store.has_entries(run.client_id, "design_system"):
                try:
                    from pipeline.brand_memory import ensure_brand_memory
                    extracted = await ensure_brand_memory(
                        self.memory_store, run.client_id, domain, self.client
                    )
                    if extracted:
                        yield json.dumps({
                            "type": "brand_extracted",
                            "message": f"Auto-extracted brand from {domain}",
                        })
                except Exception as e:
                    logger.warning("Auto brand extraction failed for %s: %s", domain, e)

            # Use context-aware brain formatter if available, fallback to raw snapshot
            try:
                from pipeline.brain_formatter import format_brain_for_workflow
                client_memory = format_brain_for_workflow(
                    self.memory_store, run.client_id, run.page_type
                )
            except ImportError:
                client_memory = self.memory_store.load_snapshot(run.client_id)

        while not run.is_complete:
            stage = run.current_stage
            if stage not in stage_runners:
                run.error = f"No runner for stage: {stage}"
                run.status = PipelineStatus.FAILED
                self._persist_run(run)
                yield json.dumps({"type": "error", "message": run.error})
                return

            # Emit stage start event
            yield json.dumps({
                "type": "stage_start",
                "stage": stage,
                "stage_index": run.current_stage_index,
                "total_stages": len(run.stages),
            })

            # Collect previous stage artifacts for context
            prev_artifacts = {}
            for prev_stage in run.stages[:run.current_stage_index]:
                if prev_stage in run.artifacts:
                    artifact_cls = ARTIFACT_TYPES.get(prev_stage)
                    if artifact_cls:
                        prev_artifacts[prev_stage] = artifact_cls.from_json(run.artifacts[prev_stage])

            # Run the stage
            stage_text = []
            runner = stage_runners[stage]
            try:
                async for chunk in runner(
                    client=self.client,
                    run=run,
                    prev_artifacts=prev_artifacts,
                    client_memory=client_memory,
                ):
                    stage_text.append(chunk)
                    yield json.dumps({"type": "token", "text": chunk, "stage": stage})
            except Exception as e:
                logger.exception("Stage %s failed for pipeline %s", stage, run.pipeline_id)
                run.error = f"Stage '{stage}' failed: {str(e)}"
                run.status = PipelineStatus.FAILED
                self._persist_run(run)
                yield json.dumps({"type": "error", "message": run.error, "stage": stage})
                return

            # Store stage output
            full_output = "".join(stage_text)
            run.stage_outputs[stage] = full_output

            # Emit stage complete event
            yield json.dumps({
                "type": "stage_complete",
                "stage": stage,
                "stage_index": run.current_stage_index,
                "output_length": len(full_output),
            })

            # Sync roadmap status if this pipeline is linked to a roadmap item
            try:
                from utils.content_db import update_roadmap_from_stage
                update_roadmap_from_stage(run.pipeline_id, stage)
            except Exception:
                pass  # Roadmap sync is best-effort

            # Check for approval gate
            if run.should_pause_after(stage):
                run.status = PipelineStatus.AWAITING_APPROVAL
                self._persist_run(run)
                yield json.dumps({
                    "type": "awaiting_approval",
                    "stage": stage,
                    "pipeline_id": run.pipeline_id,
                    "message": f"Stage '{stage}' complete. Approve to continue.",
                })
                return  # Pipeline pauses here — resume via approve_and_continue()

            # Advance to next stage
            run.current_stage_index += 1
            self._persist_run(run)

        # All stages complete
        run.status = PipelineStatus.COMPLETED
        self._persist_run(run)

        # Auto-capture learnings from this pipeline run
        if self.memory_store:
            self._capture_post_run_learnings(run)

        # Mark linked roadmap items as ready for approval
        try:
            from utils.content_db import mark_roadmap_ready
            mark_roadmap_ready(run.pipeline_id)
        except Exception:
            pass

        yield json.dumps({
            "type": "pipeline_complete",
            "pipeline_id": run.pipeline_id,
            "page_type": run.page_type,
            "client_name": run.client_name,
            "stages_completed": len(run.stages),
        })

    async def approve_and_continue(
        self,
        pipeline_id: str,
        stage_runners: dict,
        feedback: str = "",
    ) -> AsyncGenerator[str, None]:
        """Resume a paused pipeline after approval."""
        run = self.get_run(pipeline_id)
        if not run:
            yield json.dumps({"type": "error", "message": f"Pipeline {pipeline_id} not found"})
            return
        if run.status != PipelineStatus.AWAITING_APPROVAL:
            yield json.dumps({"type": "error", "message": f"Pipeline is {run.status.value}, not awaiting approval"})
            return

        # Store approval feedback as a learning
        if feedback and self.memory_store:
            stage = run.current_stage
            self.memory_store.save_learning(
                run.client_id,
                f"approval-feedback-{stage}-{run.pipeline_id[:8]}",
                feedback,
            )

        # Advance to next stage and continue
        run.current_stage_index += 1
        run.status = PipelineStatus.RUNNING
        self._persist_run(run)

        async for chunk in self.execute(run, stage_runners):
            yield chunk

    def _persist_run(self, run: PipelineRun) -> None:
        """Save pipeline run state to SQLite."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO pipeline_runs
                   (pipeline_id, page_type, client_id, client_name, inputs_json,
                    stages_json, approval_mode, status, current_stage_index,
                    artifacts_json, stage_outputs_json, error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.pipeline_id,
                    run.page_type,
                    run.client_id,
                    run.client_name,
                    json.dumps(run.inputs),
                    json.dumps(run.stages),
                    run.approval_mode.value,
                    run.status.value,
                    run.current_stage_index,
                    json.dumps(run.artifacts),
                    json.dumps(run.stage_outputs),
                    run.error,
                    run.created_at,
                ),
            )
            conn.commit()

    def _capture_post_run_learnings(self, run: PipelineRun) -> None:
        """Auto-capture learnings after a completed pipeline run.

        Records:
        1. Past content summary (for internal linking + dedup in future runs)
        2. QA score and key issues (for tracking quality over time)
        3. Page-type-specific patterns that worked
        """
        try:
            # 1. Track past content for internal linking and deduplication
            inputs = run.inputs
            keyword = inputs.get("keyword", inputs.get("service", ""))
            title = ""
            if "copywrite" in run.artifacts:
                content_data = json.loads(run.artifacts["copywrite"])
                title = content_data.get("h1", content_data.get("title_tag", ""))

            if keyword or title:
                self.memory_store.save_past_content_summary(
                    client_id=run.client_id,
                    page_type=run.page_type,
                    title=title,
                    keyword=keyword,
                )

            # 2. Capture QA score as a learning
            if "qa" in run.artifacts:
                qa_data = json.loads(run.artifacts["qa"])
                score = qa_data.get("overall_score", 0)
                approved = qa_data.get("approved", False)

                # Extract critical issues from QA review for future avoidance
                review_text = qa_data.get("review_text", "")
                critical_issues = []
                for line in review_text.split("\n"):
                    line_stripped = line.strip()
                    if line_stripped.startswith("**CRITICAL:") or line_stripped.startswith("- **CRITICAL"):
                        critical_issues.append(line_stripped)

                if critical_issues:
                    self.memory_store.save_learning(
                        run.client_id,
                        f"qa-issues-{run.page_type}-{run.pipeline_id[:8]}",
                        f"Score: {score}/100. Critical issues: {'; '.join(critical_issues[:3])}",
                    )

                # Track quality trend
                self.memory_store.save(
                    run.client_id,
                    "past_content",
                    f"qa-score-{run.pipeline_id[:8]}",
                    json.dumps({
                        "pipeline_id": run.pipeline_id,
                        "page_type": run.page_type,
                        "score": score,
                        "approved": approved,
                        "created_at": run.created_at,
                    }),
                )

            logger.info("Captured post-run learnings for pipeline %s (client %d)",
                        run.pipeline_id, run.client_id)

        except Exception as e:
            logger.warning("Failed to capture post-run learnings: %s", e)

    def _load_run(self, pipeline_id: str) -> Optional[PipelineRun]:
        """Load a pipeline run from SQLite."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE pipeline_id = ?",
                (pipeline_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            run = PipelineRun(
                pipeline_id=d["pipeline_id"],
                page_type=d["page_type"],
                client_id=d["client_id"],
                client_name=d["client_name"],
                inputs=json.loads(d["inputs_json"]),
                stages=json.loads(d["stages_json"]),
                approval_mode=d["approval_mode"],
            )
            run.status = PipelineStatus(d["status"])
            run.current_stage_index = d["current_stage_index"]
            run.artifacts = json.loads(d["artifacts_json"])
            run.stage_outputs = json.loads(d["stage_outputs_json"])
            run.error = d["error"]
            run.created_at = d["created_at"]
            self._active_runs[pipeline_id] = run
            return run
