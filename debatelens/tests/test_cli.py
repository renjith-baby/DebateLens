import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from debatelens.cli import _parse_speaker_names, main_async
from debatelens.models import AnalysisOutput, ShowMeta, SpeakerSummary


def test_parse_speaker_names_basic():
    out = _parse_speaker_names("1=Maitreyan,2=Venugopan")
    assert out == {"1": "Maitreyan", "2": "Venugopan"}


def test_parse_speaker_names_empty():
    assert _parse_speaker_names("") == {}
    assert _parse_speaker_names(None) == {}


@pytest.mark.asyncio
async def test_main_async_with_transcript(tmp_path: Path):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps({
        "segments": [{"speaker": "1", "text": "hi", "start_time": 0.0, "end_time": 1.0}],
        "language": "ml-IN",
    }))

    out_dir = tmp_path / "output"

    fake_runner_instance = MagicMock()
    fake_runner_instance.run.return_value = AnalysisOutput(
        show=ShowMeta(title="X", minutes=0),
        speakers={"1": SpeakerSummary(name="Speaker 1")},
        now=None,
    )

    with patch("debatelens.cli.AnalysisRunner", return_value=fake_runner_instance), \
         patch("debatelens.cli.GeminiClient"), \
         patch("debatelens.cli.load_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            gemini_api_key="g",
            sarvam_api_key="s",
            service_url="http://localhost:8080",
            out_dir=out_dir,
            model_fast="gemini-2.0-flash",
            model_pro="gemini-2.5-pro",
            repo_root=tmp_path,
        )
        rc = await main_async([
            "run",
            "--transcript", str(transcript_path),
            "--show-title", "Test",
        ])

    assert rc == 0
    runs = list(out_dir.glob("*/dashboard.html"))
    assert runs, "expected at least one dashboard.html"
