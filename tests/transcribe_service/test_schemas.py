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
