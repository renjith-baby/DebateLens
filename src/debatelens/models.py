from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ClaimCategory = Literal["factual", "numerical", "causal", "predictive", "opinion"]
VerdictLabel = Literal["true", "false", "disputed", "unverifiable", "outdated"]
MomentKind = Literal["verified", "wrong", "outdated", "flag", "unsure"]


class Segment(BaseModel):
    speaker: str
    text: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class Transcript(BaseModel):
    segments: list[Segment]
    language: str = "ml-IN"


class Window(BaseModel):
    index: int
    start_time: float
    end_time: float
    segments: list[Segment]

    @property
    def text(self) -> str:
        return "\n".join(f"[{s.speaker}] {s.text}" for s in self.segments)


class Claim(BaseModel):
    claim_id: str
    speaker: str
    video_timestamp: str
    claim_ml: str
    claim_en: str
    claim_category: ClaimCategory
    flags: list[str] = Field(default_factory=list)


class Source(BaseModel):
    title: str
    url: str


class Verdict(BaseModel):
    claim_id: str
    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    one_liner: str
    evidence_paragraph: str
    sources: list[Source] = Field(default_factory=list)
    context_caveat: str | None = None


class Fallacy(BaseModel):
    fallacy_type: str
    tier: Literal[1, 2, 3]
    speaker: str
    video_timestamp: str
    quote_ml: str
    quote_en: str
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    turn_range: tuple[int, int] | None = None


class Moment(BaseModel):
    kind: MomentKind
    label: str
    quote: str
    note: str


class SpeakerStats(BaseModel):
    verified: int = 0
    wrong: int = 0
    flagged: int = 0


class SpeakerScore(BaseModel):
    accuracy: int = Field(ge=0, le=100, default=100)
    civility: int = Field(ge=0, le=100, default=100)
    reasoning: int = Field(ge=0, le=100, default=100)


class SpeakerSummary(BaseModel):
    name: str
    role: str = "Speaker"
    stats: SpeakerStats = Field(default_factory=SpeakerStats)
    moments: list[Moment] = Field(default_factory=list)
    scores: SpeakerScore = Field(default_factory=SpeakerScore)


class NowItem(BaseModel):
    quote: str
    verdict_kind: MomentKind
    verdict_text: str


class ShowMeta(BaseModel):
    title: str
    minutes: int = 0


class AnalysisOutput(BaseModel):
    show: ShowMeta
    speakers: dict[str, SpeakerSummary]
    now: NowItem | None = None
