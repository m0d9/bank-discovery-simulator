# 0003. Grounded coach: analysis, model, code checks

- **Status:** accepted
- **Date:** 2026-11-20 (coach, feedback and export, PR #6)

## Context

**What the brief asks.** The AI coach reviews the interview against the client's predefined needs and covers three things:
- what went well;
- what was missed, including unsuitable recommendations;
- how to improve.

The feedback should help students learn rather than simply score them.

**What goes wrong with a model alone.** It miscounts, invents praise and contradicts the answer key. Students can't tell which parts to trust.

## Decision

The coach has three layers:

1. **Analysis in code** (`coaching/analysis.py`). With no model involved, code compares the session with the answer key:
   - which needs were uncovered, and at which turn;
   - which facts came out only after a pitch;
   - a verdict on each recommended product, with the key's reason;
   - suitable products the student didn't recommend;
   - counts, never a score.
2. **The coach model** (`coaching/coach.py`). It writes the feedback as JSON against a schema, from:
   - the analysis;
   - the numbered transcript;
   - the student's wrap-up;
   - the full client profile, which it may read only after the wrap-up.

   Each point cites the student's turns.
3. **Code checks** (`check_report`). The checks:
   - drop praise that isn't grounded in the student's turns;
   - drop points that quote the client as the student's question;
   - clear suggested questions that name a product;
   - add any missed critical need the coach left out.

**If the coach fails,** the page shows the analysis alone. **The page also says** that the coach can make mistakes, and that the discovery map and the verdicts come from the answer key.

## Consequences

**Gains:**
- The parts students act on most, the verdicts and the discovery map, never come from a model.
- Every claim points to turns that students can open and check.
- The coach can be measured and improved through its prompt alone.

**Costs:**
- Unsupported claims remain. Code can't check free text such as "she had already said…", and the [sample interview](../../samples/noura-al-kuwari-en.md) shows one.
- Each prompt change needs a replay to measure it ([0008](0008-evaluation-fixed-judge-paired-replays.md)).

## Evidence

**The coach comparison (PR #6):** `qwen3.5:9b` returned valid JSON on the first attempt in 24 of 24 calls, with a median of 8.5 s in the second batch.

**The evaluation (PR #8, [evaluation.md](../evaluation.md)):**
- The coach's reports were valid 15 of 15 times, and none were degraded.
- The checks dropped 7 items.
- One prompt iteration, measured on the same interviews, cut unsupported points from 11 of 66 to 4 of 59.
