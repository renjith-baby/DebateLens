from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

from debatelens.analysis.gemini_client import GeminiClient, GeminiConfig
from debatelens.analysis.runner import AnalysisRunner, RunnerConfig
from debatelens.config import load_settings
from debatelens.models import Transcript
from debatelens.render.dashboard import render_dashboard
from debatelens.service_supervisor import supervised_service
from debatelens.transcribe_client import TranscribeClient


logger = logging.getLogger("debatelens")


def _parse_speaker_names(spec: str | None) -> dict[str, str]:
    if not spec:
        return {}
    out: dict[str, str] = {}
    for pair in spec.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="debatelens")
    sub = p.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run the full pipeline")
    src = run_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--youtube", help="YouTube URL")
    src.add_argument("--audio", help="path to audio file")
    src.add_argument("--transcript", help="path to existing transcript JSON (skip transcription)")
    run_p.add_argument("--speaker-names", default=None,
                       help="comma-separated id=name pairs, e.g. '1=Maitreyan,2=Venugopan'")
    run_p.add_argument("--show-title", default="Debate")
    run_p.add_argument("--service-url", default=None)
    run_p.add_argument("--no-autostart", action="store_true")
    run_p.add_argument("--out-dir", default=None)
    return p


async def _get_transcript(args, settings) -> Transcript:
    if args.transcript:
        raw = json.loads(Path(args.transcript).read_text())
        return Transcript.model_validate(raw)

    service_url = args.service_url or settings.service_url

    with supervised_service(
        base_url=service_url,
        service_dir=settings.repo_root,
        auto_start=not args.no_autostart,
    ):
        client = TranscribeClient(base_url=service_url)
        if args.youtube:
            job_id = await client.submit_url(url=args.youtube)
        else:
            job_id = await client.submit_file(path=Path(args.audio))
        logger.info("transcription job_id=%s", job_id)
        return await client.wait_for_transcript(job_id, timeout_seconds=1800)


async def main_async(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.error("unknown command")

    settings = load_settings()
    out_dir = Path(args.out_dir) if args.out_dir else settings.out_dir
    run_id = uuid.uuid4().hex[:8]
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    transcript = await _get_transcript(args, settings)
    (run_dir / "transcript.json").write_text(
        json.dumps(transcript.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("transcript saved to %s", run_dir / "transcript.json")

    gemini = GeminiClient(GeminiConfig(
        api_key=settings.gemini_api_key,
        model_fast=settings.model_fast,
        model_pro=settings.model_pro,
    ))
    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(
            prompts_dir=settings.repo_root / "prompts" / "v1",
            model_fast=settings.model_fast,
            model_pro=settings.model_pro,
        ),
    )
    output = runner.run(
        transcript=transcript,
        show_title=args.show_title,
        speaker_names=_parse_speaker_names(args.speaker_names),
    )
    (run_dir / "analysis.json").write_text(
        json.dumps(output.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_dashboard(output, run_dir / "dashboard.html")

    print(f"\nDashboard: {run_dir / 'dashboard.html'}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
