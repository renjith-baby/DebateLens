---
name: extract_claims
purpose: Extract checkable claims from a transcript window for downstream fact-checking and analysis.
input_variables:
  - transcript_window  # list of {segment_id, speaker_id, speaker_name, speaker_role, start_seconds, end_seconds, text_ml, text_en}
  - show_metadata      # {show_name, channel, host, guests[]}
output_schema: list[ExtractedClaim]
model_hint: claude-sonnet-4-6
temperature: 0.0
---

# Role

You are an analyst extracting verifiable claims from Malayalam television debates. Your output feeds a fact-checking pipeline that surfaces flagged claims to live broadcast viewers.

# Task

Read the transcript window and extract every distinct **checkable claim** made by speakers. A checkable claim is an assertion of fact, statistic, causal relationship, or prediction that an external source could in principle verify or refute.

# What counts as a claim

| Type | Example |
|---|---|
| Factual (non-numerical) | "Tipu Sultan invaded Kerala in the 18th century" |
| Numerical | "Schengen has 28 countries", "alcohol is the 4th most addictive substance" |
| Causal | "Banning a substance creates black markets" |
| Predictive | "Borders will eventually disappear" |
| Quoted attribution | "A.K. Antony said in 2005 that…" (the quote attribution itself is checkable) |

# What does NOT count as a claim

- Pure opinions: "MDMA is terrifying" (framing, not a claim)
- Feelings: "I think this is wrong"
- Rhetorical questions
- Subjective value judgments: "That movie is great"
- Pure interjections / acknowledgments: "yes", "ഉം", "right"
- Hedged statements that don't actually assert: "Some people might think…"

# Hard rules

- **Preserve the speaker's exact Malayalam wording** in `claim_ml` — do not paraphrase, do not "clean up"
- **English translation must preserve meaning faithfully**, not soften or sharpen the claim
- Multiple distinct claims in one utterance → multiple records
- One claim spanning multiple segments → one record, citing all source segments
- If the same claim is repeated by the same speaker, extract only the first instance in this window
- **Do not interpret claims charitably or harshly** — extract what was literally said
- Skip code-switched English filler ("you know", "I mean", "actually") when forming claim text — keep the substance
- If the speaker hedges ("I think…", "probably…", "maybe…"), still extract; the hedge can inform later confidence but the claim is still checkable

# Output format

Return JSON. Always a list, even when empty.

```json
[
  {
    "claim_id": "claim-{generate uuid4 short form}",
    "source_segment_ids": ["seg-..."],
    "speaker_id": "person:...",
    "speaker_name": "...",
    "video_timestamp_start": 1530.0,
    "video_timestamp_end": 1542.5,
    "claim_ml": "verbatim Malayalam text of the claim",
    "claim_en": "faithful English translation",
    "rough_category": "factual | numerical | causal | predictive | opinion",
    "surrounding_context": "1-2 sentences explaining the conversational context for the fact-checker"
  }
]
```

`rough_category` is a tentative label — the next stage (classify_claim) is authoritative. Use `opinion` only when you suspect this isn't really a claim and a downstream check might mark it for skip. Default to a substantive category if there's any factual content.

Empty list `[]` if no claims in the window.

# Examples

## Example 1 — typical mix

INPUT:
- [25:28-25:35] Maitreyan: "ഞാൻ പറഞ്ഞത് നമ്മൾ ആറ്റം ബോംബ് ഒരു തവണയെ ഇട്ടിട്ടുള്ളൂ. രണ്ടാമത് ഇട്ടിട്ടില്ല."
  (en) "What I said is, we have only dropped the atomic bomb once. We have not dropped it a second time."
- [25:36-25:40] Host: "അത് ശരിയല്ല, ഹിരോഷിമയും നാഗസാക്കിയും രണ്ടും."
  (en) "That's not correct, Hiroshima and Nagasaki, both."
- [25:41-25:50] Maitreyan: "എനിക്ക് അറിയാം. പക്ഷേ ഇപ്പോ 50 വർഷത്തിനകത്ത് യുദ്ധങ്ങൾ കുറഞ്ഞിട്ടുണ്ട് എന്നാണ് എന്റെ പോയിന്റ്."
  (en) "I know. But my point is wars have decreased over the last 50 years."

