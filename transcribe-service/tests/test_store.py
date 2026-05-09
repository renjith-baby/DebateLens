from datetime import datetime, timezone
from pathlib import Path

import pytest

from transcribe_service.jobs.store import InMemoryJsonStore, JobRecord
from transcribe_service.schemas import JobStatus, JobSourceInfo


def _make_record(job_id: str = "job_001") -> JobRecord:
    return JobRecord(
        job_id=job_id,
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(timezone.utc),
        source=JobSourceInfo(type="url", url="https://x.test/a.mp4"),
        engine="sarvam",
        mode="codemix",
        language="ml-IN",
        callback_url=None,
        max_speakers=None,
    )


def test_create_and_get(tmp_path: Path):
    store = InMemoryJsonStore(tmp_path / "jobs.json")
    rec = _make_record()
    store.put(rec)
    got = store.get("job_001")
    assert got is not None
    assert got.job_id == "job_001"
    assert got.status == JobStatus.QUEUED


def test_get_missing_returns_none(tmp_path: Path):
    store = InMemoryJsonStore(tmp_path / "jobs.json")
    assert store.get("nope") is None


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "jobs.json"
    store1 = InMemoryJsonStore(path)
    store1.put(_make_record("job_a"))
    store1.put(_make_record("job_b"))

    store2 = InMemoryJsonStore(path)
    assert store2.get("job_a") is not None
    assert store2.get("job_b") is not None
    assert {r.job_id for r in store2.list()} == {"job_a", "job_b"}


def test_update_status_persists(tmp_path: Path):
    path = tmp_path / "jobs.json"
    store = InMemoryJsonStore(path)
    rec = _make_record()
    store.put(rec)
    rec.status = JobStatus.RUNNING
    rec.started_at = datetime.now(timezone.utc)
    store.put(rec)

    reloaded = InMemoryJsonStore(path)
    got = reloaded.get("job_001")
    assert got is not None
    assert got.status == JobStatus.RUNNING
    assert got.started_at is not None
