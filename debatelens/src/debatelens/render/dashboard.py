from __future__ import annotations

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


def render_dashboard(output: AnalysisOutput, out_path: Path) -> None:
    template_dir = Path(__file__).parent
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("template.html")
    html = template.render(
        show=output.show,
        speakers=output.speakers,
        now=output.now,
        icons=_ICONS,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
