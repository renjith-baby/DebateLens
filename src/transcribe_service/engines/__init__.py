"""In-process transcription engines (Sarvam, Google STT)."""

from transcribe_service.engines.base import TranscriptionEngine, TranscriptionOptions
from transcribe_service.engines.config import GoogleConfig, SarvamConfig
from transcribe_service.engines.models import Segment, TranscriptMetadata, TranscriptResult
from transcribe_service.engines.sarvam import SarvamEngine

# GoogleEngine has a hard dep on google-cloud-speech which is optional.
try:
    from transcribe_service.engines.google_stt import GoogleEngine  # noqa: F401
except ImportError:
    GoogleEngine = None  # type: ignore[assignment]

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
