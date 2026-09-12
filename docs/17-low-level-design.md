# 17 — Low-Level Design and Delivery Backlog

Stages 4 and 5 of the enterprise flow, written after stage 3 sign-off (`01`–`12`).

**Stage 4 (§A)** fixes the *contract* of every module — what goes in, what comes out, what must always be true, what it is forbidden to do. Two engineers who never speak can build either side of a contract and meet at the type.

**Stage 5 (§B)** breaks that into epics and stories with acceptance criteria, in build order.

Read §A when you ask *"why does this function take these arguments?"*. Read §B when you ask *"what do I build next and how do I know it's finished?"*.

---

# A · Low-Level Design

## How to read a contract

Every module below has the same five fields. If you can't fill all five, the design isn't finished.

| Field | Question it answers |
|---|---|
| **Purpose** | one sentence — if it needs two, split the module |
| **Interface** | the exact signatures. This is the promise to other modules |
| **Invariants** | what is always true, regardless of input |
| **Forbidden** | what this module must never do. Usually the more important half |
| **Tests** | how we know the contract holds |

---

## A1 · `domain/` — pure logic

Imports nothing from this project. No database, no clock, no randomness, no model. If a function needs "now", it is passed in as an argument.

### `models.py` ✅ built

| | |
|---|---|
| **Purpose** | the shared data shapes for case handling |
| **Interface** | `CaseState`, `CloseOutcome`, `EventType` (Literals) · `Case`, `Event` (frozen dataclasses) |
| **Invariants** | every dataclass is `frozen=True`; optional fields default to `None` |
| **Forbidden** | any method that does work. These are data, not behaviour |
| **Tests** | none of its own — exercised through `case_state` |

### `classification.py` ✅ built

| | |
|---|---|
| **Purpose** | days-past-due → delinquency bucket → IRACP asset class |
| **Interface** | `bucket_of(dpd: int) -> Bucket` · `asset_class_of(dpd: int) -> AssetClass` |
| **Invariants** | total over `dpd >= 0`; the bucket boundaries exist in exactly one place in the codebase |
| **Forbidden** | returning a default for unknown input. A negative DPD raises |
| **Tests** | boundary table 0, 1, 30, 31, 60, 61, 90, 91 for both functions, plus negative-raises |

### `case_state.py` ✅ built

| | |
|---|---|
| **Purpose** | the only place a case changes state |
| **Interface** | `apply_event(case: Case, event: Event) -> Case` · raises `InvalidTransition` |
| **Invariants** | returns a **new** `Case`; the input is never modified; an illegal move always raises; a close always records `outcome` and `closed_at` |
| **Forbidden** | writing to the database; reading the clock; silently allowing an unlisted transition |
| **Tests** | every legal transition; **every illegal one**; close-without-outcome raises; reopen clears the closure; the table-validity test |

### `signals.py` ✅ built

| | |
|---|---|
| **Purpose** | the detection rules |
| **Interface** | `AccountFacts` (in) · `Signal`, `CohortSignal` (out) · `evaluate(facts) -> list[Signal]` · `check_institution_cohort(flagged, all_accounts) -> list[CohortSignal]` |
| **Invariants** | one rule owns one concern; each rule emits a unique `signal_type`; a clean account produces `[]`; every `Signal` carries a human-readable `detail` |
| **Forbidden** | reading the database; reading the clock; two rules firing on the same underlying fact |
| **Tests** | a fires and a does-not-fire case per rule, at the threshold and just under; distinct-signal-type test |

### `routing.py` ✅ built

| | |
|---|---|
| **Purpose** | decide what a signal does to an account's open case |
| **Interface** | `route(signal_type: str, open_case_type: str \| None) -> RouteDecision` |
| **Invariants** | `None` → `"open"`; strictly greater severity → `"escalate"`; **equal severity → `"join"`** |
| **Forbidden** | knowing what a `Case` or a `Signal` is. It takes two strings |
| **Tests** | the four-row decision table, with equal-severity explicitly asserted |

