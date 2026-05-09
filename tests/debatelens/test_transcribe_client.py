import asyncio

import httpx
import pytest
import respx

from debatelens.transcribe_client import TranscribeClient
from debatelens.models import Transcript


@pytest.mark.asyncio
async def test_submit_url_returns_job_id():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.post("/jobs").respond(202, json={
            "job_id": "j-1",
            "status": "queued",
            "submitted_at": "2026-05-09T00:00:00Z",
        })
        c = TranscribeClient(base_url="http://localhost:8080")
        job_id = await c.submit_url(url="https://youtu.be/abc")
    assert job_id == "j-1"


@pytest.mark.asyncio
async def test_poll_until_done_returns_transcript():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-1").mock(side_effect=[
            httpx.Response(200, json={"job_id": "j-1", "status": "running",
                                       "submitted_at": "2026-05-09T00:00:00Z",
                                       "engine": "sarvam", "mode": "codemix"}),
            httpx.Response(200, json={"job_id": "j-1", "status": "done",
                                       "submitted_at": "2026-05-09T00:00:00Z",
                                       "engine": "sarvam", "mode": "codemix"}),
        ])
        mock.get("/jobs/j-1/transcript").respond(200, json={
            "segments": [
                {"speaker": "1", "text": "hi", "start_time": 0.0, "end_time": 1.0}
            ],
            "metadata": {"engine": "sarvam", "model": "saaras:v3", "language": "ml-IN", "source_file": "x"}
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        transcript = await c.wait_for_transcript("j-1", timeout_seconds=5)

    assert isinstance(transcript, Transcript)
    assert len(transcript.segments) == 1
    assert transcript.segments[0].text == "hi"


@pytest.mark.asyncio
async def test_poll_raises_on_failed():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-2").respond(200, json={
            "job_id": "j-2", "status": "failed", "error": "bad",
            "submitted_at": "2026-05-09T00:00:00Z",
            "engine": "sarvam", "mode": "codemix",
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        with pytest.raises(RuntimeError, match="bad"):
            await c.wait_for_transcript("j-2", timeout_seconds=2)


@pytest.mark.asyncio
async def test_poll_raises_on_timeout():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-3").respond(200, json={
            "job_id": "j-3", "status": "running",
            "submitted_at": "2026-05-09T00:00:00Z",
            "engine": "sarvam", "mode": "codemix",
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        with pytest.raises(asyncio.TimeoutError):
            await c.wait_for_transcript("j-3", timeout_seconds=0.05)
