# Privacy and security

**Status: draft (M8).** This covers the prototype as built: a teaching tool with no login and no database. The last section lists what a real deployment would still need.

## What data the app collects

**No personal data, by design.**

- There are no accounts, names, emails or student IDs, and no cookies. The browser keeps only the UI language, in `localStorage`.
- The clients are fictional and come from `content/`.
- Students do type free text: questions, a summary, reasons. Nothing stops a student from writing something personal there, so that text is handled as sensitive.

## Where data lives

- **Sessions:** server memory only.
  - A session is removed after 120 idle minutes. At most 200 are kept, and the least recently used goes first.
  - A restart clears them all, and `DELETE /api/sessions/{id}` removes one at once.
- **Coach reports:** an in-memory cache of up to 128 reports, also gone on restart.
- **Events** (`data/events.jsonl`): ids, counts, unlocked fact and product ids, models, prompt versions, tokens and latency.
  - They hold **no student, client or coach text** unless the operator sets `LOG_TRANSCRIPTS=true` (it defaults to false).
  - An API test runs a whole session and checks that none of its text reaches the file.
  - The logs (JSON on stdout) follow the same rule.
- **The Markdown export** is built when the student asks and sent as a download. The server doesn't keep it.
- **Model calls** send the transcript (and, for the coach, the client's full profile) to `LLM_BASE_URL`.
  - With local Ollama, the default, nothing leaves the machine.
  - With the optional Groq path, the text goes to a third party under its terms.

## Secrets

- The API key lives only in `.env`, which git ignores; `.env.example` has placeholders.
- It's read only on the server (a pydantic `SecretStr`) and never sent to the browser. `/api/health` shows the endpoint's host, never its URL or key.
- A filter on the log handler replaces the key wherever it appears. A test drives the API at DEBUG while the endpoint quotes the key back, and checks the key appears in no log line and no response.
- gitleaks runs in the pre-commit hook, and in CI over the full git history.

## Hardening in the app (M8)

- **Headers on every response:**
  - `Content-Security-Policy: default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - a minimal `Permissions-Policy`.
  - The SPA needs nothing more, because its fonts are self-hosted and it has no inline script or style.
  - `/api/docs` sends only `frame-ancestors 'none'`: Swagger UI loads from a CDN and starts from an inline script.
- **Limits:**
  - request bodies over 32 KB get `413 REQUEST_TOO_LARGE`;
  - a second message in a session within 1 s gets `429 SESSION_RATE_LIMIT`;
  - a student can send 30 messages, of up to 1,000 characters each.
- **Same origin only:** CORS isn't enabled.
- **Errors say little:** every error is the envelope `{"error": {"code", "message_key", "detail"}}`, and `detail` never repeats the input or an exception's message.
- **Hidden facts stay hidden:**
  - during the interview, no model sees a locked fact's content, and the coach reads the whole profile only after the wrap-up;
  - the browser gets the private profile only with the feedback.
  - Architecture and API tests enforce both.

## What a real deployment would add

- **Sign-in:** institutional SSO with student and staff roles, in place of anonymous sessions.
- **Transport and abuse:**
  - HTTPS at a reverse proxy, then HSTS (left off here because the app runs on plain HTTP on localhost);
  - rate limits per user or IP.
- **Retention:** a policy for the event log (it grows without bound today) and for any kept transcripts.
- **Consent:** tell students, before they start, what is processed, by which model provider, and for how long.
- **Institutional review** of student-record obligations (FERPA, for a US university) and of Qatar's Personal Data Privacy Protection Law (Law No. 13 of 2016). A hosted model provider needs a data-processing agreement, or the models stay on premises.
- **Audit logging** of administrative access and of any export or retention of student work.
- **Scheduled dependency and image scanning.**
