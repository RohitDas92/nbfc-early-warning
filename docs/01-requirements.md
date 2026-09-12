# 01 — Requirements
**Early Warning & Portfolio Surveillance for an education-loan NBFC**
Release one. Last updated 10 Sep 2026. Items marked ⚠ are working assumptions to validate, listed in §14.

---

## 1. Problem

An NBFC's early warning process produces far more alerts than anyone can work. The rules are cheap to run; the triage is not. For every flagged account an analyst pulls the history, looks at what actually happened, decides whether it is real deterioration or a benign explanation, and writes it up. One missed instalment could be a mandate registration failure, a salary date shift, a bank change, or the start of a default — the same signal with four causes and four different actions.

That triage is done account by account, which means it also cannot see patterns *across* accounts. Fourteen alerts in a week sharing one institution look like fourteen unrelated problems.

**Education loans make this harder in a way no other retail product does: during moratorium the borrower owes nothing, so DPD is structurally zero for years.** Conventional early warning, built on delinquency buckets, is blind across roughly a third of the book — and blind precisely during the period when the outcome is being determined.

## 2. Business case and baseline

| | |
|---|---|
| Portfolio | 10,000 loans, ~₹1,000cr AUM |
| Signals raised | ~240 per week |
| New cases after suppression | **~60–80 per week** |
| Triage effort | 15–20 minutes per case |
| Analyst load | **50–90 hours/week — 1.5 to 2.3 FTE on triage alone** |

The saving is recurring, not per-file, which is what makes it worth building. Secondary benefits: consistent treatment across the book, cohort risks visible before they become individual defaults, and an auditable record of what was reviewed and decided.

## 3. Success criteria

**Primary — early detection rate.** The share of accounts that eventually reach 90+ which were flagged and worked at least 90 days earlier. Outcome-linked, and exactly measurable against the generator's answer key.

**Secondary — analyst minutes per case.**

**Guardrail — alert precision.** Share of cases closed `resolved_benign`. Reported alongside the primary always: efficiency gains that collapse precision produce a faster noise machine, not a better one.

**Control arm.** The deterministic rules are run alone over the same book. Early detection rules-only versus rules-plus-agents is the measured contribution of the agentic layer, and it is the answer to "how do you know the agents helped?"

## 4. Scope

**In, for release one**

- Nightly full-portfolio evaluation generating signals
- Case creation, suppression, triage and prioritisation
- Agentic investigation with evidence gathering
- Cohort detection across alerts
- Recommendations grounded in RBI directions, collections SOP and settlement procedures, with citations
- Analyst dashboard and case-scoped chat
- Intervention capture and outcome linkage
- Observability and evaluation harness

**Explicitly out**

- Any automated action with external effect — no bureau pulls, no borrower contact, no account status change
- Credit decisioning of any kind
- Collections execution, dialler or field integration
- Regulatory return generation
- Real borrower data

## 5. Users

| Persona | Uses it for |
|---|---|
| **Credit risk analyst** *(primary)* | Opens the queue each morning, works cases, records interventions |
| Credit risk manager | Cohort cases, portfolio view, approves above analyst authority |
| Collections lead | Consumes cases handed over for action; restricted account view |
| Compliance / internal audit | Reads cases, evidence and traces; writes nothing |
| Batch service principal | Runs the nightly evaluation under its own identity |

## 6. Reference portfolio (synthetic)

The book is generated, not sourced. The generator is the system's evaluation ground truth.

| Parameter | Value |
|---|---|
| Loans | 10,000 |
| AUM | ~₹1,000cr |
| Foreign (study-abroad) | 20% — 2,000 loans at ₹25–40 lakh |
| Domestic | 80% — 8,000 loans at ~₹4 lakh |
| In moratorium | 30% — 3,000 accounts |
| In repayment | 7,000 accounts |
| Moratorium duration | Derived from course type — ~2.5–3 yrs PG/abroad, ~4.5–5 yrs domestic UG |
| Bounce rate | 9–11% of presentations |
| History | **3–4 years of monthly state** |

**Entities:** loan (ticket, product, institution, course, duration, moratorium end, tranche schedule, rate) · borrower and co-applicant with income · tranche events, expected versus requested · monthly repayment history with presentation outcomes and bounce reasons · periodic bureau snapshots for both parties · institution master with events · **historical interventions and their outcomes**.

That last one is load-bearing: without a history of what was tried and what followed, the recommendation engine has nothing to learn from on day one.