### `authority.py` — not built

| | |
|---|---|
| **Purpose** | who may authorise which action, at what amount |
| **Interface** | `permitted(action: str, role: str, amount: float \| None) -> bool` · `requires_second_approval(action, amount) -> bool` |
| **Invariants** | denial is the default for any unknown combination; `recommender != approver` for anything above the analyst threshold |
| **Forbidden** | reading a user object or a session. It takes a role string |
| **Tests** | the full action × role × amount matrix, including every denial |

### `pii.py` — not built

| | |
|---|---|
| **Purpose** | the registry of which columns are PII, and tokenise/detokenise |
| **Interface** | `PII_COLUMNS: dict[str, set[str]]` · `tokenise(value, kind) -> str` · `detokenise(token) -> str` |
| **Invariants** | `detokenise(tokenise(x)) == x`; a token matches no PII pattern; the registry is the single source of truth used by the egress guard |
| **Forbidden** | network calls; logging either input or output |
| **Tests** | round-trip; token contains no PAN/Aadhaar/phone/email pattern; every PII column in the schema appears in the registry |

---

## A2 · `db/` — persistence

Imports `domain` only. Contains queries and row→object mapping. **A repository that makes a business decision is in the wrong folder.**

### `engine.py` ✅ built (needs the principal extension)

| | |
|---|---|
| **Purpose** | connections, and the security context every query runs under |
| **Interface** | `connect() -> Connection` · *to add:* `session(principal: Principal)` — a context manager issuing `SET LOCAL app.branch_ids` / `app.role` |
| **Invariants** | every application query runs inside `session(...)`; an unset principal sees **zero rows**, never all rows |
| **Forbidden** | hardcoded credentials; connecting as a superuser role |
| **Tests** | integration — branch-1 principal sees only branch 1; unset sees zero; `app_rw` selecting base `party` raises |

### `repositories/accounts.py` ✅ built (adverse query added)

| | |
|---|---|
| **Purpose** | build `AccountFacts` for every loan for one month |
| **Interface** | `load_account_facts(conn, as_of: date) -> list[AccountFacts]` plus one `load_*_facts` helper per fact group, each returning `dict[loan_id, value]` |
| **Invariants** | one query per fact group, never one query per loan; every helper keyed by `loan_id`; missing data becomes the field's documented default, never a crash |
| **Forbidden** | deciding anything. It reads and maps |
| **Tests** | integration against the fixture book: known loan → expected `AccountFacts` |

### `repositories/cases.py` — **next to build**

| | |
|---|---|
| **Purpose** | read and write cases and their events |
| **Interface** | `open_case_types(conn, as_of) -> dict[account_id, case_type]` · `create_case(conn, account_id, case_type, signal) -> str` · `append_event(conn, case_id, event, signal) -> None` · `get_case(conn, case_id) -> Case` |
| **Invariants** | `case_id` is human-readable and stable (`EWS-2026-06-00123`); **at most one open case per account** — enforced by a partial unique index, not by application code; every state change is written as an event row, append-only |
| **Forbidden** | calling `apply_event` logic itself — it persists what the domain decided |
| **Tests** | integration — two concurrent opens on one account: the second fails on the constraint; the event log replays to the case's current state |

### `repositories/signals.py` — not built

| | |
|---|---|
| **Purpose** | persist each run's signals so a case can cite its evidence |
| **Interface** | `save_signals(conn, run_id, signals) -> None` · `signals_for_case(conn, case_id) -> list[Signal]` |
| **Invariants** | signals are immutable once written; every signal carries `as_of` |
| **Forbidden** | deduplication. Suppression is `engine/route.py`'s job |
| **Tests** | integration — save then read back identical |

### `migrations/` — not built

