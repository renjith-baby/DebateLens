from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from transcribe_service.engines.models import TranscriptResult


@dataclass
class TranscriptionOptions:
    language: str
    enable_diarization: bool = True
    max_speakers: int | None = None
    mode: str = "codemix"


@runtime_checkable
class TranscriptionEngine(Protocol):
    name: str
    is_configured: bool

    def transcribe(self, audio_path: str, options: TranscriptionOptions) -> "TranscriptResult":
        ...
