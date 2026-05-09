from __future__ import annotations

import os
import subprocess
from pathlib import Path

from google.cloud import speech_v1 as speech
from google.cloud.speech_v1 import RecognizeResponse

from transcribe_service.engines.base import TranscriptionOptions
from transcribe_service.engines.config import GoogleConfig
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult


def _pcm_s16le_16k_mono(audio_path: str) -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            audio_path,
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"ffmpeg_failed: {err}")
    return proc.stdout


class GoogleEngine:
    """Google Cloud Speech-to-text (v1) with optional speaker diarization."""

    name = "google"

    def __init__(self, config: GoogleConfig) -> None:
        self._config = config
        self._client: speech.SpeechClient | None = None

    @property
    def is_configured(self) -> bool:
        cred = self._config.credentials_path
        if cred:
            return Path(cred).expanduser().is_file()
        return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

    def _speech_client(self) -> speech.SpeechClient:
        if self._client is None:
            cred_path = self._config.credentials_path
            if cred_path and Path(cred_path).expanduser().is_file():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(cred_path).expanduser())
            self._client = speech.SpeechClient()
        return self._client

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        if not self.is_configured:
            raise RuntimeError("google_stt_unconfigured")

        pcm = _pcm_s16le_16k_mono(audio_path)
        audio = speech.RecognitionAudio(content=pcm)

        max_sp = options.max_speakers or 6
        max_sp = max(2, min(max_sp, 6))

        diar_cfg = None
        if options.enable_diarization:
            diar_cfg = speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=2,
                max_speaker_count=max_sp,
            )

        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=options.language,
            enable_automatic_punctuation=True,
            enable_word_time_offsets=bool(options.enable_diarization),
            diarization_config=diar_cfg,
        )

        client = self._speech_client()
        response = client.recognize(config=recognition_config, audio=audio)

        segments = _segments_from_google(response, options.enable_diarization)
        if not segments:
            segments = [
                Segment(speaker="1", text="", start_time=0.0, end_time=0.0),
            ]

        return TranscriptResult(
            segments=segments,
            metadata=TranscriptMetadata(
                engine=self.name,
                model="speech_v1",
                language=options.language,
                source_file=audio_path,
            ),
        )


def _segments_from_google(response: RecognizeResponse, diarization: bool) -> list[Segment]:
    parts: list[Segment] = []
    for result in response.results:
        alt = result.alternatives[0] if result.alternatives else None
        if alt is None:
            continue
        words = list(alt.words)
        if diarization and words:
            grouped = _group_words(words)
            if grouped:
                parts.extend(grouped)
                continue
        text = (alt.transcript or "").strip()
        if text:
            parts.append(Segment(speaker="1", text=text, start_time=0.0, end_time=0.0))
    return parts


def _group_words(words: list) -> list[Segment]:
    """Group consecutive words with the same speaker_tag into segments."""
    segments: list[Segment] = []
    cur_tag: str | None = None
    texts: list[str] = []
    start_t = 0.0
    end_t = 0.0

    def flush() -> None:
        nonlocal segments, cur_tag, texts, start_t, end_t
        if cur_tag is None or not texts:
            return
        segments.append(
            Segment(
                speaker=cur_tag,
                text=" ".join(texts).strip(),
                start_time=start_t,
                end_time=end_t,
            )
        )
        texts = []

    for w in words:
        tag = str(getattr(w, "speaker_tag", None) or getattr(w, "speaker_label", None) or "1")
        word = getattr(w, "word", "") or ""
        st = w.start_time.total_seconds() if w.start_time else 0.0
        et = w.end_time.total_seconds() if w.end_time else st

        if cur_tag is None:
            cur_tag = tag
            start_t = st
            texts.append(word)
            end_t = et
            continue

        if tag != cur_tag:
            flush()
            cur_tag = tag
            texts = [word]
            start_t = st
            end_t = et
        else:
            texts.append(word)
            end_t = et

    flush()
    return segments
