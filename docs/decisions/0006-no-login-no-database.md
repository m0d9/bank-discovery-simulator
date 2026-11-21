# 0006. No login and no database

- **Status:** accepted
- **Date:** 2026-11-20 (interview engine, PR #4)

## Context

**What the brief asks.** A simple prototype, which needs no user login and no database.

**What we must protect.** The app handles students' practice conversations, so storing less is safer.

**Who runs it.** Reviewers run it on their own machines with one command.

## Decision

**Sessions.** They live in memory, in `SessionStore`:
- one idle for 120 minutes is removed;
- at most 200 are kept, and the least recently used goes first;
- each has a lock, so one operation runs at a time.

**No accounts.** A student keeps their interview by downloading the Markdown export.

**Telemetry.** `data/events.jsonl` holds ids, counts, models and timings. It holds no message text unless an operator sets `LOG_TRANSCRIPTS=true`.

**Private content.** A client's persona, hidden facts, answer key and coach notes leave the server only once feedback is ready.

## Consequences

**Gains:**
- Nothing to set up.
- No personal data at rest.
- No database to secure.

**Costs:**
- Restarting the app ends every interview. So does saving a backend file under `make dev`, which reloads it.
- It runs as a single process, so it can't scale out as it is.
- Faculty have no history of sessions.
- Rate limits apply only per session: one message per second.

**What a real deployment would add:** persistence with a retention policy, SSO or LTI, and per-user limits ([privacy and security](../privacy-and-security.md), and the README's next steps).

## Evidence

**API tests (PR #9):**
- A whole session leaves none of its text in `events.jsonl`.
- With every logger at DEBUG and the endpoint quoting the key back, the API key appears in no log line and no response.

**No-leak tests (PR #3, PR #4):** they check that no route returns private content before feedback is ready.