| | |
|---|---|
| **Purpose** | schema changes as ordered, reviewable, reversible steps (alembic) |
| **Invariants** | every migration applies cleanly to an empty database **and** to the current one; constraints live here, not in application code |
| **Forbidden** | editing a migration that has been applied anywhere but your laptop |
| **Tests** | CI applies all migrations to an empty database; a closed case with no outcome is rejected by the constraint |

---

## A3 · `engine/` — the deterministic pipeline

Imports `domain` and `db`. **Must never import `llm/`, `agents/` or `tools/`.** That is the determinism boundary expressed as code, and an architecture test fails the build if it is violated.

### `detect.py` ✅ built

| | |
|---|---|
| **Purpose** | run every rule over the book for one month |
| **Interface** | `detect(conn, as_of: date) -> DetectionRun` |
| **Invariants** | reproducible — same book and date give byte-identical output; the run object carries `as_of` and `accounts_scanned`, not just signals |
| **Forbidden** | anything that reasons |
| **Tests** | integration on the fixture book: expected signal counts per type |

### `route.py` — in progress

| | |
|---|---|
| **Purpose** | turn signals into case actions, applying suppression |
| **Interface** | `route_signals(signals, open_case_types) -> list[CaseAction]` |
| **Invariants** | an account with n signals in one batch produces **at most one** `"open"`; later signals in the same batch see cases opened earlier in it; the input dict is copied, never mutated |
| **Forbidden** | writing to the database. It returns intended actions; the service persists them |
| **Tests** | 3 signals on 1 account → 1 open + 2 joins; a more severe signal on an existing case → escalate; an empty batch → `[]` |

### `classify.py` — not built

| | |
|---|---|
| **Purpose** | write `loan_month_state` — DPD, bucket, asset class, provisioning |
| **Interface** | `classify_month(conn, as_of: date) -> ClassifyRun` |
| **Invariants** | idempotent — running twice for the same month leaves the same rows; classification must reconcile **to the rupee** |
| **Forbidden** | an agent anywhere near it. Regulatory arithmetic is deterministic by law |
| **Tests** | integration — recompute a month and assert the rows are unchanged |

### `nightly.py` — not built

| | |
|---|---|
| **Purpose** | the batch orchestrator: classify → detect → route → persist |
| **Interface** | `run_nightly(conn, as_of: date) -> NightlyRun` |
| **Invariants** | one transaction per phase; a failure leaves a recorded run row with its failure point; safe to re-run the same date |
| **Forbidden** | business logic. It sequences the phases and records what happened |
| **Tests** | integration — run twice, assert no duplicate cases |

---

## A4 · `llm/` and `guard/` — the model boundary

### `llm/base.py`, `azure_openai.py`, `fake.py` — not built

| | |
|---|---|
| **Purpose** | one interface for every model client, so the graph never knows which model it is talking to |
| **Interface** | `class ChatModel(Protocol): def complete(self, messages, *, schema=None) -> ModelResult` · `FakeChatModel(responses=[...])` returns them in order |
| **Invariants** | every call returns tokens used and latency; a schema mismatch is **one** repair attempt, then a failure result — never a coerced guess |
| **Forbidden** | prompts. Those live with the agents that use them |
| **Tests** | `FakeChatModel` returns responses in order; invalid JSON produces a failure result, not an exception |

### `guard/egress.py` — not built

| | |
|---|---|
| **Purpose** | the single choke point through which anything reaching a model must pass |
| **Interface** | `check(payload: str) -> EgressResult` — allowed, or blocked with the reason |
| **Invariants** | **fails closed**; an unavailable detector blocks, never passes; every block is logged with the rule that fired, never the payload |
| **Forbidden** | being bypassable. No other module may call a model client directly |
| **Tests** | each PII pattern blocked; detector exception → blocked; an architecture test that no module outside `guard/` imports a model client |

---

## A5 · `tools/` — what agents may call

Imports `domain`, `db`, `retrieval`. Every tool has the **same** contract, which is what makes them safe.

