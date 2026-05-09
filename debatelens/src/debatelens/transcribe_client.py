from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from debatelens.models import Segment, Transcript


class TranscribeClient:
    def __init__(
        self,
        *,
        base_url: str,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._poll = poll_interval_seconds
        self._timeout = timeout_seconds

    async def submit_url(self, *, url: str, engine: str = "sarvam") -> str:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
            r = await client.post("/jobs", json={
                "source_url": url,
                "engine": engine,
                "language": "ml-IN",
                "mode": "codemix",
            })
            r.raise_for_status()
            return r.json()["job_id"]

    async def submit_file(self, *, path: Path, engine: str = "sarvam") -> str:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=600.0) as client:
            with Path(path).open("rb") as f:
                r = await client.post(
                    "/jobs",
                    files={"file": (Path(path).name, f, "application/octet-stream")},
                    data={"engine": engine, "language": "ml-IN", "mode": "codemix"},
                )
            r.raise_for_status()
            return r.json()["job_id"]

    async def wait_for_transcript(self, job_id: str, *, timeout_seconds: float | None = None) -> Transcript:
        deadline = (timeout_seconds or self._timeout)
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            async def poll():
                while True:
                    r = await client.get(f"/jobs/{job_id}")
                    r.raise_for_status()
                    body = r.json()
                    status = body.get("status")
                    if status == "done":
                        return body
                    if status == "failed":
                        raise RuntimeError(body.get("error") or "transcription failed")
                    await asyncio.sleep(self._poll)

            await asyncio.wait_for(poll(), timeout=deadline)

            r = await client.get(f"/jobs/{job_id}/transcript")
            r.raise_for_status()
            payload = r.json()

        segments = [Segment.model_validate(s) for s in payload.get("segments", [])]
        return Transcript(
            segments=segments,
            language=payload.get("metadata", {}).get("language", "ml-IN"),
        )
