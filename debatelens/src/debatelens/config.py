from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    gemini_api_key: str
    sarvam_api_key: str
    service_url: str
    out_dir: Path
    model_fast: str
    model_pro: str
    repo_root: Path


def load_settings(repo_root: Path | None = None) -> Settings:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    load_dotenv(root / ".env")
    load_dotenv(root / "transcribe-service" / ".env", override=False)

    gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    sarvam = os.environ.get("SARVAM_API_KEY", "").strip()
    if not gemini:
        raise RuntimeError("GEMINI_API_KEY is not set (put it in .env at repo root)")
    if not sarvam:
        raise RuntimeError("SARVAM_API_KEY is not set (put it in transcribe-service/.env)")

    return Settings(
        gemini_api_key=gemini,
        sarvam_api_key=sarvam,
        service_url=os.environ.get("DEBATELENS_SERVICE_URL", "http://localhost:8080"),
        out_dir=Path(os.environ.get("DEBATELENS_OUT_DIR", root / "output")),
        model_fast=os.environ.get("DEBATELENS_GEMINI_MODEL_FAST", "gemini-2.0-flash"),
        model_pro=os.environ.get("DEBATELENS_GEMINI_MODEL_PRO", "gemini-2.5-pro"),
        repo_root=root,
    )
