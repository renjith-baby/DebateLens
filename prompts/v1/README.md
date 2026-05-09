# DebateLens prompts — v1

LLM prompts that drive the analysis pipeline. Each is a single-stage instruction set with a typed output schema.

## Files

| File | Stage | Default model |
|---|---|---|
| `extract_claims.md` | Pull checkable claims from a transcript window | Sonnet 4.6 |
| `classify_claim.md` | Refine claim category + flag cross-cutting issues | Haiku 4.5 |
| `factcheck_claim.md` | Web-search-backed verdict + evidence + sources | Sonnet 4.6 |
| `detect_fallacy_single.md` | Single-utterance fallacies (Tier 1/2/3) | Sonnet 4.6 |
| `detect_fallacy_multiturn.md` | Multi-turn fallacies (goalposts, gish gallop, etc.) | Sonnet 4.6 |

## File format

Each prompt is a markdown file with a YAML frontmatter header followed by the prompt body. Body is a Jinja2 template — variables use `{{ var_name }}`. The orchestration layer (Amal's runtime) loads the file, fills variables, calls the model.

```yaml
---
name: <prompt name>
purpose: <one line>
input_variables: [list of variables the template expects]
output_schema: <Pydantic class name>
model_hint: <model id>
temperature: 0.0
tools: [optional list of tool names]
---
```

## Versioning

Prompts are versioned by directory: `prompts/v1/`, `prompts/v2/`, etc. Bump the version when changes affect output shape or quality. Within a version, git history tracks edits.

## Evals — TODO

Each prompt should have an adjacent `eval.jsonl` with input → expected-output pairs. CI runs evals on every PR. Not yet populated — build alongside first real test debate clips.

## Hard constraints baked into every prompt

1. **Political neutrality** — same flags regardless of speaker's politics
2. **Conservative bias on contested claims** — `disputed`/`unverifiable`, never `false`, when uncertain
3. **Descriptive tone** — explain context, don't accuse
4. **No moralizing** — facts only
5. **Precision over recall for fallacies** — better to miss than to falsely flag

See [`docs/claim-extraction-spec.md`](../../docs/claim-extraction-spec.md) for the full design rationale.

## Possible future prompts (not yet needed)

- `dedupe_claims.md` — deduplicate claims across overlapping sliding windows (may be solvable deterministically with text similarity instead)
- `topic_detection.md` — segment the debate by topic (dashboard shows topic timeline; spec doesn't yet require it)
- `post_debate_summary.md` — full-debate report mode for journalists (out of MVP scope)
