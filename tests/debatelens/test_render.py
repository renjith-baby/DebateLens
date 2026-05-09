from pathlib import Path

from debatelens.models import (
    AnalysisOutput,
    Moment,
    NowItem,
    ShowMeta,
    SpeakerScore,
    SpeakerStats,
    SpeakerSummary,
)
from debatelens.render.dashboard import render_dashboard


def _output() -> AnalysisOutput:
    return AnalysisOutput(
        show=ShowMeta(title="Test Show", minutes=12),
        speakers={
            "1": SpeakerSummary(
                name="A",
                role="Guest",
                stats=SpeakerStats(verified=1, wrong=1, flagged=1),
                moments=[
                    Moment(kind="verified", label="True", quote="Q1", note="N1"),
                    Moment(kind="wrong", label="Not true", quote="Q2", note="N2"),
                    Moment(kind="flag", label="Personal attack", quote="Q3", note="N3"),
                ],
                scores=SpeakerScore(),
            ),
            "2": SpeakerSummary(
                name="B",
                role="Host",
                stats=SpeakerStats(),
                moments=[],
                scores=SpeakerScore(),
            ),
        },
        now=NowItem(quote="Q2", verdict_kind="wrong", verdict_text="N2"),
    )


def test_render_writes_html_file(tmp_path: Path):
    out_path = tmp_path / "dashboard.html"
    render_dashboard(_output(), out_path)
    assert out_path.exists()
    content = out_path.read_text()
    assert "<!DOCTYPE html>" in content
    assert "Test Show" in content
    assert "A" in content and "B" in content
    assert "Q1" in content and "Q2" in content
    assert 'class="icon verified"' in content
    assert 'class="icon wrong"' in content
    assert 'class="icon flag"' in content


def test_render_handles_no_now(tmp_path: Path):
    out = _output()
    out.now = None
    out_path = tmp_path / "dashboard.html"
    render_dashboard(out, out_path)
    assert "No claims surfaced." in out_path.read_text()
