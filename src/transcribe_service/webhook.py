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
