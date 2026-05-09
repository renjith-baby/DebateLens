# Transcribe-Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `DebateLens/transcribe-service/` — a FastAPI service that wraps the existing `transcribing-module` library, accepts batch transcription jobs (file upload or URL), runs them in a bounded async worker pool, persists transcripts to disk, and delivers results via webhook.

**Architecture:** Single uvicorn process. FastAPI app + an `asyncio.Semaphore`-bounded worker pool sharing the same event loop. `JobStore` is an interface; the only impl is `InMemoryJsonStore` (dict + JSON file mirror) so a Redis impl can swap in later. `transcriber` library is imported as a local editable install. Synchronous engine calls run in `asyncio.to_thread` to avoid blocking the loop.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, Pydantic v2 + Pydantic Settings, httpx (async), yt-dlp (URL ingest for YouTube), pytest + pytest-asyncio + httpx.AsyncClient, Docker.

**Spec:** `docs/superpowers/specs/2026-05-09-transcribe-service-design.md`

**Commit policy:** Per project preference, do **not** commit between tasks. Stage nothing as you go; the user will commit once the whole plan is executed and verified. The "Commit" steps shown in standard plan templates are intentionally omitted here.

---

## File Structure

```
DebateLens/transcribe-service/
  pyproject.toml                            # Task 1
  README.md                                 # Task 14
  .env.example                              # Task 14
  .gitignore                                # Task 1
  Dockerfile                                # Task 13
  docker-compose.yml                        # Task 13
  src/transcribe_service/
    __init__.py                             # Task 1
    main.py                                 # Task 1, extended in Task 10
    config.py                               # Task 2
    schemas.py                              # Task 3
    api/
      __init__.py                           # Task 9
      jobs.py                               # Task 9
      health.py                             # Task 9
    jobs/
      __init__.py                           # Task 4
      store.py                              # Task 4
      runner.py                             # Task 7
      worker.py                             # Task 8
    sources/
      __init__.py                           # Task 5
      upload.py                             # Task 5
      url.py                                # Task 5
    webhook.py                              # Task 6
  tests/
    __init__.py                             # Task 1
    conftest.py                             # Task 1
    test_smoke.py                           # Task 1
    test_config.py                          # Task 2
    test_schemas.py                         # Task 3
    test_store.py                           # Task 4
    test_sources.py                         # Task 5
    test_webhook.py                         # Task 6
    test_runner.py                          # Task 7
    test_worker.py                          # Task 8
    test_api_jobs.py                        # Task 9
    test_recovery.py                        # Task 11
    test_e2e.py                             # Task 12
```

---

## Task 1: Scaffold project + install editable transcriber + smoke test

**Files:**
- Create: `transcribe-service/pyproject.toml`
- Create: `transcribe-service/.gitignore`
- Create: `transcribe-service/src/transcribe_service/__init__.py`
- Create: `transcribe-service/src/transcribe_service/main.py`
- Create: `transcribe-service/tests/__init__.py`
- Create: `transcribe-service/tests/conftest.py`
- Create: `transcribe-service/tests/test_smoke.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "transcribe-service"
version = "0.1.0"
description = "FastAPI batch service wrapping the transcribing-module"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
    "yt-dlp>=2024.4.9",
    "python-ulid>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "respx>=0.21",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
*.egg-info/
output/
uploads/
.env
.tmp/
```

- [ ] **Step 3: Create empty package files**

`src/transcribe_service/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 4: Create minimal FastAPI app in `main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="transcribe-service", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from transcribe_service.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 6: Write smoke test**

`tests/test_smoke.py`:
```python
import pytest


@pytest.mark.asyncio
async def test_healthz_returns_ok(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 7: Set up venv and install both packages editably**

Run from `transcribe-service/`:
```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e ../../transcribing-module
pip install -e ".[dev]"
```

Expected: both packages install without error. `pip list` shows `transcriber 0.1.0` and `transcribe-service 0.1.0`.

- [ ] **Step 8: Run smoke test**

```bash
pytest tests/test_smoke.py -v
```

Expected: 1 passed.

---

## Task 2: Config module (Pydantic Settings, env-driven)

**Files:**
- Create: `transcribe-service/src/transcribe_service/config.py`
- Create: `transcribe-service/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_config.py -v
```
Expected: ImportError or ModuleNotFoundError — `transcribe_service.config` not yet defined.

- [ ] **Step 3: Implement `config.py`**

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    max_concurrent_jobs: int = 2
    job_timeout_seconds: int = 1800

    output_dir: Path = Field(default=Path("./output"))
    uploads_dir: Path = Field(default=Path("./uploads"))
    job_store_path: Path = Field(default=Path("./output/jobs.json"))

    webhook_secret: str | None = None
    webhook_timeout_seconds: int = 10

    sarvam_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "asia-southeast1"
    google_application_credentials: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_config.py -v
```
Expected: 2 passed.

