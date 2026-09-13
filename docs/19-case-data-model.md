# 19 — Case Data Model

The second half of the schema, deferred in `05-portfolio-data-model.md` until the agentic design existed.

`05` covers the **book** — loans, parties, repayment, history, signals. This covers the **work** — cases, their history, and the identifiers that tie everything together.

**Every field below traces to a numbered requirement.** If a field has no requirement, it should not exist; if a requirement has no field, the schema is incomplete. That mapping is the point of this document — it is what you read *before* writing code, so the shape is argued on paper rather than discovered in the editor.

---

## 1 · Why a case exists at all

From `01-requirements.md` §9.2:

> *A case is the unit of work, the audit record, the evaluation unit, and the join key from signal → investigation → recommendation → intervention → outcome. Human-readable identifier.*

Four jobs in one sentence, and each one drives fields:

| Job | What it demands |
|---|---|
| **unit of work** | a state, a type, a queue position |
| **audit record** | an append-only history with an actor on every entry |
| **evaluation unit** | a closing outcome — the label a model learns from |
| **join key** | a stable, readable identifier other tables point at |

---

## 2 · The entities

Two tables, and the split is deliberate.

| Table | Holds | Mutability |
|---|---|---|
| **`ews_case`** | the case **as it is now** | updated in place |
| **`case_event`** | **everything that ever happened** to it | append-only, never updated or deleted |

**Why not one table.** The queue needs *"give me every open case"* — fast, current, one row each. The auditor needs *"who closed this, when, and why"* — complete and immutable. A single table cannot be both: a summary row gets overwritten, and an audit trail must never be.

**The consistency rule:** if you ever doubt `ews_case`, replay `case_event` and rebuild it. The summary is a convenience; the log is the truth.

---

## 3 · `ews_case` — field by field

| Field | Type | Null | Requirement it satisfies |
|---|---|---|---|
| `id` | bigserial | no | surrogate key. Also the source of the readable id (§5) |
| `case_id` | text unique | no | §9.2 *"human-readable identifier"* — `EWS-2026-06-00123` |
| `account_id` | text | **yes** | §8 — an account case. Null for a cohort case |
| `institution_id` | text | **yes** | §8 *"cohort cases are separate objects"*. Null for an account case |
| `case_type` | text | no | §8 *"case type set from the triggering signal"* |
| `state` | text | no | the six states in `11-case-state-machine.svg` |
| `outcome` | text | **yes** | §8 *"close — always with an outcome"*. Null until closed |
| `snoozed_until` | date | **yes** | §8 *"snooze — analyst defers with a date"* |
| `closed_at` | date | **yes** | needed to enforce §8 *"reopen permitted only within 14 days"* |
| `opened_at` | date | no | lead-time measurement in `09-evaluation-design.md` |
| `predecessor_case_id` | text | **yes** | §8 *"a new signal creates a NEW case, linked to the previous as predecessor"* |
| `created_at` | timestamptz | no | convention — every table carries one (`05` §8) |

### The three fields that are nullable on purpose

`outcome`, `snoozed_until` and `closed_at` are **empty until something happens**:

| Field | Empty until |
|---|---|
| `outcome` | the case is closed |
| `snoozed_until` | an analyst snoozes it |
| `closed_at` | the case is closed |

A brand-new case has none of them. In the Python shape they are `| None = None`, and they sit **after** the required fields — Python needs to know which arguments are mandatory.

### The two fields that are nullable as an either-or

`account_id` and `institution_id` encode the account/cohort split. Exactly one is set, never both, never neither — enforced by `ck_case_scope` (§6).

**Why not two separate tables.** An analyst's queue mixes both. A shared table means one query, one state machine, one set of events. **The cost is the check constraint; the alternative is duplicating the whole lifecycle.**

### `case_type` is `text`, not an enum

It comes from `signal_type`, and new signal rules get added. A database enum or a Python `Literal` here would mean **a change in `signals.py` forcing a change in `models.py`** — the wrong coupling.

### `predecessor_case_id` exists in the table but not yet in the Python shape

The column is there because adding one later is a migration. The dataclass field is absent because nothing reads it yet.

> **Add a column when you know you'll need it; add a field to the shape when a caller actually needs it.**

---

## 4 · `case_event` — field by field

| Field | Type | Null | Requirement |
|---|---|---|---|
| `id` | bigserial | no | ordering. **Events are read in insertion order** |
| `case_id` | text FK | no | which case this happened to |
| `event_type` | text | no | one of the `EventType` values — the arrows in the state machine |
| `at` | date | no | the business date. **Not** `now()` — see below |
| `signal_type` | text | yes | which rule produced the evidence. Null for human actions |
| `detail` | text | yes | the readable reason. §9.7 *"every assertion traceable to source"* |
| `outcome` | text | yes | set on a close event |
| `snoozed_until` | date | yes | set on a snooze event |
| `actor` | text | no | **who did it.** `"system"` for the batch, a user id for a human |
| `created_at` | timestamptz | no | when the row was written |

### `at` and `created_at` are different things, and mixing them is a classic bug

| | Means | Example |
|---|---|---|
| `at` | the **business date** the event applies to | the batch for 2026-06-01, run on 2026-06-02 |
| `created_at` | when the **row was written** | 2026-06-02 02:14:33 |

A re-run of June's batch in September must record `at = 2026-06-01`. If you used `now()` for both, every backfill would silently rewrite history to today.

