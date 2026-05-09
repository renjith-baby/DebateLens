# DebateLens — what we're building (for Amal)

Near-live fact-checker for Malayalam TV debates. During a 30–60 min debate broadcast, the product overlays claim verdicts, fallacy counts, and per-speaker scorecards. Target lag: ~60s behind live. Open [sample-dashboard.html](../sample-dashboard.html) to see what the output looks like.

**Team split:**
- **Dheeraj** — audio → transcript (Sarvam STT for live, Gemini-on-YouTube for batch, plus VAD and diarization)
- **Renjith** — the prompts: what claims to extract, how to fact-check them, what fallacies to flag
- **You (Amal)** — the pipeline that runs Renjith's prompts on Dheeraj's transcripts and streams results to the dashboard

**Pipeline.** Each stage is an LLM call with typed input/output:

1. Extract claims from a sliding window of transcript
2. Classify each claim (factual / numerical / causal / predictive / opinion)
3. Fact-check via web search (Claude's native tool_use)
4. Detect fallacies (single-turn first; multi-turn later)
5. Update per-speaker scores

**Stack.** Python + Anthropic/OpenAI/Google SDKs (default Claude Sonnet 4.6, swap per stage). Pydantic for stage contracts. Redis for the sliding-window buffer. Postgres for persistence. WebSocket to dashboard. **No LangChain** — plain async Python is enough; this is a deterministic tool-using pipeline, not an agent. Renjith's prompts live as templated files in `prompts/` so he can iterate without touching your code.

**Where to start (no blockers):**
- Repo skeleton + Pydantic models for the input/internal/output JSON shapes
- A runner that reads a saved transcript and walks all stages with mocked LLM responses
- Use the existing Maitreyan transcript as fixture data
- Once that's working end-to-end, plug in real Anthropic calls and Renjith's prompts

Talk to Dheeraj early to lock the input JSON shape (what segments + speaker IDs + metadata look like). Talk to Renjith on the output shape (what events the dashboard consumes).
