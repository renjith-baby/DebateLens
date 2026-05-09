from debatelens.models import Fallacy, Verdict
from debatelens.scoring import compute_speaker_scores, verdict_to_moment_kind


def _verdict(speaker_id: str, label: str, conf: float = 0.9) -> Verdict:
    return Verdict(
        claim_id=f"c-{speaker_id}-{label}",
        verdict=label,  # type: ignore[arg-type]
        confidence=conf,
        one_liner="x",
        evidence_paragraph="y",
        sources=[],
    )


def _fallacy(speaker_id: str, tier: int, ftype: str = "ad_hominem") -> Fallacy:
    return Fallacy(
        fallacy_type=ftype,
        tier=tier,  # type: ignore[arg-type]
        speaker=speaker_id,
        video_timestamp="00:00",
        quote_ml="x",
        quote_en="y",
        explanation="z",
        confidence=0.9,
    )


def test_starts_at_100_with_no_events():
    scores = compute_speaker_scores(verdicts_by_speaker={}, fallacies_by_speaker={}, speakers={"1"})
    assert scores["1"].accuracy == 100
    assert scores["1"].civility == 100
    assert scores["1"].reasoning == 100


def test_false_verdict_drops_accuracy():
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [_verdict("1", "false")]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy < 100


def test_true_verdict_keeps_accuracy_high():
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [_verdict("1", "true")]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy == 100


def test_tier1_fallacy_drops_civility():
    scores = compute_speaker_scores(
        verdicts_by_speaker={},
        fallacies_by_speaker={"1": [_fallacy("1", 1, "ad_hominem")]},
        speakers={"1"},
    )
    assert scores["1"].civility < 100
    assert scores["1"].reasoning < 100


def test_unverifiable_no_op():
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [_verdict("1", "unverifiable")]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy == 100


def test_verdict_to_moment_kind_mapping():
    assert verdict_to_moment_kind("true") == "verified"
    assert verdict_to_moment_kind("false") == "wrong"
    assert verdict_to_moment_kind("outdated") == "outdated"
    assert verdict_to_moment_kind("disputed") == "unsure"
    assert verdict_to_moment_kind("unverifiable") == "unsure"
