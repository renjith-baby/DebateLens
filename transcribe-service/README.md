# transcribe-service

FastAPI batch service wrapping `../../transcribing-module`. Submit a video/audio file or URL, get an async job id, receive the transcript via webhook + GET endpoint.

## Run locally

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ../../transcribing-module
pip install -e ".[dev]"
cp .env.example .env   # fill in SARVAM_API_KEY
uvicorn transcribe_service.main:app --reload --port 8080
```

## API

- `POST /jobs` — submit (multipart `file=` OR JSON `{source_url, ...}`)
- `GET /jobs/{id}` — status
- `GET /jobs/{id}/transcript` — transcript JSON (404 until done)
- `GET /healthz` — liveness

See `../docs/superpowers/specs/2026-05-09-transcribe-service-design.md` for the full contract.

## Tests

```bash
pytest -v
```
