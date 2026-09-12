# 02 — High-Level Architecture
**Early Warning & Portfolio Surveillance for an education-loan NBFC**
Companion to `02-high-level-architecture.svg`. Logical design only — technology choices are deliberately deferred to document 03.

---

## 1. Shape of the system

Two paths meet at the case store.

The **nightly path** runs top to bottom: sources are ingested, the deterministic engine classifies the book and fires signals, and the suppression router turns roughly 240 signals a week into 60–80 prioritised cases. The **interactive path** runs from the analyst's screen through the API into the same cases.

Between them sits the agentic layer, which is where the judgement lives — and it is deliberately fenced on three sides.

## 2. Context

| External | We take | We give |
|---|---|---|
| LOS | Loan, borrower, co-applicant, institution, course, tranche schedule | — |
| LMS | Presentations, outcomes, balances, DPD | — |
| Bureau | Periodic snapshots; approved on-demand pulls | Scrub requests, human-approved |
| Policy corpus | RBI directions, collections SOP, settlement procedures | — |
| Identity provider | Authentication, roles, scope claims | — |

For release one every transactional source is the synthetic generator. That substitution is at the ingest layer only, so replacing it with real feeds later touches nothing downstream.

## 3. The layers

**Data foundation.** Five stores with distinct jobs. The portfolio store holds the book and three to four years of monthly history — history, not a snapshot, because roll rates are movement. The derived store holds computed classifications and portfolio metrics. The knowledge store holds the policy corpus. The case store holds cases, evidence, recommendations, interventions and outcomes.

The **audit log is separate and append-only**. Case rows mutate; audit needs the sequence. Keeping them in one place means you can reconstruct current state but never how you got there, which is precisely what an auditor asks for.

**Deterministic engine — "the flow".** Classification (DPD, SMA, IRACP, provisioning), portfolio metrics (roll forward, roll back, transition matrix), the signal engine, and the suppression and case router.

The router belongs here, not in the agentic layer. Deciding whether a signal opens a case, joins an open one or escalates it is a rule, and at a 9–11% bounce rate it runs on every account every night. Judgement is expensive; this must not be.

**Agentic layer — "the exceptions".** A triage supervisor over five investigators, plus a narrative composer and a case chat agent.

The supervisor prioritises, allocates, arbitrates and decides when there is enough evidence. Arbitration is the part that earns the multi-agent structure: the repayment investigator concludes variable pay explains a gap; the external investigator finds the credits originate from an account in another name. Both are right about what they saw and the conclusions are incompatible. Weighing that is not expressible as a rule.

**Tool layer.** Read tools over the portfolio and derived stores, policy retrieval, intervention-history lookup.

Two properties matter more than the contents. It is **read-only by construction** — no tool exists that can act externally, so no prompt can be persuaded into one. And every tool executes under **the calling user's identity**, never a service account, so the agent cannot become a route to data the UI would refuse.

**Application API.** Case, portfolio, chat and admin services. Deny by default: an endpoint that declares no permission is denied, not open.

**Presentation.** A thin client. It renders and collects input. It decides nothing, and every request from it is treated as forgeable.

## 4. The four boundaries

**Determinism boundary** — between the deterministic engine and the agentic layer. Classification and provisioning never cross. The regulator needs that arithmetic reproducible to the rupee, and "the model classified it as SMA-2" is not a defensible sentence.

**Authority boundary** — around the agentic layer. Agents propose. A human with authority executes anything with effect outside our systems: bureau pulls, borrower contact, status changes, settlements.

**Trust boundary** — around the model endpoint. One door out. Entities are tokenised before the prompt and restored after, the gate fails closed, and **trace export passes through the same door**, because a trace contains the entire case.

**Identity boundary** — vertical, through every layer. A principal accompanies every call from API to row, and scope is enforced at the data layer rather than by remembering to filter.

Four lines, four sentences. That is the architecture.

## 5. Flows

**A · Nightly.** Ingest → portfolio store → classification and metrics → signal engine → suppression and routing → cases opened, joined or escalated → queue prioritised.

**B · Investigation.** The supervisor takes a case, allocates investigators, gathers evidence through the tool layer, arbitrates conflicts, and the composer drafts a recommendation with citations.

Investigation runs **eagerly overnight for the top N cases by priority, lazily on open for the tail.** Eager for everything wastes reasoning on cases that close as benign; lazy for everything makes the analyst wait each morning. N is a tuning knob, and its correct value is an empirical question once cost and precision are measured.

**C · Analyst working a case.** Open, review evidence and recommendation, then record an intervention, disagree, escalate or close. Every action writes an audit event; closing writes an outcome.

**D · Outcome learning.** Nightly, interventions on closed cases are linked to what the account subsequently did, feeding the intervention-history store the recommendation reads from.

Flow D is what makes this a product rather than a rules engine with a language model attached, and it is the first thing that will be dropped under time pressure. It should not be.

## 6. Design decisions to record as ADRs

1. **Deterministic core, agentic periphery.** Agents only where the sequence of steps is not knowable in advance.
2. **The case is the aggregate root** — unit of work, audit record, evaluation unit, and the join key from signal to outcome. Case-to-account is many-to-many.
3. **Eager investigation for the top N, lazy for the tail.**
4. **Append-only audit, separate from case state.**
5. **A single PII egress choke point**, covering model calls and trace export, failing closed.
6. **Scope enforced at the data layer**, not by application-level filtering.
7. **Tools execute under caller identity**, never a service principal.

Each of these is a place where a reasonable person would have chosen differently, which is what makes them worth recording.

## 7. What this architecture deliberately refuses

- No agent classifies an account or computes provisioning.
- No component can contact a borrower, pull a bureau report, or change an account's status.
- No identifying data reaches a model or an observability store.
- No business logic in the presentation layer.
- No tool that exists "just in case an agent needs it".

## 8. Carried into the low-level design

- Case identifier format, state machine, and the escalation rule when a joining signal outranks the current case type
- Evidence model — how an investigator's findings, sources and confidence are represented
- The arbitration protocol when investigators conflict
- Step budget and termination conditions for the supervisor
- Tokenisation scheme and how restoration is verified
- Retrieval strategy and how entitlement filters enter the query
- Initial value of N, and what would move it
