# DebateLens End-to-End Batch Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `debatelens` Python package that takes a YouTube URL or audio file, transcribes it via the existing `transcribe-service`, runs the `prompts/v1/*.md` analysis pipeline on Gemini, and renders a self-contained `dashboard.html`.

**Architecture:** New top-level `debatelens/` package. CLI auto-starts `transcribe-service` as a subprocess (HTTP boundary), submits a job, polls until done, ingests the transcript, walks 5 prompt stages on Gemini (Flash for cheap stages, Pro + Google Search grounding for fact-check), produces `analysis.json`, and renders a Jinja-templated copy of `sample-dashboard.html`.

**Tech Stack:** Python 3.11+, Pydantic v2, httpx, google-genai (Gemini SDK), Jinja2, pyyaml, python-dotenv, pytest + respx.

**Source spec:** [docs/superpowers/specs/2026-05-09-end-to-end-debatelens-design.md](../specs/2026-05-09-end-to-end-debatelens-design.md)

---

## File Structure

```
debatelens/
  pyproject.toml
  README.md
  src/debatelens/
    __init__.py
    cli.py
    config.py
    models.py
    transcribe_client.py
    service_supervisor.py
    scoring.py
    analysis/
      __init__.py
      windowing.py
      prompts.py
      gemini_client.py
      runner.py
    render/
      __init__.py
      dashboard.py
      template.html
  tests/
    __init__.py
    conftest.py
    fixtures/
      transcript_sample.json
      windowed_sample.json
    test_models.py
    test_windowing.py
    test_prompts.py
    test_scoring.py
    test_gemini_client.py
    test_runner.py
    test_transcribe_client.py
    test_render.py
    test_cli.py
```

Each file has one responsibility:
- `models.py` — all Pydantic types shared across modules (no logic).
- `analysis/windowing.py` — pure function: transcript → windows.
- `analysis/prompts.py` — pure function: load + render prompt files.
- `analysis/gemini_client.py` — thin Gemini SDK wrapper, retry, structured output.
- `analysis/runner.py` — orchestrator only. No I/O beyond Gemini calls.
- `transcribe_client.py` — HTTP client for transcribe-service. No process management.
- `service_supervisor.py` — subprocess management only. No HTTP.
- `scoring.py` — deterministic rollup. Pure function.
- `render/dashboard.py` — Jinja render only. Reads template, writes HTML.
- `cli.py` — argparse + glue. Thin wiring of the above.

---

## Task 1: Bootstrap package skeleton

**Files:**
- Create: `debatelens/pyproject.toml`
- Create: `debatelens/src/debatelens/__init__.py`
- Create: `debatelens/src/debatelens/analysis/__init__.py`
- Create: `debatelens/src/debatelens/render/__init__.py`
- Create: `debatelens/tests/__init__.py`
- Create: `debatelens/tests/conftest.py`
- Create: `debatelens/README.md`

- [ ] **Step 1: Create the package directory and pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "debatelens"
version = "0.1.0"
description = "End-to-end batch pipeline: audio/YT URL -> transcript -> analysis -> dashboard"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "httpx>=0.27",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "google-genai>=0.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[project.scripts]
debatelens = "debatelens.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty `__init__.py` files**

`debatelens/src/debatelens/__init__.py`:
```python
__version__ = "0.1.0"
```

`debatelens/src/debatelens/analysis/__init__.py`: empty
`debatelens/src/debatelens/render/__init__.py`: empty
`debatelens/tests/__init__.py`: empty

- [ ] **Step 3: Create conftest.py**

`debatelens/tests/conftest.py`:
```python
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
```

- [ ] **Step 4: Create README.md stub**

`debatelens/README.md`:
```markdown
# debatelens

End-to-end batch pipeline for DebateLens: hand it a YouTube URL or audio file, get back a populated `dashboard.html`.

## Run

```bash
pip install -e ".[dev]"
export GEMINI_API_KEY=...
export SARVAM_API_KEY=...
python -m debatelens run --youtube https://youtu.be/XXXX
open output/<run_id>/dashboard.html
```

See `../docs/superpowers/specs/2026-05-09-end-to-end-debatelens-design.md` for the full design.
```

- [ ] **Step 5: Install dev deps**

```bash
cd debatelens && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```

Expected: clean install, no errors.

- [ ] **Step 6: Smoke-check pytest discovery**

Run: `cd debatelens && pytest -v`
Expected: `no tests ran` (no errors).

- [ ] **Step 7: Commit**

```bash
git add debatelens/
git commit -m "feat(debatelens): bootstrap package skeleton"
```

---

## Task 2: Pydantic models

**Files:**
- Create: `debatelens/src/debatelens/models.py`
- Create: `debatelens/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_models.py`:
```python
from debatelens.models import (
    AnalysisOutput,
    Claim,
    Fallacy,
    Moment,
    Segment,
    SpeakerScore,
    Transcript,
    Verdict,
    Window,
)


def test_segment_basic():
    s = Segment(speaker="1", text="hello", start_time=0.0, end_time=1.5)
    assert s.speaker == "1"
    assert s.duration == 1.5


def test_transcript_roundtrip():
    t = Transcript(
        segments=[Segment(speaker="1", text="a", start_time=0.0, end_time=1.0)],
        language="ml-IN",
    )
    data = t.model_dump()
    again = Transcript.model_validate(data)
    assert again.segments[0].text == "a"


def test_window_concat_text():
    w = Window(
        index=0,
        start_time=0.0,
        end_time=60.0,
        segments=[
            Segment(speaker="1", text="A", start_time=0.0, end_time=1.0),
            Segment(speaker="2", text="B", start_time=1.0, end_time=2.0),
        ],
    )
    assert w.text == "[1] A\n[2] B"


def test_claim_defaults():
    c = Claim(
        claim_id="c1",
        speaker="1",
        video_timestamp="01:00",
        claim_ml="x",
        claim_en="y",
        claim_category="factual",
    )
    assert c.flags == []


def test_verdict_confidence_bounds():
    v = Verdict(
        claim_id="c1",
        verdict="true",
        confidence=0.9,
        one_liner="ok",
        evidence_paragraph="because",
        sources=[],
    )
    assert 0.0 <= v.confidence <= 1.0


def test_fallacy_basic():
    f = Fallacy(
        fallacy_type="ad_hominem",
        tier=1,
        speaker="1",
        video_timestamp="00:30",
        quote_ml="x",
        quote_en="y",
        explanation="z",
        confidence=0.93,
    )
    assert f.tier == 1


def test_moment_kinds():
    m = Moment(kind="wrong", label="Not true", quote="q", note="n")
    assert m.kind == "wrong"


def test_speaker_score_bounds():
    s = SpeakerScore(accuracy=78, civility=65, reasoning=72)
    assert s.accuracy == 78


def test_analysis_output_shape():
    out = AnalysisOutput(
        show={"title": "X", "minutes": 10},
        speakers={
            "1": {
                "name": "Speaker 1",
                "role": "Guest",
                "stats": {"verified": 1, "wrong": 0, "flagged": 0},
                "moments": [{"kind": "verified", "label": "True", "quote": "q", "note": "n"}],
                "scores": {"accuracy": 100, "civility": 100, "reasoning": 100},
            }
        },
        now=None,
    )
    assert "1" in out.speakers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatelens.models'`

