from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


def _find_analysis_for_video(output_dir: Path, video_id: str) -> dict | None:
    """Scan run directories for an analysis.json whose youtube_video_id matches."""
    for run_dir in sorted(output_dir.iterdir(), reverse=True):
        analysis_path = run_dir / "analysis.json"
        if not analysis_path.exists():
            continue
        try:
            data = json.loads(analysis_path.read_text(encoding="utf-8"))
            if data.get("show", {}).get("youtube_video_id") == video_id:
                return data
        except Exception:
            continue
    return None


@router.get("/watch", response_class=HTMLResponse)
async def watch_page(request: Request, v: str = Query(..., description="YouTube video ID")) -> HTMLResponse:
    """Serve the cricket-themed DebateLens watch page for a YouTube video."""
    from debatelens.models import AnalysisOutput
    from debatelens.render.dashboard import render_watch_page
    import tempfile

    settings = request.app.state.settings
    output_dir: Path = settings.output_dir

    analysis_data = _find_analysis_for_video(output_dir, v)
    if analysis_data is None:
        return HTMLResponse(
            _pending_html(v),
            status_code=200,
        )

    output = AnalysisOutput.model_validate(analysis_data)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    render_watch_page(output, tmp_path)
    html = tmp_path.read_text(encoding="utf-8")
    tmp_path.unlink(missing_ok=True)
    return HTMLResponse(html)


@router.get("/watch/analysis", response_class=JSONResponse)
async def watch_analysis(request: Request, v: str = Query(..., description="YouTube video ID")) -> JSONResponse:
    """Return raw analysis JSON for a video (used by external embeds)."""
    settings = request.app.state.settings
    data = _find_analysis_for_video(settings.output_dir, v)
    if data is None:
        return JSONResponse({"error": "no_analysis", "video_id": v}, status_code=404)
    return JSONResponse(data)


def _pending_html(video_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>🏏 DebateLens — Warming Up</title>
<style>
  body {{
    margin: 0; font-family: -apple-system, "Segoe UI", sans-serif;
    background: #0d1117; color: #e6edf3;
    display: flex; align-items: center; justify-content: center;
    height: 100vh; flex-direction: column; gap: 16px; text-align: center;
    padding: 24px;
  }}
  .big {{ font-size: 64px; }}
  h1 {{ font-size: 22px; font-weight: 700; }}
  p {{ color: #7d8590; max-width: 400px; line-height: 1.6; }}
  code {{ background: #161b22; border: 1px solid #30363d; padding: 2px 8px; border-radius: 4px; font-size: 13px; }}
</style>
</head>
<body>
  <div class="big">🏏</div>
  <h1>No analysis yet for this match!</h1>
  <p>We haven't fact-checked this video yet. Run the pipeline first:</p>
  <p><code>debatelens run --youtube https://youtube.com/watch?v={video_id}</code></p>
  <p>Then come back here — the scorecard will be ready.</p>
</body>
</html>"""
