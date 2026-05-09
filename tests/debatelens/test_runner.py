import json
from unittest.mock import MagicMock

import pytest

from debatelens.analysis.runner import AnalysisRunner, RunnerConfig
from debatelens.models import Transcript


@pytest.fixture
def transcript(fixtures_dir) -> Transcript:
    raw = json.loads((fixtures_dir / "transcript_sample.json").read_text())
    return Transcript.model_validate(raw)


def _write_extract_prompt(prompts_dir):
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "extract_claims.md").write_text(
        "---\n"
        "name: extract_claims\n"
        "input_variables: [transcript_window, show_metadata]\n"
        "model_hint: gemini-2.5-pro\n"
        "temperature: 0.0\n"
        "---\n"
        "Extract claims from {{ transcript_window }} given {{ show_metadata }}.\n"
    )


def _stub_gemini(extract_response, combined_response):
    """Returns extract_response on the 1st generate_json call, combined_response on the 2nd."""
    state = iter([extract_response, combined_response])

    def generate(*, model, prompt, with_search=False, temperature=0.0):
        return next(state)

    m = MagicMock()
    m.generate_json.side_effect = generate
    return m


def test_runner_produces_analysis_output_shape(transcript, tmp_path):
    prompts_dir = tmp_path / "prompts" / "v1"
    _write_extract_prompt(prompts_dir)

    extract_response = [
        {"claim_id": "c1", "speaker_id": "person:a", "speaker_name": "A",
         "video_timestamp_start": 5.0, "video_timestamp_end": 10.0,
         "claim_ml": "x", "claim_en": "We dropped the atomic bomb only once.",
         "rough_category": "factual"},
        {"claim_id": "c2", "speaker_id": "person:b", "speaker_name": "B",
         "video_timestamp_start": 65.0, "video_timestamp_end": 70.0,
         "claim_ml": "y", "claim_en": "Schengen has 28 countries.",
         "rough_category": "numerical"},
    ]
    combined_response = {
        "verdicts": [
            {"claim_id": "c1", "verdict": "false", "confidence": 0.97,
             "one_liner": "Two bombs.", "evidence_paragraph": "...", "sources": []},
            {"claim_id": "c2", "verdict": "outdated", "confidence": 0.92,
             "one_liner": "29 since 2024.", "evidence_paragraph": "...", "sources": []},
        ],
        "fallacies": [
            {"fallacy_type": "ad_hominem", "tier": 1, "speaker_id": "person:a",
             "speaker_name": "A", "video_timestamp": 15.0,
             "quote_ml": "z", "quote_en": "You are nobody important.",
             "explanation": "personal attack", "confidence": 0.95},
        ],
    }

    gemini = _stub_gemini(extract_response, combined_response)
    runner = AnalysisRunner(gemini=gemini, config=RunnerConfig(prompts_dir=prompts_dir))
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={"1": "A", "2": "B"})

    assert "1" in out.speakers
    assert "2" in out.speakers
    assert out.speakers["1"].name == "A"
    moments_1 = out.speakers["1"].moments
    assert any(m.kind == "wrong" for m in moments_1)
    assert any(m.kind == "flag" for m in moments_1)
    assert any(m.kind == "outdated" for m in out.speakers["2"].moments)
    # Exactly 2 LLM calls — extract + combined.
    assert gemini.generate_json.call_count == 2


def test_runner_skips_low_confidence(transcript, tmp_path):
    prompts_dir = tmp_path / "prompts" / "v1"
    _write_extract_prompt(prompts_dir)

    extract_response = [
        {"claim_id": "c1", "speaker_id": "person:a", "speaker_name": "A",
         "video_timestamp_start": 5.0, "video_timestamp_end": 10.0,
         "claim_ml": "x", "claim_en": "y", "rough_category": "factual"},
    ]
    combined_response = {
        "verdicts": [
            {"claim_id": "c1", "verdict": "false", "confidence": 0.5,
             "one_liner": "x", "evidence_paragraph": "y", "sources": []},
        ],
        "fallacies": [
            {"fallacy_type": "ad_hominem", "tier": 1, "speaker_id": "person:a",
             "speaker_name": "A", "video_timestamp": 0.0,
             "quote_ml": "x", "quote_en": "y", "explanation": "z", "confidence": 0.5},
        ],
    }

    gemini = _stub_gemini(extract_response, combined_response)
    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(prompts_dir=prompts_dir, confidence_threshold=0.85),
    )
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={})
    assert sum(len(s.moments) for s in out.speakers.values()) == 0


def test_runner_no_claims_does_one_call(transcript, tmp_path):
    """If extract returns no claims, the combined call is skipped."""
    prompts_dir = tmp_path / "prompts" / "v1"
    _write_extract_prompt(prompts_dir)

    gemini = MagicMock()
    gemini.generate_json.return_value = []

    runner = AnalysisRunner(gemini=gemini, config=RunnerConfig(prompts_dir=prompts_dir))
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={})
    assert sum(len(s.moments) for s in out.speakers.values()) == 0
    assert gemini.generate_json.call_count == 1