**This is why `domain/case_state.py` is forbidden from reading the clock** — the date arrives on the `Event`, from the caller who knows which business day this is.

### `actor` is not optional

Without it the log answers *what happened* but not *who did it* — which is the question an inspector actually asks. The batch writes `"system"`; a human action writes their id.

### No `update` and no `delete`, ever

That is what append-only means in practice. A correction is a **new event**, not an edited one. `05` §8 has the same rule for `signal`.

---

## 5 · The identifier

```
EWS-2026-06-00123
 │    │       │
 │    │       └── zero-padded sequence
 │    └────────── the month the case opened
 └─────────────── system prefix
```

**Two requirements in tension:**

| Requirement | Points to |
|---|---|
| human-readable — spoken on a phone call, quoted in an email | build it in application code |
| globally unique — it is a join key | only the database can guarantee it |

**Resolution: take the number from the database first, then build the string around it.**

```sql
select nextval(pg_get_serial_sequence('ews_case','id'))
```

```python
case_id = f"EWS-{as_of:%Y-%m}-{seq:05d}"
```

Then insert **once**, passing both `id` and `case_id`.

**Why not insert-then-update:** two writes, and a window where the case exists with no readable identifier. Something could read it in between.

**Why the month is in the id:** support calls arrive as *"case EWS-2026-06-something"*. The month narrows the search before you touch the database, and it makes a printed queue sortable by age.

---

## 6 · Constraints — the rules the database enforces

| Constraint | Requirement | Why the database and not code |
|---|---|---|
| `ux_case_one_open_per_account` | §8 *"one open case per account at a time"* | two nightly runs at the same instant both read "no open case", both insert. Application code has that window; a constraint does not |
| `ck_case_closed_outcome` | §8 *"**the outcome is the training label**; a case closed without one is a lost data point"* | you cannot go back six months later and ask the analyst. Too important to depend on an `if` someone might forget |
| `ck_case_scope` | §8 account cases and cohort cases are different objects | a row that is both, or neither, is meaningless |
| `case_event.case_id` FK | an event must belong to a case | an orphan event is unreadable |

### The partial unique index, and why a plain one is wrong

```sql
create unique index ux_case_one_open_per_account
    on ews_case (account_id)
    where state <> 'closed' and account_id is not null;
```

A plain `unique (account_id)` would forbid an account from **ever** having a second case — but §8 says *"after close, a new signal creates a NEW case"*.

**`where state <> 'closed'` puts closed cases outside the index**, so they no longer block. One open case at a time; any number over a lifetime.

### The close constraint reads backwards until you parse it

```sql
check (state <> 'closed' or outcome is not null)
```

*"Unless the state is closed, no constraint. If closed, outcome must exist."*

Any implication `A → B` is written `not A or B` in SQL.

---

## 7 · How a case links to everything else

```
signal.case_id          →  ews_case.case_id     filled by the router
intervention.case_id    →  ews_case.case_id     nullable: historical ones predate cases
case_event.case_id      →  ews_case.case_id     mandatory
ews_case.account_id     →  loan.loan_account_no the account under investigation
ews_case.institution_id →  institution.id       cohort cases only
```

**`ews_case.account_id` holds `loan_account_no`, not `loan.id`.** It is the value an analyst reads and types. The numeric id stays internal to the repository layer.

**Case-to-account is many-to-many in the general case** (§8): an account may sit in both its own case and a cohort case. Today the account case links by `account_id` and the cohort case by `institution_id`, and the link between them is implicit. **When the UI needs "show me every account in this cohort case", a `case_account` link table gets added.** Not before — it has no reader yet.

---

## 8 · What is deliberately not here yet

| Deferred | Why | When |
|---|---|---|
| `case_account` link table | no reader yet | E7, when the cohort view needs it |
| `case_assignee` | no user table, no auth | E4 |
| `case_finding` / `case_recommendation` | the agentic output shapes are not fixed | E6 |
| `batch_run` | `NightlyRun` exists in memory; nothing reads it back yet | E9, with tracing |

**Each of these is a column or table you could add now and nobody would query.** The rule from `05` holds: build the table when something reads it, and only earlier when a migration would be painful (as with `intervention.case_id`, which had to exist on day one because the generator produces historical interventions).

---

## 9 · The mapping, in one table

Everything above, condensed — **this is the thing to read before writing the code.**

| Requirement (`01` §8/§9) | Field or constraint |
|---|---|
| unit of work, audit record, eval unit, join key | the two-table split |
| human-readable identifier | `case_id`, built from the sequence |
| one open case per account | `ux_case_one_open_per_account` |
| case type set from the triggering signal | `case_type` |
| a more severe signal escalates the case | `case_type` is updated, an event records why |
| cohort cases are separate objects | `institution_id` + `ck_case_scope` |
| snooze with a date and a reason | `snoozed_until` + a `snoozed` event carrying `detail` |
| close always with an outcome | `outcome` + `ck_case_closed_outcome` |
| the outcome is the training label | the constraint, not application code |
| reopen only within 14 days | `closed_at` + a guard in `domain/case_state.py` |
| a new case links to its predecessor | `predecessor_case_id` |
| every assertion traceable to source | `case_event.detail` + `signal_type` |
| auditable — who did what | `case_event.actor` |
| lead time measurement | `opened_at` vs the signal's `as_of` |
