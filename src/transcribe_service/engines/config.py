from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SarvamConfig:
    api_key: str


@dataclass
class GoogleConfig:
    project_id: str
    location: str
    credentials_path: str | None = None
