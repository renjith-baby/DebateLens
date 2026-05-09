from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Segment:
    speaker: str
    text: str
    start_time: float
    end_time: float


@dataclass
class TranscriptMetadata:
    engine: str
    model: str
    language: str
    source_file: str


@dataclass
class TranscriptResult:
    segments: list[Segment]
    metadata: TranscriptMetadata

    def to_dict(self) -> dict[str, Any]:
        full_text = "\n".join(f"[{s.speaker}] {s.text}" for s in self.segments)
        return {
            "full_text": full_text,
            "segments": [
                {
                    "speaker": s.speaker,
                    "text": s.text,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                }
                for s in self.segments
            ],
            "metadata": {
                "engine": self.metadata.engine,
                "model": self.metadata.model,
                "language": self.metadata.language,
                "source_file": self.metadata.source_file,
            },
        }
