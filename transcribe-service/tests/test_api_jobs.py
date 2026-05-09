import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_with_state(tmp_path, monkeypatch):
    """Fresh FastAPI app whose state holds a temp store + a stub submitter."""
    monkeypatch.chdir(tmp_path)
    from transcribe_service.config import get_settings, Settings
    from transcribe_service.jobs.store import InMemoryJsonStore
    from transcribe_service.main import app

    get_settings.cache_clear()
    settings = Settings(
        output_dir=tmp_path / "output",
        uploads_dir=tmp_path / "uploads",
        job_store_path=tmp_path / "output" / "jobs.json",
    )
    app.state.settings = settings
    app.state.store = InMemoryJsonStore(settings.job_store_path)

    submitted: list[str] = []

    async def fake_submit(job_id: str) -> None:
        submitted.append(job_id)

    app.state.submit_job = fake_submit
    app.state.submitted = submitted
    yield app
    # Reset module-level app.state so subsequent tests start clean.
    for key in ("settings", "store", "submit_job", "submitted", "pool"):
        if hasattr(app.state, key):
            delattr(app.state, key)


@pytest.mark.asyncio
async def test_post_jobs_url(app_with_state):
    transport = ASGITransport(app=app_with_state)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/jobs",
            json={
                "source_url": "https://media.test/x.mp4",
                "callback_url": "https://hook.test/in",
                "engine": "sarvam",
                "mode": "codemix",
            },
        )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    assert app_with_state.state.submitted == [body["job_id"]]


@pytest.mark.asyncio
async def test_post_jobs_rejects_no_input(app_with_state):
    transport = ASGITransport(app=app_with_state)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/jobs", json={})
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_post_jobs_upload(app_with_state, tmp_path):
    transport = ASGITransport(app=app_with_state)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/jobs",
            files={"file": ("x.mp3", b"FAKE", "audio/mpeg")},
            data={"engine": "sarvam", "mode": "codemix"},
        )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    saved = list((tmp_path / "uploads").iterdir())
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_get_jobs_id(app_with_state):
    transport = ASGITransport(app=app_with_state)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/jobs", json={"source_url": "https://media.test/x.mp4"})
        job_id = r.json()["job_id"]
        r2 = await ac.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_get_transcript_404_until_done(app_with_state):
    transport = ASGITransport(app=app_with_state)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/jobs", json={"source_url": "https://media.test/x.mp4"})
        job_id = r.json()["job_id"]
        r2 = await ac.get(f"/jobs/{job_id}/transcript")
    assert r2.status_code == 404
