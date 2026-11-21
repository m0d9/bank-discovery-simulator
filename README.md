# Bank Client Discovery Simulator

Business students practise a discovery interview with an AI bank client, recommend banking products, and get feedback from an AI coach.
The client keeps hidden needs that only the right questions unlock, and the coach's feedback is grounded in what the student actually asked and found.
It runs on free, open models through any OpenAI-compatible API (tested with Ollama and `qwen3.5:9b`), in English or Arabic.

![The feedback page after an interview with Noura Al-Kuwari: counts, what went well and what was missed, each point linked to the student's turns](docs/images/feedback-page.png)

## Quick start

**You need:**
- [Docker](https://docs.docker.com/get-docker/) (Docker Desktop on Windows and macOS);
- [Ollama](https://ollama.com/download) (Linux: `curl -fsSL https://ollama.com/install.sh | sh`);
- git;
- a GPU with about 6 GB free ([Hardware](#hardware)).

1. **Download the model** (6.6 GB):
   ```bash
   ollama pull qwen3.5:9b
   ```
2. **Give Ollama a 16k context window.** Its default is 4,096 tokens, and it silently cuts longer prompts from the start, which would truncate the coach's input. Set `OLLAMA_CONTEXT_LENGTH=16384` for the Ollama server, then restart it:
   - **Windows:** quit Ollama from the taskbar. Run `setx OLLAMA_CONTEXT_LENGTH 16384`, or add the variable under *Edit environment variables for your account*. Then start Ollama again.
   - **macOS:** run `launchctl setenv OLLAMA_CONTEXT_LENGTH 16384`, then quit and reopen the Ollama app.
   - **Linux (systemd):** run `sudo systemctl edit ollama.service` and add `Environment="OLLAMA_CONTEXT_LENGTH=16384"` under `[Service]`. Then run `sudo systemctl daemon-reload && sudo systemctl restart ollama`.

   Once the app has used the model, `ollama ps` should show `16384` in its `CONTEXT` column.
3. **Get the app and its settings:**
   ```bash
   git clone https://github.com/m0d9/bank-discovery-simulator.git
   cd bank-discovery-simulator
   cp .env.example .env
   ```
   Only `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` are required. Their defaults already point the container at Ollama on your machine: `http://host.docker.internal:11434/v1`, `ollama` and `qwen3.5:9b`. Every other setting is optional, and [.env.example](.env.example) explains each one.
4. **Run it:**
   ```bash
   docker compose up --build
   ```
   Then open **http://localhost:8000**.

**Where this was tested:** Windows 11, in WSL2 (Ubuntu) with Docker Desktop. The macOS and Linux steps follow [Ollama's documentation](https://docs.ollama.com/faq) but weren't tested.

**On Linux,** Ollama listens only on 127.0.0.1, which a container can't reach. Either use the developer path below, or also add `Environment="OLLAMA_HOST=0.0.0.0:11434"`, which exposes Ollama to your network.

### Developer path (`make dev`)
You need [uv](https://docs.astral.sh/uv/), Node 22 and make.
1. In `.env`, set `LLM_BASE_URL=http://localhost:11434/v1`.
2. Run `make install`, then `make dev`.
3. Open **http://localhost:5173**. The API runs on :8000, and both reload when you save a file.

On Windows, run it in WSL2 with [mirrored networking](https://learn.microsoft.com/windows/wsl/networking#mirrored-mode-networking) (`networkingMode=mirrored` in `.wslconfig`), so that `localhost` reaches Ollama.

### Hardware
**The default model.** `qwen3.5:9b` plays all three roles, so one model stays loaded:
- **Memory:** `ollama ps` shows 6.1 GB, all on the GPU, with the 16k context.
- **Test machine:** an NVIDIA RTX 5060 Ti (16 GB) with Ollama 0.40.16.
- **Speed:** the first reply after a cold start took about 8 s while the model loaded. After that, a reply takes about 2 s and the coach's feedback about 10 s.

**A smaller machine.** Set `LLM_MODEL=qwen3.5:4b`, which takes 3.7 GB. It is about a third faster per call, but it does worse in the [evaluation](docs/evaluation.md):
- its gate made 9 false unlocks, against 2 for the 9b;
- its gate let 1 of 25 attacks through;
- its client answered in the wrong language 16 times;
- its coach's points were unsupported 20% of the time, against 7%, measured with an older coach prompt.

**No GPU.** Ollama runs on the CPU, much more slowly (not measured).

### Optional: Groq instead of Ollama (not tested)
Use your own free key from [console.groq.com/keys](https://console.groq.com/keys), and never commit it (`.env` is git-ignored). Then set these in `.env`:
```bash
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=<your Groq key>
LLM_MODEL=openai/gpt-oss-20b
```
- **Why this model:** Groq's gpt-oss models support the JSON-schema output that the gate and the coach request.
- **What can go wrong:** like `gpt-oss:20b` on Ollama, their hidden reasoning counts against the coach's token budget, which is fixed in code. So feedback may come back degraded.
- **Rate limits:** the free tier has them.

## Using it
1. **Choose a client.** There are five fictional clients of the fictional Al Murjan Bank: two individuals and three business owners, from easy to hard.
2. **Interview them.**
   - The client reveals a hidden need only when you ask about it. Hidden needs include customers who pay late, a preference for Sharia-compliant banking, and a contract that needs funding.
   - The product catalogue is on the interview page, and you can discuss products as you go.
3. **Wrap up.** Summarise the client's needs and recommend 1–3 products, each with a reason.
4. **Get feedback.**
   - **From the coach:** what went well, what was missed (including unsuitable recommendations) and how to improve, each point citing your turns.
   - **From the answer key:** the discovery map and the verdict on each product.
   - **To keep:** download the whole interview as Markdown.

**Languages.** The interface is fully bilingual: English, and Arabic from right to left. Switch with the button in the header. Conversations in Arabic with the AI client and coach are **experimental**.

**A complete example:** [samples/noura-al-kuwari-en.md](samples/noura-al-kuwari-en.md). The same interview in Arabic, with its known issues listed at the top: [samples/noura-al-kuwari-ar.md](samples/noura-al-kuwari-ar.md) (experimental).

## How it works

```mermaid
flowchart LR
    S([Student message]) --> G["Gate model<br/>sees fact ids and unlock<br/>conditions, never the facts"]
    G -- "unlock + quoted condition" --> V{"Code: is the quote one<br/>of that fact's conditions?"}
    V -- yes --> U[("Unlocked facts")]
    V -- no --> L[Stays locked]
    U --> C["Client model<br/>persona, open facts,<br/>unlocked facts only"]
    C --> R([Client's reply])
    W([Wrap-up]) --> A["Analysis in code<br/>answer key vs. session"]
    A --> K[Coach model]
    K --> Q{"Code checks<br/>the report"}
    Q --> F([Feedback page])
```

**Hidden facts are earned, not retrieved.**
- After each student message, a small "gate" call decides which locked facts the message has earned.
- It sees only the facts' ids and their unlock conditions, such as "asks how or when her customers pay her", never the facts themselves.
- For each unlock, it must quote one of that fact's conditions word for word. Code rejects any unlock whose quote doesn't match.
- Code also caps unlocks at 2 per message, and applies a fixed rule to product pitches.

**The client model never receives a locked fact.**
- Its prompt holds the persona, the open facts and the facts unlocked so far.
- For a fact the student can earn next, it gets an authored hint, never the fact itself.
- A reply that breaks character, or comes back in the wrong language, is regenerated once.

**The coach is grounded in a deterministic analysis.**
- When the interview ends, code first compares the session with the client's answer key: which needs were uncovered and at which turn, which facts came out only after a product pitch, and a verdict on each recommended product.
- The coach model then writes its feedback from that analysis, the transcript and the full client profile.
- Code checks the report:
  - it drops praise that cites no student turn;
  - it removes product names from suggested questions;
  - it adds any critical need the coach left out.

**The feedback page says the coach can make mistakes.** It also says that the discovery map and the verdicts come from the answer key. If the coach fails, the analysis is still shown.

**More detail:**
- [docs/architecture.md](docs/architecture.md);
- the [decision records](docs/decisions/README.md).

## Editing content
Clients (their hidden facts and answer keys) and products are YAML files in [content/](content/). To add a client:
1. Copy a template.
2. Edit the YAML.
3. Run `make validate-content`.

No code changes. The running app picks up a saved change in about 2 seconds, and if a file has an error it keeps serving the last valid version. The [faculty guide](content/README.md) explains every field and how to write unlock conditions that work.

## Evaluation
`make eval` runs scripted interviews with the five clients through the app's own services:
- **Scripts:** strong, weak, weak in Arabic, and adversarial.
- **Judging:** a separate model judges the results.

With the default setup (`qwen3.5:9b` for every role):

| Measure | Result |
|---|---|
| Gate unlocks that were correct | 27 of 29 (93%) |
| Expected unlocks the gate made | 17 of 17 (100%) |
| Attacks that got a hidden fact out | 0 of 25 |
| Coach reports valid on the first try · degraded | 15 of 15 · 0 |
| Coach points the judge found unsupported | 4 of 59 (7%) |
| Latency, median / p95 | gate 0.9 / 1.3 s · client 1.1 / 1.4 s · coach 10.0 / 13.9 s |

The method, the comparison of three model setups, and what these numbers can't tell you: [docs/evaluation.md](docs/evaluation.md).

## Limitations
- **The coach can be wrong.** About 7% of its points were unsupported in the evaluation, and 14% with the weak script in Arabic. The [sample interview](samples/noura-al-kuwari-en.md) shows one.
- **Arabic grammatical gender.**
  - The coach addresses the student with masculine or feminine forms instead of neutral ones.
  - With a female client, it sometimes uses her gender for the student too.
  - The client's Arabic also slips.

  This is why Arabic conversations are marked experimental. The [Arabic sample](samples/noura-al-kuwari-ar.md) shows these issues.
- **The "strong coach" is experimental.** `gpt-oss:20b` as the coach doesn't fit next to `qwen3.5:9b` on a 16 GB GPU, so Ollama swaps models. 11 of 15 of its reports were degraded, because its reasoning ran past the coach's token budget.
- **The evaluation is small.**
  - Each setup ran once, on five clients with scripted students.
  - The judge is itself a model, with known biases.
- **The gate can over-unlock right after a product pitch.** Both of the default setup's false unlocks happened there.
- **The client's factual accuracy isn't measured.** It can invent small details.
- **Accessibility.** Automated axe checks cover every page and its key states in both languages, and a keyboard-only run was scripted. There has been no full screen-reader audit yet ([docs/accessibility.md](docs/accessibility.md)).
- **Sessions live in memory.** Restarting the app ends every interview. There are no accounts and no database, by design ([docs/privacy-and-security.md](docs/privacy-and-security.md)).

## The brief's requirements

| Requirement | Where it's met |
|---|---|
| Two AI chatbots: a client and a coach | [`simulation/client_agent.py`](backend/app/simulation/client_agent.py), [`coaching/coach.py`](backend/app/coaching/coach.py) |
| At least two fictional clients with a background, finances, needs and hidden information | 5 clients in [`content/clients/`](content/clients/): `persona`, `open_facts`, `hidden_facts`, `needs` |
| The client stays in character, answers naturally, and reveals hidden information only to relevant questions, not all at the start | The gate ([`disclosure.py`](backend/app/simulation/disclosure.py), [`gate.md`](backend/app/prompts/gate.md)); the client's prompt and checks ([`client_system.md`](backend/app/prompts/client_system.md)); measured in [evaluation.md](docs/evaluation.md) |
| A catalogue of at least three fictional products with features and limitations, which students can discuss in the interview | 8 products in [`content/products/`](content/products/); the catalogue on the interview page; the client learns about a product once the student mentions it |
| Feedback on what went well, what was missed (including unsuitable recommendations) and how to improve, to help students learn rather than to score them | [`coaching/`](backend/app/coaching/), [`coach.md`](backend/app/prompts/coach.md); the feedback page shows counts, never a score |
| An OpenAI-compatible API for both chatbots, with a provider or a local model | [`llm/client.py`](backend/app/llm/client.py) (the `openai` SDK); tested with Ollama, Groq optional |
| The API URL, key and model in `.env` | [`.env.example`](.env.example), with the three required variables first |
| Works with the model chosen for testing | `qwen3.5:9b` on Ollama: [evaluation.md](docs/evaluation.md) and `make test-live` |
| Client profiles, hidden needs and products in simple, separate files, editable without code | YAML in [`content/`](content/), validated and reloaded while the app runs; [faculty guide](content/README.md) |
| A simple web interface, with no login and no database | [`frontend/`](frontend/); sessions in memory |
| A repository with the code, sample client data, products and `.env.example` | This repository |
| A README covering installing, running and configuring the AI, and the model used for testing | [Quick start](#quick-start), [Hardware](#hardware), [Groq](#optional-groq-instead-of-ollama-not-tested) |
| One sample interview: the conversation, the student's summary and recommendations, the coach's feedback | [samples/noura-al-kuwari-en.md](samples/noura-al-kuwari-en.md), plus an [Arabic one](samples/noura-al-kuwari-ar.md) (experimental) |
| The workflow Select Client → Interview → Receive Feedback | [Using it](#using-it) |

## Next steps
- A follow-up chat with the coach about the interview
- A model picker in the interface
- Streaming replies
- A usage report for faculty: how often students find each hidden fact
- More clients, including a referral client that no product in the catalogue fits
- SSO and LTI, so it opens from the university's LMS
- Persistence, with a retention policy
- A setting for the coach's token budget, which larger reasoning models need
- Arabic example questions in the content, and few-shot work on the coach's Arabic
- Scaling and monitoring for a class-sized deployment
- Dependabot for dependency updates

## Project structure
```
backend/app/
  api/          FastAPI routes, which return DTOs only
  llm/          the only code that talks to a model (OpenAI-compatible)
  simulation/   interviews: the gate, the AI client, in-memory sessions
  coaching/     the analysis, the coach and its checks, the export
  content/      YAML loading, validation, hot reload
  prompts/      every prompt, as a Markdown template
  telemetry/    data/events.jsonl: timings and counts, no message text
backend/tests/  unit, API, architecture and live tests
frontend/src/   React + TypeScript pages and components, English and Arabic locales
content/        clients, products, the bank, templates, JSON schemas
evals/          the evaluation harness and its committed results
scripts/        `make chat`: interview a client in the terminal
samples/        a sample interview
docs/           architecture, decisions, evaluation, accessibility, privacy, demo script
```

## Tests and CI
- **`make test`:** the backend tests (626, with a fake model and no network) and the frontend tests (238).
- **`make lint` and `make typecheck`:** ruff, mypy (strict), eslint and tsc.
- **`make test-live`:** the tests that need a real model.
- **CI** runs four jobs on every pull request:
  - backend;
  - frontend, including the build;
  - a gitleaks scan of the full history;
  - the Docker image build.

## Documentation
- [Architecture](docs/architecture.md): the components, the turn and feedback flows, the state
- [Decision records](docs/decisions/README.md): the main choices and the evidence behind them
- [Evaluation](docs/evaluation.md): the method, the results and their limits
- [Accessibility](docs/accessibility.md) and [Privacy and security](docs/privacy-and-security.md)
- [Faculty guide to the content](content/README.md)
- [Sample interview](samples/noura-al-kuwari-en.md), the [Arabic one](samples/noura-al-kuwari-ar.md) (experimental), and the [demo script](docs/demo-script.md)

## License
[MIT](LICENSE)
