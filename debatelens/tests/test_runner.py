import json
from unittest.mock import MagicMock

import pytest

from debatelens.analysis.runner import AnalysisRunner, RunnerConfig
from debatelens.models import Transcript


@pytest.fixture
def transcript(fixtures_dir) -> Transcript:
    raw = json.loads((fixtures_dir / "transcript_sample.json").read_text())
    return Transcript.model_validate(raw)


def _stub_gemini(responses_by_stage: dict[str, list]) -> MagicMock:
    """GeminiClient mock that returns canned JSON, picking by keyword in the prompt."""
    state = {k: iter(v) for k, v in responses_by_stage.items()}

    def generate(*, model, prompt, with_search=False, temperature=0.0):
        for key, it in state.items():
            if key in prompt.lower():
                return next(it)
        return {}

    m = MagicMock()
    m.generate_json.side_effect = generate
    return m


def _write_minimal_prompts(prompts_dir):
    prompts_dir.mkdir(parents=True)
    spec = {
        "extract_claims": (["window_text"], "extract from {{ window_text }}"),
        "classify_claim": (["claim_en"], "classify {{ claim_en }}"),
        "factcheck_claim": (["claim_en"], "factcheck {{ claim_en }}"),
        "detect_fallacy_single": (["window_text"], "fallacy single {{ window_text }}"),
        "detect_fallacy_multiturn": (["window_text"], "fallacy multiturn {{ window_text }}"),
    }
    for name, (vars_list, body) in spec.items():
        (prompts_dir / f"{name}.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"input_variables: {vars_list}\n"
            f"model_hint: gemini-2.0-flash\n"
            "temperature: 0.0\n"
            "---\n"
            f"{body}\n"
        )


def test_runner_produces_analysis_output_shape(transcript, tmp_path):
    prompts_dir = tmp_path / "prompts" / "v1"
    _write_minimal_prompts(prompts_dir)

    # All 4 transcript segments fall into a single 60s window, so extract is called once with both claims.
    gemini = _stub_gemini({
        "extract from": [
            {"claims": [
                {"claim_id": "c1", "speaker": "1", "video_timestamp": "00:05",
                 "claim_ml": "x", "claim_en": "We dropped the atomic bomb only once.",
                 "claim_category": "factual", "flags": []},
                {"claim_id": "c2", "speaker": "2", "video_timestamp": "01:05",
                 "claim_ml": "y", "claim_en": "Schengen has 28 countries.",
                 "claim_category": "numerical", "flags": []},
            ]},
        ],
        "classify": [
            {"claim_id": "c1", "claim_category": "factual", "flags": []},
            {"claim_id": "c2", "claim_category": "numerical", "flags": []},
        ],
        "factcheck": [
            {"verdict": "false", "confidence": 0.97,
             "one_liner": "Two bombs.", "evidence_paragraph": "...", "sources": []},
            {"verdict": "outdated", "confidence": 0.92,
             "one_liner": "29 since 2024.", "evidence_paragraph": "...", "sources": []},
        ],
        "fallacy single": [
            {"fallacies": [
                {"fallacy_type": "ad_hominem", "tier": 1, "speaker": "1",
                 "video_timestamp": "00:15", "quote_ml": "z", "quote_en": "You are nobody important.",
                 "explanation": "personal attack", "confidence": 0.95}
            ]},
        ],
        "fallacy multiturn": [
            {"fallacies": []},
        ],
    })

    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(prompts_dir=prompts_dir),
    )
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={"1": "A", "2": "B"})

    assert "1" in out.speakers
    assert "2" in out.speakers
    assert out.speakers["1"].name == "A"
    moments_1 = out.speakers["1"].moments
    assert any(m.kind == "wrong" for m in moments_1)
    assert any(m.kind == "flag" for m in moments_1)
    moments_2 = out.speakers["2"].moments
    assert any(m.kind == "outdated" for m in moments_2)


def test_runner_skips_low_confidence(transcript, tmp_path):
    prompts_dir = tmp_path / "prompts" / "v1"
    _write_minimal_prompts(prompts_dir)

    gemini = MagicMock()
    gemini.generate_json.return_value = {"claims": [], "fallacies": []}

    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(prompts_dir=prompts_dir, confidence_threshold=0.85),
    )
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={})
    assert sum(len(s.moments) for s in out.speakers.values()) == 0
