# 0008. Evaluation with a fixed judge and paired replays

- **Status:** accepted
- **Date:** 2026-11-21 (evaluation harness, PR #8)

## Context

**What needed evidence.** The choices of models and prompts needed evidence, not impressions.

**What makes it hard:**
- Hand-checking interviews doesn't scale.
- The models are non-deterministic, so the same prompt varies from run to run.
- Judging free-text feedback needs a model, and a model has biases of its own.

## Decision

**What `make eval` runs.** Four scripted scenarios with each of the five clients, for each model setup:
- **strong;**
- **weak;**
- **weak in Arabic;**
- **adversarial:** five attacks.

The runs go through the app's own `InterviewService` and `FeedbackService`.

**One judge.** A fixed judge (`gpt-oss:20b`) scores every setup, so the judged numbers compare across setups. The metrics are plain functions over the session records and the telemetry.

**Measuring a prompt change.** It replays only the coach and the judge on the same recorded interviews, a paired comparison. A keep rule fixed before the runs decides what stays: the target must improve, and no other metric may get worse.

**What is kept.** Results are committed in `evals/results/`. Full traces stay local.

## Consequences

**Gains:**
- The setups can be compared on the same scale.
- A prompt iteration costs about 15 minutes and compares like with like.
- The code guards are measured as part of the system that students see.

**Costs:**
- The judge favours its own model, which matters for the `strong-coach` row.
- Each setup ran once, on a small sample: one changed verdict moves a five-report rate by 20 points.
- Scripted students don't adapt the way real students do.

[evaluation.md](../evaluation.md) states these limits next to the numbers.

## Evidence

The [evaluation](../evaluation.md) covers the method, the three setups, the per-client notes and two prompt iterations:
- **Iteration 1 was kept:** unsupported points went from 11 of 66 to 4 of 59.
- **Iteration 2 was reverted:** its target stayed at 0 of 5, and unsupported points rose to 13 of 64.
