# Claim Extraction & Analysis — Spec

**Owner:** Renjith
**Scope:** the analysis layer — extract claims, verdict them, detect fallacies, score speakers
**Status:** Draft for review

---

## What this layer does

Given a cleaned, speaker-labeled Malayalam transcript, output:
- Per-claim verdicts (true / false / disputed / unverifiable / outdated)
- Detected fallacies (single-turn and multi-turn)
- Per-speaker running scores (accuracy, civility, reasoning)

Consumed by the dashboard overlay during a near-live broadcast (~60s lag). See [sample-dashboard.html](../sample-dashboard.html) for the rendered target.

## Primary user

The broadcast surface — audience at home + anchor on-air. Outputs are short, declarative, audience-readable. Sources are present for credibility but secondary. A separate post-mortem report mode for journalists is a later rendering of the same data.

## Failure modes, ranked

These rankings shape every prompt and threshold below:

1. **Politically asymmetric flagging** — product-ending. Defended via adversarial neutrality eval.
2. **False positive (true claim flagged false)** — credibility nuke on-air. Defended via confidence threshold + conservative bias.
3. False negative (missed a false claim) — recoverable
4. Wishy-washy "disputed" verdicts — annoying but honest
5. Tone — tunable

## What gets extracted

Five claim categories. Different verification approaches per category:

| Category | Example | Verification |
|---|---|---|
| Factual (non-numerical) | "Tipu Sultan invaded Kerala" | Direct lookup |
| Numerical | "Schengen has 28 countries" | Dataset lookup; flag stat misuse |
| Causal | "Banning creates black markets" | Evidence search; flag as causal |
| Predictive | "Borders will disappear" | Mark as prediction, not fact |
| Opinion | "MDMA is terrifying" | Skip — not a claim |

Cross-cutting flags emitted on the claim record (not separate events):
- `source_vague` — "studies show…" without citation
- `misattribution` — quoted statement that wasn't said by the attributed person
- `prediction_as_fact` — predictive claim delivered with the certainty of a present fact

## Verdict schema

One record per surfaced claim:

```json
{
  "claim_id": "claim-0001",
  "speaker": "Maitreyan",
  "video_timestamp": "25:30",
  "claim_ml": "ആറ്റം ബോംബ് ഒരു തവണയെ നമ്മൾ ഇട്ടിട്ടുള്ളൂ.",
  "claim_en": "The atomic bomb has only been used once.",
  "claim_category": "factual",
  "verdict": "false",
  "confidence": 0.97,
  "one_liner": "Two atomic bombs were dropped — Hiroshima (Aug 6, 1945) and Nagasaki (Aug 9, 1945).",
  "evidence_paragraph": "The U.S. dropped two atomic bombs on Japan three days apart in August 1945. Hiroshima on Aug 6, Nagasaki on Aug 9. Universally documented.",
  "sources": [{"title": "...", "url": "..."}],
  "context_caveat": null,
  "flags": []
}
```

**Field constraints:**
- `one_liner` ≤ 120 chars (fits dashboard overlay)
- `evidence_paragraph` ≤ 300 chars (~10s read aloud)
- `sources`: 2–3 entries max
- `confidence` ∈ [0.0, 1.0]

### Verdict types

| Verdict | When to use |
|---|---|
| `true` | Claim matches authoritative sources |
| `false` | Claim contradicts authoritative sources |
| `disputed` | Experts disagree; verdict depends on interpretation or metric |
| `unverifiable` | No authoritative source confirms or denies (claim may still be correct, just unprovable) |
| `outdated` | Was correct historically but no longer current |

### Surfacing rule

**Only verdicts with `confidence ≥ 0.85` surface to the dashboard.** Below threshold, the claim is logged for review but not shown live. This is the central dial for the false-positive-vs-false-negative tradeoff.

## Fallacy detection

Two detectors run in parallel on each window.

### Single-turn (within one utterance)

**Tier 1 — flag at confidence ≥ 0.85:**
- Ad hominem
- Whataboutism / tu quoque
- Straw man
- False dichotomy
- False equivalence
- Cherry-picking
- Anecdotal evidence as proof

**Tier 2 — flag at stricter confidence ≥ 0.90 (more subjective):**
- Slippery slope
- Appeal to emotion
- Hasty generalization
- Red herring
- Post hoc ergo propter hoc
- Burden of proof shifting
- Loaded language (only if systematic)