| | |
|---|---|
| **Purpose** | answer one question about one case, read-only |
| **Interface** | `def __call__(self, principal: Principal, **params) -> ToolResult` where `ToolResult = {ok, data, as_of, omitted, reason}` |
| **Invariants** | scoped by the principal — a branch-1 agent gets nothing from branch 2; every record carries `as_of`; row limits are enforced and what was omitted is reported; a bad input returns `{ok: false, reason}` and **does not raise** |
| **Forbidden** | any write, any external side effect. There must be no tool that *can* act. Authority to act lives with humans |
| **Tests** | the same five contract tests for every tool, the fifth being the scope test |

Planned: `payment.get_payment_behaviour` · `payment.get_balance_trend` · `external.get_bureau_history` · `context.get_institution_profile` · `context.get_tranche_history` · `cohort.find_similar_alerts` · `policy.search_policy` · `policy.get_intervention_outcomes`.

---

## A6 · `agents/` — the reasoning layer

Imports `domain`, `tools`, `llm`, `guard`. **Never SQL.**

| Module | Purpose | Key invariant |
|---|---|---|
| `state.py` | `CaseInvestigationState` — what flows through the graph | serialisable, so a run can checkpoint and resume |
| `supervisor.py` | pick investigators for this case type, and record why | the selection is recorded as a decision, not implied |
| `investigators/` | five specialists, each with its own tools | **round one is independent** — no investigator sees another's findings |
| `arbitrate.py` | resolve contradictory findings | arbitration is recorded with its reasoning; it never averages |
| `compose.py` | the case narrative and recommendation | every assertion carries a citation; anything uncitable is not asserted |
| `graph.py` | nodes and edges only | no business logic in the wiring |

**Forbidden across the whole folder:** touching the database, acting on the world, or producing a recommendation outside the permitted set.

**Tests** (all with `FakeChatModel`, no API calls): supervisor selection per case type · invalid JSON → one repair then `inconclusive` · contradiction → arbitration runs · budget exceeded → escalate with partial findings · cycle guard · tool error recorded as a gap · no policy clause → refuse and escalate · uncited recommendation withheld · interrupt checkpoints and resumes.

---

## A7 · `services/`, `api/`, `ui/`, `eval/`, `obs/`

| Module | Purpose | Forbidden |
|---|---|---|
| `services/` | the operations the API exposes — combine domain + db + engine + agents | HTTP concerns, request parsing |
| `api/` | routing, auth, serialisation | business logic. An `if` about lending in a router belongs in a service |
| `ui/` | Streamlit — portfolio, queue, case detail, cohorts, policy | importing anything from `src`. HTTP only |
| `eval/` | scoring, metrics, the harness, the two-arm comparison | being imported **by** `src`. One-way street |
| `obs/` | case-level traces and cost, to Langfuse | changing behaviour. Observation only |

**CI rule for `api/`:** a new endpoint without an authorisation test fails the build. Authorisation that isn't tested is an intention, not a control.

---

# B · Delivery Backlog

Epics in dependency order. A story is **done** when every acceptance criterion passes in CI, not when the code runs on your laptop.

---

## E1 · Pure domain ✅ complete

| # | Story | Acceptance |
|---|---|---|
| 1.1 | Classification | ✅ boundary table passes both functions; negative raises |
| 1.2 | Case state machine | ✅ every legal and illegal transition tested; table-validity test |
| 1.3 | Signal rules | ✅ 11 account rules + cohort rule, each with fires / does-not-fire |
| 1.4 | Routing decision | ✅ four-row decision table, equal-severity asserted |

## E2 · Read the book ✅ complete

| # | Story | Acceptance |
|---|---|---|
| 2.1 | Connection + config | ✅ DSN from environment, one `connect()` |
| 2.2 | Account facts repository | ✅ seven fact groups; one query each |
| 2.3 | Detection engine | ✅ full book runs; all 11 rules fire; cohort finds the 4 seeded institutions |

## E3 · Cases exist — **current**

