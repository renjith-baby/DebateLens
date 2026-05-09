"""In-process transcription engines (Sarvam, Google STT)."""

from transcribe_service.engines.base import TranscriptionEngine, TranscriptionOptions
from transcribe_service.engines.config import GoogleConfig, SarvamConfig
from transcribe_service.engines.google_stt import GoogleEngine
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult
from transcribe_service.engines.sarvam import SarvamEngine

__all__ = [
    "GoogleConfig",
    "GoogleEngine",
    "SarvamConfig",
    "SarvamEngine",
    "Segment",
    "TranscriptMetadata",
    "TranscriptResult",
    "TranscriptionEngine",
    "TranscriptionOptions",
]
