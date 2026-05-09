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
