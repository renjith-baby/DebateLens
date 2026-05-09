# Transcribe-Service — Design

**Owner:** Dheeraj
**Status:** Draft for review
**Date:** 2026-05-09

---

## Purpose

Wrap the existing `transcribing-module` Python library as an HTTP service so Amal's analysis pipeline (and other internal callers) can submit a video/audio file or URL and receive a speaker-labeled Malayalam/Manglish transcript asynchronously.

The service is the runtime form of "Dheeraj — audio → transcript" in the DebateLens team split. It is **not** the live broadcast pipeline; it is the batch layer that ships first.

## In scope

- HTTP API (FastAPI) exposing async transcription jobs
- Two input sources: multipart file upload, or JSON body with a media URL (direct media or YouTube)
- Job lifecycle: `queued → running → done | failed`
- Result delivery via webhook to a caller-supplied `callback_url`
- Transcript persistence to disk for re-fetch via `GET /jobs/{id}/transcript`
- In-memory job store with JSON-file mirror for crash recovery
- Bounded async worker pool via `asyncio.Semaphore`
- Local dev runtime (`uvicorn`) with a `Dockerfile` + `docker-compose.yml` for container parity
- Env-driven config (`.env`)
- Tests for: happy-path job lifecycle, webhook delivery, URL download, crash recovery, schema validation

## Out of scope

- Live streaming / RTMP / WebSocket ingestion — separate spec, later
- Pre-windowed (~60s) output — Amal's pipeline does its own windowing
- Authentication, rate limiting, multi-tenant isolation
- Persistent job store (Redis/Postgres) — `JobStore` interface designed so this can swap in later without touching handlers
- Webhook retry on receiver failure — manual re-deliver via `GET /jobs/{id}/transcript` is enough for now
- Speaker identification (mapping `speaker: "1"` → real names) — future work
- Cloud deployment — service must be container-ready, but no deploy target is committed

## Architecture

### Repo placement

The service lives in the DebateLens repo at `DebateLens/transcribe-service/`. The `transcribing-module` is imported as a local editable install — exact mechanism (a `requirements.txt` line, `uv` source, or a `pip install -e ../../transcribing-module` build step in the Dockerfile) is a plan-stage detail. Single deployable artifact (the service container) bundles both packages.

### Layout

```
DebateLens/
  transcribe-service/
    pyproject.toml
    Dockerfile
    docker-compose.yml
    .env.example
    src/transcribe_service/
      __init__.py
      main.py                   # FastAPI app + lifespan (job recovery + worker startup)
      config.py                 # Pydantic Settings (env-driven)
      schemas.py                # Pydantic request/response models
      api/
        __init__.py
        jobs.py                 # POST /jobs, GET /jobs/{id}, GET /jobs/{id}/transcript
        health.py               # GET /healthz
      jobs/
        __init__.py
        store.py                # JobStore protocol + InMemoryJsonStore impl
        worker.py               # WorkerPool: Semaphore + asyncio.Queue
        runner.py               # run_job(job) — one job's full lifecycle
      sources/
        __init__.py
        upload.py               # save multipart upload to uploads/
        url.py                  # httpx download; yt-dlp for youtube.com / youtu.be
      webhook.py                # POST result with HMAC-SHA256 signature header
    output/                     # transcripts: {job_id}.json
    uploads/                    # raw inputs: {job_id}{original_ext}
    tests/
      conftest.py
      test_api_jobs.py
      test_runner.py
      test_store_recovery.py
      test_webhook.py
      test_sources_url.py
```

### Process model

One uvicorn worker process runs both the API and the worker pool in the same event loop. On startup, the FastAPI `lifespan` handler:

1. Loads `output/jobs.json` into the in-memory `JobStore`.
2. Marks any job in state `running` as `failed` with reason `"crash_recovery"` (we cannot resume mid-transcription).
3. Re-enqueues any job in state `queued` into the worker queue.
4. Starts `MAX_CONCURRENT_JOBS` worker coroutines, each pulling from the queue.

On shutdown, workers drain the in-flight job (or are cancelled if drain exceeds the timeout) and the store is flushed to disk.

## API

All endpoints return JSON. Errors follow `{"error": "<code>", "message": "<human readable>"}`.

