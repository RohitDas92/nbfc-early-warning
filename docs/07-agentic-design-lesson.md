# 07 — Agentic System Design: the method, and how we got here

Two halves. The first is transferable to any agent system you're ever asked to design. The second walks the actual chain of decisions on this project, in the order they happened — which is the answer to "how did you arrive at this architecture?"

---

# Part A — The method

## The one idea underneath everything

**Agentic design is mostly the discipline of deciding what is *not* an agent.**

That sounds backwards. It isn't. Anyone can wire up a model with tools and let it loop. The hard part — and the part that separates a system that gets approved from a demo — is drawing a defensible line between the parts that reason and the parts that just execute.

Everything below is a way of drawing that line and then living with it.

## Step 1 — Find the judgement

Write out the work the way a human does it today. Then mark each step with one question:

> **Is the next action knowable before you see the data?**

If yes, it's software. A rule, a query, a state machine, a scoring model. If no — if the next thing you'd do depends on what the last thing revealed — that's where an agent earns its place.

Do this honestly and you'll find the judgement is usually a small island in a large sea of procedure. That's normal. In our system, roughly 90% of the nightly work is arithmetic and thresholds; the agentic part starts only after an alert fires.

**The practical test:** could you draw the flowchart before seeing the case? If you could, draw the flowchart. It'll be faster, cheaper, testable, and you'll be able to explain what it did.

## Step 2 — Draw the boundary, and defend it from both sides

There are two ways to get this wrong and they're mirror images:

**Agentic everywhere.** Non-deterministic where you needed reproducibility, expensive where you needed cheap, unevaluable, and impossible to get past a risk committee. The classic symptom is a "classification agent" — a thing that should be a lookup table.

**Agentic nowhere.** You've built a rules engine with a language model writing the summary. Perfectly useful, but don't call it agentic, because the first technical interviewer who asks "where does it reason?" will find nothing.

**The boundary between those two is the design.** Everything else is detail.

## Step 3 — Pick the topology, knowing what each one costs

Four shapes, in increasing order of power and decreasing order of control:

| Shape | Good for | Costs you |
|---|---|---|
| **One agent, many tools** | Most things. Genuinely. | Can't evaluate parts separately; hard to debug when wrong |
| **Sequential pipeline** | Fixed-order work with a known path | Can't adapt or skip |
| **Supervisor + specialists** | Different evidence types, need per-dimension evaluation | More calls, more latency, more to test |
| **Peer network** | Open-ended exploration | Unbounded, unauditable — usually disqualifying in regulated work |

**The rule: start at the simplest shape that can do the job, and only move up when you can name in one sentence what the extra structure buys.** "It's more advanced" is not a reason. "I can't tell whether the income reasoning or the cohort reasoning is broken" is.

Most systems that call themselves multi-agent should be one agent with good tools.

## Step 4 — Design the state before the agents

The state object is the contract between every part of the system. Get it wrong and every agent receives confused input, and no prompt will save you.

Four questions to answer explicitly:

- **What's immutable for the run?** Inputs and precomputed facts. Nobody rewrites these.
- **What accumulates?** Findings, evidence, citations. If more than one writer touches it, make it **append-only** — otherwise the last agent silently erases the others.
- **What's control?** Step count, budget, status. Kept separate from content.
- **What must never enter it?** State gets serialised into checkpoints and traces. Anything you wouldn't want in a log must not be in state.

**And precompute the shared facts once, deterministically, before the graph starts.** If five agents each look up the same number, you pay five times and — worse — two of them can end up arguing over a difference that's an artefact of when they queried.

## Step 5 — Design tools before prompts

This is the part people get backwards. They spend a week on prompt wording and an hour on tools.

**Tools bound what is possible. Prompts only bias what is likely.** A prompt saying "never contact the borrower" is a hope. Not having a tool that can contact the borrower is a guarantee.

Six rules:

1. **One tool per question, not per table.** `get_payment_behaviour(loan, months)` returning a characterised summary beats `run_sql(...)` every time. The tool does the retrieval and the shaping; the agent does the reasoning.
2. **Structured in, structured out.** Never prose.
3. **Bounded.** Every tool has a limit and reports what it omitted, so the agent knows it's seeing a subset.
4. **Errors are values, not exceptions.** `{ok: false, reason}` lets the agent record a gap and continue instead of crashing the run.
5. **Every tool carries the caller's identity.** Otherwise the agent becomes a way around your access control — the most commonly missed hole in agent systems.
6. **Capability, not instruction.** If the agent must not do X, remove the tool. Don't write "do not do X" in a prompt.

