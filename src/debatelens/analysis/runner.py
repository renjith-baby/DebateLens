from __future__ import annotations

from dataclasses import dataclass
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
            extract_resp = self._safe_call(
                model=self._config.model_fast,
                prompt_key="extract",
                vars={"window_text": w.text} if "window_text" in self._prompts["extract"].header.input_variables else {},
            )
            claims_raw = extract_resp.get("claims", []) if isinstance(extract_resp, dict) else []
            claims: list[Claim] = []
            for c in claims_raw:
                try:
                    claims.append(Claim.model_validate(c))
                except Exception:
                    continue

            for claim in claims:
                self._safe_call(
                    model=self._config.model_fast,
                    prompt_key="classify",
                    vars={"claim_en": claim.claim_en} if "claim_en" in self._prompts["classify"].header.input_variables else {},
                )
                fc_resp = self._safe_call(
                    model=self._config.model_pro,
                    prompt_key="factcheck",
                    vars={"claim_en": claim.claim_en} if "claim_en" in self._prompts["factcheck"].header.input_variables else {},
                    with_search=True,
                )
                if not isinstance(fc_resp, dict):
                    continue
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
                resp = self._safe_call(
                    model=self._config.model_pro,
                    prompt_key=stage_key,
                    vars={"window_text": w.text} if "window_text" in self._prompts[stage_key].header.input_variables else {},
                )
                if not isinstance(resp, dict):
                    continue
                for f_raw in resp.get("fallacies", []):
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

    def _safe_call(self, *, model: str, prompt_key: str, vars: dict, with_search: bool = False):
        prompt_text = render_prompt(self._prompts[prompt_key], **vars)
        return self._gemini.generate_json(
            model=model,
            prompt=prompt_text,
            with_search=with_search,
            temperature=self._prompts[prompt_key].header.temperature,
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
