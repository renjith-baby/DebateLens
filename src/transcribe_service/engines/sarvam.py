from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from sarvamai import SarvamAI

from transcribe_service.engines.base import TranscriptionOptions
from transcribe_service.engines.config import SarvamConfig
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult


logger = logging.getLogger(__name__)

SARVAM_MODEL = "saaras:v3"
DEFAULT_POLL_INTERVAL = 5
DEFAULT_BATCH_TIMEOUT = 1800  # 30 min — Sarvam batch can take a while


class SarvamEngine:
    """Sarvam batch speech-to-text. Uses the Saaras v3 model with diarization."""

    name = "sarvam"

    def __init__(self, config: SarvamConfig) -> None:
        self._config = config

    @property
    def is_configured(self) -> bool:
        return bool(self._config.api_key and self._config.api_key.strip())

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        if not self.is_configured:
            raise RuntimeError("sarvam_unconfigured")

        client = SarvamAI(api_subscription_key=self._config.api_key.strip())
        job = client.speech_to_text_job.create_job(
            model=SARVAM_MODEL,
            mode=options.mode or "codemix",
            with_diarization=True,
            language_code=options.language or "ml-IN",
        )
        logger.info("sarvam batch job created: %s", job.job_id)

        if not job.upload_files([str(audio_path)]):
            raise RuntimeError("sarvam batch: upload_files returned False")

        job.start()
        logger.info("sarvam batch job started: %s", job.job_id)

        status = job.wait_until_complete(
            poll_interval=DEFAULT_POLL_INTERVAL,
            timeout=DEFAULT_BATCH_TIMEOUT,
        )
        if not job.is_successful():
            raise RuntimeError(f"sarvam batch job failed: {status}")

        with tempfile.TemporaryDirectory(prefix="sarvam-out-") as out_dir:
            if not job.download_outputs(output_dir=out_dir):
                raise RuntimeError("sarvam batch: download_outputs returned False")

            payload = _load_first_json(Path(out_dir))

        segments = _segments_from_sarvam(payload)
        return TranscriptResult(
            segments=segments,
            metadata=TranscriptMetadata(
                engine=self.name,
                model=SARVAM_MODEL,
                language=str(payload.get("language_code") or options.language or "ml-IN"),
                source_file=audio_path,
            ),
        )


def _load_first_json(out_dir: Path) -> dict:
    for path in sorted(out_dir.rglob("*.json")):
        return json.loads(path.read_text(encoding="utf-8"))
    raise RuntimeError(f"sarvam batch: no transcript JSON found in {out_dir}")


def _segments_from_sarvam(payload: dict) -> list[Segment]:
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
    return [Segment(speaker="1", text=transcript, start_time=0.0, end_time=0.0)]
