from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcribe_service.engines.base import TranscriptionEngine, TranscriptionOptions

from transcribe_service.jobs.store import JobRecord, JobStore
from transcribe_service.schemas import JobStatus
from transcribe_service.sources.url import download_to_file
from transcribe_service.webhook import deliver_webhook

logger = logging.getLogger(__name__)


async def run_job(
    *,
    record: JobRecord,
    store: JobStore,
    engine: TranscriptionEngine,
    output_dir: Path,
    uploads_dir: Path,
    timeout_seconds: int,
    webhook_secret: str | None,
    webhook_timeout: float,
) -> None:
    record.status = JobStatus.RUNNING
    record.started_at = datetime.now(timezone.utc)
    store.put(record)

    try:
        if not engine.is_configured:
            raise RuntimeError(f"engine_unconfigured: {engine.name}")

        # Resolve source: URL submissions need to be downloaded first.
        if not record.audio_path:
            if record.source.type == "url" and record.source.url:
                uploads_dir.mkdir(parents=True, exist_ok=True)
                suffix = Path(record.source.url).suffix or ".bin"
                dest = uploads_dir / f"{record.job_id}{suffix}"
                await download_to_file(record.source.url, dest)
                record.audio_path = str(dest)
                store.put(record)
            else:
                raise RuntimeError("audio_path missing on record")

        options = TranscriptionOptions(
            language=record.language,
            enable_diarization=True,
            max_speakers=record.max_speakers,
            mode=record.mode,  # type: ignore[arg-type]
        )

        result = await asyncio.wait_for(
            asyncio.to_thread(engine.transcribe, record.audio_path, options),
            timeout=timeout_seconds,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / f"{record.job_id}.json"
        transcript_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        record.status = JobStatus.DONE
        record.finished_at = datetime.now(timezone.utc)
        record.transcript_path = str(transcript_path)
        store.put(record)

        if record.callback_url:
            await _send_webhook(
                record=record,
                event="job.done",
                payload={
                    "event": "job.done",
                    "job_id": record.job_id,
                    "submitted_at": record.submitted_at.isoformat(),
                    "finished_at": record.finished_at.isoformat(),
                    "transcript": result.to_dict(),
                },
                store=store,
                secret=webhook_secret,
                timeout=webhook_timeout,
            )

    except asyncio.TimeoutError:
        await _mark_failed(record, store, "timeout")
        await _maybe_send_failure_webhook(record, store, webhook_secret, webhook_timeout)
    except Exception as exc:
        logger.exception("job %s failed", record.job_id)
        await _mark_failed(record, store, f"engine_failed: {exc}")
        await _maybe_send_failure_webhook(record, store, webhook_secret, webhook_timeout)


async def _mark_failed(record: JobRecord, store: JobStore, error: str) -> None:
    record.status = JobStatus.FAILED
    record.finished_at = datetime.now(timezone.utc)
    record.error = error
    store.put(record)


async def _maybe_send_failure_webhook(
    record: JobRecord, store: JobStore, secret: str | None, timeout: float
) -> None:
    if not record.callback_url:
        return
    await _send_webhook(
        record=record,
        event="job.failed",
        payload={
            "event": "job.failed",
            "job_id": record.job_id,
            "error": record.error,
        },
        store=store,
        secret=secret,
        timeout=timeout,
    )


async def _send_webhook(
    *,
    record: JobRecord,
    event: str,
    payload: dict[str, Any],
    store: JobStore,
    secret: str | None,
    timeout: float,
) -> None:
    assert record.callback_url is not None
    ok, attempts = await deliver_webhook(
        url=record.callback_url,
        event=event,
        job_id=record.job_id,
        body=payload,
        secret=secret,
        timeout=timeout,
    )
    record.callback_delivered = ok
    record.callback_attempts = (record.callback_attempts or 0) + attempts
    store.put(record)
