import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_running_jobs_marked_failed_on_boot(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    jobs_path = tmp_path / "output" / "jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "job_id": "job_stuck",
                        "status": "running",
                        "submitted_at": datetime.now(timezone.utc).isoformat(),
                        "source": {"type": "url", "url": "https://media.test/x.mp4"},
                        "engine": "sarvam",
                        "mode": "codemix",
                        "language": "ml-IN",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from transcribe_service.config import Settings, get_settings

    get_settings.cache_clear()

    from transcribe_service.main import app, lifespan

    monkeypatch.setattr(
        "transcribe_service.main.get_settings",
        lambda: Settings(
            output_dir=tmp_path / "output",
            uploads_dir=tmp_path / "uploads",
            job_store_path=jobs_path,
            max_concurrent_jobs=1,
        ),
    )

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/jobs/job_stuck")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"] == "crash_recovery"
    for key in ("settings", "store", "submit_job", "pool"):
        if hasattr(app.state, key):
            delattr(app.state, key)