## Step 6 — Decide what each agent sees

Context engineering, and it's where cost and quality both live.

Too little and it can't reason. Too much and it anchors on irrelevance, costs more, and gets slower. And there's a subtler trap: **sharing context between agents destroys their independence.** If agent B reads agent A's conclusion, B stops looking. You lose the disagreement — which, in an investigation system, is the most valuable thing you produce.

Default to giving each agent the minimum slice it needs, and share findings only through the supervisor.

## Step 7 — Bound it

Every agent loop needs, without exception:

- **A step budget** — maximum rounds
- **Cycle detection** — the same agent can't be invoked twice with the same input
- **A timeout** and **a cost ceiling**
- **A defined behaviour at the limit** — and it must never be "return whatever we have and pretend it's complete"

**The invariant worth adopting everywhere: a run never fails silently.** It completes, completes-with-gaps, or escalates — and it always says which.

## Step 8 — Design the evaluation at the same time

If you can't describe how you'd score a run, the design isn't finished.

And for agents you score the **trajectory**, not just the answer. Did it gather evidence before concluding? Did every claim cite something actually retrieved? Did it stop at the right point? Did it escalate when it should have? Those four are deterministic checks — free, fast, and they catch most regressions.

A correct answer reached by a broken path will break tomorrow.

---

# Part B — How we arrived at this design

Worth knowing the order, because "how did you design this?" is a real interview question and the honest answer is more impressive than a tidy one.

**1. It started wrong, and you corrected it.**
The first design put agents on document extraction for a credit file. You asked: *if we have deterministic rules, where are we actually using agents?* That was the right challenge and it moved the entire project. Extraction and field-matching are exactly the "knowable in advance" case from Step 1 — making them agentic would have added non-determinism to the part that most needed to be repeatable.

**2. Which forced the real question.** Not "what should we build" but *where in an NBFC is the sequence genuinely unknowable?* Mapping the lifecycle gave a consistent answer: **at the exception, never in the flow.** The happy path is high-volume and rule-shaped. The cost and the risk sit in the 10–20% where something doesn't reconcile.

**3. Early warning, because the effort recurs.** A one-off saving per file is a number. The same work repeating every week is a number that compounds — and a sponsor already feels it.

**4. Education loans, because moratorium breaks the standard approach.** DPD is structurally zero for years. Conventional early warning is blind across a third of the book, precisely while the outcome is being determined. That's what makes the problem interesting rather than generic.

**5. Then Step 1 applied to EWS itself.** DPD, SMA and IRACP classification → deterministic, because the regulator needs it reproducible to the rupee. Signal thresholds → deterministic. Case routing and suppression → deterministic, because it runs on every account every night and judgement is too expensive to spend there. Triage and investigation → agentic, because the path depends on what you find.

**6. Topology came from evidence, not from architecture taste.** Five investigators exist because the evidence lives in five different places with five different notions of proof — and because you must be able to tell which one is wrong.

**7. The arbitration insight.** Independent investigators can reach incompatible conclusions from different evidence, and *that conflict is the highest-value output of the system* — it's the signal that a human is needed. Which is what drove the counterintuitive rule that investigators don't see each other's findings in round one.

**8. The cohort agent came from your roll-forward / roll-back idea.** Reasoning across alerts rather than within one is the capability human triage structurally cannot have.

**9. The case ID came from your chatbot idea** — and turned out to be the join key for the entire learning loop: alert → investigation → recommendation → intervention → outcome.

**10. Your PII challenge shaped the state object.** No identifying data reaches a model, one egress gate — and therefore no PII in state either, because state is serialised into traces.

**11. Your intervention-outcome idea gave recommendations two groundings:** policy says what's permitted, history says what has worked.

**12. The regulated setting supplied the rest** — budgets, failure semantics, prompt versioning, nothing silent, everything reconstructable.

## The point of that list

**Almost every good decision in this design came from a constraint, not from a pattern.** PII, regulatory reproducibility, cost, auditability, the moratorium blind spot — those are what produced the architecture. Nobody sat down and chose "supervisor with specialists" from a catalogue.

That's also the honest answer in an interview, and it's a much better one than reciting a topology: *"the shape came out of the constraints — here's the one that mattered most and what it forced."*

And the single most useful habit to take from this: **when anyone shows you an agent design, ask where the judgement is.** If they can't point at a step where the next action isn't knowable in advance, they don't need agents. You found that on this project by asking it yourself.
