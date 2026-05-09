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
```

The dashboard mockup is the clearest single artifact for understanding what the system produces.

## Setup

This will be filled in as the three subsystems land. For now: clone, read the docs.
