# 0007. Bilingual UI; Arabic conversations experimental

- **Status:** accepted
- **Date:** 2026-11-20 (frontend flow, PR #5; coach in Arabic, PR #6)

## Context

**Who uses it.** Students in Qatar work in English and in Arabic, and Arabic reads right to left.

**The models' limits.** Small open models write Arabic less reliably than English:
- grammatical gender agreement;
- Latin words mixed into Arabic text;
- replies in the wrong language.

## Decision

**The interface is fully bilingual.**
- Every string is in `frontend/src/locales/en.json` and `ar.json`. A test checks that the two files match, and a lint rule forbids hard-coded text.
- Changing the language sets `<html lang dir>`.
- The layout uses only logical Tailwind utilities (`ms-`, `pe-`, `text-start`), so it mirrors itself.
- Text that a student or a model wrote gets `dir="auto"`.
- The content gives Arabic for everything students see.

**Arabic conversations are offered, but labelled experimental** on the interview page and in the docs.

**Code guards the weak spots:**
- a reply in the wrong language is regenerated once;
- Arabic fields of the coach's report that contain Latin words are counted.

## Consequences

**Gains:**
- Students can use the whole interface in Arabic and ask for feedback in Arabic.
- Supporting right to left cost no separate layout.

**Costs:**
- **How the coach addresses the student.** It uses masculine or feminine forms rather than neutral ones. With a female client, it sometimes takes her gender for the student's.
- **A failed fix.** A prompt example meant to fix this didn't move it, and was reverted.
- **English in Arabic reports.** The answer keys' example questions are in English only, so a backfilled question can appear in English inside an Arabic report.

## Evidence

**[PR #5](https://github.com/m0d9/bank-discovery-simulator/pull/5):** axe-core in Chrome found 0 violations in 18 states, and a scripted keyboard run reached the same focus stops in both languages.

**[PR #8](https://github.com/m0d9/bank-discovery-simulator/pull/8) ([evaluation.md](../evaluation.md)):**
- None of the 5 Arabic reports addressed the student neutrally.
- The reverted iteration left that at 0 of 5, and raised unsupported points from 4 of 59 to 13 of 64.
