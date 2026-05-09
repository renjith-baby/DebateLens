from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


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
