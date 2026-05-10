from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from debatelens.models import AnalysisOutput


_ICONS = {
    "verified": "✓",
    "wrong": "×",
    "outdated": "⚠",
    "flag": "!",
    "unsure": "?",
}


def _make_env() -> Environment:
    template_dir = Path(__file__).parent
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )


def render_dashboard(output: AnalysisOutput, out_path: Path) -> None:
    env = _make_env()
    html = env.get_template("template.html").render(
        show=output.show,
        speakers=output.speakers,
        now=output.now,
        icons=_ICONS,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")


def render_watch_page(output: AnalysisOutput, out_path: Path) -> None:
    timed_events: list[dict] = []
    for sp_id, speaker in output.speakers.items():
        for moment in speaker.moments:
            if moment.timestamp_seconds is None:
                continue
            timed_events.append({
                "speaker_id": sp_id,
                "speaker_name": speaker.name,
                "kind": moment.kind,
                "timestamp_seconds": moment.timestamp_seconds,
                "quote": moment.quote,
                "note": moment.note,
                "label": moment.label,
            })

    env = _make_env()
    html = env.get_template("watch_template.html").render(
        show=output.show,
        speakers=output.speakers,
        video_id_js=json.dumps(output.show.youtube_video_id),
        timed_events_js=json.dumps(timed_events, ensure_ascii=False),
        speakers_js=json.dumps(
            {
                sp_id: {
                    "name": sp.name,
                    "role": sp.role,
                    "accuracy": sp.scores.accuracy,
                    "civility": sp.scores.civility,
                    "reasoning": sp.scores.reasoning,
                }
                for sp_id, sp in output.speakers.items()
            },
            ensure_ascii=False,
        ),
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
