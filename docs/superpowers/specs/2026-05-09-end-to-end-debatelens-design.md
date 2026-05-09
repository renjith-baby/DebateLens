# DebateLens End-to-End Batch Demo — Design

**Date:** 2026-05-09
**Status:** Draft for review
**Goal in one line:** `python -m debatelens run --youtube <URL>` (or `--audio <FILE>`) produces a `dashboard.html` showing real per-speaker verdicts, fallacies, and scores from a real Malayalam debate.

## Why

The repo today contains three separately-developed pieces:

- `transcribe-service/` — a working FastAPI service that turns audio or YouTube URLs into diarized transcripts via Sarvam STT.
- `prompts/v1/` — five model-agnostic prompt templates for the analysis pipeline (extract → classify → factcheck → fallacy_single → fallacy_multiturn).
- `sample-dashboard.html` — a static visual mockup of the target output.

There is no glue. "Make it work" means: connect these three so a user can hand the system one debate (audio file or YouTube URL) and get back a real, populated dashboard.

The full live-streaming product described in [docs/amal-brief.md](../../amal-brief.md) is out of scope. This spec covers the batch demo path.

## Constraints

- **Only the API keys the user has:** `SARVAM_API_KEY` (transcription) and `GEMINI_API_KEY` (analysis). No Anthropic key, no Google Cloud STT credentials.
- **Reuse, don't rewrite:** transcribe-service stays as-is; prompts stay as-is.
- **Batch only:** no live streaming, no Redis, no Postgres, no WebSocket, no FastAPI for the analysis layer.
- **One self-contained output:** a single `dashboard.html` you can open in a browser. No server required to view.

## Architecture

```
┌────────────────────┐   POST /jobs        ┌───────────────────────┐
│  debatelens.cli    │ ──────────────────▶ │  transcribe-service   │
│  (this spec)       │   GET /jobs/{id}    │  (existing, unchanged)│
└────────────────────┘ ◀────────────────── └───────────────────────┘
         │                  transcript JSON           │
         │                                            │ Sarvam STT
         ▼                                            │ (yt-dlp for YT)
┌────────────────────┐
│  analysis runtime  │   prompts/v1/*.md
│  (5 stages, Gemini)│ ─────────────────────▶ Gemini API
└────────────────────┘   + Google Search grounding (factcheck)
         │                                            
         │ analysis.json (per-speaker moments + scores)
         ▼
┌────────────────────┐
│  dashboard render  │   sample-dashboard.html (template)
│  (Jinja fill)      │ ──▶ output/<run_id>/dashboard.html
└────────────────────┘
```

### Why HTTP and not direct import

transcribe-service is async FastAPI with a worker pool, file-store, webhooks. Importing it as a library would force the analysis runtime into its async lifecycle. HTTP keeps the boundary clean: start the service once (or auto-start it as a subprocess), submit a job, poll until done.

The CLI auto-starts transcribe-service in a subprocess if `--no-autostart` isn't passed, so the user runs one command end-to-end.

## Components

### 1. `debatelens/` — new top-level Python package

```
debatelens/
  pyproject.toml            # name=debatelens, deps: pydantic, httpx, google-genai, jinja2, python-dotenv, pyyaml
  src/debatelens/
    __init__.py
    cli.py                  # argparse entry: `run --youtube ... | --audio ...`
    config.py               # env var loading (GEMINI_API_KEY, SARVAM_API_KEY, service URL)
    models.py               # Pydantic: Transcript, Window, Claim, Verdict, Fallacy, Moment, SpeakerScore, AnalysisOutput
    transcribe_client.py    # HTTP client for transcribe-service (POST /jobs, poll, fetch transcript)
    service_supervisor.py   # spawns transcribe-service as a subprocess if not already running
    analysis/
      __init__.py
      runner.py             # orchestrator: walks 5 stages over windows
      prompts.py            # loads prompts/v1/*.md (frontmatter YAML + Jinja2 body)
      gemini_client.py      # thin wrapper: structured-output calls + search grounding for factcheck
      windowing.py          # transcript -> ~60s sliding windows (5-turn overlap for multiturn)
    scoring.py              # deterministic per-speaker rollup
    render/
      __init__.py
      dashboard.py          # AnalysisOutput -> dashboard.html via Jinja-templated sample
      template.html         # copy of sample-dashboard.html with {{ }} placeholders
  tests/
    test_prompts.py
    test_windowing.py
    test_scoring.py
    test_render.py
    test_runner_integration.py    # end-to-end with mocked Gemini against a fixture transcript
```