---

## Task 3: Pydantic schemas (request/response models)

**Files:**
- Create: `transcribe-service/src/transcribe_service/schemas.py`
- Create: `transcribe-service/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

`tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError

from transcribe_service.schemas import (
    JobStatus,
    JobUrlRequest,
    JobResponse,
)


def test_url_request_minimal():
    req = JobUrlRequest(source_url="https://youtu.be/abc")
    assert req.engine == "sarvam"
    assert req.mode == "codemix"
    assert req.language == "ml-IN"
    assert req.callback_url is None


def test_url_request_rejects_non_http():
    with pytest.raises(ValidationError):
        JobUrlRequest(source_url="ftp://example.com/x.mp4")


def test_job_response_round_trip():
    resp = JobResponse(
        job_id="job_01HW9",
        status=JobStatus.QUEUED,
        submitted_at="2026-05-09T17:55:00Z",
    )
    assert resp.status == JobStatus.QUEUED
    dumped = resp.model_dump()
    assert dumped["status"] == "queued"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_schemas.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `schemas.py`**

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


Engine = Literal["sarvam", "google"]
Mode = Literal["transcribe", "translate", "verbatim", "translit", "codemix"]


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobUrlRequest(BaseModel):
    source_url: HttpUrl
    callback_url: HttpUrl | None = None
    engine: Engine = "sarvam"
    mode: Mode = "codemix"
    language: str = "ml-IN"
    max_speakers: int | None = Field(default=None, ge=1, le=10)


class JobSourceInfo(BaseModel):
    type: Literal["upload", "url"]
    url: str | None = None
    filename: str | None = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    source: JobSourceInfo | None = None
    engine: Engine = "sarvam"
    mode: Mode = "codemix"
    callback_url: str | None = None
    callback_delivered: bool = False
    callback_attempts: int = 0
    transcript_url: str | None = None