### `POST /jobs` — submit a job

Two input modes, distinguished by `Content-Type`.

**Multipart upload:**

```
POST /jobs
Content-Type: multipart/form-data

file=<binary>
callback_url=https://amal.local/webhook   (optional)
engine=sarvam                              (optional, default: sarvam)
mode=codemix                               (optional, default: codemix)
language=ml-IN                             (optional, default: ml-IN)
max_speakers=2                             (optional)
```

**JSON URL body:**

```json
POST /jobs
Content-Type: application/json

{
  "source_url": "https://youtu.be/...",
  "callback_url": "https://amal.local/webhook",
  "engine": "sarvam",
  "mode": "codemix",
  "language": "ml-IN",
  "max_speakers": 2
}
```

**Response (202 Accepted):**

```json
{
  "job_id": "job_01HW9...",
  "status": "queued",
  "submitted_at": "2026-05-09T17:55:00Z"
}
```

`job_id` is a ULID for sortability.

### `GET /jobs/{id}` — job status

```json
{
  "job_id": "job_01HW9...",
  "status": "running",
  "submitted_at": "2026-05-09T17:55:00Z",
  "started_at": "2026-05-09T17:55:01Z",
  "finished_at": null,
  "error": null,
  "source": {"type": "url", "url": "https://youtu.be/...", "filename": null},
  "engine": "sarvam",
  "mode": "codemix",
  "callback_url": "https://amal.local/webhook",
  "callback_delivered": false,
  "callback_attempts": 0,
  "transcript_url": null
}
```

When `status == "done"`, `transcript_url` is `/jobs/{id}/transcript`.

### `GET /jobs/{id}/transcript` — fetch transcript

Returns the persisted `TranscriptResult` JSON exactly as the existing CLI's JSON writer produces it (same schema as `transcribing-module`'s `TranscriptResult.to_dict()`). 404 if job is not yet `done`.

### `GET /healthz` — liveness

```json
{"status": "ok", "queue_depth": 0, "in_flight": 0}
```

## Job lifecycle

```
queued ──> running ──> done
              │
              └────> failed
```

State transitions are written through the `JobStore`, which mirrors to disk on every change.

`run_job(job)` (in `jobs/runner.py`):

1. Mark job `running`, record `started_at`.
2. Resolve source: copy upload from `uploads/` or download URL → local file.
3. Construct `TranscriptionOptions` from job params; pick engine via `transcriber.engines.{sarvam,google_stt}`.
4. Run `engine.transcribe(audio_path, options)` (sync call, run in a thread via `asyncio.to_thread` to avoid blocking the event loop).
5. Write result to `output/{job_id}.json` via `transcriber.output.json_writer.write_json`.
6. Mark job `done`, record `finished_at`, set internal `transcript_path` (the on-disk path; the API surface exposes this as `transcript_url = /jobs/{id}/transcript`).
7. If `callback_url` is set, POST the result. Update `callback_delivered` / `callback_attempts`.
8. On any exception: mark `failed`, record `error` (string), still attempt one webhook POST with `status: "failed"` payload.

## Webhook contract

When a job finishes (success or failure) and a `callback_url` is set, the service POSTs:

```
POST <callback_url>
Content-Type: application/json
X-Transcribe-Signature: sha256=<hex>           # HMAC-SHA256(WEBHOOK_SECRET, body)
X-Transcribe-Job-Id: job_01HW9...
X-Transcribe-Event: job.done | job.failed
```

**Body for `job.done`:**

```json
{
  "event": "job.done",
  "job_id": "job_01HW9...",
  "submitted_at": "...",
  "finished_at": "...",
  "transcript": { /* full TranscriptResult.to_dict() */ }
}
```

**Body for `job.failed`:**

```json
{
  "event": "job.failed",
  "job_id": "job_01HW9...",
  "error": "engine_failed: <message>"
}
```

One delivery attempt; failures are logged but not retried in v1. Caller can re-fetch via `GET /jobs/{id}/transcript`. `WEBHOOK_SECRET` is set via env; if unset, no signature header is sent and a startup warning is logged.

## Output schema

The webhook `transcript` field and `GET /jobs/{id}/transcript` both return the existing `TranscriptResult.to_dict()` shape from `transcribing-module`:

