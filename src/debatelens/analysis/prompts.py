from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import StrictUndefined, Template
from pydantic import BaseModel, Field


class PromptHeader(BaseModel):
    name: str
    purpose: str = ""
    input_variables: list[str] = Field(default_factory=list)
    output_schema: str | None = None
    model_hint: str | None = None
    temperature: float = 0.0
    tools: list[str] = Field(default_factory=list)


@dataclass
class Prompt:
    header: PromptHeader
    body: str


def load_prompt(path: Path) -> Prompt:
    raw = Path(path).read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"prompt file missing frontmatter: {path}")
    _, fm, body = raw.split("---\n", 2)
    header = PromptHeader.model_validate(yaml.safe_load(fm))
    return Prompt(header=header, body=body.lstrip("\n"))


def render_prompt(prompt: Prompt, **kwargs) -> str:
    declared = set(prompt.header.input_variables)
    given = set(kwargs.keys())
    unknown = given - declared
    if unknown:
        raise KeyError(f"unknown variables: {sorted(unknown)}")
    missing = declared - given
    if missing:
        raise KeyError(f"missing variables: {sorted(missing)}")
    template = Template(prompt.body, undefined=StrictUndefined)
    return template.render(**kwargs)
