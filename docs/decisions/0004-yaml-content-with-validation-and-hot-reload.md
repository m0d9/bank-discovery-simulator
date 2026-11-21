# 0004. YAML content with validation and hot reload

- **Status:** accepted
- **Date:** 2026-11-20 (content schema, PR #3)

## Context

**What the brief asks.** Client profiles, hidden needs and products must be stored in simple, separate files that can be edited without changing the application code.

**Who edits them.** Faculty, who aren't developers. A mistake in an answer key, such as a misspelt product id, would quietly mislead students, and a broken file must never stop the app in the middle of a class.

## Decision

**The files.** `content/` holds one YAML file per client and per product, plus `bank.yaml`.

**Validation.** Pydantic models validate them strictly:
- unknown fields are errors;
- ids must match file names;
- referenced products and facts must exist;
- requirements can't be circular;
- every client needs a critical fact.

**Help for authors:**
- Every error names its file and field.
- JSON schemas give editors autocomplete.
- Commented templates sit in `content/_templates/`.
- [The faculty guide](../../content/README.md) explains every field.
- `make validate-content` checks everything at once.

**Hot reload.** `ContentStore` reloads changed files, checking at most every 2 seconds. If an edit is invalid, it keeps the last valid version and lists the errors in `/api/health`. A running interview keeps the content it started with.

## Consequences

**Gains:**
- A new client needs no code: copy a template, edit the YAML, run `make validate-content`.
- A bad edit never takes the running app down.

**Costs:**
- YAML is easy to break with indentation, which is why the guide has a table of common errors and their fixes.
- Some content rules are tests, not validation: Arabic text for everything students see, and the templates still validating. They run in `make test`.

## Evidence

- **Reload speed (PR #3):** a saved edit appeared in about 2.1 s.
- **New clients without code (PR #7):** three clients were added, and the templates and the guide were written, with no app code changes.
- **Coverage:** a test checks that both templates validate.