- [ ] **Step 3: Implement `models.py`**

`debatelens/src/debatelens/models.py`:
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ClaimCategory = Literal["factual", "numerical", "causal", "predictive", "opinion"]
VerdictLabel = Literal["true", "false", "disputed", "unverifiable", "outdated"]
MomentKind = Literal["verified", "wrong", "outdated", "flag", "unsure"]


class Segment(BaseModel):
    speaker: str
    text: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class Transcript(BaseModel):
    segments: list[Segment]
    language: str = "ml-IN"


class Window(BaseModel):
    index: int
    start_time: float
    end_time: float
    segments: list[Segment]

    @property
    def text(self) -> str:
        return "\n".join(f"[{s.speaker}] {s.text}" for s in self.segments)


class Claim(BaseModel):
    claim_id: str
    speaker: str
    video_timestamp: str
    claim_ml: str
    claim_en: str
    claim_category: ClaimCategory
    flags: list[str] = Field(default_factory=list)


class Source(BaseModel):
    title: str
    url: str


class Verdict(BaseModel):
    claim_id: str
    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    one_liner: str
    evidence_paragraph: str
    sources: list[Source] = Field(default_factory=list)
    context_caveat: str | None = None


class Fallacy(BaseModel):
    fallacy_type: str
    tier: Literal[1, 2, 3]
    speaker: str
    video_timestamp: str
    quote_ml: str
    quote_en: str
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    turn_range: tuple[int, int] | None = None


class Moment(BaseModel):
    kind: MomentKind
    label: str
    quote: str
    note: str


class SpeakerStats(BaseModel):
    verified: int = 0
    wrong: int = 0
    flagged: int = 0


class SpeakerScore(BaseModel):
    accuracy: int = Field(ge=0, le=100, default=100)
    civility: int = Field(ge=0, le=100, default=100)
    reasoning: int = Field(ge=0, le=100, default=100)


class SpeakerSummary(BaseModel):
    name: str
    role: str = "Speaker"
    stats: SpeakerStats = Field(default_factory=SpeakerStats)
    moments: list[Moment] = Field(default_factory=list)
    scores: SpeakerScore = Field(default_factory=SpeakerScore)


class NowItem(BaseModel):
    quote: str
    verdict_kind: MomentKind
    verdict_text: str


class ShowMeta(BaseModel):
    title: str
    minutes: int = 0


class AnalysisOutput(BaseModel):
    show: ShowMeta
    speakers: dict[str, SpeakerSummary]
    now: NowItem | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_models.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/models.py debatelens/tests/test_models.py
git commit -m "feat(debatelens): add pydantic models for pipeline I/O"
```

---

## Task 3: Windowing

**Files:**
- Create: `debatelens/src/debatelens/analysis/windowing.py`
- Create: `debatelens/tests/test_windowing.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_windowing.py`:
```python
from debatelens.analysis.windowing import to_windows
from debatelens.models import Segment, Transcript


def _seg(speaker, text, start, end):
    return Segment(speaker=speaker, text=text, start_time=start, end_time=end)