**Tier 3 — only when explicit and unambiguous:**
- Begging the question
- Equivocation
- Appeal to tradition / nature
- Genetic fallacy

Output:

```json
{
  "fallacy_type": "ad_hominem",
  "tier": 1,
  "speaker": "Maitreyan",
  "video_timestamp": "21:14",
  "quote_ml": "നിങ്ങൾ വലിയൊരു കോപ്പല്ല",
  "quote_en": "You are not a great anything",
  "explanation": "Attacks the host personally rather than addressing the argument.",
  "confidence": 0.93
}
```

### Multi-turn (across a 5-turn sliding window)

Patterns that don't fit in one utterance:
- Moving the goalposts (changing the standard of proof when met)
- Gish gallop (rapid-fire low-quality claims)
- Sustained refusal to answer
- Sustained interruption / dominance

Same schema plus `turn_range`.

## Per-speaker scoring

Three running scores in [0, 100], starting at 100, updated after each event:

| Score | Driven by |
|---|---|
| Accuracy | Claim verdicts: `true` ↑, `false` ↓↓, `disputed` ↓, `outdated` ↓, `unverifiable` no-op |
| Civility | Tier-1 fallacies (heavy weight on ad hominem) |
| Reasoning | All fallacies, weighted by tier |

Time-decay over a 10-minute trailing window so early heat doesn't permanently sink a speaker. Exact decay rate and per-event weights tuned during implementation.

Scoring is deterministic post-v1 — not an LLM call.

## Hard constraints (non-negotiable)

These are enforced in every prompt:

1. **Political neutrality.** The system flags patterns regardless of speaker's politics. Adversarial neutrality eval (flip the political framing, verdict must not change) gates every prompt deploy.
2. **Conservative bias on contested claims.** When in doubt → `disputed` or `unverifiable`, never `false`.
3. **Descriptive tone, not accusatory.** "Hiroshima and Nagasaki were two bombings" beats "FALSE — speaker is wrong."
4. **No moralizing.** No "this is dangerous misinformation." Facts only.

## Pipeline stages

Each stage = one LLM call with typed I/O. Renjith owns the prompts; Amal owns the wiring.

1. **Extract claims** from a sliding window of cleaned transcript (~60s)
2. **Classify** each as factual / numerical / causal / predictive / opinion-skip
3. **Fact-check** (parallel per claim) — web search via Claude `tool_use` — returns verdict + confidence + sources
4. **Detect fallacies** (parallel) — single-turn and multi-turn detectors
5. **Update scores** — deterministic, not an LLM call

Default model: Claude Sonnet 4.6. Stage-by-stage override allowed (e.g. Haiku 4.5 for cheap classification).

## Prompts as files

Prompts live in `prompts/v{N}/` as templated files. Each has:
- A header block (purpose, input variables, output schema name, model hint)
- The prompt body (Jinja2 template)
- An adjacent `eval.jsonl` of input → expected-output pairs

Renjith iterates here without touching pipeline code.

```
prompts/v1/
  extract_claims.md         + eval.jsonl
  classify_claim.md         + eval.jsonl
  factcheck_claim.md        + eval.jsonl
  detect_fallacy_single.md  + eval.jsonl
  detect_fallacy_multiturn.md + eval.jsonl
```

## Eval approach

Two test sets, both versioned in the repo:

1. **Frozen eval set** — 5 hand-annotated Malayalam debate clips with ground-truth verdicts and fallacies. Runs on every prompt change. Tracks: claim recall, verdict accuracy, fallacy precision.
2. **Adversarial neutrality set** — same claims with political framing flipped (e.g. swap the speaker's party affiliation). Verdict must not change. Gates broadcast deploys.

Initial targets:
- **Verdict accuracy on surfaced claims (confidence ≥ 0.85): ≥ 95%** — this is the broadcast safety metric
- **Verdict accuracy across all extracted claims: ≥ 80%** — overall extraction quality
- **Fallacy precision: ≥ 95%** — recall deliberately undertuned for broadcast safety
- **End-to-end latency: < 90s** from utterance to dashboard
- **Cost: < ₹500 per hour of debate analyzed**

## Out of scope

- Live streaming mode (sliding window first; per-claim trigger comes later)
- Translation / speaker identification (Dheeraj's pipeline)
- Dashboard rendering (separate)
- Production deployment / scaling
