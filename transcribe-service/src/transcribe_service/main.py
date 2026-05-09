from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from transcriber.config import GoogleConfig, SarvamConfig

from transcribe_service.api import health as health_api
from transcribe_service.api import jobs as jobs_api
from transcribe_service.config import Settings, get_settings
from transcribe_service.jobs.runner import run_job
from transcribe_service.jobs.store import InMemoryJsonStore, JobRecord
from transcribe_service.jobs.worker import WorkerPool
from transcribe_service.schemas import JobStatus

logger = logging.getLogger(__name__)


def _build_engine(name: str, settings: Settings):
    if name == "sarvam":
        from transcriber.engines.sarvam import SarvamEngine

        return SarvamEngine(SarvamConfig(api_key=settings.sarvam_api_key))
    if name == "google":
        from transcriber.engines.google_stt import GoogleEngine

        return GoogleEngine(
            GoogleConfig(
                project_id=settings.google_cloud_project,
                location=settings.google_cloud_location,
                credentials_path=settings.google_application_credentials,
            )
        )
    raise ValueError(f"unknown engine: {name}")


def _make_submitter(app: FastAPI):
    async def submit(job_id: str) -> None:
        store = app.state.store
        settings = app.state.settings
        pool: WorkerPool = app.state.pool
        rec: JobRecord | None = store.get(job_id)
        if rec is None:
            logger.warning("submit: job %s not found", job_id)
            return
        engine = _build_engine(rec.engine, settings)
        await pool.submit(
            run_job(
                record=rec,
                store=store,
                engine=engine,
                output_dir=settings.output_dir,
                uploads_dir=settings.uploads_dir,
                timeout_seconds=settings.job_timeout_seconds,
                webhook_secret=settings.webhook_secret,
                webhook_timeout=settings.webhook_timeout_seconds,
            )
        )

    return submit


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = getattr(app.state, "settings", None) or get_settings()
    app.state.settings = settings

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    store = getattr(app.state, "store", None) or InMemoryJsonStore(settings.job_store_path)
    app.state.store = store

    # Crash recovery: any RUNNING job at boot is unrecoverable.
    requeue: list[str] = []
    for rec in list(store.list()):
        if rec.status == JobStatus.RUNNING:
            rec.status = JobStatus.FAILED
            rec.error = "crash_recovery"
            rec.finished_at = datetime.now(timezone.utc)
            store.put(rec)
        elif rec.status == JobStatus.QUEUED:
            requeue.append(rec.job_id)

    if not getattr(app.state, "pool", None):
        pool = WorkerPool(concurrency=settings.max_concurrent_jobs)
        await pool.start()
        app.state.pool = pool

    if not getattr(app.state, "submit_job", None):
        app.state.submit_job = _make_submitter(app)

    for job_id in requeue:
        await app.state.submit_job(job_id)

    try:
        yield
    finally:
        pool = getattr(app.state, "pool", None)
        if pool is not None:
            await pool.stop()


app = FastAPI(title="transcribe-service", version="0.1.0", lifespan=lifespan)
app.include_router(jobs_api.router)
app.include_router(health_api.router)