### 2. Pipeline stages (in `analysis/runner.py`)

For each window:

| Stage | Input | Output | Prompt | Model |
|---|---|---|---|---|
| 1. Extract claims | window text | `list[Claim]` | `prompts/v1/extract_claims.md` | Gemini Flash |
| 2. Classify | each `Claim` | `Claim` (with category, flags) | `prompts/v1/classify_claim.md` | Gemini Flash |
| 3. Factcheck | `Claim` | `Verdict` | `prompts/v1/factcheck_claim.md` | Gemini Pro + Google Search grounding |
| 4. Fallacy (single) | window text | `list[Fallacy]` | `prompts/v1/detect_fallacy_single.md` | Gemini Pro |
| 5. Fallacy (multiturn) | 5-turn rolling window | `list[Fallacy]` | `prompts/v1/detect_fallacy_multiturn.md` | Gemini Pro |

After all windows complete: `scoring.py` produces deterministic per-speaker scores from the verdicts and fallacies (logic per [docs/claim-extraction-spec.md](../../claim-extraction-spec.md) §"Per-speaker scoring").

Stages 3, 4, 5 run in parallel per window (asyncio.gather). Windows themselves run sequentially to keep token budgets predictable.

### 3. Output: `analysis.json`

Single document keyed by speaker:

```json
{
  "show": {"title": "...", "minutes": 28},
  "speakers": {
    "Speaker 1": {
      "name": "Speaker 1",
      "role": "Guest",
      "stats": {"verified": 5, "wrong": 2, "flagged": 4},
      "moments": [
        {"kind": "wrong", "label": "Not true", "quote": "...", "note": "..."},
        {"kind": "flag", "label": "Personal attack", "quote": "...", "note": "..."}
      ],
      "scores": {"accuracy": 78, "civility": 65, "reasoning": 72}
    }
  },
  "now": {"quote": "...", "verdict_kind": "outdated", "verdict_text": "..."}
}
```

Speaker names come from the diarized transcript (Sarvam returns `speaker_id`s like "1", "2"). The CLI takes optional `--speaker-names "1=Maitreyan,2=V.V. Venugopan"` to relabel for the demo. Default labels: "Speaker 1", "Speaker 2".

### 4. Dashboard render

`render/template.html` is `sample-dashboard.html` with the hardcoded blocks replaced by Jinja2 loops:

```jinja
{% for speaker in speakers.values() %}
  <section class="speaker">
    <div class="speaker-name">{{ speaker.name }}</div>
    ...
    {% for m in speaker.moments %}
      <div class="moment">
        <div class="icon {{ m.kind }}">{{ icon_for(m.kind) }}</div>
        ...
      </div>
    {% endfor %}
  </section>
{% endfor %}
```

Output is a single self-contained HTML file. No JS, no fetch, no server. Open in a browser.

## Inputs and outputs

**CLI:**

```
python -m debatelens run --youtube https://youtu.be/XXXX
python -m debatelens run --audio path/to/debate.mp3
python -m debatelens run --transcript path/to/transcript.json   # skip transcribe step
```