class JobSubmitAck(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime


class ErrorResponse(BaseModel):
    error: str
    message: str
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_schemas.py -v
```
Expected: 3 passed.

---

## Task 4: JobStore (in-memory dict + JSON file mirror)

**Files:**
- Create: `transcribe-service/src/transcribe_service/jobs/__init__.py` (empty)
- Create: `transcribe-service/src/transcribe_service/jobs/store.py`
- Create: `transcribe-service/tests/test_store.py`

- [ ] **Step 1: Write failing tests**

`tests/test_store.py`:
```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_store.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `jobs/__init__.py`**

Create empty file.

- [ ] **Step 4: Implement `jobs/store.py`**

```python
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from pydantic import BaseModel

from transcribe_service.schemas import JobSourceInfo, JobStatus


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    source: JobSourceInfo
    engine: str
    mode: str
    language: str
    max_speakers: int | None = None
    callback_url: str | None = None
    callback_delivered: bool = False
    callback_attempts: int = 0
    transcript_path: str | None = None
    audio_path: str | None = None


class JobStore(Protocol):
    def get(self, job_id: str) -> JobRecord | None: ...
    def put(self, record: JobRecord) -> None: ...
    def list(self) -> Iterable[JobRecord]: ...


class InMemoryJsonStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._records: dict[str, JobRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for raw in data.get("records", []):
            rec = JobRecord.model_validate(raw)
            self._records[rec.job_id] = rec

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": [r.model_dump(mode="json") for r in self._records.values()],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def put(self, record: JobRecord) -> None:
        with self._lock:
            self._records[record.job_id] = record
            self._flush()

    def list(self) -> list[JobRecord]:
        with self._lock:
            return list(self._records.values())
```

- [ ] **Step 5: Run, expect pass**

```bash
pytest tests/test_store.py -v
```
Expected: 4 passed.

---

## Task 5: Sources — upload save + URL download (httpx + yt-dlp)

**Files:**
- Create: `transcribe-service/src/transcribe_service/sources/__init__.py` (empty)
- Create: `transcribe-service/src/transcribe_service/sources/upload.py`
- Create: `transcribe-service/src/transcribe_service/sources/url.py`
- Create: `transcribe-service/tests/test_sources.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sources.py`:
```python
from pathlib import Path

import httpx
import pytest
import respx

from transcribe_service.sources.upload import save_upload_stream
from transcribe_service.sources.url import (
    UnsupportedSourceError,
    download_to_file,
    is_youtube_url,
)


@pytest.mark.asyncio
async def test_save_upload_stream(tmp_path: Path):
    async def chunks():
        yield b"abc"
        yield b"def"

    out = tmp_path / "u.bin"
    written = await save_upload_stream(chunks(), out)
    assert written == out
    assert out.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_direct_media(tmp_path: Path):
    async with respx.mock(assert_all_called=True):
        respx.get("https://media.test/x.mp4").mock(
            return_value=httpx.Response(200, content=b"BINARY", headers={"content-type": "video/mp4"})
        )
        out = await download_to_file("https://media.test/x.mp4", tmp_path / "x.mp4")
        assert out.read_bytes() == b"BINARY"


@pytest.mark.asyncio
async def test_download_rejects_ftp():
    with pytest.raises(UnsupportedSourceError):
        await download_to_file("ftp://x.test/a.mp4", Path("/tmp/x"))


def test_is_youtube_url():
    assert is_youtube_url("https://youtu.be/abc")
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert not is_youtube_url("https://media.test/a.mp4")
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_sources.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `sources/__init__.py`**

Empty file.

- [ ] **Step 4: Implement `sources/upload.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator


async def save_upload_stream(stream: AsyncIterator[bytes], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        async for chunk in stream:
            if chunk:
                f.write(chunk)
    return dest
```

- [ ] **Step 5: Implement `sources/url.py`**

```python
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx


class UnsupportedSourceError(ValueError):
    pass


class DownloadError(RuntimeError):
    pass


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in YOUTUBE_HOSTS


async def download_to_file(url: str, dest: Path, timeout: float = 600.0) -> Path:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsupportedSourceError(f"unsupported scheme: {parsed.scheme}")

    if is_youtube_url(url):
        return await _download_youtube(url, dest)

    return await _download_direct(url, dest, timeout)


async def _download_direct(url: str, dest: Path, timeout: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise DownloadError(f"download_failed: HTTP {resp.status_code}")
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
    return dest


async def _download_youtube(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    return await asyncio.to_thread(_yt_dlp_download, url, dest)


def _yt_dlp_download(url: str, dest: Path) -> Path:
    import yt_dlp

    template = str(dest.with_suffix("")) + ".%(ext)s"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        produced = Path(ydl.prepare_filename(info))
    if produced != dest:
        produced.replace(dest)
    return dest
```

- [ ] **Step 6: Run, expect pass**

```bash
pytest tests/test_sources.py -v
```
Expected: 4 passed.

---

## Task 6: Webhook delivery with HMAC signature

**Files:**
- Create: `transcribe-service/src/transcribe_service/webhook.py`
- Create: `transcribe-service/tests/test_webhook.py`

- [ ] **Step 1: Write failing tests**

`tests/test_webhook.py`:
```python
import hashlib
import hmac

import httpx
import pytest
import respx

from transcribe_service.webhook import deliver_webhook


@pytest.mark.asyncio
async def test_deliver_signs_with_hmac():
    async with respx.mock(assert_all_called=True) as mock:
        route = mock.post("https://hook.test/in").mock(return_value=httpx.Response(200))

        ok, attempts = await deliver_webhook(
            url="https://hook.test/in",
            event="job.done",
            job_id="job_001",
            body={"event": "job.done", "job_id": "job_001"},
            secret="topsecret",
            timeout=5.0,
        )
        assert ok is True
        assert attempts == 1
        request = route.calls.last.request
        sig = request.headers["x-transcribe-signature"]
        assert sig.startswith("sha256=")
        expected = hmac.new(b"topsecret", request.content, hashlib.sha256).hexdigest()
        assert sig == f"sha256={expected}"
        assert request.headers["x-transcribe-event"] == "job.done"
        assert request.headers["x-transcribe-job-id"] == "job_001"


@pytest.mark.asyncio
async def test_deliver_returns_false_on_5xx():
    async with respx.mock():
        respx.post("https://hook.test/in").mock(return_value=httpx.Response(503))
        ok, attempts = await deliver_webhook(
            url="https://hook.test/in",
            event="job.done",
            job_id="job_001",
            body={},
            secret=None,
            timeout=5.0,
        )
        assert ok is False
        assert attempts == 1


@pytest.mark.asyncio
async def test_deliver_without_secret_skips_signature():
    async with respx.mock(assert_all_called=True) as mock:
        route = mock.post("https://hook.test/in").mock(return_value=httpx.Response(200))
        ok, _ = await deliver_webhook(
            url="https://hook.test/in",
            event="job.failed",
            job_id="job_001",
            body={"event": "job.failed"},
            secret=None,
            timeout=5.0,
        )
        assert ok is True
        assert "x-transcribe-signature" not in route.calls.last.request.headers
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_webhook.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `webhook.py`**

```python
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def deliver_webhook(
    *,
    url: str,
    event: str,
    job_id: str,
    body: dict[str, Any],
    secret: str | None,
    timeout: float = 10.0,
) -> tuple[bool, int]:
    """Deliver one webhook POST. Returns (ok, attempts)."""
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Transcribe-Event": event,
        "X-Transcribe-Job-Id": job_id,
    }
    if secret:
        headers["X-Transcribe-Signature"] = _sign(secret, payload)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content=payload, headers=headers)
        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning("webhook %s -> %s: HTTP %s", job_id, url, resp.status_code)
        return ok, 1
    except httpx.HTTPError as exc:
        logger.warning("webhook %s -> %s: %s", job_id, url, exc)
        return False, 1
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_webhook.py -v
```
Expected: 3 passed.

---

## Task 7: Job runner (`run_job`)

**Files:**
- Create: `transcribe-service/src/transcribe_service/jobs/runner.py`
- Create: `transcribe-service/tests/test_runner.py`

- [ ] **Step 1: Write failing tests**

`tests/test_runner.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
    await run_job(
        record=rec,
        store=store,
        engine=FakeEngine(),
        output_dir=out_dir,
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
    await run_job(
        record=rec,
        store=store,
        engine=FakeEngine(raises=RuntimeError("boom")),
        output_dir=out_dir,
        timeout_seconds=30,
        webhook_secret=None,
        webhook_timeout=5,
    )

    final = store.get("job_001")
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert "boom" in (final.error or "")
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_runner.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `jobs/runner.py`**

```python
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcriber.engines.base import TranscriptionEngine, TranscriptionOptions

from transcribe_service.jobs.store import JobRecord, JobStore
from transcribe_service.schemas import JobStatus
from transcribe_service.webhook import deliver_webhook

logger = logging.getLogger(__name__)


async def run_job(
    *,
    record: JobRecord,
    store: JobStore,
    engine: TranscriptionEngine,
    output_dir: Path,
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
        if not record.audio_path:
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
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_runner.py -v
```
Expected: 2 passed.

---

## Task 8: Worker pool (Semaphore-bounded queue)

**Files:**
- Create: `transcribe-service/src/transcribe_service/jobs/worker.py`
- Create: `transcribe-service/tests/test_worker.py`

- [ ] **Step 1: Write failing test**

`tests/test_worker.py`:
```python
import asyncio

import pytest

from transcribe_service.jobs.worker import WorkerPool


@pytest.mark.asyncio
async def test_pool_runs_submitted_coroutines():
    seen: list[int] = []

    async def task(i: int) -> None:
        await asyncio.sleep(0.01)
        seen.append(i)

    pool = WorkerPool(concurrency=2)
    await pool.start()
    for i in range(5):
        await pool.submit(task(i))
    await pool.drain()
    await pool.stop()

    assert sorted(seen) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_pool_respects_concurrency_limit():
    in_flight = 0
    peak = 0

    async def slow() -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    pool = WorkerPool(concurrency=2)
    await pool.start()
    for _ in range(6):
        await pool.submit(slow())
    await pool.drain()
    await pool.stop()

    assert peak <= 2
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_worker.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `jobs/worker.py`**

```python
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class WorkerPool:
    """Bounded async worker pool: at most `concurrency` coroutines run at once."""

    def __init__(self, concurrency: int) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task] = set()
        self._stopped = False

    async def start(self) -> None:
        self._stopped = False

    async def submit(self, coro: Coroutine) -> None:
        if self._stopped:
            coro.close()
            raise RuntimeError("WorkerPool stopped")
        task = asyncio.create_task(self._run(coro))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, coro: Coroutine) -> None:
        async with self._sem:
            try:
                await coro
            except Exception:
                logger.exception("worker task raised")

    async def drain(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def stop(self) -> None:
        self._stopped = True
        await self.drain()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_worker.py -v
```
Expected: 2 passed.

---

## Task 9: API routes (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/transcript)

**Files:**
- Create: `transcribe-service/src/transcribe_service/api/__init__.py` (empty)
- Create: `transcribe-service/src/transcribe_service/api/jobs.py`
- Create: `transcribe-service/src/transcribe_service/api/health.py`
- Create: `transcribe-service/tests/test_api_jobs.py`
- Modify: `transcribe-service/src/transcribe_service/main.py`

This task wires the API but does not start the worker pool yet (that happens in Task 10). Tests run jobs synchronously through a stub submitter.

- [ ] **Step 1: Write failing tests**

`tests/test_api_jobs.py`:
```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_api_jobs.py -v
```
Expected: ImportError or failures because routes don't exist.

- [ ] **Step 3: Create `api/__init__.py`**

Empty file.

- [ ] **Step 4: Implement `api/health.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    pool = getattr(request.app.state, "pool", None)
    in_flight = len(pool._tasks) if pool else 0
    return {"status": "ok", "in_flight": in_flight}
```

- [ ] **Step 5: Implement `api/jobs.py`**

```python
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
```

- [ ] **Step 6: Update `main.py` to mount routers**

Replace the contents of `src/transcribe_service/main.py`:

```python
from __future__ import annotations

import logging

from fastapi import FastAPI

from transcribe_service.api import health as health_api
from transcribe_service.api import jobs as jobs_api
from transcribe_service.config import get_settings
from transcribe_service.jobs.store import InMemoryJsonStore

logger = logging.getLogger(__name__)

app = FastAPI(title="transcribe-service", version="0.1.0")


@app.on_event("startup")
async def _bootstrap() -> None:
    # Bare-minimum bootstrap: settings + store. Worker pool wired in Task 10.
    if not getattr(app.state, "settings", None):
        app.state.settings = get_settings()
    if not getattr(app.state, "store", None):
        app.state.store = InMemoryJsonStore(app.state.settings.job_store_path)
    if not getattr(app.state, "submit_job", None):
        async def _no_op(_job_id: str) -> None:
            logger.warning("submit_job not configured; job will not run")
        app.state.submit_job = _no_op


app.include_router(jobs_api.router)
app.include_router(health_api.router)
```

- [ ] **Step 7: Run, expect pass**

```bash
pytest tests/test_api_jobs.py -v
```
Expected: 5 passed.

- [ ] **Step 8: Re-run smoke test to confirm no regression**

```bash
pytest tests/test_smoke.py -v
```
Expected: 1 passed.

---

## Task 10: Wire lifespan — recovery + worker pool + real submitter

**Files:**
- Modify: `transcribe-service/src/transcribe_service/main.py`
- Create: `transcribe-service/src/transcribe_service/jobs/__init__.py` already exists; no change

This replaces the `_bootstrap` event handler with a full lifespan that: (a) recovers stale `running` jobs, (b) starts the worker pool, (c) re-enqueues `queued` jobs, (d) provides a real `submit_job` that wraps `run_job` in the worker pool.

- [ ] **Step 1: Replace `main.py` with lifespan-based wiring**

```python
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
```

- [ ] **Step 2: Re-run all existing tests to confirm wiring still passes**

```bash
pytest -v
```
Expected: all previous tests still pass. `test_api_jobs.py` continues to work because the test fixture sets `app.state.submit_job` explicitly, overriding the lifespan-installed default.

---

## Task 11: Crash-recovery test

**Files:**
- Create: `transcribe-service/tests/test_recovery.py`

- [ ] **Step 1: Write the test**

`tests/test_recovery.py`:
```python
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
    from transcribe_service.main import app

    monkeypatch.setattr(
        "transcribe_service.main.get_settings",
        lambda: Settings(
            output_dir=tmp_path / "output",
            uploads_dir=tmp_path / "uploads",
            job_store_path=jobs_path,
            max_concurrent_jobs=1,
        ),
    )

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
```

- [ ] **Step 2: Run, expect pass**

```bash
pytest tests/test_recovery.py -v
```
Expected: 1 passed.

---

## Task 12: End-to-end happy path test (with fake engine)

**Files:**
- Create: `transcribe-service/tests/test_e2e.py`

This drives the real lifespan + real worker pool, but injects a fake engine in place of Sarvam.

- [ ] **Step 1: Write the test**

`tests/test_e2e.py`:
```python
import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from transcriber.engines.base import TranscriptionOptions
from transcriber.output.models import Segment, TranscriptMetadata, TranscriptResult


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
    from transcribe_service.main import app

    monkeypatch.setattr("transcribe_service.main.get_settings", lambda: settings)
    monkeypatch.setattr(
        "transcribe_service.main._build_engine", lambda name, s: FakeEngine()
    )

    transport = ASGITransport(app=app)
    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://hook.test/in").mock(return_value=httpx.Response(200))
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
```

- [ ] **Step 2: Run, expect pass**

```bash
pytest tests/test_e2e.py -v
```
Expected: 1 passed.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```
Expected: all tests pass.

---

## Task 13: Dockerfile + docker-compose

**Files:**
- Create: `transcribe-service/Dockerfile`
- Create: `transcribe-service/docker-compose.yml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the sibling transcribing-module first so it can be installed as a dep.
COPY transcribing-module /opt/transcribing-module
RUN pip install --no-cache-dir /opt/transcribing-module

COPY DebateLens/transcribe-service /app
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/data/output \
    UPLOADS_DIR=/data/uploads \
    JOB_STORE_PATH=/data/output/jobs.json

EXPOSE 8080
CMD ["uvicorn", "transcribe_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  transcribe-service:
    build:
      context: ../..
      dockerfile: DebateLens/transcribe-service/Dockerfile
    image: transcribe-service:local
    ports:
      - "8080:8080"
    environment:
      - SARVAM_API_KEY=${SARVAM_API_KEY:-}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET:-}
      - MAX_CONCURRENT_JOBS=${MAX_CONCURRENT_JOBS:-2}
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/data
```

- [ ] **Step 3: Build the image to verify the Dockerfile**

From the repo root (`DebateLens/`'s parent — the directory that contains both `DebateLens/` and `transcribing-module/`):
```bash
docker build -f DebateLens/transcribe-service/Dockerfile -t transcribe-service:local .
```

Expected: image builds without error.

- [ ] **Step 4: Run the container and hit `/healthz`**

```bash
docker run --rm -p 8080:8080 transcribe-service:local &
sleep 3
curl -s http://localhost:8080/healthz
```

Expected: `{"status":"ok","in_flight":0}`.

Stop the container (`docker ps`, `docker kill <id>`).

---

## Task 14: README + .env.example

**Files:**
- Create: `transcribe-service/README.md`
- Create: `transcribe-service/.env.example`

- [ ] **Step 1: Create `.env.example`**

```
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO

MAX_CONCURRENT_JOBS=2
JOB_TIMEOUT_SECONDS=1800

OUTPUT_DIR=./output
UPLOADS_DIR=./uploads
JOB_STORE_PATH=./output/jobs.json

WEBHOOK_SECRET=
WEBHOOK_TIMEOUT_SECONDS=10

# Engine credentials (passed through to transcribing-module)
SARVAM_API_KEY=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=asia-southeast1
GOOGLE_APPLICATION_CREDENTIALS=
```

- [ ] **Step 2: Create `README.md`**

```markdown
# transcribe-service

FastAPI batch service wrapping `../../transcribing-module`. Submit a video/audio file or URL, get an async job id, receive the transcript via webhook + GET endpoint.

## Run locally

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ../../transcribing-module
pip install -e ".[dev]"
cp .env.example .env   # fill in SARVAM_API_KEY
uvicorn transcribe_service.main:app --reload --port 8080
```

## API

- `POST /jobs` — submit (multipart `file=` OR JSON `{source_url, ...}`)
- `GET /jobs/{id}` — status
- `GET /jobs/{id}/transcript` — transcript JSON (404 until done)
- `GET /healthz` — liveness

See `docs/superpowers/specs/2026-05-09-transcribe-service-design.md` for the full contract.

## Tests

```bash
pytest -v
```
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```bash
cd transcribe-service && pytest -v
```
Expected: all tests pass.

- [ ] **Smoke test the running service**

```bash
uvicorn transcribe_service.main:app --port 8080 &
sleep 2
curl -s http://localhost:8080/healthz
curl -s -X POST http://localhost:8080/jobs \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://media.test/x.mp4"}'
kill %1
```

Expected: healthz returns ok; POST /jobs returns a `job_id` and `status: queued`. (The job will fail because the URL is fake — that's fine; this is just confirming the API responds.)
