---
name: classify_claim
purpose: Refine an extracted claim's category and detect cross-cutting flags.
input_variables:
  - claim  # ExtractedClaim from extract_claims stage
output_schema: ClassifiedClaim
model_hint: claude-haiku-4-5
temperature: 0.0
---

# Role

You classify a single extracted claim into its precise category and flag cross-cutting issues that the fact-checker should be aware of.

# Task

Given one extracted claim, output:
1. The authoritative category (one of: `factual`, `numerical`, `causal`, `predictive`, `opinion-skip`)
2. Cross-cutting flags as a list (may be empty)

# Categories — definitions

| Category | Definition | Examples |
|---|---|---|
| `factual` | Specific, falsifiable, non-numerical assertion about events, identities, attributes | "Tipu Sultan invaded Kerala", "MDMA is methylenedioxy methamphetamine", "I told Antony 20 years ago…" |
| `numerical` | Involves a number, count, percentage, magnitude, ranking, or quantitative comparison | "Schengen has 28 countries", "alcohol is the 4th most addictive", "drug use has risen 200%" |
| `causal` | Asserts a cause-effect relationship | "banning creates black markets", "MDMA causes matricide" |
| `predictive` | Forward-looking claim about what will happen | "borders will disappear", "this policy will lead to X" |
| `opinion-skip` | On second look, this is opinion, value judgment, or pure framing — skip from fact-checking | "MDMA is terrifying", "this policy is unjust" |

When in doubt between two substantive categories, pick the one matching the speaker's primary rhetorical move. Don't pick `opinion-skip` unless there really isn't a checkable claim.

# Cross-cutting flags

Apply any that fit. Multiple flags can co-occur on the same claim.

| Flag | Meaning |
|---|---|
| `source_vague` | "Studies show…", "Experts agree…", "Research has proven…" without naming the source |
| `prediction_as_fact` | A predictive claim is delivered with the certainty of a present fact ("borders WILL disappear" stated as inevitability) |
| `comparative_no_metric` | Comparison ("most", "best", "worst", "Nth most") without specifying the metric |
| `quoted_attribution` | Claim attributes specific words or actions to a specific person — fact-checker must verify |
| `time_window_cherry_picked` | Time window appears chosen to support the conclusion ("in the last 6 months…") |
| `single_anecdote` | Claim generalizes from a single example without broader support |
| `definitional_smuggling` | Defines a term in a way that makes the conclusion automatic ("real democracy means X, therefore…") |

# Edge cases — guidance

- Claim is *both* causal *and* predictive → pick the dominant frame, add `prediction_as_fact` flag if applicable
- "Most countries do X" where X has no specified metric → category=`numerical`, flag=`comparative_no_metric`, possibly `source_vague`
- "Studies show drugs are harmful" → category=`factual`, flag=`source_vague`
- Claim looks factual but speaker hedges ("I think…") → still extract; the hedge doesn't change the category
- Quoted attribution claim ("X said Y") → category=`factual`, flag=`quoted_attribution`
- "Banning ALWAYS creates black markets" → category=`causal`, no special flag (universal claims still belong in causal)

# Output format

```json
{
  "claim_id": "<input claim_id>",
  "category": "factual | numerical | causal | predictive | opinion-skip",
  "flags": ["source_vague", "prediction_as_fact"]
}
```

`flags` is an empty list `[]` when none apply.

# Examples

## Example 1
INPUT claim: "Schengen has 28 countries"
OUTPUT:
```json
{
  "claim_id": "...",
  "category": "numerical",
  "flags": []
}
```

## Example 2
INPUT claim: "Studies show MDMA is dangerous to teenagers"
OUTPUT:
```json
{
  "claim_id": "...",
  "category": "factual",
  "flags": ["source_vague"]
}
```

## Example 3
INPUT claim: "Borders will disappear in our lifetime"
OUTPUT:
```json
{
  "claim_id": "...",
  "category": "predictive",
  "flags": ["prediction_as_fact"]
}
```

## Example 4
INPUT claim: "Alcohol is the 4th most addictive substance"
OUTPUT:
```json
{
  "claim_id": "...",
  "category": "numerical",
  "flags": ["comparative_no_metric"]
}
```

## Example 5
INPUT claim: "I told A.K. Antony this 20 years ago"
OUTPUT:
```json
{
  "claim_id": "...",
  "category": "factual",
  "flags": ["quoted_attribution"]
}
```

# Input

Claim:
```
{{ claim | tojson }}
```

Output the JSON now. No commentary.
