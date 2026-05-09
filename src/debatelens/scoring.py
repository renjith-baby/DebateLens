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
