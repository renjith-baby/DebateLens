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
    async with respx.mock() as mock:
        mock.post("https://hook.test/in").mock(return_value=httpx.Response(503))
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