```json
{
  "metadata": {
    "engine": "sarvam",
    "model": "saaras:v3",
    "language": "ml-IN",
    "audio_duration_seconds": 1234.5,
    "speaker_count": 2,
    "processing_time_seconds": 13.5,
    "source_file": "uploads/job_01HW9....mp4",
    "options": {"mode": "codemix", "diarization": true}
  },
  "speakers": ["1", "2"],
  "speaker_count": 2,
  "segments": [
    {
      "speaker": "1",
      "text": "...",
      "start_time": 0.01,
      "end_time": 20.01,
      "confidence": null,
      "language": null,
      "duration": 20.0
    }
  ],
  "full_text": "[1] ...\n[2] ..."
}
```

This is the contract with Amal's pipeline. The transcribe-service does not transform it.

## Configuration

`.env` (loaded via Pydantic Settings):

```
# Server
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO

# Concurrency
MAX_CONCURRENT_JOBS=2
JOB_TIMEOUT_SECONDS=1800

# Storage
OUTPUT_DIR=./output
UPLOADS_DIR=./uploads
JOB_STORE_PATH=./output/jobs.json

# Webhook
WEBHOOK_SECRET=                    # optional; HMAC signing key
WEBHOOK_TIMEOUT_SECONDS=10

# Engine credentials (passed through to transcribing-module)
SARVAM_API_KEY=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=asia-southeast1
GOOGLE_APPLICATION_CREDENTIALS=
```

## Error handling

| Scenario | Response |
|---|---|
| Missing `file` and `source_url` on submit | 400 `invalid_input` |
| Both `file` and `source_url` provided | 400 `invalid_input` |
| `source_url` host unsupported (not http/https/youtube) | 400 `unsupported_source` |
| File extension not in transcriber's supported list | 400 `unsupported_format` |
| URL download fails (network, 4xx, 5xx) | Job → `failed`, error `download_failed: ...` |
| yt-dlp fails | Job → `failed`, error `youtube_download_failed: ...` |
| Engine credentials missing | Job → `failed`, error `engine_unconfigured: <engine>` |
| `engine.transcribe` raises | Job → `failed`, error `engine_failed: <message>` |
| Job exceeds `JOB_TIMEOUT_SECONDS` | Cancel task, job → `failed`, error `timeout` |
| Webhook POST fails (network/non-2xx) | Job stays `done`, `callback_delivered=false`, `callback_attempts=1`, log warning |
| Service crashes mid-job | On restart, job marked `failed` with `error: "crash_recovery"` |

## Testing

Unit / integration tests in `tests/`, using `pytest` + `httpx.AsyncClient` against the FastAPI app.

- **`test_api_jobs.py`** — POST upload + URL paths, validation errors, GET status, GET transcript, with the engine call patched to return a fixture `TranscriptResult`.
- **`test_runner.py`** — `run_job` happy path, engine-raises path, timeout path, all using a fake engine adapter.
- **`test_store_recovery.py`** — write a `jobs.json` containing `running` + `queued` jobs, boot the app, assert `running` becomes `failed` and `queued` is re-enqueued.
- **`test_webhook.py`** — webhook POSTs the right body and signature; receiver-down case marks `callback_delivered=false`.
- **`test_sources_url.py`** — direct media via mocked `httpx`; YouTube path mocked at `yt-dlp` boundary.

A small fixture `TranscriptResult` (one of the existing `transcribing-module/output/*.json` files) is reused so tests don't depend on Sarvam credentials. CI runs without any cloud creds.

## Open questions (resolved)

- **Live mode?** Out of scope; batch first.
- **Output schema transformation?** No — pass through `TranscriptResult` unchanged.
- **Webhook retries?** No in v1; persistent transcript + manual re-fetch covers it.
- **Auth?** Not in v1.

## References

- Existing library: `../../transcribing-module/` (CLI entry: `python -m transcriber`)
- Library data model: `transcribing-module/src/transcriber/output/models.py`
- Library exploration notes: `transcribing-module/EXPLORATION.md`
- Amal's brief: `docs/amal-brief.md`
- Analysis spec (downstream consumer): `docs/claim-extraction-spec.md`
