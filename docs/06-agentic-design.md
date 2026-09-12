# 06 — Agentic System Design

How the investigation layer works. This is the piece with no equivalent in ordinary software design, and it decides more about quality than any prompt will.

Everything here sits *below* the determinism boundary from doc 02: signals, classification and case routing have already happened deterministically. This document starts the moment a prioritised case exists.

---

## 1. Topology

**A supervisor over five specialists**, with the four evidence-gathering investigators running concurrently and the policy investigator running after them.

Three alternatives were considered, and you should be able to say why not:

**A sequential pipeline** — each agent in fixed order, no supervisor. Cheaper and easier to evaluate. Rejected because the whole premise is that the next step depends on what the last step found; a fixed order cannot skip an irrelevant investigator or ask for a second look.

**A peer network** — agents handing off to each other freely. Rejected because it cannot be bounded or audited. In a regulated lender, "I can't tell you why it did that" ends the conversation.

**One agent with ten tools** — genuinely the strongest alternative, and the honest answer is that it would work. Rejected for three specific reasons: the five investigators have different notions of what counts as evidence; they need different context, and merging it produces a prompt full of irrelevance; and you cannot evaluate the income reasoning separately from the cohort reasoning, which means you can't tell which half is broken.

**Be ready for this question.** "Why multi-agent?" is the most likely challenge on this project, and the answer that lands is the third reason — independent evaluability — not "because it's more advanced."

## 2. The state object

The single most important artefact in this document. Everything else is downstream of getting this right.

```
CaseInvestigationState
  # identity and scope
  case_id                    the trace session id
  account_refs[]             tokenised - never a name, never a PAN
  case_type
  principal                  the calling user; every tool call inherits it

  # inputs, immutable for the run
  signals[]                  what fired: type, threshold, observed value, as_of
  facts                      precomputed deterministic context (see below)

  # accumulating, append-only
  findings[]                 one per investigator
  conflicts[]                detected incompatibilities between findings
  citations[]                policy clauses retrieved, with locators

  # control
  step_count, budget, round, status, next_action

  # output
  recommendation, narrative, confidence, escalation_reason
```

Three rules that matter more than the field list:

**Findings are append-only.** No investigator ever overwrites another's work. Contradiction is data, not a problem to be resolved by last-write-wins.

**No identifying data enters state, ever.** State is serialised into checkpoints and traces. If a name reaches it, the name reaches the observability store, and the no-PII property is gone by the back door.

**`facts` is computed once, deterministically, before the graph starts.** Current bucket, DPD, POS, moratorium status, ticket size, product, institution, months since sanction. Not fetched by agents.

That last one is worth dwelling on. If each investigator queries DPD itself, you pay for the same lookup five times, and worse, two agents can reason over slightly different numbers and produce a conflict that isn't real. Precomputing guarantees every agent argues from the same facts.

## 3. Control flow

**Fixed skeleton:**

```
entry
  → compute facts
  → supervisor: triage and select investigators
  → fan out: repayment | external | borrower context | cohort   (concurrent)
  → collect findings
  → detect conflicts
  → [arbitration, only if conflicts exist]
  → policy investigator
  → compose narrative and recommendation
  → groundedness gate
  → end, or interrupt for human
```

**The supervisor decides only three things:**

1. Which investigators to run. Not every case needs all four — a mandate-failure pattern needs repayment behaviour and little else.
2. Whether a second round is warranted after seeing round-one findings.
3. Whether to escalate instead of concluding.

Everything else is a fixed edge. **Resist making more of this a decision.** Every LLM decision point is latency, cost, non-determinism and another thing to evaluate. The skeleton being fixed is what makes the system approvable.

## 4. Agent contracts

Every investigator returns **the same shape**. This is what makes arbitration mechanical, evaluation uniform, and the UI a single component.

```
Finding
  investigator          which one
  conclusion            one sentence
  evidence[]            EvidenceItem, at least one
  confidence            low | medium | high
  supports              deterioration | benign | inconclusive
  contradicts[]         references to other findings, optional
  recommended_next[]    optional, advisory only

EvidenceItem
  source                table or document
  field, value, as_of
  tool_call_id          so the trace can be walked back
```

A finding with no evidence is invalid and rejected by validation, not by a prompt instruction.

| Investigator | Question it answers | Tools | Stops when |
|---|---|---|---|
| **Repayment behaviour** | Why are payments failing on our book? Technical or genuine shortfall? | payment behaviour, balance trend, schedule | Bounce pattern is characterised |
| **External behaviour** | Are they paying everyone else and not us? | bureau history *(existing pulls only — never triggers one)* | Distress vs unwillingness is settled, or no data |
| **Borrower context** | Is the course or institution driving this? | institution profile, institution events, tranche history | Course status established |
| **Cohort** | Idiosyncratic, or is a group moving together? | similar alerts across the book | Cluster confirmed or ruled out |
| **Action & policy** | What may we do, and what has worked? | policy search, intervention outcomes | Permitted actions cited, or refuses |

