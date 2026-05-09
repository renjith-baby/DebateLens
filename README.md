# DebateLens

Near-live fact-check + bias detection for Malayalam TV debates. Output is a dashboard overlay showing claim verdicts, fallacy counts, and per-speaker scorecards while a debate is on air (~60s lag).

## Team

- **Dheeraj** — audio → transcript (VAD, STT, diarization, speaker ID)
- **Renjith** — analysis prompts + quality (claim extraction, fact-check, fallacy detection, scoring)
- **Amal** — orchestration runtime (pipeline that runs Renjith's prompts on Dheeraj's transcripts)

## What's here so far

```
docs/
  claim-extraction-spec.md   # the analysis layer spec
  amal-brief.md              # orchestration brief
sample-dashboard.html        # target output mockup — open in a browser
transcribe-service/          # FastAPI async transcription jobs (Sarvam + Google STT)
```

The dashboard mockup is the clearest single artifact for understanding what the system produces.

## Setup

This will be filled in as the three subsystems land. For now: clone, read the docs.

### transcribe-service

Batch transcription API (upload or URL in, JSON transcript out). Engines live in-repo under `transcribe-service/src/transcribe_service/engines/` (no separate package).

```bash
cd transcribe-service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # SARVAM_API_KEY and/or Google credentials as needed
pytest -v
uvicorn transcribe_service.main:app --reload --port 8080
```

The **Google** engine requires **ffmpeg** on `PATH` (used to normalize audio before Speech-to-Text). Docker images install ffmpeg automatically; install it locally if you use Google STT outside Docker.

See `transcribe-service/README.md` for the HTTP API and environment variables.
