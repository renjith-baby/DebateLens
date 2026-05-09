from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from ulid import ULID

from transcribe_service.jobs.store import JobRecord
from transcribe_service.schemas import (
    JobResponse,
    JobSourceInfo,
    JobStatus,
    JobSubmitAck,
    JobUrlRequest,
)
from transcribe_service.sources.upload import save_upload_stream

router = APIRouter()


def _new_job_id() -> str:
    return f"job_{ULID()}"


def _record_to_response(rec: JobRecord) -> JobResponse:
    transcript_url = (
        f"/jobs/{rec.job_id}/transcript" if rec.status == JobStatus.DONE else None
    )
    return JobResponse(
        job_id=rec.job_id,
        status=rec.status,
        submitted_at=rec.submitted_at,
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        error=rec.error,
        source=rec.source,
        engine=rec.engine,  # type: ignore[arg-type]
        mode=rec.mode,  # type: ignore[arg-type]
        callback_url=rec.callback_url,
        callback_delivered=rec.callback_delivered,
        callback_attempts=rec.callback_attempts,
        transcript_url=transcript_url,
    )


@router.post("/jobs", response_model=JobSubmitAck, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    request: Request,
    file: Annotated[UploadFile | None, File()] = None,
    source_url: Annotated[str | None, Form()] = None,
    callback_url: Annotated[str | None, Form()] = None,
    engine: Annotated[str, Form()] = "sarvam",
    mode: Annotated[str, Form()] = "codemix",
    language: Annotated[str, Form()] = "ml-IN",
    max_speakers: Annotated[int | None, Form()] = None,
):
    settings = request.app.state.settings
    store = request.app.state.store
    submit = request.app.state.submit_job

    content_type = request.headers.get("content-type", "")

    # JSON body path
    if content_type.startswith("application/json"):
        raw = await request.json()
        try:
            body = JobUrlRequest.model_validate(raw)
        except Exception as exc:
            raise HTTPException(400, f"invalid_input: {exc}") from exc
        job_id = _new_job_id()
        rec = JobRecord(
            job_id=job_id,
            status=JobStatus.QUEUED,
            submitted_at=datetime.now(timezone.utc),
            source=JobSourceInfo(type="url", url=str(body.source_url)),
            engine=body.engine,
            mode=body.mode,
            language=body.language,
            max_speakers=body.max_speakers,
            callback_url=str(body.callback_url) if body.callback_url else None,
        )
        store.put(rec)
        await submit(job_id)
        return JobSubmitAck(job_id=job_id, status=rec.status, submitted_at=rec.submitted_at)

    # Multipart path
    if file is None and not source_url:
        raise HTTPException(400, "invalid_input: provide file or source_url")
    if file is not None and source_url:
        raise HTTPException(400, "invalid_input: provide either file or source_url, not both")

    job_id = _new_job_id()
    audio_path: str | None = None
    source_info: JobSourceInfo

    if file is not None:
        suffix = Path(file.filename or "input").suffix or ".bin"
        dest = Path(settings.uploads_dir) / f"{job_id}{suffix}"

        async def stream():
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

        await save_upload_stream(stream(), dest)
        audio_path = str(dest)
        source_info = JobSourceInfo(type="upload", filename=file.filename)
    else:
        assert source_url is not None
        source_info = JobSourceInfo(type="url", url=source_url)

    rec = JobRecord(
        job_id=job_id,
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(timezone.utc),
        source=source_info,
        engine=engine,
        mode=mode,
        language=language,
        max_speakers=max_speakers,
        callback_url=callback_url,
        audio_path=audio_path,
    )
    store.put(rec)
    await submit(job_id)
    return JobSubmitAck(job_id=job_id, status=rec.status, submitted_at=rec.submitted_at)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request):
    rec = request.app.state.store.get(job_id)
    if rec is None:
        raise HTTPException(404, "not_found")
    return _record_to_response(rec)


@router.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: str, request: Request):
    rec = request.app.state.store.get(job_id)
    if rec is None:
        raise HTTPException(404, "not_found")
    if rec.status != JobStatus.DONE or not rec.transcript_path:
        raise HTTPException(404, "transcript_not_ready")
    path = Path(rec.transcript_path)
    if not path.exists():
        raise HTTPException(410, "transcript_missing")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))