**Deterioration patterns planted:** idiosyncratic distress (co-applicant income loss → bounces → DPD) · dropout (tranche not requested → silence → default at moratorium exit) · institution collapse (cohort, staggered over months) · willful default (paying others but not us — visible in bureau, invisible in our own data).

**Confounders that must also be planted:** mandate registration failure that bounces then self-cures · salary date shift causing two months of bounces · a student legitimately self-funding a final semester · an institution with unrelated defaults and no actual problem.

**Two disciplines:**
- The labels file is emitted separately and is never read by the pipeline.
- Two books from different seeds — one for development, one held out and not examined until W4.

Planted signals must sit at realistic strength (a failing institution's accounts deteriorate at roughly three times base rate, not 100%). A synthetic set that is too clean produces an evaluation only this system can pass.

*Note: with 3–4 years of history and domestic UG moratoria of 4.5–5 years, some domestic accounts remain in moratorium throughout the window. Realistic and intended.*

## 7. Signal inventory

**Portfolio metrics — reported, do not create cases**

DPD 30+/60+/90+ and NPA: loan counts and POS · roll-forward and roll-back rates · bucket transition matrix. A sharp move in a rate may raise a *portfolio-level* alert.

**Account and cohort signals — create cases**

| Signal | Level | Threshold | Est./week ⚠ | Lead time |
|---|---|---|---|---|
| NACH bounce pattern | Account | 2 bounces in rolling 3 months, or 1 bounce with ≥2 retries | ~90 | Weeks |
| DPD bucket movement | Account | crossing into 30+ | ~30 | Lagging |
| Moratorium ending | Account | T-75 days | ~25 | Predictable |
| Declining balance | Account | avg monthly balance down >40% over 3 months **and** < 1.5× EMI | ~25 | Weeks |
| Interest not serviced | Account | 2 consecutive months during moratorium | ~20 | Years |
| Bureau deterioration | Account | score drop ≥40 pts, or ≥3 new enquiries in 60 days | ~20 | Months |
| Tranche not requested | Account | 30 days past expected semester start | ~15, bursty | **Years — strongest early signal** |
| Contactability decay | Account | 2 failed contacts or bounced comms in 60 days | ~15 | Months |
| Institution event | **Cohort** | ≥5 accounts flagged from one institution in 30 days, or ≥2× base rate | 1–2 cases | Months |
| Visa rejection / student returned *(foreign)* | Account | event-driven | ~2 | Months |
| | | **Total** | **~240** | |

Roughly 240 signals a week resolve to **60–80 new cases** after suppression. The gap is why suppression is load-bearing rather than cosmetic.

## 8. Case lifecycle

**One open case per account at a time** — not one per signal, not one per concern type. An analyst needs a single view of what is happening with a borrower; parallel cases on one account is how ops teams lose track.

- **Open** — a signal fires on an account with no open case. Case type set from the triggering signal.
- **Join** — any further signal on an account with an open case appends as evidence. If the new signal is more severe than the current type, the case **escalates** and re-enters the queue even if snoozed.
- **Cohort cases are separate objects.** An account may sit in both; the account case links to the cohort case. Case-to-account is many-to-many.
- **Snooze** — analyst defers with a date and a reason; the case leaves the queue and returns on the date. Without this, analysts fake-close to clear the list.
- **Close** — always with an outcome: `resolved_benign` · `intervened` · `escalated` · `no_action_authorised`. **The outcome is the training label; a case closed without one is a lost data point.**
- **Auto-close** — no signal for 90 days and the account current → `resolved_benign`, reason `auto_quiet`.
- **After close, a new signal creates a NEW case**, linked to the previous as predecessor. Reopen is permitted only within 14 days, for genuine mis-closures.

The no-reopen rule exists for evaluation integrity: one clean outcome per episode. If a cured account relapses into the same case, whether the intervention worked becomes unanswerable.

## 9. Functional requirements

1. **Nightly evaluation** of the full portfolio; 10,000 loans needs no incremental processing.
2. **Case management** per §8. A case is the unit of work, the audit record, the evaluation unit, and the join key from signal → investigation → recommendation → intervention → outcome. Human-readable identifier.
3. **Triage.** The supervisor prioritises which cases warrant investigation and records why.
4. **Investigation** by specialist agents: repayment behaviour, external behaviour, borrower context, cohort, action & policy.
5. **Arbitration.** Where investigators reach incompatible conclusions, the supervisor weighs the evidence and records the reasoning.
6. **Recommendation**, grounded twice — policy for what is permitted, intervention history for what has worked. Language states association, never causation.
7. **Citations.** Every assertion traceable to source; anything uncitable is not asserted.
8. **Dashboard** — portfolio, case queue, case detail, cohorts, interventions and outcomes, policy reached from a citation.
9. **Case-scoped chat** that writes auditable events: record an intervention, disagree with a recommendation, escalate, close.
10. **Analyst disagreement captured as a score on the case**, feeding evaluation.

## 10. Deterministic / agentic boundary

**Deterministic:** DPD computation, SMA and IRACP classification, provisioning arithmetic, roll rates, threshold rules that raise signals. Classification must be reproducible to the rupee — an agent never classifies an account.

**Agentic:** everything after a signal fires — triage, investigation, cohort reasoning, arbitration, recommendation, case narrative.

## 11. Actions and authority

Actions are classified by whether they have effect outside our own systems.

**Agent performs freely:** add investigation note · flag to watchlist · record no-action-needed.

**Agent recommends only; a human with authority executes:**

| Action | Authority |
|---|---|
| `MANDATE_REPAIR` | Analyst |
| `PAYMENT_DATE_CHANGE` | Analyst |
| `SOFT_CONTACT_BORROWER` | Analyst — fair-practice contact hours apply |
| `CONTACT_CO_APPLICANT` | Analyst |
| `BUREAU_SCRUB` | Analyst, within the weekly batch |
| `INSTITUTION_ENQUIRY` | Manager |
| `FIELD_VISIT` | Manager |
| `TENURE_EXTENSION / RESTRUCTURE` | Manager |
| `MORATORIUM_EXTENSION` | Manager / committee |
| `HANDOVER_TO_COLLECTIONS` | Manager |
| `PROVISION_REVIEW` | Risk manager |
| `SETTLEMENT / WAIVER` | ⚠ analyst nil, manager ≤₹50k, head ≤₹5L, committee above. Maker-checker mandatory |
| `LEGAL_NOTICE` | Head / legal |

**Design bias:** mandate repair and payment date change are the cheapest interventions with the highest cure rates. Early-stage recommendations should favour them. A system that mostly proposes restructuring and legal notices is not doing its job.

**Bureau scrub batch.** Budget ⚠ **1% of the book per week — 100 pulls**, roughly ₹5,000 at ~₹50 each. The agent proposes a ranked list with reasoning; a human approves the batch. Ranking is expected deterioration probability × exposure, with a hard constraint of **no re-scrub within 90 days** on the same borrower. Note that exposure ranking will favour foreign loans at ₹25–40 lakh; that is correct on economics, and is a fairness question to be able to answer.

**Maker-checker:** the recommender cannot be the approver.

## 12. Non-functional

- **PII.** No identifying data reaches a language model, by construction — entity tokenisation before the prompt, values restored after. Enforced at a single egress choke point that fails closed. Trace export passes through the same point.
- **Access control.** Permission × scope. Row-level security at the data layer. Agent tools execute under the calling user's identity, never a system account. Retrieval entitlement filters go into the query, not applied to results. Observability access is itself a permission.
- **Observability.** Langfuse, self-hosted. **Trace granularity is the case**, not the model call. Cost and latency recorded per case.
- **Audit.** Every case reconstructable: what was read, concluded, recommended, decided by whom, and under which prompt version.
- **Architecture.** API-first. No business logic in the presentation layer.

## 13. Evaluation

Three layers, built in order:

1. **Deterministic checks**, every case — citations present and resolvable, step budget respected, recommendation within the permitted set. Gates CI.
2. **Labelled golden set** against the generator's answer key — early detection rate, cohort discovery, action permissibility, and false positives on the planted confounders.
3. **LLM-as-judge**, sparingly, for narrative coherence and reasoning defensibility, validated against human labels on a sample first.

Trajectories are evaluated, not just final answers: was the investigation path sensible, did it stop at the right point, was the conclusion supported by the evidence actually gathered. Analyst disagreements accumulate as human labels.

## 14. Assumptions to validate

1. Per-signal weekly volumes in §7 — modelled, not observed. The bounce-derived figure drives everything.
2. The 240 signals → 60–80 cases suppression ratio.
3. Settlement and waiver authority slabs in §11.
4. Bureau pull unit cost (~₹50) and the 1%-per-week budget.
5. Whether 15–20 minutes per case matches real triage time.