| # | Story | Acceptance |
|---|---|---|
| 3.1 | Case + event tables, migration | applies to an empty DB; partial unique index enforces one open case per account; closed-without-outcome rejected |
| 3.2 | `route_signals` | 3 signals on 1 account → 1 open + 2 joins; more severe → escalate; empty batch → `[]` |
| 3.3 | Case repository | create / append / read; event log replays to current state; concurrent open fails on the constraint |
| 3.4 | `nightly.py` | one command runs classify → detect → route → persist; **re-running the same date creates no duplicate cases** |
| 3.5 | Run the month | 3,651 signals resolve to **60–80 cases**; the number is explained, not just observed |

**E3 is the milestone.** At its end you have the **rules-only arm** — a complete working product with no agents in it, and the control group the entire evaluation compares against.

## E4 · Access control

| # | Story | Acceptance |
|---|---|---|
| 4.1 | Principal + `SET LOCAL` session | branch-1 principal sees only branch 1; **unset sees zero rows** |
| 4.2 | `authority.py` | full action × role × amount matrix; `recommender != approver` |
| 4.3 | PII registry + tokenisation | round-trip holds; a token matches no PII pattern; every PII column registered |

## E5 · Tools

| # | Story | Acceptance |
|---|---|---|
| 5.1 | `Tool` protocol + registry | schema declared; which agent may use which tool |
| 5.2–5.5 | Four tools to start: payment behaviour, bureau history, institution profile, similar alerts | each passes the five contract tests, including scope |
| 5.6 | Policy retrieval | pgvector index; a query returns clauses with citable ids |

## E6 · Agents

| # | Story | Acceptance |
|---|---|---|
| 6.1 | `FakeChatModel` + `ChatModel` interface | responses returned in order; invalid JSON → failure result |
| 6.2 | Egress guard | fails closed; no module outside `guard/` imports a model client (architecture test) |
| 6.3 | State + graph skeleton | a case flows through and checkpoints |
| 6.4 | Supervisor | selects the expected investigators per case type, and records why |
| 6.5 | Two investigators (repayment, context) | findings carry evidence; an evidence-free finding is rejected |
| 6.6 | Arbitration | contradiction detected; arbitration node runs and records reasoning |
| 6.7 | Compose + citations | an uncited recommendation is withheld |
| 6.8 | Budget and cycle guards | budget exceeded → escalate with partial findings; same investigator + same input hash refused |

## E7 · Surface

| # | Story | Acceptance |
|---|---|---|
| 7.1 | Case service | open / join / snooze / close, going through `apply_event` |
| 7.2 | API + auth | the role × endpoint × scope matrix, each 403 asserted |
| 7.3 | Streamlit dashboard | portfolio, queue, case detail, cohort; imports nothing from `src` |
| 7.4 | Case-scoped chat | every action writes an auditable event |

## E8 · Evaluation

| # | Story | Acceptance |
|---|---|---|
| 8.1 | Layer 1 structural checks | run in CI, gate the build |
| 8.2 | Two-arm harness | rules-only vs rules+agents on the same book |
| 8.3 | Second seeded book | different seed, held out — the agents were never tuned on it |
| 8.4 | The number | lead time, precision, analyst-hours, on the holdout book |

## E9 · Operations

| # | Story | Acceptance |
|---|---|---|
| 9.1 | Langfuse tracing | one trace per case, showing every node and tool call |
| 9.2 | Cost per case | recorded per run, visible on the dashboard |
| 9.3 | Docker compose | one command brings up the whole system |
| 9.4 | CI pipeline | tests, mypy, ruff, architecture tests, Layer 1 eval |

---

## The three rules that make this work

**1 · Agree the interface before writing the body.** §A is the agreement. Two people can build either side of a contract and meet at the type.

**2 · Machines enforce the rules, not memory.** The dependency rule is an architecture test. The one-open-case rule is a database constraint. The authorisation rule is a CI gate. Anything relying on people remembering will erode.

**3 · A story is finished when its acceptance criteria pass in CI.** Not when it runs locally, not when it looks right.
