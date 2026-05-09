from pathlib import Path

from transcribe_service.config import Settings


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAX_CONCURRENT_JOBS", raising=False)
    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8080
    assert s.max_concurrent_jobs == 2
    assert s.job_timeout_seconds == 1800
    assert s.output_dir == Path("./output")
    assert s.uploads_dir == Path("./uploads")
    assert s.webhook_secret is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_JOBS", "5")
    monkeypatch.setenv("WEBHOOK_SECRET", "shhh")
    s = Settings()
    assert s.max_concurrent_jobs == 5
    assert s.webhook_secret == "shhh"
