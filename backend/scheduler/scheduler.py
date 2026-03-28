"""
Pipeline Scheduler — APScheduler integration for automated content production.

Runs inside the FastAPI process. Checks for due jobs and executes pipelines
on their configured schedules. Inspired by Hermes Agent's cron system but
simpler — no file locks needed since we run in a single process.

Usage:
    from scheduler.scheduler import PipelineScheduler
    scheduler = PipelineScheduler(pipeline_engine, db_connect_fn)
    scheduler.start()  # Call on FastAPI startup
    scheduler.stop()   # Call on FastAPI shutdown
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scheduler.jobs import (
    _parse_schedule,
    get_due_jobs,
    get_scheduled_job,
    list_scheduled_jobs,
    mark_job_run,
)

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Manages scheduled pipeline executions via APScheduler."""

    def __init__(self, pipeline_engine, db_connect_fn, stage_runners: dict):
        self.engine = pipeline_engine
        self._connect = db_connect_fn
        self.stage_runners = stage_runners
        self.scheduler = AsyncIOScheduler()
        self._loaded_jobs: set[str] = set()

    def start(self) -> None:
        """Start the scheduler and load all existing jobs."""
        self.scheduler.start()
        self._sync_jobs()
        # Also add a periodic job to check for new/changed scheduled jobs
        self.scheduler.add_job(
            self._sync_jobs,
            trigger=IntervalTrigger(minutes=5),
            id="_sync_scheduled_jobs",
            replace_existing=True,
        )
        logger.info("Pipeline scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Pipeline scheduler stopped")

    def _sync_jobs(self) -> None:
        """Load scheduled jobs from DB and register them with APScheduler."""
        with self._connect() as conn:
            jobs = list_scheduled_jobs(conn)

        current_ids = set()
        for job in jobs:
            job_id = job["id"]
            current_ids.add(job_id)

            if not job.get("enabled"):
                # Remove disabled jobs from scheduler
                if job_id in self._loaded_jobs:
                    try:
                        self.scheduler.remove_job(job_id)
                    except Exception:
                        pass
                    self._loaded_jobs.discard(job_id)
                continue

            # Parse schedule into APScheduler trigger
            parsed = _parse_schedule(job.get("schedule", ""))
            if not parsed:
                logger.warning("Invalid schedule for job %s: %s", job_id, job.get("schedule"))
                continue

            trigger_type = parsed.pop("trigger")
            if trigger_type == "cron":
                trigger = CronTrigger(**parsed)
            elif trigger_type == "interval":
                trigger = IntervalTrigger(**parsed)
            else:
                continue

            # Add or update the job in APScheduler
            self.scheduler.add_job(
                self._execute_scheduled_job,
                trigger=trigger,
                id=job_id,
                args=[job_id],
                replace_existing=True,
                name=job.get("name", job_id),
            )
            self._loaded_jobs.add(job_id)

        # Remove jobs that no longer exist in DB
        for old_id in self._loaded_jobs - current_ids:
            try:
                self.scheduler.remove_job(old_id)
            except Exception:
                pass
        self._loaded_jobs = self._loaded_jobs & current_ids

        logger.info("Synced %d scheduled jobs (%d active)",
                     len(jobs), len(self._loaded_jobs))

    async def _execute_scheduled_job(self, job_id: str) -> None:
        """Execute a scheduled pipeline job."""
        with self._connect() as conn:
            job = get_scheduled_job(conn, job_id)

        if not job or not job.get("enabled"):
            return

        logger.info("Executing scheduled job: %s (%s for client %d)",
                     job["name"], job["pipeline_type"], job["client_id"])

        try:
            # Resolve client name
            from utils.db import get_client as db_get_client
            client = db_get_client(job["client_id"])
            client_name = client.get("name", "") if client else ""

            # Get page type config for stages
            from pipeline.page_types.service_page import PAGE_CONFIG as SP
            from pipeline.page_types.location_page import PAGE_CONFIG as LP
            from pipeline.page_types.blog_post import PAGE_CONFIG as BP
            configs = {
                "service-page": SP,
                "location-page": LP,
                "blog-post": BP,
            }
            config = configs.get(job["pipeline_type"])
            if not config:
                logger.error("Unknown pipeline type: %s", job["pipeline_type"])
                return

            inputs = json.loads(job["inputs_json"]) if isinstance(job.get("inputs_json"), str) else job.get("inputs", {})

            # Create and execute the pipeline
            run = self.engine.create_run(
                page_type=job["pipeline_type"],
                client_id=job["client_id"],
                client_name=client_name,
                inputs=inputs,
                stages=config["stages"],
                approval_mode=job.get("approval_mode", "autopilot"),
            )

            # Execute (consume the async generator without streaming)
            async for _ in self.engine.execute(run, self.stage_runners):
                pass  # Scheduled jobs don't stream — they run silently

            # Record the execution
            with self._connect() as conn:
                mark_job_run(conn, job_id, run.pipeline_id, run.status.value)

            logger.info("Scheduled job %s completed: pipeline %s, status %s",
                        job_id, run.pipeline_id, run.status.value)

        except Exception as e:
            logger.exception("Scheduled job %s failed: %s", job_id, e)
            with self._connect() as conn:
                mark_job_run(conn, job_id, "", f"failed: {str(e)[:200]}")

    def add_job_from_db(self, job_id: str) -> None:
        """Immediately register a newly created job (called after API create)."""
        self._sync_jobs()

    def remove_job(self, job_id: str) -> None:
        """Remove a job from the scheduler."""
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass
        self._loaded_jobs.discard(job_id)