def test_to_windows_single_window_under_target():
    t = Transcript(segments=[
        _seg("1", "a", 0.0, 10.0),
        _seg("2", "b", 10.0, 20.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert len(windows) == 1
    assert windows[0].index == 0
    assert len(windows[0].segments) == 2


def test_to_windows_splits_on_target_seconds():
    t = Transcript(segments=[
        _seg("1", "a", 0.0, 30.0),
        _seg("2", "b", 30.0, 65.0),
        _seg("1", "c", 65.0, 90.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert len(windows) == 2
    assert windows[0].segments[0].text == "a"
    assert windows[0].segments[-1].text == "b"
    assert windows[1].segments[0].text == "c"


def test_to_windows_empty():
    t = Transcript(segments=[])
    assert to_windows(t, target_seconds=60.0) == []


def test_window_indices_sequential():
    t = Transcript(segments=[
        _seg("1", str(i), float(i * 30), float((i + 1) * 30)) for i in range(5)
    ])
    windows = to_windows(t, target_seconds=60.0)
    indices = [w.index for w in windows]
    assert indices == sorted(indices)
    assert indices[0] == 0


def test_window_times_match_segments():
    t = Transcript(segments=[
        _seg("1", "a", 5.0, 15.0),
        _seg("2", "b", 15.0, 70.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert windows[0].start_time == 5.0
    assert windows[0].end_time == 70.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_windowing.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `windowing.py`**

`debatelens/src/debatelens/analysis/windowing.py`:
```python
from __future__ import annotations

from debatelens.models import Segment, Transcript, Window


def to_windows(transcript: Transcript, target_seconds: float = 60.0) -> list[Window]:
    if not transcript.segments:
        return []

    windows: list[Window] = []
    current: list[Segment] = []
    current_start: float | None = None
    idx = 0

    for seg in transcript.segments:
        if current_start is None:
            current_start = seg.start_time
        current.append(seg)
        if seg.end_time - current_start >= target_seconds:
            windows.append(Window(
                index=idx,
                start_time=current_start,
                end_time=seg.end_time,
                segments=current,
            ))
            idx += 1
            current = []
            current_start = None

    if current:
        windows.append(Window(
            index=idx,
            start_time=current_start or current[0].start_time,
            end_time=current[-1].end_time,
            segments=current,
        ))

    return windows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_windowing.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/analysis/windowing.py debatelens/tests/test_windowing.py
git commit -m "feat(debatelens): add transcript windowing"
```

---

## Task 4: Prompt loader

**Files:**
- Create: `debatelens/src/debatelens/analysis/prompts.py`
- Create: `debatelens/tests/test_prompts.py`
- Create: `debatelens/tests/fixtures/example_prompt.md`

- [ ] **Step 1: Write fixture prompt file**

`debatelens/tests/fixtures/example_prompt.md`:
```markdown
---
name: example
purpose: test fixture
input_variables: [window_text]
output_schema: ExampleOut
model_hint: gemini-2.0-flash
temperature: 0.0
---

You will analyze: {{ window_text }}.
```

- [ ] **Step 2: Write failing tests**

`debatelens/tests/test_prompts.py`:
```python
from pathlib import Path

import pytest

from debatelens.analysis.prompts import PromptHeader, load_prompt, render_prompt


def test_load_prompt_parses_frontmatter(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    assert isinstance(p.header, PromptHeader)
    assert p.header.name == "example"
    assert p.header.input_variables == ["window_text"]
    assert p.header.model_hint == "gemini-2.0-flash"
    assert p.header.temperature == 0.0
    assert "{{ window_text }}" in p.body


def test_render_prompt_substitutes_variables(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    out = render_prompt(p, window_text="hello world")
    assert "You will analyze: hello world." in out


def test_render_prompt_rejects_unknown_variable(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    with pytest.raises(KeyError):
        render_prompt(p, wrong_var="x")


def test_load_prompt_missing_frontmatter_fails(tmp_path: Path):
    f = tmp_path / "no_fm.md"
    f.write_text("just a body")
    with pytest.raises(ValueError):
        load_prompt(f)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_prompts.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `prompts.py`**

`debatelens/src/debatelens/analysis/prompts.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_prompts.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add debatelens/src/debatelens/analysis/prompts.py debatelens/tests/test_prompts.py debatelens/tests/fixtures/example_prompt.md
git commit -m "feat(debatelens): add prompt loader with frontmatter + jinja"
```

---

## Task 5: Scoring rollup

**Files:**
- Create: `debatelens/src/debatelens/scoring.py`
- Create: `debatelens/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_scoring.py`:
```python
from debatelens.models import Fallacy, Verdict
from debatelens.scoring import compute_speaker_scores, verdict_to_moment_kind


def _verdict(speaker_id: str, label: str, conf: float = 0.9) -> tuple[str, Verdict]:
    return speaker_id, Verdict(
        claim_id=f"c-{speaker_id}-{label}",
        verdict=label,  # type: ignore[arg-type]
        confidence=conf,
        one_liner="x",
        evidence_paragraph="y",
        sources=[],
    )


def _fallacy(speaker_id: str, tier: int, ftype: str = "ad_hominem") -> Fallacy:
    return Fallacy(
        fallacy_type=ftype,
        tier=tier,  # type: ignore[arg-type]
        speaker=speaker_id,
        video_timestamp="00:00",
        quote_ml="x",
        quote_en="y",
        explanation="z",
        confidence=0.9,
    )


def test_starts_at_100_with_no_events():
    scores = compute_speaker_scores(verdicts_by_speaker={}, fallacies_by_speaker={}, speakers={"1"})
    assert scores["1"].accuracy == 100
    assert scores["1"].civility == 100
    assert scores["1"].reasoning == 100


def test_false_verdict_drops_accuracy():
    v = _verdict("1", "false")
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [v[1]]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy < 100


def test_true_verdict_keeps_accuracy_high():
    v = _verdict("1", "true")
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [v[1]]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy == 100


def test_tier1_fallacy_drops_civility():
    scores = compute_speaker_scores(
        verdicts_by_speaker={},
        fallacies_by_speaker={"1": [_fallacy("1", 1, "ad_hominem")]},
        speakers={"1"},
    )
    assert scores["1"].civility < 100
    assert scores["1"].reasoning < 100


def test_unverifiable_no_op():
    v = _verdict("1", "unverifiable")
    scores = compute_speaker_scores(
        verdicts_by_speaker={"1": [v[1]]},
        fallacies_by_speaker={},
        speakers={"1"},
    )
    assert scores["1"].accuracy == 100


def test_verdict_to_moment_kind_mapping():
    assert verdict_to_moment_kind("true") == "verified"
    assert verdict_to_moment_kind("false") == "wrong"
    assert verdict_to_moment_kind("outdated") == "outdated"
    assert verdict_to_moment_kind("disputed") == "unsure"
    assert verdict_to_moment_kind("unverifiable") == "unsure"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scoring.py`**

`debatelens/src/debatelens/scoring.py`:
```python
from __future__ import annotations

from debatelens.models import Fallacy, MomentKind, SpeakerScore, Verdict, VerdictLabel


VERDICT_DELTA: dict[VerdictLabel, int] = {
    "true": 0,
    "false": -25,
    "disputed": -8,
    "outdated": -10,
    "unverifiable": 0,
}

FALLACY_CIVILITY_BY_TIER = {1: -12, 2: -6, 3: -3}
FALLACY_REASONING_BY_TIER = {1: -8, 2: -5, 3: -2}
AD_HOMINEM_EXTRA_CIVILITY = -8

VERDICT_TO_KIND: dict[VerdictLabel, MomentKind] = {
    "true": "verified",
    "false": "wrong",
    "outdated": "outdated",
    "disputed": "unsure",
    "unverifiable": "unsure",
}


def verdict_to_moment_kind(label: VerdictLabel) -> MomentKind:
    return VERDICT_TO_KIND[label]


def _clamp(n: int) -> int:
    return max(0, min(100, n))


def compute_speaker_scores(
    *,
    verdicts_by_speaker: dict[str, list[Verdict]],
    fallacies_by_speaker: dict[str, list[Fallacy]],
    speakers: set[str],
) -> dict[str, SpeakerScore]:
    out: dict[str, SpeakerScore] = {}
    for sp in speakers:
        accuracy = 100
        civility = 100
        reasoning = 100
        for v in verdicts_by_speaker.get(sp, []):
            accuracy += VERDICT_DELTA[v.verdict]
        for f in fallacies_by_speaker.get(sp, []):
            civility += FALLACY_CIVILITY_BY_TIER[f.tier]
            reasoning += FALLACY_REASONING_BY_TIER[f.tier]
            if f.fallacy_type == "ad_hominem":
                civility += AD_HOMINEM_EXTRA_CIVILITY
        out[sp] = SpeakerScore(
            accuracy=_clamp(accuracy),
            civility=_clamp(civility),
            reasoning=_clamp(reasoning),
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_scoring.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/scoring.py debatelens/tests/test_scoring.py
git commit -m "feat(debatelens): add per-speaker scoring rollup"
```

---

## Task 6: Gemini client wrapper

**Files:**
- Create: `debatelens/src/debatelens/analysis/gemini_client.py`
- Create: `debatelens/tests/test_gemini_client.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_gemini_client.py`:
```python
from unittest.mock import MagicMock, patch

import pytest

from debatelens.analysis.gemini_client import GeminiClient, GeminiConfig


@pytest.fixture
def gemini_config():
    return GeminiConfig(
        api_key="test-key",
        model_fast="gemini-2.0-flash",
        model_pro="gemini-2.5-pro",
    )


def test_generate_json_returns_parsed_dict(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = '{"key": "value"}'
    fake_models = MagicMock()
    fake_models.generate_content.return_value = fake_resp
    fake_client = MagicMock()
    fake_client.models = fake_models

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="hello")

    assert result == {"key": "value"}


def test_generate_json_strips_code_fence(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = "```json\n{\"k\": 1}\n```"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="x")

    assert result == {"k": 1}


def test_generate_json_retries_on_invalid_json(gemini_config):
    bad = MagicMock()
    bad.text = "not json"
    good = MagicMock()
    good.text = '{"ok": true}'
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [bad, good]

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="x")

    assert result == {"ok": True}
    assert fake_client.models.generate_content.call_count == 2


def test_generate_with_search_uses_grounding_tool(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = '{"verdict": "true"}'
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.5-pro", prompt="x", with_search=True)

    assert result == {"verdict": "true"}
    call = fake_client.models.generate_content.call_args
    config = call.kwargs.get("config") or call.args[-1]
    # Tools should be present when with_search=True
    assert config is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_gemini_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `gemini_client.py`**

`debatelens/src/debatelens/analysis/gemini_client.py`:
```python
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from google import genai
from google.genai import types as gtypes


logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass
class GeminiConfig:
    api_key: str
    model_fast: str = "gemini-2.0-flash"
    model_pro: str = "gemini-2.5-pro"
    max_retries: int = 2


class GeminiClient:
    def __init__(self, config: GeminiConfig) -> None:
        self._config = config
        self._client = genai.Client(api_key=config.api_key)

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        with_search: bool = False,
        temperature: float = 0.0,
    ) -> dict | list:
        config = gtypes.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if not with_search else None,
        )
        if with_search:
            config.tools = [gtypes.Tool(google_search=gtypes.GoogleSearch())]

        last_err: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            resp = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            text = (resp.text or "").strip()
            stripped = _strip_fence(text)
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning("gemini returned non-JSON (attempt %s): %s", attempt + 1, text[:200])
                prompt = (
                    f"{prompt}\n\nYour previous response was not valid JSON. "
                    "Return ONLY the JSON object, no prose, no code fences."
                )

        raise RuntimeError(f"gemini failed to produce valid JSON: {last_err}")


def _strip_fence(text: str) -> str:
    m = _FENCE.match(text.strip())
    return m.group(1) if m else text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_gemini_client.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/analysis/gemini_client.py debatelens/tests/test_gemini_client.py
git commit -m "feat(debatelens): add gemini client wrapper with json + search grounding"
```

---

## Task 7: Analysis runner (orchestrator)

**Files:**
- Create: `debatelens/src/debatelens/analysis/runner.py`
- Create: `debatelens/tests/test_runner.py`
- Create: `debatelens/tests/fixtures/transcript_sample.json`

- [ ] **Step 1: Create transcript fixture**

`debatelens/tests/fixtures/transcript_sample.json`:
```json
{
  "segments": [
    {"speaker": "1", "text": "We dropped the atomic bomb only once.", "start_time": 5.0, "end_time": 10.0},
    {"speaker": "2", "text": "That is incorrect — there were two.", "start_time": 10.0, "end_time": 15.0},
    {"speaker": "1", "text": "You are nobody important.", "start_time": 15.0, "end_time": 18.0},
    {"speaker": "2", "text": "Schengen has 28 countries.", "start_time": 65.0, "end_time": 70.0}
  ],
  "language": "ml-IN"
}
```

- [ ] **Step 2: Write failing tests**

`debatelens/tests/test_runner.py`:
```python
import json
from unittest.mock import MagicMock

import pytest

from debatelens.analysis.runner import AnalysisRunner, RunnerConfig
from debatelens.models import Transcript


@pytest.fixture
def transcript(fixtures_dir) -> Transcript:
    raw = json.loads((fixtures_dir / "transcript_sample.json").read_text())
    return Transcript.model_validate(raw)


def _stub_gemini(responses_by_stage: dict[str, list]) -> MagicMock:
    """Build a mock GeminiClient that returns canned JSON per call.

    responses_by_stage maps prompt name (extract/classify/factcheck/etc) -> list of responses to return in order.
    The mock infers stage from the prompt content keyword.
    """
    state = {k: iter(v) for k, v in responses_by_stage.items()}

    def generate(*, model, prompt, with_search=False, temperature=0.0):
        for key, it in state.items():
            if key in prompt.lower():
                return next(it)
        return {}

    m = MagicMock()
    m.generate_json.side_effect = generate
    return m


def test_runner_produces_analysis_output_shape(transcript, tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts" / "v1"
    prompts_dir.mkdir(parents=True)
    for name, body in [
        ("extract_claims", "extract from {{ window_text }}"),
        ("classify_claim", "classify {{ claim_en }}"),
        ("factcheck_claim", "factcheck {{ claim_en }}"),
        ("detect_fallacy_single", "fallacy single {{ window_text }}"),
        ("detect_fallacy_multiturn", "fallacy multiturn {{ window_text }}"),
    ]:
        vars_list = {
            "extract_claims": ["window_text"],
            "classify_claim": ["claim_en"],
            "factcheck_claim": ["claim_en"],
            "detect_fallacy_single": ["window_text"],
            "detect_fallacy_multiturn": ["window_text"],
        }[name]
        (prompts_dir / f"{name}.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"input_variables: {vars_list}\n"
            f"model_hint: gemini-2.0-flash\n"
            "temperature: 0.0\n"
            "---\n"
            f"{body}\n"
        )

    gemini = _stub_gemini({
        "extract from": [
            {"claims": [
                {"claim_id": "c1", "speaker": "1", "video_timestamp": "00:05",
                 "claim_ml": "x", "claim_en": "We dropped the atomic bomb only once.",
                 "claim_category": "factual", "flags": []}
            ]},
            {"claims": [
                {"claim_id": "c2", "speaker": "2", "video_timestamp": "01:05",
                 "claim_ml": "y", "claim_en": "Schengen has 28 countries.",
                 "claim_category": "numerical", "flags": []}
            ]},
        ],
        "classify": [
            {"claim_id": "c1", "claim_category": "factual", "flags": []},
            {"claim_id": "c2", "claim_category": "numerical", "flags": []},
        ],
        "factcheck": [
            {"claim_id": "c1", "verdict": "false", "confidence": 0.97,
             "one_liner": "Two bombs.", "evidence_paragraph": "...", "sources": []},
            {"claim_id": "c2", "verdict": "outdated", "confidence": 0.92,
             "one_liner": "29 since 2024.", "evidence_paragraph": "...", "sources": []},
        ],
        "fallacy single": [
            {"fallacies": [
                {"fallacy_type": "ad_hominem", "tier": 1, "speaker": "1",
                 "video_timestamp": "00:15", "quote_ml": "z", "quote_en": "You are nobody important.",
                 "explanation": "personal attack", "confidence": 0.95}
            ]},
            {"fallacies": []},
        ],
        "fallacy multiturn": [
            {"fallacies": []},
            {"fallacies": []},
        ],
    })

    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(prompts_dir=prompts_dir),
    )
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={"1": "A", "2": "B"})

    assert "1" in out.speakers
    assert "2" in out.speakers
    assert out.speakers["1"].name == "A"
    moments_1 = out.speakers["1"].moments
    assert any(m.kind == "wrong" for m in moments_1)
    assert any(m.kind == "flag" for m in moments_1)
    moments_2 = out.speakers["2"].moments
    assert any(m.kind == "outdated" for m in moments_2)


def test_runner_skips_low_confidence(transcript, tmp_path):
    prompts_dir = tmp_path / "prompts" / "v1"
    prompts_dir.mkdir(parents=True)
    for name in ["extract_claims", "classify_claim", "factcheck_claim",
                 "detect_fallacy_single", "detect_fallacy_multiturn"]:
        (prompts_dir / f"{name}.md").write_text(
            f"---\nname: {name}\ninput_variables: []\nmodel_hint: gemini-2.0-flash\ntemperature: 0.0\n---\nbody\n"
        )

    gemini = MagicMock()
    gemini.generate_json.return_value = {"claims": [], "fallacies": []}

    runner = AnalysisRunner(
        gemini=gemini,
        config=RunnerConfig(prompts_dir=prompts_dir, confidence_threshold=0.85),
    )
    out = runner.run(transcript=transcript, show_title="Test", speaker_names={})
    assert sum(len(s.moments) for s in out.speakers.values()) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `runner.py`**

`debatelens/src/debatelens/analysis/runner.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from debatelens.analysis.gemini_client import GeminiClient
from debatelens.analysis.prompts import Prompt, load_prompt, render_prompt
from debatelens.analysis.windowing import to_windows
from debatelens.models import (
    AnalysisOutput,
    Claim,
    Fallacy,
    Moment,
    NowItem,
    ShowMeta,
    SpeakerStats,
    SpeakerSummary,
    Transcript,
    Verdict,
)
from debatelens.scoring import compute_speaker_scores, verdict_to_moment_kind


PROMPT_FILES = {
    "extract": "extract_claims.md",
    "classify": "classify_claim.md",
    "factcheck": "factcheck_claim.md",
    "fallacy_single": "detect_fallacy_single.md",
    "fallacy_multi": "detect_fallacy_multiturn.md",
}


@dataclass
class RunnerConfig:
    prompts_dir: Path
    confidence_threshold: float = 0.85
    window_seconds: float = 60.0
    model_fast: str = "gemini-2.0-flash"
    model_pro: str = "gemini-2.5-pro"


class AnalysisRunner:
    def __init__(self, *, gemini: GeminiClient, config: RunnerConfig) -> None:
        self._gemini = gemini
        self._config = config
        self._prompts: dict[str, Prompt] = {
            key: load_prompt(config.prompts_dir / fname)
            for key, fname in PROMPT_FILES.items()
        }

    def run(
        self,
        *,
        transcript: Transcript,
        show_title: str,
        speaker_names: dict[str, str],
    ) -> AnalysisOutput:
        windows = to_windows(transcript, target_seconds=self._config.window_seconds)

        all_verdicts: dict[str, list[Verdict]] = {}
        all_fallacies: dict[str, list[Fallacy]] = {}
        moments_per_speaker: dict[str, list[Moment]] = {}
        speaker_set: set[str] = {seg.speaker for seg in transcript.segments}
        last_moment: tuple[str, Moment] | None = None

        for w in windows:
            extract_resp = self._gemini.generate_json(
                model=self._config.model_fast,
                prompt=render_prompt(self._prompts["extract"], window_text=w.text),
            )
            claims_raw = extract_resp.get("claims", []) if isinstance(extract_resp, dict) else []
            claims: list[Claim] = []
            for c in claims_raw:
                try:
                    claims.append(Claim.model_validate(c))
                except Exception:
                    continue

            for claim in claims:
                self._gemini.generate_json(
                    model=self._config.model_fast,
                    prompt=render_prompt(self._prompts["classify"], claim_en=claim.claim_en),
                )
                fc_resp = self._gemini.generate_json(
                    model=self._config.model_pro,
                    prompt=render_prompt(self._prompts["factcheck"], claim_en=claim.claim_en),
                    with_search=True,
                )
                try:
                    verdict = Verdict.model_validate({**fc_resp, "claim_id": claim.claim_id})
                except Exception:
                    continue
                if verdict.confidence < self._config.confidence_threshold:
                    continue
                all_verdicts.setdefault(claim.speaker, []).append(verdict)
                kind = verdict_to_moment_kind(verdict.verdict)
                moment = Moment(
                    kind=kind,
                    label=_label_for_kind(kind),
                    quote=claim.claim_en,
                    note=verdict.one_liner,
                )
                moments_per_speaker.setdefault(claim.speaker, []).append(moment)
                last_moment = (claim.speaker, moment)

            for stage_key in ("fallacy_single", "fallacy_multi"):
                resp = self._gemini.generate_json(
                    model=self._config.model_pro,
                    prompt=render_prompt(self._prompts[stage_key], window_text=w.text),
                )
                for f_raw in (resp.get("fallacies", []) if isinstance(resp, dict) else []):
                    try:
                        fallacy = Fallacy.model_validate(f_raw)
                    except Exception:
                        continue
                    if fallacy.confidence < self._config.confidence_threshold:
                        continue
                    all_fallacies.setdefault(fallacy.speaker, []).append(fallacy)
                    moment = Moment(
                        kind="flag",
                        label=_fallacy_label(fallacy.fallacy_type),
                        quote=fallacy.quote_en,
                        note=fallacy.explanation,
                    )
                    moments_per_speaker.setdefault(fallacy.speaker, []).append(moment)
                    last_moment = (fallacy.speaker, moment)

        scores = compute_speaker_scores(
            verdicts_by_speaker=all_verdicts,
            fallacies_by_speaker=all_fallacies,
            speakers=speaker_set,
        )

        speakers_out: dict[str, SpeakerSummary] = {}
        for sp in speaker_set:
            moments = moments_per_speaker.get(sp, [])
            stats = SpeakerStats(
                verified=sum(1 for m in moments if m.kind == "verified"),
                wrong=sum(1 for m in moments if m.kind == "wrong"),
                flagged=sum(1 for m in moments if m.kind == "flag"),
            )
            speakers_out[sp] = SpeakerSummary(
                name=speaker_names.get(sp, f"Speaker {sp}"),
                role="Speaker",
                stats=stats,
                moments=moments,
                scores=scores[sp],
            )

        now = None
        if last_moment is not None:
            sp, m = last_moment
            now = NowItem(
                quote=m.quote,
                verdict_kind=m.kind,
                verdict_text=m.note,
            )

        total_seconds = transcript.segments[-1].end_time if transcript.segments else 0.0
        return AnalysisOutput(
            show=ShowMeta(title=show_title, minutes=int(total_seconds // 60)),
            speakers=speakers_out,
            now=now,
        )


def _label_for_kind(kind: str) -> str:
    return {
        "verified": "True",
        "wrong": "Not true",
        "outdated": "Out of date",
        "unsure": "Couldn't verify",
        "flag": "Flagged",
    }.get(kind, kind)


def _fallacy_label(ftype: str) -> str:
    return {
        "ad_hominem": "Personal attack",
        "whataboutism": "Changes the subject",
        "straw_man": "Misrepresents argument",
        "false_dichotomy": "False either/or",
        "false_equivalence": "False equivalence",
        "cherry_picking": "Selective evidence",
        "anecdotal": "One example, big claim",
        "slippery_slope": "Slippery slope",
        "appeal_to_emotion": "Emotional pressure",
        "hasty_generalization": "Hasty generalization",
        "red_herring": "Red herring",
    }.get(ftype, ftype.replace("_", " ").title())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_runner.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add debatelens/src/debatelens/analysis/runner.py debatelens/tests/test_runner.py debatelens/tests/fixtures/transcript_sample.json
git commit -m "feat(debatelens): add analysis runner orchestrating 5 prompt stages"
```

---

## Task 8: Transcribe-service HTTP client

**Files:**
- Create: `debatelens/src/debatelens/transcribe_client.py`
- Create: `debatelens/tests/test_transcribe_client.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_transcribe_client.py`:
```python
import asyncio

import httpx
import pytest
import respx

from debatelens.transcribe_client import TranscribeClient
from debatelens.models import Transcript


@pytest.mark.asyncio
async def test_submit_url_returns_job_id():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.post("/jobs").respond(202, json={
            "job_id": "j-1",
            "status": "queued",
            "submitted_at": "2026-05-09T00:00:00Z",
        })
        c = TranscribeClient(base_url="http://localhost:8080")
        job_id = await c.submit_url(url="https://youtu.be/abc")
    assert job_id == "j-1"


@pytest.mark.asyncio
async def test_poll_until_done_returns_transcript():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-1").mock(side_effect=[
            httpx.Response(200, json={"job_id": "j-1", "status": "running",
                                       "submitted_at": "2026-05-09T00:00:00Z",
                                       "engine": "sarvam", "mode": "codemix"}),
            httpx.Response(200, json={"job_id": "j-1", "status": "done",
                                       "submitted_at": "2026-05-09T00:00:00Z",
                                       "engine": "sarvam", "mode": "codemix"}),
        ])
        mock.get("/jobs/j-1/transcript").respond(200, json={
            "segments": [
                {"speaker": "1", "text": "hi", "start_time": 0.0, "end_time": 1.0}
            ],
            "metadata": {"engine": "sarvam", "model": "saaras:v3", "language": "ml-IN", "source_file": "x"}
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        transcript = await c.wait_for_transcript("j-1", timeout_seconds=5)

    assert isinstance(transcript, Transcript)
    assert len(transcript.segments) == 1
    assert transcript.segments[0].text == "hi"


@pytest.mark.asyncio
async def test_poll_raises_on_failed():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-2").respond(200, json={
            "job_id": "j-2", "status": "failed", "error": "bad",
            "submitted_at": "2026-05-09T00:00:00Z",
            "engine": "sarvam", "mode": "codemix",
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        with pytest.raises(RuntimeError, match="bad"):
            await c.wait_for_transcript("j-2", timeout_seconds=2)


@pytest.mark.asyncio
async def test_poll_raises_on_timeout():
    async with respx.mock(base_url="http://localhost:8080") as mock:
        mock.get("/jobs/j-3").respond(200, json={
            "job_id": "j-3", "status": "running",
            "submitted_at": "2026-05-09T00:00:00Z",
            "engine": "sarvam", "mode": "codemix",
        })
        c = TranscribeClient(base_url="http://localhost:8080", poll_interval_seconds=0.01)
        with pytest.raises(asyncio.TimeoutError):
            await c.wait_for_transcript("j-3", timeout_seconds=0.05)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_transcribe_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `transcribe_client.py`**

`debatelens/src/debatelens/transcribe_client.py`:
```python
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from debatelens.models import Segment, Transcript


class TranscribeClient:
    def __init__(
        self,
        *,
        base_url: str,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._poll = poll_interval_seconds
        self._timeout = timeout_seconds

    async def submit_url(self, *, url: str, engine: str = "sarvam") -> str:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
            r = await client.post("/jobs", json={
                "source_url": url,
                "engine": engine,
                "language": "ml-IN",
                "mode": "codemix",
            })
            r.raise_for_status()
            return r.json()["job_id"]

    async def submit_file(self, *, path: Path, engine: str = "sarvam") -> str:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=600.0) as client:
            with Path(path).open("rb") as f:
                r = await client.post(
                    "/jobs",
                    files={"file": (Path(path).name, f, "application/octet-stream")},
                    data={"engine": engine, "language": "ml-IN", "mode": "codemix"},
                )
            r.raise_for_status()
            return r.json()["job_id"]

    async def wait_for_transcript(self, job_id: str, *, timeout_seconds: float | None = None) -> Transcript:
        deadline = (timeout_seconds or self._timeout)
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            async def poll():
                while True:
                    r = await client.get(f"/jobs/{job_id}")
                    r.raise_for_status()
                    body = r.json()
                    status = body.get("status")
                    if status == "done":
                        return body
                    if status == "failed":
                        raise RuntimeError(body.get("error") or "transcription failed")
                    await asyncio.sleep(self._poll)

            await asyncio.wait_for(poll(), timeout=deadline)

            r = await client.get(f"/jobs/{job_id}/transcript")
            r.raise_for_status()
            payload = r.json()

        segments = [Segment.model_validate(s) for s in payload.get("segments", [])]
        return Transcript(segments=segments, language=payload.get("metadata", {}).get("language", "ml-IN"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_transcribe_client.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/transcribe_client.py debatelens/tests/test_transcribe_client.py
git commit -m "feat(debatelens): add transcribe-service http client"
```

---

## Task 9: Service supervisor

**Files:**
- Create: `debatelens/src/debatelens/service_supervisor.py`

- [ ] **Step 1: Implement supervisor (no test — process-management is best verified manually)**

`debatelens/src/debatelens/service_supervisor.py`:
```python
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(host, port):
            return
        time.sleep(0.5)
    raise TimeoutError(f"transcribe-service did not become reachable at {host}:{port} within {timeout}s")


@contextmanager
def supervised_service(
    *,
    base_url: str,
    service_dir: Path,
    auto_start: bool = True,
):
    host = "127.0.0.1"
    port = int(base_url.rsplit(":", 1)[-1].split("/", 1)[0])

    if _is_port_open(host, port):
        yield None
        return

    if not auto_start:
        raise RuntimeError(f"transcribe-service not reachable at {base_url} and auto-start disabled")

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "transcribe_service.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    env = os.environ.copy()
    log_path = service_dir / "transcribe-service.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(service_dir),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        _wait_for_port(host, port, timeout=30.0)
        yield proc
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        log.close()
```

- [ ] **Step 2: Smoke-check import**

Run: `cd debatelens && python -c "from debatelens.service_supervisor import supervised_service; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add debatelens/src/debatelens/service_supervisor.py
git commit -m "feat(debatelens): add transcribe-service subprocess supervisor"
```

---

## Task 10: Dashboard template

**Files:**
- Create: `debatelens/src/debatelens/render/template.html`

- [ ] **Step 1: Copy sample-dashboard.html and replace hardcoded blocks with Jinja**

Use `sample-dashboard.html` from the repo root as the base. Keep the entire `<head>` and `<style>` block verbatim. Replace `<header>`, the two `<section class="speaker">` blocks inside `<main>`, and `<footer>` with Jinja2 loops.

`debatelens/src/debatelens/render/template.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DebateLens</title>
<style>
  :root {
    --bg: #14181d;
    --card: #1c2128;
    --line: #2a3038;
    --text: #e6edf3;
    --muted: #8b96a6;
    --green: #4ade80;
    --red: #f87171;
    --yellow: #facc15;
    --orange: #fb923c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, "Segoe UI", Inter, Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.55;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
  header { padding: 18px 32px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; }
  .logo { font-weight: 700; font-size: 18px; letter-spacing: -0.3px; }
  .show { color: var(--muted); font-size: 13px; }
  .show strong { color: var(--text); font-weight: 500; }
  .live { display: inline-flex; align-items: center; gap: 8px; color: var(--red); font-weight: 600; font-size: 12px; letter-spacing: 0.5px; }
  .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  main { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--line); }
  .speaker { background: var(--bg); padding: 28px 32px; overflow-y: auto; }
  .speaker-name { font-size: 22px; font-weight: 600; letter-spacing: -0.3px; }
  .speaker-role { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
  .stats { display: flex; gap: 18px; color: var(--muted); font-size: 13px; padding-bottom: 18px; border-bottom: 1px solid var(--line); margin-bottom: 22px; }
  .stats .num { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
  .stats .verified .num { color: var(--green); }
  .stats .wrong .num { color: var(--red); }
  .stats .flagged .num { color: var(--orange); }
  .moment { display: flex; gap: 14px; padding: 14px 0; border-bottom: 1px solid var(--line); }
  .moment:last-child { border-bottom: none; }
  .icon { width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; margin-top: 1px; }
  .icon.verified { background: rgba(74, 222, 128, 0.15); color: var(--green); }
  .icon.wrong    { background: rgba(248, 113, 113, 0.15); color: var(--red); }
  .icon.outdated { background: rgba(250, 204, 21, 0.15); color: var(--yellow); }
  .icon.flag     { background: rgba(251, 146, 60, 0.15); color: var(--orange); }
  .icon.unsure   { background: rgba(139, 150, 166, 0.15); color: var(--muted); }
  .moment-body { flex: 1; min-width: 0; }
  .moment-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 4px; }
  .moment-label.verified { color: var(--green); }
  .moment-label.wrong    { color: var(--red); }
  .moment-label.outdated { color: var(--yellow); }
  .moment-label.flag     { color: var(--orange); }
  .moment-label.unsure   { color: var(--muted); }
  .moment-quote { font-size: 14px; margin-bottom: 4px; }
  .moment-quote.italic { font-style: italic; }
  .moment-note { color: var(--muted); font-size: 13px; }
  footer { background: var(--card); border-top: 1px solid var(--line); padding: 18px 32px; display: flex; align-items: center; gap: 24px; }
  .now-label { color: var(--muted); font-size: 11px; letter-spacing: 0.8px; text-transform: uppercase; font-weight: 600; flex-shrink: 0; }
  .now-quote { flex: 1; font-style: italic; font-size: 15px; }
  .now-verdict { color: var(--yellow); font-size: 13px; flex-shrink: 0; }
  .now-verdict strong { font-weight: 600; }
</style>
</head>
<body>

<header>
  <div class="logo">Debate Lens</div>
  <div class="show"><strong>{{ show.title }}</strong> &middot; {{ show.minutes }} min</div>
  <div class="live"><span class="live-dot"></span>BATCH</div>
</header>

<main>
{% for sp_id, speaker in speakers.items() %}
  <section class="speaker">
    <div class="speaker-name">{{ speaker.name }}</div>
    <div class="speaker-role">{{ speaker.role }}</div>

    <div class="stats">
      <span class="verified"><span class="num">{{ speaker.stats.verified }}</span> verified</span>
      <span class="wrong"><span class="num">{{ speaker.stats.wrong }}</span> wrong</span>
      <span class="flagged"><span class="num">{{ speaker.stats.flagged }}</span> flagged</span>
    </div>

    {% for m in speaker.moments %}
    <div class="moment">
      <div class="icon {{ m.kind }}">{{ icons[m.kind] }}</div>
      <div class="moment-body">
        <div class="moment-label {{ m.kind }}">{{ m.label }}</div>
        <div class="moment-quote italic">"{{ m.quote }}"</div>
        <div class="moment-note">{{ m.note }}</div>
      </div>
    </div>
    {% endfor %}
  </section>
{% endfor %}
</main>

<footer>
  <div class="now-label">Just now</div>
  {% if now %}
    <div class="now-quote">"{{ now.quote }}"</div>
    <div class="now-verdict"><strong>{{ now.verdict_kind|title }}.</strong> {{ now.verdict_text }}</div>
  {% else %}
    <div class="now-quote">No claims surfaced.</div>
    <div class="now-verdict"></div>
  {% endif %}
</footer>

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add debatelens/src/debatelens/render/template.html
git commit -m "feat(debatelens): add jinja dashboard template"
```

---

## Task 11: Dashboard renderer

**Files:**
- Create: `debatelens/src/debatelens/render/dashboard.py`
- Create: `debatelens/tests/test_render.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_render.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_render.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `dashboard.py`**

`debatelens/src/debatelens/render/dashboard.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_render.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add debatelens/src/debatelens/render/dashboard.py debatelens/tests/test_render.py
git commit -m "feat(debatelens): add jinja dashboard renderer"
```

---

## Task 12: Config

**Files:**
- Create: `debatelens/src/debatelens/config.py`

- [ ] **Step 1: Implement config**

`debatelens/src/debatelens/config.py`:
```python
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
```

- [ ] **Step 2: Smoke-check import**

Run: `cd debatelens && python -c "from debatelens.config import load_settings; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add debatelens/src/debatelens/config.py
git commit -m "feat(debatelens): add settings loader"
```

---

## Task 13: CLI entry

**Files:**
- Create: `debatelens/src/debatelens/cli.py`
- Create: `debatelens/src/debatelens/__main__.py`
- Create: `debatelens/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

`debatelens/tests/test_cli.py`:
```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from debatelens.cli import _parse_speaker_names, main_async
from debatelens.models import AnalysisOutput, Segment, ShowMeta, SpeakerSummary, Transcript


def test_parse_speaker_names_basic():
    out = _parse_speaker_names("1=Maitreyan,2=Venugopan")
    assert out == {"1": "Maitreyan", "2": "Venugopan"}


def test_parse_speaker_names_empty():
    assert _parse_speaker_names("") == {}
    assert _parse_speaker_names(None) == {}


@pytest.mark.asyncio
async def test_main_async_with_transcript(tmp_path: Path, monkeypatch):
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
        # Provide a prompts dir
        prompts_dir = tmp_path / "prompts" / "v1"
        prompts_dir.mkdir(parents=True)
        for n in ["extract_claims", "classify_claim", "factcheck_claim",
                  "detect_fallacy_single", "detect_fallacy_multiturn"]:
            (prompts_dir / f"{n}.md").write_text(
                f"---\nname: {n}\ninput_variables: []\nmodel_hint: gemini-2.0-flash\ntemperature: 0.0\n---\nbody\n"
            )

        rc = await main_async([
            "run",
            "--transcript", str(transcript_path),
            "--show-title", "Test",
        ])

    assert rc == 0
    runs = list(out_dir.glob("*/dashboard.html"))
    assert runs, "expected at least one dashboard.html"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatelens && pytest tests/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement CLI**

`debatelens/src/debatelens/cli.py`:
```python
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
    service_dir = settings.repo_root / "transcribe-service"

    with supervised_service(
        base_url=service_url,
        service_dir=service_dir,
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
```

- [ ] **Step 4: Create `__main__.py`**

`debatelens/src/debatelens/__main__.py`:
```python
from debatelens.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd debatelens && pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add debatelens/src/debatelens/cli.py debatelens/src/debatelens/__main__.py debatelens/tests/test_cli.py
git commit -m "feat(debatelens): add CLI entry point with run subcommand"
```

---

## Task 14: Full test suite + repo-level wiring

**Files:**
- Modify: `debatelens/README.md`
- Modify: `README.md` (repo root)
- Create: `.env.example` (repo root)

- [ ] **Step 1: Run the full test suite**

Run: `cd debatelens && pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Add repo-level `.env.example`**

`/.env.example`:
```
# debatelens analysis pipeline
GEMINI_API_KEY=

# transcribe-service (also reads its own transcribe-service/.env)
SARVAM_API_KEY=

# Optional overrides
DEBATELENS_SERVICE_URL=http://localhost:8080
DEBATELENS_GEMINI_MODEL_FAST=gemini-2.0-flash
DEBATELENS_GEMINI_MODEL_PRO=gemini-2.5-pro
DEBATELENS_OUT_DIR=./output
```

- [ ] **Step 3: Update repo README with run instructions**

Append to `README.md`:
```markdown
## End-to-end batch demo

```bash
# 1. Set keys
cp .env.example .env  # add GEMINI_API_KEY
cp transcribe-service/.env.example transcribe-service/.env  # add SARVAM_API_KEY

# 2. Install
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ./transcribe-service[dev]
pip install -e ./debatelens[dev]

# 3. Run
python -m debatelens run --youtube https://youtu.be/<your-url>
# or: python -m debatelens run --audio path/to/debate.mp3

# 4. Open the dashboard
open output/<run_id>/dashboard.html
```

See [docs/superpowers/specs/2026-05-09-end-to-end-debatelens-design.md](docs/superpowers/specs/2026-05-09-end-to-end-debatelens-design.md) for full design.
```

- [ ] **Step 4: Manual verification (cannot be automated)**

The agent stops here and reports to the user. The user runs:
```bash
python -m debatelens run --youtube https://youtu.be/<short-malayalam-debate>
```
and opens the produced `dashboard.html`. Verification criteria from the spec:
- 2 speakers shown
- ≥1 verified moment
- ≥1 wrong moment
- ≥1 flag (fallacy) moment
- Stats counters populated
- "Just now" footer shows the most recent claim

Any issues at this stage are addressed via follow-up debugging — not part of this plan.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example debatelens/README.md
git commit -m "docs: add end-to-end run instructions and .env.example"
```

---

## Self-Review Notes

**Spec coverage:**
- Goal — Tasks 7, 13 (runner + CLI produce the artifact).
- Architecture diagram — implemented across Tasks 8, 9, 7, 11 (transcribe client, supervisor, runner, dashboard render).
- Components 1 (package) — Task 1.
- Components 2 (5 stages) — Task 7 + the 5 prompt files (already in repo).
- Components 3 (analysis.json shape) — Task 7 produces it; Task 2 defines its model.
- Components 4 (dashboard render) — Tasks 10, 11.
- Inputs/outputs CLI — Task 13.
- Env vars — Task 12, 14.
- Failure handling — Task 6 (Gemini retries), Task 8 (timeout/failed status), Task 9 (port wait).
- Testing — every task ships its tests; manual verification in Task 14.
- Verification checklist — Task 14 step 4 maps directly.

**Placeholder scan:** none — every step has runnable code or commands.

**Type consistency:** `Verdict.verdict`, `Moment.kind`, `verdict_to_moment_kind` use the same `VerdictLabel` and `MomentKind` literal sets. Runner produces `AnalysisOutput` matching what the renderer in Task 11 consumes. `Transcript`/`Segment` are produced by `transcribe_client.wait_for_transcript` and consumed by `runner.run` — matched.

**No gaps found.**
