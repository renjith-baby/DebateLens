from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    max_concurrent_jobs: int = 2
    job_timeout_seconds: int = 1800

    output_dir: Path = Field(default=Path("./output"))
    uploads_dir: Path = Field(default=Path("./uploads"))
    job_store_path: Path = Field(default=Path("./output/jobs.json"))

    webhook_secret: str | None = None
    webhook_timeout_seconds: int = 10

    sarvam_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "asia-southeast1"
    google_application_credentials: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
