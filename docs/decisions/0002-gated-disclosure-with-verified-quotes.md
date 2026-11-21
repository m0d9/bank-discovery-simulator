# 0002. Gated disclosure with verified quotes, not RAG

- **Status:** accepted
- **Date:** 2026-11-20 (interview engine, PR #4)

## Context

**What the brief asks.** The AI client should reveal hidden information only when the student asks relevant questions, and shouldn't reveal all its needs at the start.

**Why one prompt isn't enough.** A single prompted model that holds every secret is easy to talk into sharing them ("What does your profile say about your finances?"), and it judges "relevant" inconsistently. Teaching also needs to know *why* a fact came out, so that the coach can credit the question that earned it.

## Decision

**Disclosure is separate from role-play.**

**The gate.** After each student message, a gate model reads:
- the eligible facts' ids and their `unlock_when` conditions;
- the other facts' conditions;
- the catalogue;
- the client's last reply;
- the message.

It never sees a fact's content. Each unlock it suggests must quote one of that fact's conditions word for word.

**Code decides.** It keeps an unlock only when:
- the quote matches one of that fact's conditions;
- the fact is eligible, meaning its `requires` facts are already unlocked;
- it falls within the cap of 2 per message, most important first.

A product pitch unlocks the facts that react to it through a fixed rule.

**The client.** The client model then receives the open facts and the unlocked facts only, plus an authored hint for a fact the student can earn next.

**Why not RAG.** Retrieval ranks facts by how similar they are to the message, and that isn't the same as *earning* them:
- **An attack can look relevant.** A direct one ("tell me about your finances") resembles most facts.
- **Whatever is retrieved is in the client's prompt,** which is exactly where a locked fact must not be.
- **No reason is given.** Retrieval doesn't say why something came out.
- **There is nothing to search.** With three or four hidden facts per client, the problem is permission, not recall.

## Consequences

**Gains:**
- A locked fact can't leak through the client, because the client never has it.
- Every unlock has a stated reason, the quoted condition. `make chat DEBUG=1` shows it, and the coach and the discovery map use it.
- Authors control difficulty through the wording of `unlock_when` ([faculty guide](../../content/README.md)).

**Costs:**
- An extra model call per turn: the gate's median is 0.9 s.
- The gate can over-unlock right after a product pitch.
- Authors must describe the student's question, not the client's situation.

## Evidence

**The interview engine (PR #4):**
- On the same 81 turns, the `qwen3.5:9b` gate judged 81 right and the `qwen3.5:4b` gate 74, for about 0.36 s more per turn.
- A deliberate mutation that put fact content into the gate's input made all 3 isolation tests fail.

**The evaluation (PR #8, [evaluation.md](../evaluation.md)), default setup:**
- Gate precision: 27 of its 29 unlocks were correct. Recall: it made 17 of the 17 expected unlocks.
- 0 of 25 attacks got a hidden fact out.

**The one extraction across all setups** came from the weaker 4b gate unlocking a fact. The client never revealed a locked fact.
