# 0001. OpenAI-compatible model layer only

- **Status:** accepted
- **Date:** 2026-11-19 (model-access layer, PR #2)

## Context

**What the brief asks.** Both chatbots must use an OpenAI-compatible API. The URL, key and model must come from `.env`, and free models are expected: reviewers may run Ollama on their own machine or use a hosted free tier such as Groq.

**What the roles need.** The three roles have different needs:
- the gate returns a small JSON decision;
- the client chats;
- the coach returns a long, structured report.

**The trouble with small servers.** They differ in the details. Some reject `response_format` or `reasoning_effort`, some return thinking text, and Ollama crashes now and then while reloading a model.

## Decision

**One package.** `backend/app/llm/` is the only code that imports `openai`, and it uses the async SDK. It exposes `LLMClient`, with `chat`, `chat_json` and `list_models`, and one implementation, `OpenAICompatClient`.

**Roles.** The gate, the client and the coach each take their model from their own setting, or else from `LLM_MODEL`, and each has its own timeout.

**Robustness.**
- Retries with back-off for timeouts, connection errors, 429 and 5xx.
- A concurrency limit.
- JSON through `response_format`, with a fallback to the prompt.
- A parameter the server rejects is dropped automatically.
- Thinking text is stripped from replies.

**What it doesn't use.** No LangChain, LiteLLM or provider SDK.

**Tests.** They use `FakeLLM`, or a scripted HTTP transport injected into the SDK. Only tests marked `live` call a real model.

## Consequences

**Gains:**
- Changing provider means changing three variables.
- Every call is timed and counted in one place (the `llm_call` event), without message text.

**Costs:**
- We maintain the retry and JSON handling ourselves: about 600 lines, with their own tests.
- Settings that only a provider's native API offers can't be used, such as Ollama's per-request context size. That is why `OLLAMA_CONTEXT_LENGTH` must be set on the Ollama server.
- The Groq path was written for, but not tested.

## Evidence

- **The boundary:** `backend/tests/architecture/test_boundaries.py` fails if anything outside `app/llm/` imports `openai`.
- **The smoke check:** `uv run python -m app.llm.smoke` calls every role. Its long-prompt check finds Ollama's silent truncation: Ollama cuts an over-long prompt from the start and still answers HTTP 200 (PR #2).
- **The crash:** the retry layer absorbed Ollama's reload crash (HTTP 500) in the PR #2 smoke runs.
