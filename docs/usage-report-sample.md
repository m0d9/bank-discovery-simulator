# Sample usage report

Generated on 2026-11-21 with `uv run --project backend python scripts/usage_report.py`, from this machine's `data/events.jsonl`. Those events come from the development and test sessions of 19–21 November 2026: scripted runs (in the terminal and through the API), manual tests and the Groq test. **They are not from students**, so the rates show what the report looks like, not how students perform. Everything below the line is the script's output, unedited.

---

# Usage report

From `data/events.jsonl`: 4,016 events from 2026-11-19 to 2026-11-21 (UTC).
The report reads counts, ids, models and timings only, never message text.
An *interview* below is a session with at least one student turn.

## Sessions

| Stage | Sessions | Share of started | Median student turns |
| --- | ---: | ---: | ---: |
| Started | 301 | 100% | – |
| Interviewed | 298 | 99% | 4 |
| Reached wrap-up | 96 | 32% | 5 |
| Reached feedback | 84 | 28% | 5 |

## How often students find each hidden fact

The share of interviews in which the fact was unlocked, by a question or by a product pitch.

### Fatima Al-Sulaiti (`fatima-al-sulaiti`)

5 interviews, 2 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `sharia-preference` | critical | 2 of 5 (40%) |
| `risk-averse` | critical | 2 of 5 (40%) |
| `may-need-funds` | important | 4 of 5 (80%) |

### Rajesh Menon (`rajesh-menon`)

41 interviews, 21 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `corporate-invoices` | critical | 18 of 41 (44%) |
| `short-history` | critical | 26 of 41 (63%) |
| `payroll-pressure` | important | 12 of 41 (29%) |
| `no-religious-preference` | minor | 13 of 41 (32%) |

### Ahmed Hassan (`ahmed-hassan`)

4 interviews, 2 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `family-remittance` | critical | 3 of 4 (75%) |
| `existing-loan` | critical | 4 of 4 (100%) |
| `car-plan` | important | 3 of 4 (75%) |

### Noura Al-Kuwari (`noura-al-kuwari`)

231 interviews, 69 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `late-payments` | critical | 81 of 231 (35%) |
| `sharia-only` | critical | 167 of 231 (72%) |
| `big-contract` | important | 49 of 231 (21%) |

### Khalid Al-Marri (`khalid-al-marri`)

17 interviews, 2 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `needs-trucks` | critical | 16 of 17 (94%) |
| `sharia-on-pitch` | critical | 14 of 17 (82%) |
| `brother-exit` | important | 13 of 17 (76%) |
| `seasonal-peaks` | minor | 13 of 17 (76%) |

## Gate failures and character breaks

A gate failure is a turn whose gate call failed, so it unlocked nothing.

| Gate model | Turns | Gate failures |
| --- | ---: | ---: |
| `qwen3.5:9b` | 901 | 0 (0.0%) |
| `qwen3.5:4b` | 159 | 0 (0.0%) |
| `openai/gpt-oss-20b` | 6 | 6 (100.0%) |
| `qwen/qwen3.8-27b` | 6 | 0 (0.0%) |

A character break is a client reply that spoke of itself as an AI, a model or a prompt, so it was regenerated. The fallback line is the fixed line shown when the regenerated reply broke character too.

| Client model | Turns | Character breaks | Fallback line |
| --- | ---: | ---: | ---: |
| `qwen3.5:9b` | 1,060 | 0 (0.0%) | 0 (0.0%) |
| `openai/gpt-oss-20b` | 6 | 0 (0.0%) | 0 (0.0%) |
| `qwen/qwen3.8-27b` | 6 | 0 (0.0%) | 0 (0.0%) |

## Latency per call

| Role | Model | Calls | p50 | p95 |
| --- | --- | ---: | ---: | ---: |
| gate | `qwen3.5:9b` | 901 | 1.0 s | 1.4 s |
| gate | `qwen3.5:4b` | 159 | 0.6 s | 0.9 s |
| gate | `openai/gpt-oss-20b` | 7 | 10.9 s | 20.3 s |
| gate | `qwen/qwen3.8-27b` | 6 | 0.4 s | 0.6 s |
| client | `qwen3.5:9b` | 1,079 | 1.0 s | 1.4 s |
| client | `openai/gpt-oss-20b` | 11 | 0.8 s | 9.2 s |
| client | `qwen/qwen3.8-27b` | 6 | 0.4 s | 1.4 s |
| coach | `qwen3.5:9b` | 76 | 8.4 s | 11.7 s |
| coach | `no-such-coach-model` | 4 | 0.0 s | 0.0 s |
| coach | `qwen/qwen3.8-27b` | 3 | 2.2 s | 11.3 s |
| coach | `gpt-oss:20b` | 2 | 41.5 s | 62.8 s |
| coach | `openai/gpt-oss-20b` | 2 | 11.3 s | 11.5 s |

## Tokens per session

| Role | Model | Sessions | Input | Output | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| gate | `qwen3.5:9b` | 253 | 5,136 | 148 | 5,284 |
| gate | `qwen3.5:4b` | 41 | 4,605 | 148 | 4,753 |
| gate | `openai/gpt-oss-20b` | 2 | – | – | – |
| gate | `qwen/qwen3.8-27b` | 2 | 4,358 | 182 | 4,540 |
| client | `qwen3.5:9b` | 294 | 4,180 | 176 | 4,356 |
| client | `openai/gpt-oss-20b` | 2 | 5,075 | 894 | 5,969 |
| client | `qwen/qwen3.8-27b` | 2 | 3,111 | 134 | 3,245 |
| coach | `qwen3.5:9b` | 74 | 4,838 | 495 | 5,333 |
| coach | `no-such-coach-model` | 4 | – | – | – |
| coach | `qwen/qwen3.8-27b` | 2 | 4,720 | 394 | 5,114 |
| coach | `gpt-oss:20b` | 2 | 7,930 | 3,474 | 11,404 |
| coach | `openai/gpt-oss-20b` | 2 | – | – | – |

## Estimated cost

No estimate: no call recorded a cost, because no prices were configured when the calls ran. Set `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` (USD per million tokens) in `.env` to record one.

## How this is counted

- `llm_call` events carry no session id, so a model call counts for interviews when its prompt version is one that a turn or feedback event recorded for the same role. The calls that don't match, such as the smoke check's, are left out of latency, tokens and cost: 122 calls.
- Latency is by nearest rank, over every call: retries, regenerated replies and model swaps included.
- Tokens per session: a role's tokens with that model, divided by the sessions that used the model for that role. A session counts for the coach when the coach ran, not when it reused a cached report.
- 0 lines of the events file couldn't be read.
