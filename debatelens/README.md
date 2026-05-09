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
