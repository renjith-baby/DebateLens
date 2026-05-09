from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from debatelens.analysis.gemini_client import GeminiClient
from debatelens.analysis.prompts import Prompt, load_prompt, render_prompt
from debatelens.models import (
    AnalysisOutput,
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
}


@dataclass
class RunnerConfig:
    prompts_dir: Path
    confidence_threshold: float = 0.85
    model_fast: str = "gemini-2.5-flash"
    model_pro: str = "gemini-2.5-pro"


class AnalysisRunner:
    """Fast 2-call analysis: one extract over the whole transcript, one combined
    factcheck+fallacy pass over the whole thing.
    """

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
        speaker_set: set[str] = {seg.speaker for seg in transcript.segments}
        show_metadata = self._build_show_metadata(show_title, speaker_names, speaker_set)
        transcript_window = self._build_transcript_window(transcript.segments, speaker_names)

        # Call 1: extract all claims from the entire transcript.
        claims = self._call_extract(transcript_window, show_metadata)

        # Call 2: batch factcheck all claims AND detect all fallacies in one shot.
        verdicts_raw, fallacies_raw = self._call_combined_analysis(
            transcript_window, claims, show_metadata
        )

        all_verdicts: dict[str, list[Verdict]] = {}
        all_fallacies: dict[str, list[Fallacy]] = {}
        moments_per_speaker: dict[str, list[Moment]] = {}
        last_moment: tuple[str, Moment] | None = None

        claim_by_id = {c.get("claim_id"): c for c in claims}
        for raw in verdicts_raw:
            try:
                verdict = Verdict.model_validate(raw)
            except Exception:
                continue
            if verdict.confidence < self._config.confidence_threshold:
                continue
            claim = claim_by_id.get(verdict.claim_id, {})
            speaker_id = self._resolve_speaker(claim.get("speaker_id"), speaker_names, speaker_set)
            all_verdicts.setdefault(speaker_id, []).append(verdict)
            kind = verdict_to_moment_kind(verdict.verdict)
            moment = Moment(
                kind=kind,
                label=_label_for_kind(kind),
                quote=claim.get("claim_en") or claim.get("claim_ml") or "",
                note=verdict.one_liner,
            )
            moments_per_speaker.setdefault(speaker_id, []).append(moment)
            last_moment = (speaker_id, moment)

        for raw in fallacies_raw:
            try:
                fallacy = self._fallacy_from_raw(raw)
            except Exception:
                continue
            if fallacy.confidence < self._config.confidence_threshold:
                continue
            speaker_id = self._resolve_speaker(raw.get("speaker_id"), speaker_names, speaker_set)
            all_fallacies.setdefault(speaker_id, []).append(fallacy)
            moment = Moment(
                kind="flag",
                label=_fallacy_label(fallacy.fallacy_type),
                quote=fallacy.quote_en,
                note=fallacy.explanation,
            )
            moments_per_speaker.setdefault(speaker_id, []).append(moment)
            last_moment = (speaker_id, moment)

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
            now = NowItem(quote=m.quote, verdict_kind=m.kind, verdict_text=m.note)

        total_seconds = transcript.segments[-1].end_time if transcript.segments else 0.0
        return AnalysisOutput(
            show=ShowMeta(title=show_title, minutes=int(total_seconds // 60)),
            speakers=speakers_out,
            now=now,
        )

    def _build_show_metadata(
        self, show_title: str, speaker_names: dict[str, str], speaker_set: set[str]
    ) -> dict[str, Any]:
        return {
            "show_name": show_title,
            "channel": "Unknown",
            "host": speaker_names.get("2", "Speaker 2"),
            "guests": [
                {"name": speaker_names.get(sp, f"Speaker {sp}"), "speaker_id": _person_id(speaker_names.get(sp, sp))}
                for sp in sorted(speaker_set)
                if sp != "2"
            ],
        }

    def _build_transcript_window(
        self, segments, speaker_names: dict[str, str]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, s in enumerate(segments):
            name = speaker_names.get(s.speaker, f"Speaker {s.speaker}")
            out.append({
                "segment_id": f"seg-{i:04d}",
                "speaker_id": _person_id(name),
                "speaker_name": name,
                "speaker_role": "host" if s.speaker == "2" else "guest",
                "start_seconds": s.start_time,
                "end_seconds": s.end_time,
                "text_ml": s.text,
                "text_en": s.text,
            })
        return out

    def _resolve_speaker(
        self, speaker_id: str | None, speaker_names: dict[str, str], speaker_set: set[str]
    ) -> str:
        if not speaker_id:
            return next(iter(speaker_set), "1")
        for sp_key, name in speaker_names.items():
            if _person_id(name) == speaker_id:
                return sp_key
        if speaker_id in speaker_set:
            return speaker_id
        return next(iter(speaker_set), "1")

    def _call_extract(
        self, transcript_window: list[dict[str, Any]], show_metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        prompt_text = render_prompt(
            self._prompts["extract"],
            transcript_window=transcript_window,
            show_metadata=show_metadata,
        )
        resp = self._gemini.generate_json(
            model=self._config.model_pro,
            prompt=prompt_text,
            temperature=self._prompts["extract"].header.temperature,
        )
        if isinstance(resp, list):
            return [c for c in resp if isinstance(c, dict)]
        if isinstance(resp, dict):
            for k in ("claims", "items", "data"):
                if k in resp and isinstance(resp[k], list):
                    return [c for c in resp[k] if isinstance(c, dict)]
        return []

    def _call_combined_analysis(
        self,
        transcript_window: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        show_metadata: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """One Gemini call (Pro + Google Search grounding) that fact-checks every
        extracted claim AND detects fallacies in the transcript, returning
        {verdicts, fallacies} in a single JSON document.
        """
        if not claims:
            return [], []

        prompt = _build_combined_prompt(transcript_window, claims, show_metadata)
        resp = self._gemini.generate_json(
            model=self._config.model_pro,
            prompt=prompt,
            with_search=True,
            temperature=0.0,
        )
        if not isinstance(resp, dict):
            return [], []
        verdicts = resp.get("verdicts") or []
        fallacies = resp.get("fallacies") or []
        return (
            [v for v in verdicts if isinstance(v, dict)],
            [f for f in fallacies if isinstance(f, dict)],
        )

    def _fallacy_from_raw(self, raw: dict[str, Any]) -> Fallacy:
        return Fallacy(
            fallacy_type=raw["fallacy_type"],
            tier=raw.get("tier", 1),
            speaker=str(raw.get("speaker_id") or raw.get("speaker_name") or "1"),
            video_timestamp=str(raw.get("video_timestamp") or raw.get("video_timestamp_start") or "00:00"),
            quote_ml=raw.get("quote_ml", ""),
            quote_en=raw.get("quote_en") or " ".join(raw.get("quote_excerpts", []))[:300],
            explanation=raw.get("explanation", ""),
            confidence=float(raw.get("confidence", 0.0)),
        )


def _build_combined_prompt(
    transcript_window: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    show_metadata: dict[str, Any],
) -> str:
    return f"""You are fact-checking a Malayalam TV debate. You receive (1) the full transcript with speaker labels and (2) a list of pre-extracted checkable claims. Use Google Search to verify each claim against authoritative sources.

# Show context
```json
{json.dumps(show_metadata, ensure_ascii=False, indent=2)}
```

# Transcript (turns ordered chronologically)
```json
{json.dumps(transcript_window, ensure_ascii=False, indent=2)}
```

# Claims to fact-check
```json
{json.dumps(claims, ensure_ascii=False, indent=2)}
```

# Your task

1. **Fact-check every claim.** For each claim, return one verdict record. Use web search.
2. **Detect logical fallacies in the transcript.** Single-turn fallacies (ad_hominem, whataboutism, straw_man, false_dichotomy, false_equivalence, cherry_picking, anecdotal, slippery_slope, appeal_to_emotion, hasty_generalization, red_herring) AND multi-turn ones (moving_goalposts, gish_gallop, refusal_to_answer, interruption).

# Hard rules

- **Political neutrality.** Flag patterns regardless of speaker's politics.
- **Conservative bias on contested claims.** When in doubt → "disputed" or "unverifiable", never "false".
- **Descriptive tone, not accusatory.** Facts only, no moralizing.
- Only include verdicts/fallacies with `confidence ≥ 0.85`. Below that, omit the record.
- `one_liner` ≤ 120 characters. `evidence_paragraph` ≤ 300 characters. `explanation` ≤ 200 characters.

# Output format

Return ONE JSON object with exactly these top-level keys:

```json
{{
  "verdicts": [
    {{
      "claim_id": "<copy from input claim>",
      "verdict": "true | false | disputed | unverifiable | outdated",
      "confidence": 0.0,
      "one_liner": "...",
      "evidence_paragraph": "...",
      "sources": [{{"title": "...", "url": "..."}}],
      "context_caveat": null
    }}
  ],
  "fallacies": [
    {{
      "fallacy_type": "ad_hominem",
      "tier": 1,
      "speaker_id": "person:...",
      "speaker_name": "...",
      "video_timestamp": 1274.0,
      "quote_ml": "...",
      "quote_en": "...",
      "explanation": "...",
      "confidence": 0.93
    }}
  ]
}}
```

Empty arrays if nothing applies. Return ONLY the JSON object, no prose, no markdown fences."""


def _person_id(name: str) -> str:
    slug = name.lower().replace(" ", "_").replace(".", "").replace("-", "_")
    return f"person:{slug}"


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
        "moving_goalposts": "Moves the goalposts",
        "gish_gallop": "Rapid-fire claims",
        "refusal_to_answer": "Refuses to answer",
        "interruption": "Sustained interruption",
    }.get(ftype, ftype.replace("_", " ").title())
