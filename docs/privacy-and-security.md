# Privacy and security

This covers the prototype as built: a teaching tool with no login and no database. The last section lists what a real deployment would still need.

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
  - Deleting a session leaves its report in the cache until newer reports push it out.
  - The cache key is a hash that includes the transcript and the wrap-up, so only the same text finds the report.
- **Events** (`data/events.jsonl`): ids, counts, unlocked fact and product ids, models, prompt versions, tokens and latency.
  - They hold **no student, client or coach text** unless the operator sets `LOG_TRANSCRIPTS=true` (it defaults to false).
  - An API test runs a whole session and checks that none of its text reaches the file.
- **Logs:**
  - The app's own logs (JSON lines on stderr) follow the same rule.
  - Uvicorn, the web server, logs separately: a line for each request (client address, method, path and status), and the traceback of any unexpected error.
- **The Markdown export** is built when the student asks and sent as a download. The server doesn't keep it.
- **Model calls** send the conversation to `LLM_BASE_URL`. The coach also gets the wrap-up and the client's full profile.
  - With local Ollama, the default, nothing leaves the machine.
  - With the optional Groq path, the text goes to a third party under its terms.

## Secrets

- **Where the API key lives:**
  - It's kept only in `.env`, which git ignores; `.env.example` has placeholders.
  - Docker passes it to the container when it starts (`env_file`), and `.dockerignore` keeps it out of the image.
- **Who can read it:** only the server (a pydantic `SecretStr`); it's never sent to the browser. `/api/health` shows the endpoint's host, never its URL or key.
- **The logs:**
  - A filter on the app's log handler replaces the key wherever it appears. Uvicorn's own logs don't pass through it.
  - A test drives the API at DEBUG while the endpoint quotes the key back. It checks that the key appears in none of the app's log lines and in no response.
- **gitleaks** runs in the pre-commit hook, and in CI over the full git history.

## Hardening in the app (M8)

- **Headers on every response** (except a 500 from an unexpected error, which Starlette sends from outside the middleware; its body is a fixed envelope):
  - `Content-Security-Policy: default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - a minimal `Permissions-Policy` (no camera, microphone or geolocation).
  - The SPA needs nothing more, because its fonts are self-hosted and it has no inline script or style.
  - `/api/docs` has a looser policy, `frame-ancestors 'none'` only, because Swagger UI loads from a CDN and starts from an inline script.
- **Limits:**
  - request bodies over 32 KB get `413 REQUEST_TOO_LARGE`;
  - a second message in a session within 1 s gets `429 SESSION_RATE_LIMIT`;
  - a student can send 30 messages, of up to 1,000 characters each.
- **Same origin only:** CORS isn't enabled.
- **Errors say little:**
  - The API's errors use the envelope `{"error": {"code", "message_key", "detail"}}`.
  - `detail` is a fixed sentence, or names the field, id or path at fault. It never quotes what a student wrote, or an exception's own message.
  - One exception: a 405 (`OPTIONS` or `HEAD` on a route that doesn't take it) comes from FastAPI, with its own `{"detail": "Method Not Allowed"}`.
- **Hidden facts stay hidden:**
  - during the interview, no model sees a locked fact's content, and the coach reads the whole profile only after the wrap-up;
  - the browser gets the private profile only with the feedback.
  - Tests enforce both: the prompt-isolation tests check every model input in an interview, and the API tests check every route.

## What a real deployment would add

- **Sign-in:** institutional SSO with student and staff roles, in place of anonymous sessions.
- **Transport and abuse:**
  - HTTPS at a reverse proxy, then HSTS (left off here because the app runs on plain HTTP on localhost);
  - rate limits per user or IP.
- **Retention:** a policy for the event log (it grows without bound today) and for any kept transcripts.
- **Server logs:** Uvicorn's logs sent through the app's handler, so that the key filter covers them too.
- **Consent:** tell students, before they start, what is processed, by which model provider, and for how long.
- **Institutional review** of student-record obligations (FERPA, for a US university) and of Qatar's Personal Data Privacy Protection Law (Law No. 13 of 2016). A hosted model provider needs a data-processing agreement, or the models stay on premises.
- **Audit logging** of administrative access and of any export or retention of student work.
- **Scheduled dependency and image scanning.**
