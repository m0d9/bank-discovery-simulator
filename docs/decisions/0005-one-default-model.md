# 0005. One default model; the swap is optional

- **Status:** accepted
- **Date:** 2026-11-20 (gate model, PR #4; confirmed by the evaluation, PR #8)

## Context

**The roles and the GPU.** Three roles call models: the gate, the client and the coach. On the 16 GB GPU used for testing, models of different sizes compete for memory.

**What a swap costs.** When Ollama has to swap models, it pays a reload each time. It also crashes now and then while reloading: HTTP 500, `llama-server` exit `0xc0000409`.

**What reviewers have.** Their machines vary, and the brief asks that the app work with the model chosen for testing.

## Decision

**The default.** `qwen3.5:9b` plays every role, so one model stays loaded and nothing swaps.

**The options:**
- Each role can still be overridden (`LLM_MODEL_GATE`, `LLM_MODEL_CLIENT`, `LLM_MODEL_COACH`).
- **Strong coach:** `gpt-oss:20b` as the coach is opt-in (`make dev-strong-coach`) and marked experimental.
- **Smaller machines:** `qwen3.5:4b` is documented for them, with its trade-offs.

## Consequences

**Gains:**
- In normal use there are no swaps and no reload crashes.
- A turn takes about 2 s once warm, and feedback about 10 s.
- There is one model to download (6.6 GB).

**Costs:**
- The coach is a 9b model: about 7% of its points are unsupported, and its Arabic has gender issues.
- A stronger coach needs two things first: a setting for the coach's token budget, and enough GPU memory to keep both models loaded. Both are on the roadmap.

## Evidence

**PR #2:**
- A swap to the bigger coach cost about 17 s, and swapping back about 11.5 s.
- The reload crash came and went.
- The 9b (6.1 GB) and the 4b (3.7 GB) fit side by side with a 16k context.

**PR #4:** on the same 81 turns, the 9b gate was right 81 times and the 4b gate 74 times, for about 0.36 s more per turn.

**PR #6:**
- The 9b coach gave valid JSON on the first attempt 24 of 24 times, with a median of 8.5 s.
- `gpt-oss:20b` managed 11 of 24, with a median of 19.4 s, and degraded once.

**PR #8 ([evaluation.md](../evaluation.md)):**
- `strong-coach` degraded 11 of 15 reports, because its hidden reasoning ran past the token budget.
- `default` degraded none.
- `single-small` (the 4b) made 9 false unlocks, against `default`'s 2.
