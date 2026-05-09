import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from transcribe_service.engines.base import TranscriptionOptions
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult


class FakeEngine:
    name = "fake"
    is_configured = True

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        return TranscriptResult(
            segments=[Segment(speaker="1", text="hello", start_time=0.0, end_time=1.0)],
            metadata=TranscriptMetadata(
                engine="fake", model="m", language=options.language, source_file=audio_path
            ),
        )


@pytest.mark.asyncio
async def test_upload_to_done_with_webhook(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from transcribe_service.config import Settings, get_settings

    get_settings.cache_clear()
    settings = Settings(
        output_dir=tmp_path / "output",
        uploads_dir=tmp_path / "uploads",
        job_store_path=tmp_path / "output" / "jobs.json",
        max_concurrent_jobs=1,
    )

    from transcribe_service.main import app, lifespan

    monkeypatch.setattr("transcribe_service.main.get_settings", lambda: settings)
    monkeypatch.setattr(
        "transcribe_service.main._build_engine", lambda name, s: FakeEngine()
    )

    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://hook.test/in").mock(return_value=httpx.Response(200))
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.post(
                    "/jobs",
                    files={"file": ("x.wav", b"FAKE", "audio/wav")},
                    data={"engine": "sarvam", "mode": "codemix", "callback_url": "https://hook.test/in"},
                )
                assert r.status_code == 202
                job_id = r.json()["job_id"]

                # Poll until done
                for _ in range(40):
                    rr = await ac.get(f"/jobs/{job_id}")
                    if rr.json()["status"] in ("done", "failed"):
                        break
                    await asyncio.sleep(0.05)

                assert rr.json()["status"] == "done"

                tr = await ac.get(f"/jobs/{job_id}/transcript")
                assert tr.status_code == 200
                data = tr.json()
                assert data["segments"][0]["text"] == "hello"

    transcript_file = settings.output_dir / f"{job_id}.json"
    assert transcript_file.exists()
    persisted = json.loads(transcript_file.read_text(encoding="utf-8"))
    assert persisted["full_text"].startswith("[1] hello")
    for key in ("settings", "store", "submit_job", "pool"):
        if hasattr(app.state, key):
            delattr(app.state, key)