Optional flags:
- `--speaker-names "1=Maitreyan,2=Venugopan"` — pretty labels
- `--show-title "Janakeeya Kodathi"`
- `--service-url http://localhost:8080` — default; subprocess-spawned if not reachable
- `--no-autostart` — assume transcribe-service already running
- `--out-dir output/` — default

**Outputs (per run):**
```
output/<run_id>/
  transcript.json        # from transcribe-service
  analysis.json          # the structured analysis output
  dashboard.html         # what the user opens
  run.log                # stage timings, prompt costs, errors
```

## Env vars

```
# Required
GEMINI_API_KEY=...        # analysis pipeline + factcheck grounding
SARVAM_API_KEY=...        # transcribe-service (consumed by it, not by debatelens directly)

# Optional
DEBATELENS_SERVICE_URL=http://localhost:8080
DEBATELENS_GEMINI_MODEL_FAST=gemini-2.0-flash      # stages 1, 2
DEBATELENS_GEMINI_MODEL_PRO=gemini-2.5-pro          # stages 3, 4, 5
DEBATELENS_OUT_DIR=./output
```

`SARVAM_API_KEY` is read by transcribe-service from its own `.env`. The supervisor passes the parent process's env through when it spawns the service.

## Failure handling

Boundaries that need real handling (not boilerplate):

1. **transcribe-service unreachable** → supervisor tries to start it; if that fails, fail loud with a clear error pointing at the service's own startup logs.
2. **Job stuck in QUEUED/RUNNING past timeout** → CLI polls with timeout; on hit, surfaces the service-side error.
3. **Gemini rate limit / 5xx** → retry with exponential backoff (3 tries) inside `gemini_client.py`. Fail loud after.
4. **Stage parsing failure (model returns malformed JSON)** → one repair attempt with a "your previous response was not valid JSON, return only the JSON" follow-up. Fail the window after that.
5. **Window with zero claims or zero fallacies** → not a failure; just empty stage output.

Trust internal boundaries: no defensive checks between debatelens modules, no validation of well-typed Pydantic objects mid-pipeline.

## Testing

- **Unit:** prompt loader (frontmatter parsing), windowing logic, scoring rollup, dashboard renderer (snapshot test against sample-dashboard.html structure).
- **Integration:** mocked Gemini responses against a fixture transcript. End-to-end run produces `analysis.json` matching expected shape.
- **Manual verification:** real YT URL of a short Malayalam debate (you provide), open `dashboard.html`, eyeball the moments. This is the only way to verify quality of the actual prompts; spec'd as a manual step.

No real-API integration tests in CI (cost + flakiness).

## What this deliberately does not include

- Live streaming mode and the 60s lag target.
- Persistent storage (Postgres). Each run writes a flat directory.
- The dashboard's "Live" indicator and rolling footer animation. The static rendered HTML shows the most recent claim as the "Just now" footer item but doesn't auto-update.
- Adversarial neutrality eval. Single-run only.
- Cost ceiling enforcement. We log per-stage token usage but don't gate.
- Re-using transcribe-service's webhook callback path. The CLI polls instead.
- The `transcribe-service/README.md` "transcribing-module" reference is stale doc; ignored, not fixed in this spec.

## Verification checklist

To call this "done":

1. Fresh clone + `pip install -e ./transcribe-service[dev] && pip install -e ./debatelens` works.
2. `.env` with `GEMINI_API_KEY` and `SARVAM_API_KEY` is read end-to-end.
3. `python -m debatelens run --youtube <real-malayalam-debate-url>` completes without manual intervention.
4. `output/<run_id>/dashboard.html` renders in a browser with at least: 2 speakers, ≥1 verified moment, ≥1 wrong moment, ≥1 fallacy moment, populated stats counters.
5. Re-run with `--transcript output/<prev-run>/transcript.json` skips the transcribe step and reuses the cached transcript.

## Open questions

None blocking. Speaker name display is the only judgment call (default to "Speaker 1/2" or fail without `--speaker-names`?). Going with default labels — user can relabel if they care.
