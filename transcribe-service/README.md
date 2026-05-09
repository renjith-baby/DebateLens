# transcribe-service

FastAPI batch service for transcribing audio or video. You submit a file or URL, get an async job id, then poll for status or receive a webhook when the transcript is ready.

Transcription engines (**Sarvam** REST and **Google Cloud Speech-to-Text**) are implemented in this repo under `src/transcribe_service/engines/`. There is no separate `transcribing-module` package.

## Prerequisites

- Python **3.11+**
- **ffmpeg** on `PATH` if you use the **google** engine (normalizes input to 16 kHz mono PCM). Not required for **sarvam** alone if Google is unused.
- Optional: Docker (image installs ffmpeg)

## Configuration

Copy `.env.example` to `.env`. Important variables:

| Variable | Used by | Purpose |
|----------|---------|---------|
| `SARVAM_API_KEY` | `engine=sarvam` | Sarvam API subscription key (`api-subscription-key` header) |
| `GOOGLE_APPLICATION_CREDENTIALS` | `engine=google` | Path to GCP service account JSON (or rely on ambient ADC) |
| `GOOGLE_CLOUD_PROJECT` | settings | Stored for future use; Speech client uses credentials |
| `GOOGLE_CLOUD_LOCATION` | settings | Region hint for settings |
| `OUTPUT_DIR`, `UPLOADS_DIR`, `JOB_STORE_PATH` | service | Job output and persistence paths |
| `JOB_TIMEOUT_SECONDS`, `MAX_CONCURRENT_JOBS` | service | Worker limits |

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env   # fill keys for the engine(s) you use
uvicorn transcribe_service.main:app --reload --port 8080
```

## API

- `POST /jobs` — submit (`multipart/form-data` with `file=`, or JSON `{ "source_url": "https://..." }`)
- `GET /jobs/{id}` — job status and metadata
- `GET /jobs/{id}/transcript` — transcript JSON once status is `done` (404 until ready)
- `GET /healthz` — liveness

Transcript JSON shape (written to disk and returned by GET) includes `full_text`, `segments` (speaker, text, times), and `metadata` (engine, model, language, source file).

## Docker

`docker-compose.yml` expects the **build context** to be the parent directory of your **`DebateLens`** repo clone (the compose file uses `context: ../..` so paths like `DebateLens/transcribe-service` resolve correctly).

From that parent directory:

```bash
docker compose -f DebateLens/transcribe-service/docker-compose.yml build
docker compose -f DebateLens/transcribe-service/docker-compose.yml up
```

The Dockerfile installs **ffmpeg** and only installs this service package (no external transcription wheel).

## Tests

```bash
pytest -v
```

Uses in-memory/fake engines where integration calls are mocked; does not call Sarvam or Google in CI unless you add live tests.