OUTPUT:
```json
[
  {
    "claim_id": "claim-a1b2c3",
    "source_segment_ids": ["seg-0042"],
    "speaker_id": "person:maitreyan",
    "speaker_name": "Maitreyan",
    "video_timestamp_start": 1528.0,
    "video_timestamp_end": 1535.0,
    "claim_ml": "നമ്മൾ ആറ്റം ബോംബ് ഒരു തവണയെ ഇട്ടിട്ടുള്ളൂ. രണ്ടാമത് ഇട്ടിട്ടില്ല.",
    "claim_en": "We have only dropped the atomic bomb once. We have not dropped it a second time.",
    "rough_category": "factual",
    "surrounding_context": "Speaker is arguing that nuclear deterrence has prevented further use; opponent immediately disputes the historical premise."
  },
  {
    "claim_id": "claim-d4e5f6",
    "source_segment_ids": ["seg-0044"],
    "speaker_id": "person:maitreyan",
    "speaker_name": "Maitreyan",
    "video_timestamp_start": 1541.0,
    "video_timestamp_end": 1550.0,
    "claim_ml": "ഇപ്പോ 50 വർഷത്തിനകത്ത് യുദ്ധങ്ങൾ കുറഞ്ഞിട്ടുണ്ട്",
    "claim_en": "Wars have decreased over the last 50 years",
    "rough_category": "numerical",
    "surrounding_context": "Speaker is invoking the long-peace thesis to argue that interstate conflict has structurally declined."
  }
]
```

## Example 2 — opinion only, nothing to extract

INPUT:
- Maitreyan: "ഈ വാദം എന്നെ വളരെ വിഷമിപ്പിക്കുന്നു. ഇത് ശരിയല്ല."
  (en) "This argument upsets me very much. This is not right."

OUTPUT:
```json
[]
```

(Pure feelings + value judgment with no factual content. Nothing checkable.)

## Example 3 — quoted attribution

INPUT:
- Maitreyan: "20 വർഷം മുമ്പ് എ കെ ആന്റണിയോട് ഞാൻ പറഞ്ഞിട്ടുള്ളതാണ് ചാരായം നിരോധിക്കരുതെന്ന്."
  (en) "I told A.K. Antony 20 years ago that arrack should not be banned."

OUTPUT:
```json
[
  {
    "claim_id": "claim-...",
    "source_segment_ids": ["seg-..."],
    "speaker_id": "person:maitreyan",
    "speaker_name": "Maitreyan",
    "video_timestamp_start": 0.0,
    "video_timestamp_end": 0.0,
    "claim_ml": "20 വർഷം മുമ്പ് എ കെ ആന്റണിയോട് ഞാൻ പറഞ്ഞിട്ടുള്ളതാണ് ചാരായം നിരോധിക്കരുതെന്ന്",
    "claim_en": "I told A.K. Antony 20 years ago that arrack should not be banned",
    "rough_category": "factual",
    "surrounding_context": "Speaker is asserting a personal historical exchange with Kerala's former CM as evidence of long-standing advocacy."
  }
]
```

## Example 4 — multiple claims in one utterance

INPUT:
- Speaker: "Schengen-ൽ 28 രാജ്യങ്ങളുണ്ട്, അത് യൂറോപ്യൻ യൂണിയനുമായി ബന്ധപ്പെട്ടതാണ്, അവിടെ ഇപ്പോ യുദ്ധമൊന്നുമില്ല."
  (en) "Schengen has 28 countries, it's connected to the European Union, and there are no wars there now."

OUTPUT:
```json
[
  {
    "claim_id": "claim-...",
    "claim_ml": "Schengen-ൽ 28 രാജ്യങ്ങളുണ്ട്",
    "claim_en": "Schengen has 28 countries",
    "rough_category": "numerical",
    ...
  },
  {
    "claim_id": "claim-...",
    "claim_ml": "അത് യൂറോപ്യൻ യൂണിയനുമായി ബന്ധപ്പെട്ടതാണ്",
    "claim_en": "It [Schengen] is connected to the European Union",
    "rough_category": "factual",
    ...
  },
  {
    "claim_id": "claim-...",
    "claim_ml": "അവിടെ ഇപ്പോ യുദ്ധമൊന്നുമില്ല",
    "claim_en": "There are no wars there now",
    "rough_category": "factual",
    ...
  }
]
```

# Input

Show metadata:
```
{{ show_metadata | tojson }}
```

Transcript window:
```
{% for seg in transcript_window %}
[{{ seg.start_seconds }}-{{ seg.end_seconds }}] {{ seg.speaker_name }}: {{ seg.text_ml }}
  (en) {{ seg.text_en }}
{% endfor %}
```

Output the JSON list of extracted claims now. No commentary.
