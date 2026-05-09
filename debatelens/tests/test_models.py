from debatelens.models import (
    AnalysisOutput,
    Claim,
    Fallacy,
    Moment,
    Segment,
    SpeakerScore,
    SpeakerStats,
    SpeakerSummary,
    Transcript,
    Verdict,
    Window,
)


def test_segment_basic():
    s = Segment(speaker="1", text="hello", start_time=0.0, end_time=1.5)
    assert s.speaker == "1"
    assert s.duration == 1.5


def test_transcript_roundtrip():
    t = Transcript(
        segments=[Segment(speaker="1", text="a", start_time=0.0, end_time=1.0)],
        language="ml-IN",
    )
    data = t.model_dump()
    again = Transcript.model_validate(data)
    assert again.segments[0].text == "a"


def test_window_concat_text():
    w = Window(
        index=0,
        start_time=0.0,
        end_time=60.0,
        segments=[
            Segment(speaker="1", text="A", start_time=0.0, end_time=1.0),
            Segment(speaker="2", text="B", start_time=1.0, end_time=2.0),
        ],
    )
    assert w.text == "[1] A\n[2] B"


def test_claim_defaults():
    c = Claim(
        claim_id="c1",
        speaker="1",
        video_timestamp="01:00",
        claim_ml="x",
        claim_en="y",
        claim_category="factual",
    )
    assert c.flags == []


def test_verdict_confidence_bounds():
    v = Verdict(
        claim_id="c1",
        verdict="true",
        confidence=0.9,
        one_liner="ok",
        evidence_paragraph="because",
        sources=[],
    )
    assert 0.0 <= v.confidence <= 1.0


def test_fallacy_basic():
    f = Fallacy(
        fallacy_type="ad_hominem",
        tier=1,
        speaker="1",
        video_timestamp="00:30",
        quote_ml="x",
        quote_en="y",
        explanation="z",
        confidence=0.93,
    )
    assert f.tier == 1


def test_moment_kinds():
    m = Moment(kind="wrong", label="Not true", quote="q", note="n")
    assert m.kind == "wrong"


def test_speaker_score_bounds():
    s = SpeakerScore(accuracy=78, civility=65, reasoning=72)
    assert s.accuracy == 78


def test_analysis_output_shape():
    out = AnalysisOutput(
        show={"title": "X", "minutes": 10},
        speakers={
            "1": SpeakerSummary(
                name="Speaker 1",
                role="Guest",
                stats=SpeakerStats(verified=1, wrong=0, flagged=0),
                moments=[Moment(kind="verified", label="True", quote="q", note="n")],
                scores=SpeakerScore(),
            )
        },
        now=None,
    )
    assert "1" in out.speakers
