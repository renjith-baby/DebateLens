from __future__ import annotations

import logging
from pathlib import Path

import httpx

from transcribe_service.engines.base import TranscriptionOptions
from transcribe_service.engines.config import SarvamConfig
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = "saaras:v3"


class SarvamEngine:
    """Sarvam REST speech-to-text (Saaras v3)."""

    name = "sarvam"

    def __init__(self, config: SarvamConfig) -> None:
        self._config = config

    @property
    def is_configured(self) -> bool:
        return bool(self._config.api_key and self._config.api_key.strip())

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        if not self.is_configured:
            raise RuntimeError("sarvam_unconfigured")

        path = Path(audio_path)
        data: bytes = path.read_bytes()
        filename = path.name

        form = {
            "model": SARVAM_MODEL,
            "mode": options.mode,
            "language_code": options.language,
        }

        headers = {"api-subscription-key": self._config.api_key.strip()}

        with httpx.Client(timeout=600.0) as client:
            r = client.post(
                SARVAM_STT_URL,
                headers=headers,
                files={"file": (filename, data, "application/octet-stream")},
                data=form,
            )
        if r.status_code >= 400:
            logger.warning("sarvam error %s: %s", r.status_code, r.text[:500])
            r.raise_for_status()

        payload = r.json()
        segments = _segments_from_sarvam(payload, audio_path)

        return TranscriptResult(
            segments=segments,
            metadata=TranscriptMetadata(
                engine=self.name,
                model=SARVAM_MODEL,
                language=str(payload.get("language_code") or options.language),
                source_file=audio_path,
            ),
        )


def _segments_from_sarvam(payload: dict, audio_path: str) -> list[Segment]:
    diarized = payload.get("diarized_transcript") or {}
    entries = diarized.get("entries") if isinstance(diarized, dict) else None
    if isinstance(entries, list) and entries:
        out: list[Segment] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            text = (e.get("transcript") or "").strip()
            if not text:
                continue
            sp = str(e.get("speaker_id") or "1")
            st = float(e.get("start_time_seconds") or 0.0)
            et = float(e.get("end_time_seconds") or st)
            out.append(Segment(speaker=sp, text=text, start_time=st, end_time=et))
        if out:
            return out

    transcript = (payload.get("transcript") or "").strip()
    return [
        Segment(speaker="1", text=transcript, start_time=0.0, end_time=0.0),
    ]
