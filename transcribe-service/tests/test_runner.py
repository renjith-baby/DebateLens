from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from transcriber.engines.base import TranscriptionOptions
from transcriber.output.models import Segment, TranscriptMetadata, TranscriptResult

from transcribe_service.jobs.runner import run_job
from transcribe_service.jobs.store import InMemoryJsonStore, JobRecord
from transcribe_service.schemas import JobSourceInfo, JobStatus


class FakeEngine:
    name = "fake"
    is_configured = True

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        if self._raises:
            raise self._raises
        return TranscriptResult(
            segments=[Segment(speaker="1", text="hi", start_time=0.0, end_time=1.0)],
            metadata=TranscriptMetadata(
                engine="fake", model="m", language=options.language, source_file=audio_path
            ),
        )


def _make_audio(tmp_path: Path) -> Path:
    p = tmp_path / "uploads" / "job_001.wav"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00" * 16)
    return p


def _make_record(audio: Path) -> JobRecord:
    return JobRecord(
        job_id="job_001",
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(timezone.utc),
        source=JobSourceInfo(type="upload", filename=audio.name),
        engine="fake",
        mode="codemix",
        language="ml-IN",
        audio_path=str(audio),
    )


@pytest.mark.asyncio
async def test_runner_happy_path(tmp_path: Path):
    audio = _make_audio(tmp_path)
    store = InMemoryJsonStore(tmp_path / "jobs.json")
    rec = _make_record(audio)
    store.put(rec)

    out_dir = tmp_path / "output"
    uploads = tmp_path / "uploads"
    await run_job(
        record=rec,
        store=store,
        engine=FakeEngine(),
        output_dir=out_dir,
        uploads_dir=uploads,
        timeout_seconds=30,
        webhook_secret=None,
        webhook_timeout=5,
    )

    final = store.get("job_001")
    assert final is not None
    assert final.status == JobStatus.DONE
    assert final.transcript_path is not None
    assert Path(final.transcript_path).exists()


@pytest.mark.asyncio
async def test_runner_engine_failure_marks_failed(tmp_path: Path):
    audio = _make_audio(tmp_path)
    store = InMemoryJsonStore(tmp_path / "jobs.json")
    rec = _make_record(audio)
    store.put(rec)

    out_dir = tmp_path / "output"
    uploads = tmp_path / "uploads"
    await run_job(
        record=rec,
        store=store,
        engine=FakeEngine(raises=RuntimeError("boom")),
        output_dir=out_dir,
        uploads_dir=uploads,
        timeout_seconds=30,
        webhook_secret=None,
        webhook_timeout=5,
    )

    final = store.get("job_001")
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert "boom" in (final.error or "")


@pytest.mark.asyncio
async def test_runner_downloads_url_source(tmp_path: Path):
    """URL submissions have audio_path=None; runner must download before transcribing."""
    store = InMemoryJsonStore(tmp_path / "jobs.json")
    rec = JobRecord(
        job_id="job_url",
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(timezone.utc),
        source=JobSourceInfo(type="url", url="https://media.test/clip.mp4"),
        engine="fake",
        mode="codemix",
        language="ml-IN",
    )
    store.put(rec)

    out_dir = tmp_path / "output"
    uploads = tmp_path / "uploads"
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://media.test/clip.mp4").mock(
            return_value=httpx.Response(200, content=b"DOWNLOADED_BYTES")
        )
        await run_job(
            record=rec,
            store=store,
            engine=FakeEngine(),
            output_dir=out_dir,
            uploads_dir=uploads,
            timeout_seconds=30,
            webhook_secret=None,
            webhook_timeout=5,
        )

    final = store.get("job_url")
    assert final is not None
    assert final.status == JobStatus.DONE
    assert final.audio_path is not None
    assert Path(final.audio_path).read_bytes() == b"DOWNLOADED_BYTES"