**The cohort investigator is the only one that sees beyond this case.** It queries across the current alert set. That's deliberate — it's the capability human triage structurally cannot have, and it's the most valuable thing the system does.

**The policy investigator runs last** and takes only confirmed findings, so it isn't reasoning about evidence that later gets contradicted. If it finds no applicable clause it must refuse and escalate — never improvise a recommendation.

## 5. Tool design

Prompt wording matters far less than people assume. Tool shape is where agent quality actually lives.

- **One tool per question, not per table.** `get_payment_behaviour(loan_id, months)` returning a characterised summary — attempts, bounces grouped by reason, retry pattern, cure behaviour — beats a raw row dump every time.
- **Structured returns, never prose.** The agent reasons; the tool reports.
- **Every tool takes the principal.** Scope is enforced at the database. The agent is not a way around access control.
- **Bounded results.** Every tool has a limit and returns how many rows it omitted, so the agent knows it's seeing a subset.
- **`as_of` on everything.** A bureau score without a date is not evidence.
- **Errors are values, not exceptions.** `{ok: false, reason}` lets the agent record a gap and carry on rather than crashing the case.
- **No tool has external effect.** Enforced by what exists in the layer, not by instructions.

Starting set, ten tools:

`get_payment_behaviour` · `get_balance_trend` · `get_bureau_history` · `get_institution_profile` · `get_tranche_history` · `find_similar_alerts` · `search_policy` · `get_intervention_outcomes` · `get_case_history` · `get_account_timeline`

## 6. Context strategy

**Investigators do not see each other's findings in round one.**

This is a deliberate and slightly counterintuitive choice. Sharing context feels helpful, but it makes agents anchor on each other — the external investigator reads "variable pay explains it" and stops looking. Independence is what produces genuine disagreement, and **the disagreement is the most valuable output the system has.** Two investigators reaching incompatible conclusions from different evidence is exactly the signal that this case needs a human.

- The **supervisor** sees all findings as structured objects, never raw tool output.
- In **round two**, an investigator may be handed one specific conflicting finding to respond to. Targeted, not broadcast.
- The **composer** sees findings and citations only.

## 7. Budgets and termination

| Limit | Value |
|---|---|
| Supervisor rounds | 2 |
| Tool calls per investigator | 6 |
| Tool calls per case | 30 |
| Wall clock per case | 90 s |
| Cost per case | ceiling, logged every run |

Plus a **cycle guard**: an investigator cannot be invoked twice with the same input hash. That is Block 11's cycle detection doing real work.

**On exceeding any limit the case stops, is marked `incomplete`, and escalates to a human with whatever was gathered.** It never silently truncates and it never quietly returns a weaker answer.

## 8. Failure semantics

| Failure | Behaviour |
|---|---|
| Model returns invalid schema | One repair attempt with the validation error fed back, then finding = `inconclusive` with reason. **Never coerce.** |
| Tool errors | Recorded as a gap in the finding; the case continues |
| Investigator times out | That dimension marked unavailable; the narrative says so explicitly |
| Policy finds no clause | Refuse to recommend, escalate |
| Groundedness gate fails | Recommendation withheld, case escalates |

**The invariant: a case never fails silently.** It completes, completes-with-gaps, or escalates — and the narrative always says which.

## 9. Human in the loop

The graph interrupts and checkpoints when: a recommendation exceeds the analyst's authority; confidence is low; the budget was exhausted; or investigators conflicted and the arbitration itself came out low-confidence.

On interrupt the case returns to the queue with everything gathered so far visible. Resuming continues from the checkpoint rather than re-running.

## 10. Prompts

Versioned externally and fetched by name and version at runtime. **The prompt version is recorded on the case.** In a regulated setting you will be asked which prompt produced a given recommendation on a given date, and "we edited it in place" is not an answer.

Never edit a prompt in place. New version, always.

## 11. What gets traced

One trace per case run, with the case id as the session. A span per node and per tool call. Recorded on every run: model version, prompt version, tokens, cost, latency.

Which makes the trajectory checks possible — and these, not the final answer, are what you actually evaluate:

- Did it gather evidence before concluding?
- Did every conclusion cite evidence that was actually retrieved?
- Did it stop at the right point, rather than looping or quitting early?
- Did it escalate when it should have?
- Was the recommendation inside the permitted set?

The first four are deterministic checks and cost nothing to run on every case. They are what gates CI.

## 12. Carried into the case data model

`findings`, `evidence`, `conflicts`, `citations`, `recommendation` and the checkpoint store are all shaped by this document. That's why the case tables come next, not before.
