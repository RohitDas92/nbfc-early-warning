# 18 — Build Reference

**How each module actually got written.**

Every section follows the same four beats:

1. **The ticket** — what lands in your queue: the story, the acceptance criteria, the contract the tech lead wrote
2. **Reading it** — what an engineer notices, and the questions they ask before typing anything
3. **Writing it** — question by question, each one producing specific lines
4. **Concepts** — the Python and DSA ideas used, and what was rejected

The point is the **middle two**. Anyone can read finished code; the skill is getting from a ticket to it.

---

## The method — how to read any ticket

An engineer reads a contract in a fixed order, and each field answers a different question:

| Read this | To learn |
|---|---|
| **Interface** *first* | what to type. The `def` line, the types, the return |
| **Purpose** | the docstring, and whether this is one job or two |
| **Invariants** | the `if` statements inside, and the asserts in the tests |
| **Forbidden** | the imports you must **not** write |
| **Tests / acceptance** | the test file — often written first |

**Then four questions, in this order:**

1. **What does it hand back?** — if that type doesn't exist yet, that's line one
2. **What does it take in?** — type the `def` line and stop
3. **What's the easiest case?** — write that branch first; it shortens everything below
4. **What's the hard case actually asking?** — this is where the real design decision hides

**Step 4 is the job.** Steps 1–3 are transcription.

---

## The pipeline you are building

```
Postgres (2.1M rows)
    │  db/repositories/accounts.py      7 queries, one per fact group
    ▼
AccountFacts × 9,951
    │  domain/signals.py                11 rules + 1 cohort rule
    ▼
Signal × 3,651
    │  domain/routing.py + engine/route.py     suppression
    ▼
CaseAction × 3,651                      2,161 open · 1,175 join · 315 escalate
    │  db/repositories/cases.py
    ▼
ews_case 2,161 · case_event 7,302
```

**Arrows point one way only.** `domain/` imports nothing of ours. `db/` imports `domain`. `engine/` imports both.

---
---

# Part 1 · `domain/` — pure logic

No database, no clock, no randomness, no model. Need "now"? It's passed in as an argument.

**Why the rule exists:** 71 of your 77 tests run in 0.15 seconds because nothing here touches infrastructure.

---

## 1.1 · `domain/models.py`

### 📋 The ticket

**Story E1.0 — Case data shapes**
*Depends on: nothing. This is the bottom of the import graph.*

**Acceptance criteria**

1. `CaseState` lists exactly the six states in `docs/11-case-state-machine.svg`
2. `CloseOutcome` lists exactly the four outcomes in `01-requirements.md` §8
3. `EventType` covers every arrow in the state machine diagram
4. `Case` and `Event` are `frozen=True` — assignment after creation raises
5. Every optional field defaults to `None`
6. No method on either class does any work

**Contract**

| | |
|---|---|
| Purpose | the shared data shapes for case handling |
| Interface | `CaseState`, `CloseOutcome`, `EventType` (Literals) · `Case`, `Event` (frozen dataclasses) |
| Invariants | every dataclass is `frozen=True` · optional fields default to `None` |
| Forbidden | any method that does work. These are data, not behaviour |
| Tests | none of its own — exercised through `case_state.py` |

### 🔍 Reading it

**First thing noticed: this is a tiny ticket with an expensive mistake attached.** "Depends on: nothing" means *everything* depends on it. Get a state name wrong here and you rename it in six files later.

**Second: criteria 1–3 don't describe code, they describe a *source*.** "exactly the six states in the SVG". So the first action isn't typing — it's **opening the diagram and the requirements doc** and listing what's there.

**Third: "Forbidden — any method that does work" tells you the class body has no `def` in it.** That single line settles the entire shape.

**Questions before typing:**

- *Literal or Enum?* Both express "one of these values". Enum gives you `CaseState.OPEN` and real runtime checking; Literal gives you plain strings that go straight into a database column with no conversion. **Every one of these values ends up as a `text` column.** Literal wins — no `.value` at every boundary.
- *Class or dataclass?* A plain class means hand-writing `__init__`, `__repr__` and `__eq__`. Dataclass writes all three. No contest.
- *frozen or not?* The contract says frozen. But *why* — that's the interesting part, answered below.

### ⌨️ Writing it

**Step 1 — the vocabularies, read off the design docs.**

```python
from typing import Literal

CaseState = Literal["open", "investigating", "awaiting_review",
                    "snoozed", "escalated", "closed"]

CloseOutcome = Literal["resolved_benign", "intervened",
                       "escalated", "no_action_authorised"]

EventType = Literal["signal_joined", "investigation_started",
                    "investigation_completed", "investigation_failed",
                    "escalation_required", "snoozed", "snooze_expired",
                    "closed", "reopened"]
```

Six, four, nine — counted against the diagram, not invented.

**Step 2 — the case.**

```python
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Case:
    case_id: str
    state: CaseState
    case_type: str
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None
    closed_at: date | None = None
```

*Order matters:* fields **with** defaults must come after fields **without**. Python needs to know which arguments are required.

*Why `case_type: str` and not a Literal:* case type comes from `signal_type`, and new signal rules get added. A Literal here would need editing every time a rule is added — a change in `signals.py` forcing a change in `models.py` is the wrong coupling.

**Step 3 — the event.**

```python
@dataclass(frozen=True)
class Event:
    type: EventType
    at: date
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None
```

*Why `Event` carries `outcome` and `snoozed_until`:* a close event must say **why**, a snooze must say **until when**. Most events carry neither, hence the `None` defaults.

### 🧠 Concepts

**`@dataclass`** — writes `__init__`, `__repr__`, `__eq__`. Twenty lines of boilerplate you don't type.

**`frozen=True`** — the object cannot change after creation. `case.state = "closed"` raises.

*Why that matters here:* the state machine hands `Case` objects around. If any function could mutate one, a bug in module A would corrupt data module B is holding, and you'd debug it in B. **Frozen turns a whole class of bug into an immediate exception at the line that caused it.**

*The cost:* you can't edit, only copy-with-changes (`dataclasses.replace`). That's the trade, and it's worth it.

**`| None = None`** — may hold a value *or* nothing, defaults to nothing. Read it as "optional".

**`Literal`** — the only legal values are these exact strings. **Invisible at runtime** — it's only checked if you run `mypy`. That gap caused two real bugs in this project (1.3 and 1.5), both fixed the same way: a test that reads the Literal back with `get_args()`.

**No DSA here.** This file is vocabulary, not algorithm.

---

## 1.2 · `domain/classification.py`

### 📋 The ticket

**Story E1.1 — DPD classification**

**Acceptance criteria**

1. The boundary table passes for both functions: 0, 1, 30, 31, 60, 61, 90, 91
2. A negative DPD raises `ValueError`
3. The bucket boundaries exist in exactly one place in the codebase

**Contract**

| | |
|---|---|
| Purpose | days-past-due → delinquency bucket → IRACP asset class |
| Interface | `bucket_of(dpd: int) -> Bucket` · `asset_class_of(dpd: int) -> AssetClass` |
| Invariants | total over `dpd >= 0` · boundaries live in one place |
| Forbidden | returning a default for unknown input |
| Tests | the boundary table, plus negative-raises |

### 🔍 Reading it

**Criterion 1 is the whole ticket.** Those eight numbers aren't examples — they're the *boundaries themselves*, chosen in pairs: 30 and 31, 60 and 61, 90 and 91. An off-by-one at a bucket edge has regulatory consequences.

**"Forbidden: returning a default for unknown input" is a warning about a specific temptation.** The obvious shape is:

```python
if dpd <= 0: return "0"
elif dpd <= 30: return "1-30"
...
else: return "NPA"
```

That final `else` catches *anything* — including a bug that passed a string. A healthy loan silently classified NPA. **The Forbidden line exists because someone has made that mistake before.**

**Criterion 3 — "one place" — is about the future.** `signals.py` will also care about 30 vs 31. If it hardcodes the number, the two drift the day RBI moves a threshold.

**The question before typing:** *what data structure holds these boundaries?*

### ⌨️ Writing it

**Step 1 — the two vocabularies.**

```python
from typing import Literal

Bucket = Literal["0", "1-30", "31-60", "61-90", "90+"]
AssetClass = Literal["standard", "SMA0", "SMA1", "SMA2", "NPA"]
```

**Step 2 — the design decision: two structures, not one.**

Notice there are **two different kinds of mapping** here:

| Mapping | Kind |
|---|---|
| `dpd → bucket` | a **range** — "anything from 1 to 30" |
| `bucket → asset_class` | an **exact lookup** — one key, one value |

A dict cannot express a range. A list scan is wasteful for an exact lookup. **So you use one of each.**

```python
_BUCKETS: list[tuple[int, Bucket]] = [
    (0, "0"), (30, "1-30"), (60, "31-60"), (90, "61-90"),
]

_BUCKET_TO_CLASS: dict[Bucket, AssetClass] = {
    "0": "standard", "1-30": "SMA0", "31-60": "SMA1",
    "61-90": "SMA2", "90+": "NPA",
}
```

*Each `_BUCKETS` entry is (upper bound, name).* Walk it in order, return the first bucket whose upper bound you don't exceed.

*The leading underscore* means "internal to this module" — a convention, not enforced.

**Step 3 — the range function, guard first.**

```python
def bucket_of(dpd: int) -> Bucket:
    """Map days-past-due to a delinquency bucket."""
    if dpd < 0:
        raise ValueError(f"dpd cannot be negative: {dpd}")

    for upper, name in _BUCKETS:
        if dpd <= upper:
            return name

    return "90+"
```

*The guard satisfies criterion 2.* A negative DPD is impossible; failing loudly beats hiding a data bug.

*`return "90+"` after the loop is not a catch-all default* — it's the deliberate open-ended top bucket. The difference from the forbidden `else`: this line is only reached by a number larger than 90, because the guard already rejected everything else.

**Step 4 — the exact lookup, built on step 3.**

```python
def asset_class_of(dpd: int) -> AssetClass:
    """Map days-past-due to an IRACP asset class."""
    return _BUCKET_TO_CLASS[bucket_of(dpd)]
```

*One line, and it satisfies criterion 3.* `asset_class_of` doesn't know any boundaries — it asks `bucket_of`. One source of truth.

### 🧠 Concepts

**Dict lookup — O(1).** Hashes the key, jumps straight to the value. No scanning, regardless of size.

**List scan — O(k).** Walks at most 4 entries here. Fine because k is tiny and fixed. With 10,000 ranges you'd use `bisect` for O(log k).

> **The rule worth memorising: exact match → dict; range match → ordered list.**

You will make this exact decision again in `routing.py` (1.5) and it'll take ten seconds the second time.

**`raise` vs return a default.** A default hides bad input; a raise surfaces it at the line that caused it. The heuristic: *if the input is impossible, raise. If it's merely absent, return None.*

**`Literal` as a return type** — `-> Bucket` promises one of five strings. mypy checks every `return` against it.

**Bug caught in review:** the first version was an `if/elif` chain that fell through to `"NPA"` — the silent-wrong-answer shape the Forbidden line warned about.

---

## 1.3 · `domain/case_state.py`

### 📋 The ticket

**Story E1.2 — Case state machine**
*Depends on: E1.0 (models)*

**Acceptance criteria**

1. Every legal transition in `docs/11-case-state-machine.svg` works
2. **Every illegal combination raises `InvalidTransition`**
3. A close without an outcome raises
4. A close records `outcome` and `closed_at`
5. A reopen clears `outcome` and `closed_at`
6. The input `Case` is never modified

**Contract**

| | |
|---|---|
| Purpose | the only place a case changes state |
| Interface | `apply_event(case: Case, event: Event) -> Case` · raises `InvalidTransition` |
| Invariants | returns a **new** Case · input never modified · illegal always raises · a close always records outcome and closed_at |
| Forbidden | writing to the database · reading the clock · silently allowing an unlisted transition |
| Tests | the legal table, the illegal table, the guards, the table-validity test |

### 🔍 Reading it

**Criterion 2 is in bold for a reason.** Most engineers test that the happy paths work. This ticket says the *illegal* moves matter more — because an illegal transition that silently succeeds corrupts a case and nobody notices for weeks.

**"Forbidden: reading the clock"** — so the close date can't be `date.today()`. It has to come in on the `Event`. That's already decided by `models.py` having `Event.at`.

**Interface returns `Case`, and the input is a `Case`.** Combined with invariant "input never modified", that means: **copy, don't edit**. And `Case` is frozen, so you couldn't edit it anyway — `frozen=True` and this invariant are the same decision seen from two sides.

**Questions before typing:**

- *How do I represent "which moves are legal"?* — the central design decision
- *Where do conditions like "close needs an outcome" live?* — in the table or in code?
- *How do I make a new Case from an old one?*

### ⌨️ Writing it

**Step 1 — the error type.**

```python
class InvalidTransition(Exception):
    """Raised when an event is not legal for a case's current state."""
```

*Why a custom exception and not `ValueError`:* callers need to catch **this** failure specifically — an API turning it into a 409, a batch skipping the case. `except ValueError` would also catch a date parsing bug.

**Step 2 — the design decision: how to represent legal moves.**

Options an engineer weighs:

| Option | Verdict |
|---|---|
| `if/elif` chain | ~40 lines, unreviewable, and a compliance officer can't read it |
| Nested dict `{state: {event: new_state}}` | works, but two lookups and clumsier to iterate for the test |
| **Dict keyed by a `(state, event)` tuple** | one O(1) lookup, prints as a flat table, trivial to iterate |

**The winning argument isn't performance — it's that the table can be *printed and reviewed*.** This is a regulated domain; "show me the legal state transitions" is a real question you will be asked.

```python
_TRANSITIONS: dict[tuple[CaseState, EventType], CaseState] = {
    ("open", "investigation_started"): "investigating",
    ("investigating", "investigation_completed"): "awaiting_review",
    ("investigating", "investigation_failed"): "escalated",
    ("investigating", "escalation_required"): "escalated",
    ("awaiting_review", "escalation_required"): "escalated",
    ("awaiting_review", "snoozed"): "snoozed",
    ("awaiting_review", "closed"): "closed",
    ("escalated", "closed"): "closed",
    ("snoozed", "snooze_expired"): "awaiting_review",
    ("closed", "reopened"): "awaiting_review",
    ("open", "signal_joined"): "open",
    ("investigating", "signal_joined"): "investigating",
    ("awaiting_review", "signal_joined"): "awaiting_review",
    ("snoozed", "signal_joined"): "snoozed",
}
```

*Fourteen rows, read off the diagram arrow by arrow.*

*The last four are self-transitions* — a signal joining doesn't move the case, but the move must still be **listed as legal**, or criterion 2 turns every join into a raise.

**Step 3 — lookup and the illegal case.**

```python
def apply_event(case: Case, event: Event) -> Case:
    """Return a new Case with the event applied. Raises if the move is illegal."""
    key = (case.state, event.type)

    if key not in _TRANSITIONS:
        raise InvalidTransition(f"{event.type} is not allowed for {case.state}")

    new_state = _TRANSITIONS[key]
```

*Criterion 2 satisfied by construction:* anything not in the table raises. You don't enumerate illegal moves — **absence from the table is the definition of illegal.**

*The message includes both values.* "Invalid transition" tells a 2am on-call engineer nothing; "`snoozed` is not allowed for `open`" tells them exactly what broke.

**Step 4 — the second design decision: where do conditions go?**

Criterion 3 says a close needs an outcome. **Can the table express that?**

No. A dict key is `(state, event)` — there's nowhere to put "…but only if `event.outcome` is set". So:

> **The table answers *does this move exist*. Code answers *is it allowed right now*.**

```python
    if event.type == "closed" and event.outcome is None:
        raise InvalidTransition("closing a case requires an outcome")
```

*Use `is None`, not `== None`.* `is` asks "is it literally this one object" — which is what you mean, and it can't be fooled by a class with a strange `__eq__`.

**Step 5 — the third decision: building the new Case.**

Criteria 4 and 5 say different events change different fields:

| Event | Fields to write |
|---|---|
| closed | state, outcome, closed_at |
| snoozed | state, snoozed_until |
| reopened | state, outcome=None, closed_at=None |
| anything else | state only |

**So no single fixed `replace(...)` call works.** Four branches each with their own `replace` would mean four exits and four copies of `state=new_state`.

**The fix: separate *deciding* from *doing*.** Build a dict of what changes, call `replace` once.

```python
    changes = {"state": new_state}

    if event.type == "closed":
        changes["outcome"] = event.outcome
        changes["closed_at"] = event.at
    elif event.type == "snoozed":
        changes["snoozed_until"] = event.snoozed_until
    elif event.type == "reopened":
        changes["outcome"] = None
        changes["closed_at"] = None

    return replace(case, **changes)
```

*Why this works:* **`replace` only changes the fields you name.** Anything left out is copied unchanged. So a snooze never has to think about `outcome` — it simply isn't in the dict.

*Why `reopened` clears explicitly:* a reopened case is live again. Leaving a closure outcome on it would make "closed cases by outcome" silently count a case that is currently open. **That's a business decision, and it gets its own visible branch.**

### 🧠 Concepts

**Tuple as a dict key — O(1).** `(state, event)` hashes as a single unit. Nested dicts would be two lookups; a list of rules would be O(n) per call.

**Why a tuple and not a list:** dict keys must be **hashable**, i.e. immutable. `{[a, b]: c}` raises `TypeError`. Tuples are immutable; lists aren't.

**`dataclasses.replace(obj, **changes)`** — copy with overrides. The only way to "change" a frozen object.

**`**` unpacking** — a dict becomes keyword arguments:

```python
replace(case, **{"state": "closed", "outcome": "recovered"})
    ≡  replace(case, state="closed", outcome="recovered")
```

*Two stars for a dict into keyword args; one star for a list into positional args.* Python matches the **dict keys against the parameter names** — so a typo'd key gives `unexpected keyword argument`.

**Build-then-apply.** The `changes` dict is a *shopping list*; `replace` is the shopping. Deciding and doing separated. **You will see this shape three more times** — in `route_signals`, in `run_nightly`, and in every agent that recommends rather than acts.

### 🐛 Bugs caught, and what each taught

| Bug | Lesson |
|---|---|
| `"investigatigation_started"` in the table | a misspelled string is a **valid dict key**. The row looks present but can never match. `Literal` does **not** catch this at runtime |
| `event.outcome or None` | `x or None` is identical to `x`. A no-op that looks like a decision |
| SonarQube warning on `replace` | a linter warning is a **hypothesis, not a verdict**. Confirm with a second tool before silencing; never add a `cast` to quiet a false positive |

### 🛡 The guard test — and how you'd think of writing it

After the typo, the engineer asks: *what class of bug is this, and how do I make it impossible?*

The class is: **a hand-maintained table whose keys must match a Literal, with nothing checking that they do.**

The fix needs the Literal's values **at runtime** — and `typing.get_args()` does exactly that.

```python
VALID_STATES = set(get_args(CaseState))
VALID_EVENTS = set(get_args(EventType))


def test_transition_table_uses_only_valid_names():
    bad = []
    for (state, event), new_state in _TRANSITIONS.items():
        if state not in VALID_STATES:
            bad.append(f"bad from-state: {state!r}")
        if event not in VALID_EVENTS:
            bad.append(f"bad event: {event!r}")
        if new_state not in VALID_STATES:
            bad.append(f"bad to-state: {new_state!r}")

    assert not bad, "\n".join(bad)
```

**`get_args()` is the bridge** between "type hint" and "runtime data". Without it, a `Literal` is a comment.

**Collect failures, assert once.** An `assert` inside the loop stops at the first problem; a list reports all of them in one run. Same reason a compiler shows twelve errors instead of making you rebuild twelve times.

**`!r`** prints the repr — `'investigatigation_started'` with quotes, so a stray space or empty string is visible.

**Set membership is O(1).** `state not in VALID_STATES` on a set. On a list it'd be O(n) per check.

---

## 1.4 · `domain/signals.py`

### 📋 The ticket

**Story E1.3 — Signal rules**
*Depends on: E1.1 (classification)*

**Acceptance criteria**

1. Eleven account rules from `01-requirements.md` §7, each matching its stated threshold
2. Each rule has a **fires** test and a **does-not-fire** test, at the threshold and just under
3. A clean account produces `[]`
4. Every rule emits a distinct `signal_type`
5. The cohort rule fires on institutions well above the portfolio's flag rate

**Contract**

| | |
|---|---|
| Purpose | the detection rules |
| Interface | `AccountFacts` (in) · `Signal`, `CohortSignal` (out) · `evaluate(facts) -> list[Signal]` · `check_institution_cohort(flagged, all_accounts) -> list[CohortSignal]` |
| Invariants | one rule owns one concern · unique `signal_type` per rule · a clean account produces `[]` · every Signal carries a readable `detail` |
| Forbidden | reading the database · reading the clock · two rules firing on the same fact |
| Tests | fires/does-not-fire per rule, plus the distinct-type guard |

### 🔍 Reading it

**This is the biggest ticket so far, and the first question is how to break it up.** Eleven rules — do you write one function with eleven branches, or eleven functions?

**"One rule owns one concern"** in the invariants answers it: eleven functions. A branch inside a function can't be tested or disabled independently.

**"Forbidden: reading the database"** is the load-bearing constraint. The rules need DPD, bounces, bureau scores — all of which live in Postgres. **So something else must fetch them and hand them over.** That's what forces `AccountFacts` to exist: it's the shape of "everything a rule might need, already fetched".

**Criterion 3 — "a clean account produces `[]`" — is the anti-noise requirement.** The whole project exists because analysts drown in alerts. A rule engine that fires on healthy accounts is the disease, not the cure.

**Criterion 4 is odd until you think about it.** Why would two rules emit the same type? Because you build rule 7 by copy-pasting rule 6 and forget to change one string. It's a copy-paste-bug guard.

**Questions before typing:**

- *What shape do the inputs take?* — one object per account, or loose arguments?
- *What does a rule return when it doesn't fire?*
- *How do I run all eleven without an eleven-line function?*
- *The cohort rule takes a different input and produces a different output — same type or new one?*

### ⌨️ Writing it

**Step 1 — the input shape.**

Eleven rules, each needing different facts. Options:

| Option | Verdict |
|---|---|
| Each rule takes what it needs: `check_bounce(bounces, retries)` | the caller now has to know what each rule wants. Eleven different call signatures |
| **One object carrying everything** | one call signature, `evaluate` can loop |

```python
@dataclass(frozen=True)
class AccountFacts:
    account_id: str
    dpd: int
    dpd_last_month: int
    bounces_last_3m: int = 0
    retries_on_last_bounce: int = 0
    days_to_moratorium_end: int | None = None
    payment_days_last_3m: tuple[int, ...] = ()
    paid_ratio_last_3m: tuple[float, ...] = ()
    in_moratorium: bool = False
    months_interest_unserviced: int = 0
    bureau_score_now: int | None = None
    bureau_score_prev: int | None = None
    new_enquiries_60d: int = 0
    days_past_expected_tranche: int | None = None
    failed_contacts_60d: int = 0
    adverse_event: str | None = None
    institution_id: str | None = None
```

**Only the first three are required.** Everything else has a default — and that decision is what let the repository be built **one fact group at a time**, over two days, with nothing breaking in between. A ticket that said "all fields required" would have forced all seven queries to be written before a single rule could run.

*`tuple[int, ...]`* — the `...` means "any number of these". An early draft said `tuple[int, int, int]` (exactly three) while defaulting to `()` (zero) — a contradiction.

*Tuples not lists,* because `AccountFacts` is frozen and a list inside a frozen object can still be mutated from outside.

**Step 2 — the output shape.**

```python
@dataclass(frozen=True)
class Signal:
    account_id: str
    signal_type: str
    detail: str
```

*`detail` exists because of the invariant "every Signal carries a readable detail".* An analyst opening the case must see **why** without re-running anything.

**Step 3 — the first rule, and a decision about what "no signal" means.**

A rule either fires or doesn't. Options: return `None`, return an empty list, raise. **`None` is the obvious one** — and it makes the return type `Signal | None`, which mypy will then police.

```python
def check_dpd_bucket_movement(facts: AccountFacts) -> Signal | None:
    """Fires when an account moves into a different delinquency bucket."""
    before = bucket_of(facts.dpd_last_month)
    now = bucket_of(facts.dpd)

    if now != before:
        return Signal(
            account_id=facts.account_id,
            signal_type="dpd_bucket_movement",
            detail=f"DPD {facts.dpd_last_month} to {facts.dpd} ({before} to {now})",
        )
    return None
```

**The first draft compared to the literal `30`.** Then: *"30 is still SMA0 — the movement happens at 31."*

The fix isn't to change 30 to 31. **It's to stop hardcoding a number that already lives in `classification.py`.** Calling `bucket_of` means the boundary is owned by one module. Two copies of a threshold will drift the day RBI moves one.

**Step 4 — a two-condition rule, and why you name conditions.**

```python
def check_bounce_pattern(facts: AccountFacts) -> Signal | None:
    """Fires on repeat bounces, or one bounce that needed multiple retries."""
    repeat = facts.bounces_last_3m >= 2
    struggling = facts.bounces_last_3m >= 1 and facts.retries_on_last_bounce >= 2

    if repeat or struggling:
        return Signal(...)
    return None
```

The one-liner is correct and unreadable:

```python
if facts.bounces_last_3m >= 2 or (facts.bounces_last_3m >= 1 and facts.retries_on_last_bounce >= 2):
```

**`repeat` and `struggling` name the two business conditions**, so the `if` reads like the policy document. That matters when a credit head reviews the rule.

**Step 5 — a rule with absent data, and the sign trap.**

```python
def check_moratorium_ending(facts: AccountFacts) -> Signal | None:
    """Fires 75 days before a moratorium ends, so outreach can start."""
    if facts.days_to_moratorium_end is None:
        return None

    if 0 <= facts.days_to_moratorium_end <= 75:
        return Signal(...)
    return None
```

**Guard clause first** — deal with "not in moratorium at all" up front, so the rest can assume a real number.

**`0 <= x <= 75`, not `x <= 75`.** The first version **fired 7,000 times on a 9,939-account book**, because a loan whose moratorium ended two years ago has `days = -730`, and `-730 <= 75` is true.

> **A one-sided threshold on a signed number is a trap.** `<= 75` looks like "within 75 days" but means "within 75 days, or any time in the past".

**Step 6 — running all eleven without an eleven-branch function.**

The naive version:

```python
def evaluate(facts):
    out = []
    s = check_dpd_bucket_movement(facts)
    if s: out.append(s)
    s = check_bounce_pattern(facts)
    if s: out.append(s)
    ...    # nine more times
```

Adding rule 12 means editing `evaluate`. **The fix: in Python a function is a value.** Put them in a list and loop.

```python
_RULES = [
    check_dpd_bucket_movement,
    check_bounce_pattern,
    check_moratorium_ending,
    check_payment_date_drift,
    check_part_payment,
    check_drift_with_bounce,
    check_interest_not_serviced,
    check_bureau_deterioration,
    check_tranche_not_requested,
    check_contactability_decay,
    check_adverse_event,
]


def evaluate(facts: AccountFacts) -> list[Signal]:
    """Run every rule over one account and return the signals that fired."""
    fired = []
    for rule in _RULES:
        signal = rule(facts)
        if signal is not None:
            fired.append(signal)
    return fired
```

**Adding rule 12 is now one line in `_RULES`.** `evaluate` never changes again.

**Step 7 — the cohort rule: a different question needs a different shape.**

Every rule so far looked at **one account**. This one asks *are many accounts from one institution being flagged?* — which cannot be answered from a single `AccountFacts`.

**So it needs a different input and a different output.**

```python
@dataclass(frozen=True)
class CohortSignal:
    institution_id: str
    signal_type: str
    detail: str
```

*Why not reuse `Signal`:* it requires `account_id`. A cohort signal isn't about one account — you'd leave the field blank, and **a blank required field is a lie in your data.** Different unit of work, different type.

**First version, and why it was wrong:**

```python
if n >= 5:      # five flagged accounts from one institution
```

It fired **185 times**. The reason:

| | flagged | total | rate | should fire? |
|---|---|---|---|---|
| Institution A | 8 | 400 | 2% | no |
| Institution B | 8 | 12 | 67% | yes |

**A flat count can't tell them apart.** 5 of 400 means nothing; 5 of 12 means everything.

> **A count with no denominator is not a signal.**

The fix needs the institution's *total* accounts — which the function doesn't have. **So the signature changes.**

```python
def check_institution_cohort(
    flagged: list[AccountFacts],
    all_accounts: list[AccountFacts],
) -> list[CohortSignal]:
    """Fires when an institution's flag rate is well above the portfolio's."""
    flagged_counts = Counter(f.institution_id for f in flagged if f.institution_id)
    total_counts = Counter(f.institution_id for f in all_accounts if f.institution_id)

    base_rate = len(flagged) / len(all_accounts) if all_accounts else 0

    out = []
    for institution_id, n in flagged_counts.items():
        total = total_counts[institution_id]
        rate = n / total

        if n >= 5 and rate >= 2 * base_rate:
            out.append(CohortSignal(
                institution_id=institution_id,
                signal_type="institution_event",
                detail=f"{n} of {total} flagged ({rate:.0%} vs portfolio {base_rate:.0%})",
            ))
    return out
```

**185 false positives → 4 true ones.** And those four were institutions 103, 142, 172 and 238 — exactly the ones seeded with problems in the generator. **Nothing in the code knew which they were.**

### 🧠 Concepts

**Functions as values.** `_RULES` is a list of functions; `rule(facts)` calls whichever the loop is on. This is what makes the rule set data rather than code.

**`Counter`** — counts occurrences in **O(N)**, one pass. `Counter(["A","B","A"])` → `{"A": 2, "B": 1}`.

**Generator expression** — `(f.institution_id for f in flagged)` produces values one at a time. **O(1) extra memory** instead of building an intermediate list.

**Dict lookup inside the loop — O(1).** `total_counts[institution_id]` is instant. The naive alternative:

```python
total = len([f for f in all_accounts if f.institution_id == institution_id])
```

rescans all 9,939 accounts **per institution**: O(I × N) ≈ 2.5 million steps vs 10,000. **250× slower for the same answer.**

**O(N) is the floor here.** You must examine every account at least once to count it. Knowing you're already optimal is a stronger interview answer than any micro-optimisation.

**Negative indexing** — `ratios[-2:]` takes the last two with no length arithmetic.

**`all(...)` short-circuits** — stops at the first `False`.

**Chained comparison** — `days[0] < days[1] < days[2]` reads as maths and is what the drift rule needs.

**Set for uniqueness** — `len(types) == len(set(types))` checks duplicates in O(N); comparing every pair is O(N²).

### 🐛 Four bugs, all found against the real book

| Symptom | Cause | Fix |
|---|---|---|
| `moratorium_ending` fired 7,000× | `days <= 75` true for negatives | `0 <= days <= 75` |
| `part_payment` fired 2,027× | moratorium accounts pay interest only, so paid ÷ EMI ≈ 0.35 | skip the rule during moratorium |
| `bureau_deterioration` fired every month | bureau data is **quarterly**; the same comparison re-reported in April, May, June | read only a snapshot from the last month. **A signal from periodic data fires on the refresh, not on every batch run** |
| `institution_event` fired 185× | a count with no denominator | compare against the portfolio rate |

**Every one was found by looking at counts against real data, not by reading code.**

> **Verify each layer against real data before building the next.**

---

## 1.5 · `domain/routing.py`

### 📋 The ticket

**Story E1.4 — Routing decision**
*Depends on: E1.3 (signal types exist)*

**Acceptance criteria**

1. No open case → `"open"`
2. Less severe signal on an existing case → `"join"`
3. **Equal severity → `"join"`**, never `"escalate"`
4. More severe → `"escalate"`

**Contract**

| | |
|---|---|
| Purpose | decide what a signal does to an account's open case |
| Interface | `route(signal_type: str, open_case_type: str \| None) -> RouteDecision` |
| Invariants | `None` → open · strictly greater → escalate · **equal → join** |
| Forbidden | knowing what a `Case` or a `Signal` is. It takes two strings |
| Tests | the four-row decision table, equal-severity explicitly asserted |

### 🔍 Reading it

**The Interface line is unusually specific: two strings, not objects.** That's deliberate and worth pausing on. The obvious signature would be `route(signal: Signal, case: Case)`. The contract says no.

*Why:* a function taking two strings can be tested in one line, has no imports, and can never accidentally read a field it shouldn't. **The narrowest input that does the job.**

**Criterion 3 is in bold and looks pedantic.** It isn't. If equal severity escalated, a case would re-escalate **every single month** on the same signal type and never leave the queue. That's the alert fatigue this whole project exists to remove, reintroduced by one `>=` instead of `>`.

**The only real question:** *how do you compare "worse than" between two strings?*

### ⌨️ Writing it

**Step 1 — what does it hand back?**

`RouteDecision` doesn't exist. **You can't write a function returning a type you haven't defined**, so that's line one.

```python
from typing import Literal

RouteDecision = Literal["open", "join", "escalate"]
```

*Three strings, never carrying data, typo-catchable.* Same reasoning as `CaseState`.

**Step 2 — the signature and the easy branch.**

```python
def route(signal_type: str, open_case_type: str | None) -> RouteDecision:
    """Decide what to do with a signal, given the account's open case (if any)."""
    if open_case_type is None:
        return "open"
```

**Write the easy case first.** It's criterion 1, it's one line, and it gets a whole branch out of the way.

**Step 3 — the design decision.**

Now the hard part. Criterion 4 needs "more severe than" — and Python has no idea:

```python
"bounce_pattern" > "moratorium_ending"    # alphabetical nonsense
```

**You need to turn each type into something comparable.** Options:

| Option | Complexity | Verdict |
|---|---|---|
| A list, compare `.index()` | **O(n)** per lookup, twice per signal × 3,651 | no |
| An `Enum` with integer values | O(1), but every signal type is a plain string from a database column — you'd convert at every boundary | no |
| **A dict of ranks** | **O(1)**, reads as a table, one place to change the ordering | yes |

**This is the same *exact-lookup → dict* decision as `_BUCKET_TO_CLASS`.** Second time you meet it, it takes ten seconds.

```python
_SEVERITY: dict[str, int] = {
    "moratorium_ending": 1,
    "contactability_decay": 2,
    "payment_date_drift": 3,
    "part_payment": 4,
    "bounce_pattern": 5,
    "drift_with_bounce": 6,
    "bureau_deterioration": 7,
    "interest_not_serviced": 8,
    "tranche_not_requested": 9,
    "dpd_bucket_movement": 10,
    "adverse_event": 11,
}
```

*Module level, not inside the function* — built once at import, not rebuilt 3,651 times.

**The ordering is a business decision, not a technical one:**

| Rank | Signal | Reasoning |
|---|---|---|
| 1 | moratorium_ending | **scheduled**, not distress. Outreach work |
| 2 | contactability_decay | can't reach them — a problem for later |
| 3 | payment_date_drift | earliest behavioural sign, weeks of lead time |
| 4 | part_payment | paying, but can't cover the EMI |
| 5 | bounce_pattern | a payment actually failed |
| 6 | drift_with_bounce | both — strictly worse than either |
| 7 | bureau_deterioration | stress visible at other lenders too |
| 8 | interest_not_serviced | not servicing even the small moratorium amount |
| 9 | tranche_not_requested | probably stopped studying. Unrecoverable in a way DPD won't show for years |
| 10 | dpd_bucket_movement | money is already late |
| 11 | adverse_event | a reported **fact**, not an inference |

**Step 4 — the comparison, and criteria 3 and 4 together.**

```python
    if _SEVERITY[signal_type] > _SEVERITY[open_case_type]:
        return "escalate"

    return "join"
```

**`>` not `>=`.** Equal severity falls through to `"join"` — criterion 3, satisfied by one character.

*Everything that isn't "open" and isn't "escalate" is a join*, so the final `return` needs no condition.

### 🧠 Concepts

**Dict as a rank table — O(1).** Turns an unorderable thing (strings) into an orderable one (ints).

**`>` vs `>=`** — the whole of criterion 3.

**Guard clause first**, then the interesting case, then the default. This shape appears in nine of the eleven signal rules too.

**`__name__`** — every Python function knows its own name. Used in the guard test below.

**Set subtraction — O(n).** `emitted - set(_SEVERITY)` finds every missing key in one operation. The nested-loop alternative is O(n·m).

### 🐛 The bug, and the guard test

`_SEVERITY` contained `"interest_not_services"` — a typo. **No test could see it**, because nothing compared the dict against the rules. It crashed with `KeyError` on the first run against 3,651 real signals.

**This is the same bug class as `_TRANSITIONS`** — a hand-maintained table with a misspelled key. The difference: the first was caught by a test, the second by a production-shaped run, which is one step too late.

**Writing the guard test — how you'd get there.** You need "every signal type a rule can emit". Where does that live? Inside each rule's `return Signal(signal_type="...")`. You can't read that.

**But every rule is named `check_<signal_type>`.** The naming convention *is* the data.

```python
def test_every_signal_type_has_a_severity():
    from nbfc_ews.domain.routing import _SEVERITY
    from nbfc_ews.domain.signals import _RULES

    emitted = {rule.__name__.replace("check_", "") for rule in _RULES}
    missing = emitted - set(_SEVERITY)

    assert not missing, f"no severity for: {sorted(missing)}"
```

> **Rule: every hand-maintained table gets a guard test that checks its keys against the real source.**

---
---

# Part 2 · `db/` — persistence

Imports `domain` only. Queries and row→object mapping. **A repository that makes a business decision is in the wrong folder.**

---

## 2.1 · `config.py` and `db/engine.py`

### 📋 The ticket

**Story E2.1 — Connection and config**

**Acceptance criteria**

1. The DSN comes from an environment variable, with a local default
2. One `connect()` function; nothing else opens a connection
3. No credentials in any committed file

### 🔍 Reading it

**Criterion 3 explains criteria 1 and 2.** A password in a committed file is how credentials leak — so the DSN must come from outside the code, and there must be exactly one place that reads it.

**Criterion 2 is about the future.** Row-level security will later need `SET LOCAL app.branch_ids` on every connection. If twenty files call `psycopg.connect()`, that's twenty edits. If one does, it's one.

### ⌨️ Writing it

```python
# config.py
import os

DATABASE_URL = os.environ.get(
    "EWS_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ews",
)
```

```python
# db/engine.py
import psycopg

from nbfc_ews.config import DATABASE_URL


def connect() -> psycopg.Connection:
    """Open a connection to the EWS database."""
    return psycopg.connect(DATABASE_URL)
```

**`os.environ.get(name, default)`** — look for the variable; if unset, use the second value. Production, staging and your laptop point at different databases; the code is identical.

### 🧠 The packaging lesson

`pytest` finds `nbfc_ews` because of `pythonpath = ["src"]` — **pytest-only**. The REPL and scripts need a real install:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[project]
dependencies = [
    "psycopg[binary]>=3.2",
    "alembic>=1.13",
]
```

```
pip install -e .      # -e = editable: points at your source, no reinstall after edits
```

**`dependencies` vs `requirements.txt`:** the first is part of the package definition, so installing the package can't miss them. The second is a list someone has to remember to use. **CI failed on exactly this** — `pip install -e .` succeeded, then `import psycopg` failed.

---

## 2.2 · `db/repositories/accounts.py`

### 📋 The ticket

**Story E2.2 — Account facts repository**
*Depends on: E1.3 (AccountFacts exists), E2.1*

**Acceptance criteria**

1. `load_account_facts(conn, as_of)` returns one `AccountFacts` per loan for that month
2. **One query per fact group — never one query per loan**
3. Missing data becomes the field's documented default, never a crash
4. A known loan produces the expected `AccountFacts`

**Contract**

| | |
|---|---|
| Purpose | build `AccountFacts` for every loan for one month |
| Interface | `load_account_facts(conn, as_of: date) -> list[AccountFacts]` plus one `load_*_facts` helper per group, each returning `dict[loan_id, value]` |
| Invariants | one query per fact group · every helper keyed by `loan_id` · missing data → default |
| Forbidden | deciding anything. It reads and maps |
| Tests | integration against the fixture book |

### 🔍 Reading it

**Criterion 2 in bold is a performance requirement written as a design constraint.** "One query per loan" over 10,000 loans is 10,000 round trips — minutes instead of milliseconds. The ticket forbids the shape, not just the slowness.

**The Interface line is doing something unusual:** it prescribes *helpers*, and it says what each returns — `dict[loan_id, value]`. The tech lead has already decided the internal structure. That's a strong hint: **the dict-keyed-by-id shape is the answer to criterion 2.**

**"Forbidden: deciding anything"** means no thresholds, no rules, no `if dpd > 30`. If you find yourself writing a business condition here, it belongs in `domain/`.

**Questions before typing:**

- *One big query with eight joins, or several small ones?*
- *How do the pieces get stitched back together?*
- *What holds them together — what's the key?*

### ⌨️ Writing it

**Step 1 — the first design decision: one query or many?**

| Option | Verdict |
|---|---|
| One query, eight `left join`s | It will be wrong somewhere over 2M rows and you won't know which part. Unverifiable |
| **One query per fact group, stitched in Python** | each query is small, separately runnable, separately checkable against the real book |

**The deciding argument is debuggability.** Every one of the four signal bugs was found by running *one* of these queries and looking at its numbers.

**Step 2 — the main query.**

```python
_FACTS_SQL = """
select
    l.id,
    l.loan_account_no,
    l.institution_id,
    cur.dpd,
    coalesce(prev.dpd, 0) as dpd_last_month,
    cur.is_in_moratorium,
    (l.moratorium_end_date - %(as_of)s::date) as days_to_moratorium_end
from loan l
join loan_month_state cur
  on cur.loan_id = l.id
 and cur.as_of_month = %(as_of)s
left join loan_month_state prev
  on prev.loan_id = l.id
 and prev.as_of_month = (%(as_of)s::date - interval '1 month')::date
"""
```

*`%(as_of)s` is a **parameter placeholder**, not string formatting.* psycopg sends the value separately from the SQL text. **Never build SQL with f-strings** — that's SQL injection, the most common serious security bug in this kind of code.

*`left join` + `coalesce(prev.dpd, 0)`* — a loan in its first month has no previous row. `left join` keeps the loan anyway and gives `NULL`; `coalesce` turns that into `0`. **That's criterion 3.**

*`date - date` in Postgres gives an integer* — exactly what `days_to_moratorium_end` expects.

**Step 3 — the second design decision: the join key.**

The bounce query returns `presentation.loan_id`. The main query returns `loan_account_no`. **These don't match.**

> **When you merge two result sets, both must carry the same join key.**

So `l.id` goes into the main query's select list — **even though no rule uses it**. It exists purely to stitch.

**Step 4 — a helper, and why it returns a plain dict.**

```python
_BOUNCE_SQL = """
select
    p.loan_id,
    count(*) as bounces,
    max(p.retry_sequence) as max_retries
from presentation p
where p.status = 'bounce'
  and p.presentation_date >= (%(as_of)s::date - interval '3 months')
  and p.presentation_date <  (%(as_of)s::date + interval '1 month')
group by p.loan_id
"""


def load_bounce_facts(conn, as_of) -> dict[int, tuple[int, int]]:
    """Bounces and worst retry count per loan over the last 3 months."""
    cur = conn.execute(_BOUNCE_SQL, {"as_of": as_of})
    return {
        loan_id: (bounces, max_retries or 0)
        for loan_id, bounces, max_retries in cur.fetchall()
    }
```

**Why not return `AccountFacts` here?** A bounce query knows nothing about DPD. You'd have to invent the other fields — and **invented values in a domain object are worse than no object.**

> **Build a domain object once, when every field is known. Everything before that is plain data.**

*`>=` and `<`, never `between`* — half-open ranges stop a boundary date landing in two windows.

**Step 5 — stitching.**

```python
def load_account_facts(conn, as_of) -> list[AccountFacts]:
    bounce_map   = load_bounce_facts(conn, as_of)     # {loan_id: (bounces, retries)}
    payment_map  = load_payment_facts(conn, as_of)
    bureau_map   = load_bureau_facts(conn, as_of)
    tranche_map  = load_tranche_facts(conn, as_of)
    contact_map  = load_contact_facts(conn, as_of)
    interest_map = load_interest_facts(conn, as_of)
    adverse_map  = load_adverse_facts(conn, as_of)

    cur = conn.execute(_FACTS_SQL, {"as_of": as_of})

    facts = []
    for (loan_id, account_no, institution_id, dpd, dpd_last,
         in_mor, days_to_end) in cur.fetchall():

        bounces, retries = bounce_map.get(loan_id, (0, 0))
        pay_days, ratios = payment_map.get(loan_id, ((), ()))
        score, prev_score, enquiries = bureau_map.get(loan_id, (None, None, 0))

        facts.append(AccountFacts(
            account_id=account_no,
            dpd=dpd,
            dpd_last_month=dpd_last,
            institution_id=str(institution_id),
            bounces_last_3m=bounces,
            retries_on_last_bounce=retries,
            in_moratorium=in_mor,
            days_to_moratorium_end=days_to_end,
            payment_days_last_3m=pay_days,
            paid_ratio_last_3m=ratios,
            bureau_score_now=score,
            bureau_score_prev=prev_score,
            new_enquiries_60d=enquiries,
            days_past_expected_tranche=tranche_map.get(loan_id),
            failed_contacts_60d=contact_map.get(loan_id, 0),
            months_interest_unserviced=interest_map.get(loan_id, 0),
            adverse_event=adverse_map.get(loan_id),
        ))
    return facts
```

**The seven maps are fetched *before* the loop, not inside it.** Seven queries total, then 9,951 dict lookups.

**`.get(key, default)`** — most loans aren't in most maps. `.get` handles that with no `if`. **That's criterion 3, satisfied seven times.**

### 🧠 The DSA content that matters most

```python
bounces, retries = bounce_map.get(loan_id, (0, 0))     # O(1)
```

versus:

```python
for f in facts:
    row = conn.execute("select ... where loan_id = %s", [f.loan_id])   # 10,000 queries
```

**One query + 10,000 dict lookups ≈ milliseconds. 10,000 queries ≈ minutes.**

This is the **hash map instead of repeated search** pattern — the same idea behind "two sum". **Build the index once, look up in O(1).** It's the single most valuable optimisation in ordinary application code, and it's what criterion 2 was really asking for.

### 🧠 SQL techniques, and when to reach for each

| Technique | Use when |
|---|---|
| `%(name)s` parameter | **always.** Never f-strings in SQL |
| `left join` + `coalesce` | the child row may not exist and you still want the parent |
| `group by` + `count/max/sum` | collapse many child rows into one per parent |
| `with x as (...)` — **CTE** | the query needs two stages; makes it read top-to-bottom |
| `date_trunc('month', d)` | group by month |
| `array_agg(x order by m)` | collect several rows into one ordered list |
| `distinct on (k) order by k, d desc` | **latest row per group** — the most useful Postgres pattern. Used twice here |
| `nullif(x, 0)` | a division whose denominator might be zero |
| `>=` and `<` | always, over `between` |

**The payment query, showing a CTE:**

```sql
with monthly as (
    select
        p.loan_id,
        date_trunc('month', p.payment_date)::date as pay_month,
        min(extract(day from p.payment_date))::int as pay_day,
        sum(p.amount) as paid
    from payment p
    where p.payment_date >= (%(as_of)s::date - interval '2 months')
      and p.payment_date <  (%(as_of)s::date + interval '1 month')
    group by 1, 2
)
select
    m.loan_id,
    array_agg(m.pay_day order by m.pay_month) as pay_days,
    array_agg((m.paid / nullif(l.emi, 0))::float order by m.pay_month) as ratios
from monthly m
join loan l on l.id = m.loan_id
group by m.loan_id
```

**Top half:** one row per loan **per month**. **Bottom half:** one row per loan, with the monthly values collected into ordered arrays.

**`tuple(pay_days)` in Python** — psycopg returns a Postgres array as a **list**. `AccountFacts` is frozen and declares tuples, so convert at the boundary.

---

## 2.3 · Migrations — alembic

### 📋 The ticket

**Story E3.1 — Case and event tables**

**Acceptance criteria**

1. `alembic upgrade head` applies cleanly to an empty database
2. `alembic downgrade -1` reverses it cleanly
3. Inserting a **second open case** for one account raises a unique violation
4. Inserting a **closed case with no outcome** raises a check violation
5. `case_id` reads as `EWS-2026-06-00123`

### 🔍 Reading it

**Criteria 3 and 4 say "raises", not "is rejected by the code".** That's the tech lead telling you these are **database constraints**, not `if` statements. Application code can race; a constraint cannot.

**Criterion 2 is easy to skip and the reason migrations exist.** Anyone can write a `create table`. The discipline is writing the `drop` beside it, so a bad deploy at 2am has a way back.

**Questions before typing:**

- *One table or two?*
- *How do you express "only one open case per account" in SQL?*
- *How do you express "closed implies outcome"?*

### ⌨️ Writing it

**Step 0 — what a migration is.**

`schema.sql` creates everything from scratch and works **exactly once**. Production has data; you can never recreate the schema, only change it — in numbered, reviewable, reversible steps.

```
alembic init src\nbfc_ews\db\migrations
alembic revision -m "add case and case_event tables"
alembic upgrade head          # apply
alembic downgrade -1          # reverse
```

**Two setup gotchas:**

- `alembic.ini` keeps `sqlalchemy.url =` **empty**; `env.py` fills it from `config.py`. One source of truth, no password committed.
- `DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)` — SQLAlchemy defaults to **psycopg2**. The `+psycopg` suffix selects psycopg **3**. Without it: `ModuleNotFoundError: No module named 'psycopg2'`.

**Step 1 — the design decision: one table or two?**

| Need | Table |
|---|---|
| "show me the open case queue" — fast, current | a **summary** row per case |
| "who closed this, when, and why" — complete, immutable | an **event log** |

**One table can't do both.** A summary row is overwritten; an audit trail must never be. So: two.

```sql
create table ews_case (
    id                  bigserial primary key,
    case_id             text not null unique,
    account_id          text,
    institution_id      text,
    case_type           text not null,
    state               text not null default 'open',
    outcome             text,
    snoozed_until       date,
    closed_at           date,
    opened_at           date not null,
    predecessor_case_id text,
    created_at          timestamptz not null default now(),

    constraint ck_case_scope check (
        (account_id is not null and institution_id is null)
        or (account_id is null and institution_id is not null)
    ),
    constraint ck_case_closed_outcome check (
        state <> 'closed' or outcome is not null
    )
);
```

***`ews_case`, not `case`*** — `case` is a reserved SQL keyword (`CASE WHEN …`). Naming a table that means quoting it forever.

**Step 2 — criterion 4 as a constraint.**

```sql
constraint ck_case_closed_outcome check (
    state <> 'closed' or outcome is not null
)
```

Read it as: *"unless the state is closed, no constraint; if closed, outcome must exist."*

**Why the database and not the code:** **the outcome is the training label.** A case closed without one is a permanently lost data point — you can't go back and ask the analyst six months later. Too important to depend on an `if` somebody might forget.

**Step 3 — criterion 3, and the interesting SQL.**

"One open case per account." A plain `unique (account_id)` is wrong — a *closed* case must allow a new one.

**Postgres has exactly the tool: a partial unique index.**

```sql
create unique index ux_case_one_open_per_account
    on ews_case (account_id)
    where state <> 'closed' and account_id is not null;
```

**Unique only across the rows matching the `where`.** Closed cases are outside the index, so they don't block a new one.

*Why not do this check in Python:* two nightly runs at the same instant both read "no open case", both insert. The database has no such window.

**Step 4 — the event log.**

```sql
create table case_event (
    id            bigserial primary key,
    case_id       text not null references ews_case(case_id),
    event_type    text not null,
    at            date not null,
    signal_type   text,
    detail        text,
    outcome       text,
    snoozed_until date,
    actor         text,
    created_at    timestamptz not null default now()
);
```

*`actor`* — every event records **who**. The batch is `"system"`; a human action records their id. Without it the log answers *what happened* but not *who did it*, which is the question an inspector actually asks.

**Step 5 — the downgrade, criterion 2.**

```python
def downgrade() -> None:
    op.execute("drop table if exists case_event")
    op.execute("drop table if exists ews_case")
```

**Reverse order.** `case_event` references `ews_case`, so it must go first.

### ✅ Proving criteria 3 and 4

```
ERROR: duplicate key value violates unique constraint "ux_case_one_open_per_account"
ERROR: new row violates check constraint "ck_case_closed_outcome"
```

**No application code was involved in either refusal.** That is the difference between a rule and an intention.

---

## 2.4 · `db/repositories/cases.py`

### 📋 The ticket

**Story E3.3 — Case repository**
*Depends on: E3.1, E3.2*

**Acceptance criteria**

1. `open_case_types` on an empty database returns `{}`
2. After creating a case for A1, it returns `{"A1": <type>}`
3. `append_event` adds a row and leaves the case's state unchanged
4. `escalate_case` changes `case_type` **and** writes an event
5. Feeding `open_case_types` back into `route_signals` on the **same month** produces **zero** opens

**Contract**

| | |
|---|---|
| Purpose | read and write cases and their events |
| Interface | `open_cases` · `open_case_types` · `create_case` · `append_event` · `escalate_case` |
| Invariants | every write also writes an event row · `create_case` returns the new `case_id` · `open_case_types` returns exactly the dict `route_signals` expects |
| Forbidden | deciding anything. It persists what `route_signals` already decided |
| Tests | create → read back · append → log grows · escalate changes both · concurrent create fails |

### 🔍 Reading it

**"Returns exactly the dict `route_signals` expects" is the clearest instruction in the ticket.** Go and look at that function's signature: `open_case_types: dict[str, str]`. **The shape is already decided.**

**Criterion 5 is the real acceptance test** and it's not about this file in isolation — it's about the loop closing. Cases persist, the next run sees them, nothing duplicates.

**"Forbidden: deciding anything"** — so no `if severity > ...` here. That decision already happened in `routing.py`.

**Questions before typing:**

- *Where does `case_id` come from?* Criterion says `EWS-2026-06-00123` — readable **and** unique, which are in tension
- *What writes the event — the caller, or each function?*

### ⌨️ Writing it

**Step 1 — the simplest function first.**

```python
_OPEN_CASES_SQL = """
select account_id, case_id, case_type
from ews_case
where state <> 'closed'
  and account_id is not null
"""


def open_case_types(conn) -> dict[str, str]:
    """account_id -> case_type. The shape route_signals expects."""
    cur = conn.execute(_OPEN_CASES_SQL)
    return {a: ct for a, _cid, ct in cur.fetchall()}
```

*No `as_of` parameter.* An open case is open **now**; it isn't a monthly snapshot. (The original contract had one — that was wrong, and this is the moment to fix the contract rather than carry a parameter nobody uses.)

**Step 2 — the event writer, because everything else calls it.**

Invariant: *"every write also writes an event row"*. Two ways to honour that: make each caller remember, or have each write function do it. **The second — invariants that depend on callers remembering get violated.**

```python
_APPEND_EVENT_SQL = """
insert into case_event (case_id, event_type, at, signal_type, detail, actor)
values (%(case_id)s, %(event_type)s, %(at)s, %(signal_type)s, %(detail)s, %(actor)s)
"""


def append_event(conn, case_id, event_type, signal, at, actor="system") -> None:
    """Record something that happened to a case. Append-only."""
    conn.execute(_APPEND_EVENT_SQL, {
        "case_id": case_id,
        "event_type": event_type,
        "at": at,
        "signal_type": signal.signal_type if signal else None,
        "detail": signal.detail if signal else None,
        "actor": actor,
    })
```

*`signal.signal_type if signal else None`* — some events have no signal behind them (an analyst snoozing, an auto-close). The expression handles `None` so the parameter can be optional.

*`actor="system"` as a default* — the batch is the common caller, humans are the exception.

**Step 3 — the `case_id` problem.**

Two requirements pulling opposite ways:

| Requirement | Points to |
|---|---|
| Human-readable — an analyst says it on a phone call | build it in Python |
| Globally unique | only the database can guarantee that |

**The resolution: ask the database for the number first, then build the string around it.**

```python
_NEXT_ID_SQL = "select nextval(pg_get_serial_sequence('ews_case','id'))"

_CREATE_CASE_SQL = """
insert into ews_case (id, case_id, account_id, case_type, opened_at)
values (%(id)s, %(case_id)s, %(account_id)s, %(case_type)s, %(as_of)s)
"""


def create_case(conn, account_id, case_type, signal, as_of) -> str:
    """Open a new case for an account. Returns the new case_id."""
    (seq,) = conn.execute(_NEXT_ID_SQL).fetchone()
    case_id = f"EWS-{as_of:%Y-%m}-{seq:05d}"

    conn.execute(_CREATE_CASE_SQL, {
        "id": seq,
        "case_id": case_id,
        "account_id": account_id,
        "case_type": case_type,
        "as_of": as_of,
    })

    append_event(conn, case_id, "case_opened", signal, as_of)
    return case_id
```

| Line | What it does |
|---|---|
| `nextval(pg_get_serial_sequence(...))` | takes the next number from the table's own id sequence — the same counter `bigserial` uses |
| `(seq,) = ...fetchone()` | `fetchone()` returns `(3,)`; the comma on the left unpacks it to `3` |
| `f"EWS-{as_of:%Y-%m}-{seq:05d}"` | `%Y-%m` → `2026-06`; `:05d` pads to five digits |
| `insert ... (id, ...)` | pass the id explicitly — we already consumed it |

*Why not insert-then-update:* two writes, and a window where the case exists with no readable identifier.

**Step 4 — escalate, and the one place `update` is allowed.**

```python
_ESCALATE_SQL = """
update ews_case
set case_type = %(case_type)s,
    state = 'escalated'
where case_id = %(case_id)s
"""


def escalate_case(conn, case_id, new_case_type, signal, at) -> None:
    """Re-type a case to a more severe concern and put it back in the queue."""
    conn.execute(_ESCALATE_SQL, {"case_id": case_id, "case_type": new_case_type})
    append_event(conn, case_id, "escalation_required", signal, at)
```

**`ews_case` is a mutable summary; `case_event` is immutable history.** The update changes the summary; the event records why. Both are correct — they're different kinds of table.

**Known gap, written down rather than hidden:** `state = 'escalated'` is set here in SQL, but `domain/case_state.py` owns state transitions. Those two could disagree. Closed in story 7.1.

**Step 5 — the contract gets refined.**

Writing `nightly.py` reveals a problem: to append an event you need the **`case_id`**, but `open_case_types` only returns the *type*.

**So the contract changes — deliberately:**

```python
def open_cases(conn) -> dict[str, tuple[str, str]]:
    """account_id -> (case_id, case_type) for every open account case."""
    cur = conn.execute(_OPEN_CASES_SQL)
    return {
        account_id: (case_id, case_type)
        for account_id, case_id, case_type in cur.fetchall()
    }


def open_case_types(conn) -> dict[str, str]:
    """account_id -> case_type. The shape route_signals expects."""
    return {
        account_id: case_type
        for account_id, (_case_id, case_type) in open_cases(conn).items()
    }
```

**One query, two views of it.**

> **Contracts survive until a caller reveals what they actually need. You change them deliberately rather than bolting on.**

### 🧠 Concepts

**`(seq,) = ...`** — tuple unpacking of a one-element tuple. The trailing comma is the whole syntax.

**f-string format specs** — `{as_of:%Y-%m}` applies a date format; `{seq:05d}` pads an integer to 5 digits with zeros.

**`_case_id`** — a leading underscore on an unpacked-but-unused variable says *"the omission is deliberate, not a bug"*.

**Nested tuple unpacking in a comprehension** — `for account_id, (case_id, case_type) in ...`. If it confuses you, **write the long version**:

```python
case_types = {}
for acct, pair in existing.items():
    case_types[acct] = pair[1]
```

**Four readable lines beat one clever line.** Read a comprehension **right to left**: find the `for`, read that first, then look at what's before it — that's what gets put in.

---
---

# Part 3 · `engine/` — the deterministic pipeline

Imports `domain` and `db`. **Must never import `llm/`, `agents/` or `tools/`** — the determinism boundary expressed as code, enforced by an architecture test.

---

## 3.1 · `engine/detect.py`

### 📋 The ticket

**Story E2.3 — Detection engine**

**Acceptance criteria**

1. Runs the full book for one month
2. All eleven rules fire on real data
3. The cohort rule finds the four seeded institutions
4. Reproducible — same book and date give identical output

### 🔍 Reading it

**Criterion 4 explains the Forbidden line.** Reproducibility is why nothing here may reason, read a clock, or use randomness.

**Criterion 3 is a clever acceptance test.** The generator seeded four bad institutions; nothing in the pipeline knows which. If the cohort rule finds exactly those four, the whole chain — repository, rules, cohort logic — is right.

**Question before typing:** *what does this hand back?* A list of signals is the obvious answer, and it's wrong.

### ⌨️ Writing it

**Step 1 — the return type, and why a bare list is wrong.**

A batch run is a thing that happened. It has a date, it scanned a number of accounts, it produced signals. **If you return only the signals, `as_of` and `accounts_scanned` are lost** — and those are exactly what a run record, a trace and an evaluation harness need.

```python
@dataclass(frozen=True)
class DetectionRun:
    as_of: date
    accounts_scanned: int
    signals: list[Signal]
    cohort_signals: list[CohortSignal]
```

**Step 2 — the loop.**

```python
def detect(conn, as_of: date) -> DetectionRun:
    """Run every signal rule over the book for one month."""
    facts = load_account_facts(conn, as_of)

    signals: list[Signal] = []
    flagged = []

    for f in facts:
        fired = evaluate(f)
        if fired:
            signals.extend(fired)
            flagged.append(f)

    return DetectionRun(
        as_of=as_of,
        accounts_scanned=len(facts),
        signals=signals,
        cohort_signals=check_institution_cohort(flagged, facts),
    )
```

**`extend` vs `append`.** `append` adds **one item**; `extend` adds **every item** of a list. `evaluate` returns a list, so `extend`.

**Why `flagged` is collected separately.** The cohort rule needs accounts that fired *anything* — five flagged accounts at one institution is a pattern; five accounts merely existing there is not. Collecting it inside this loop costs nothing; a second pass would cost O(N).

### 🧠 Concepts

**Single pass collecting two things.** `signals` and `flagged` are both built in one walk of `facts`. Two loops would be O(2N) — same order, but pointlessly slower and no clearer.

**`list[Signal]` annotation on an empty list** — `signals: list[Signal] = []` tells mypy what will go in. Without it, mypy infers `list[Never]` and complains at the first `extend`.

---

## 3.2 · `engine/route.py`

### 📋 The ticket

**Story E3.2 — Suppression**
*Depends on: E1.4 (routing decision)*

**Acceptance criteria**

1. 3 signals on 1 account, no existing case → exactly 1 `open`, 2 others
2. A more severe signal on an existing case → `escalate`, and `case_type` is the **new** type
3. A less severe signal → `join`, and `case_type` stays the **old** type
4. An empty signal list → `[]`
5. The dict passed in is **unchanged** after the call
6. On the real June book, opens = the number of flagged accounts

**Contract**

| | |
|---|---|
| Purpose | turn signals into case actions, applying suppression |
| Interface | `route_signals(signals, open_case_types) -> list[CaseAction]` |
| Invariants | at most one `open` per account per batch · later signals see cases opened earlier in the batch · the input dict is copied, never mutated · output length = input length |
| Forbidden | writing to the database. It returns *intended* actions |
| Tests | the six criteria above |

### 🔍 Reading it

**What problem is this solving?** 3,651 alerts, 2,161 accounts — some fired three or four each. If every alert became a task, the analyst has 3,651 things to look at, mostly about the same accounts.

**Hospital version:** new patient → open a file. Already has a file → add today's note. Already has a file but now it's chest pain → same file, moved to the front.

**Criterion 1 is the hard one, and it hides the whole design.** *"3 signals on 1 account → exactly 1 open."* For that to work, **the second signal must somehow know the first one opened a case** — and the case doesn't exist in the database yet, because nothing has been written.

**Criterion 5 is a subtle one.** "The dict passed in is unchanged" — meaning whatever bookkeeping you do, do it on a copy.

**"Forbidden: writing to the database"** plus criterion 1 tells you the answer must be **in memory, inside this function**.

**Questions before typing:**

- *How does signal 2 learn about the case signal 1 opened?*
- *What comes out — a decision, or a written case?*

### ⌨️ Writing it

**Step 1 — the output type.**

The Interface says `list[CaseAction]`, which doesn't exist. What does the caller need to persist a decision?

```python
@dataclass(frozen=True)
class CaseAction:
    account_id: str
    decision: RouteDecision
    case_type: str
    signal: Signal
```

| Field | Why the caller needs it |
|---|---|
| `account_id` | which account to write the case for |
| `decision` | open / join / escalate |
| `case_type` | criteria 2 and 3 are specifically about this field |
| `signal` | the case needs the **evidence** attached — `signal.detail` is what the analyst reads |

**Step 2 — the signature.**

```python
def route_signals(
    signals: list[Signal],
    open_case_types: dict[str, str] | None = None,
) -> list[CaseAction]:
    """Route a batch of signals into open / join / escalate decisions."""
```

*Why `open_case_types` is a **parameter** and not fetched inside:* the Forbidden line says no database. If this function queried, it would need a connection, and then it couldn't be tested without one. **The caller fetches; this function decides.**

*`| None = None`* so a test can call it with nothing, and the first-ever run has no existing cases.

**Step 3 — the design decision: how signal 2 learns about signal 1.**

This is criterion 1, and it's the whole ticket.

**The answer: keep a notebook in memory, and update it as you go.**

```python
    current: dict[str, str] = dict(open_case_types or {})
```

Think of `current` as **a notebook listing which accounts already have a case open, and what each is about**:

```
current = { "EDU0000005": "bounce_pattern" }
```

**`dict(...)` makes a copy** — that's criterion 5. Without it, the lines below would edit the caller's dictionary.

**Step 4 — the loop.**

```python
    actions = []
    for s in signals:
        decision = route(s.signal_type, current.get(s.account_id))

        if decision in ("open", "escalate"):
            current[s.account_id] = s.signal_type

        actions.append(
            CaseAction(
                account_id=s.account_id,
                decision=decision,
                case_type=current[s.account_id],
                signal=s,
            )
        )
    return actions
```

**Four steps per signal:**

1. **Look the account up** — `current.get(...)`. Not there → `None` → `route` says `"open"`.
2. **Ask `route` what to do** — the decision itself lives in `domain/`.
3. **If opened or re-typed, write it in the notebook.** ← **this is the mechanism**
4. **Record the decision.**

**Step 3 is criterion 1.** The next signal for that account *finds* it in the notebook and joins instead of opening a second case.

**Why not on `"join"`:** a join is evidence, not a re-type. Criterion 3 says `case_type` must stay the old type, so `current` isn't touched.

**`current[s.account_id]` uses square brackets, not `.get()`.** By this point the account is guaranteed present — either it already was, or step 3 just put it there. `[ ]` says "this must exist" and would raise loudly if the logic above ever broke.

**Walking three alerts for `EDU0000011`:**

| Alert | Notebook says | Decision | Notebook after |
|---|---|---|---|
| `dpd_bucket_movement` (10) | *(nothing)* | open | `dpd_bucket_movement` |
| `moratorium_ending` (1) | `dpd_bucket_movement` | join | unchanged |
| `adverse_event` (11) | `dpd_bucket_movement` | escalate | `adverse_event` |

**One case, three pieces of evidence.** Without step 3: three cases.

### 🔑 Two things engineers ask about this function

**"Does it process all 3,651 at once, or one at a time?"**

The whole list goes in as one argument, but they're processed **one at a time, in order** — and **the order is part of the logic**. If all 3,651 were judged simultaneously against the *original* notebook, every one would see "no case" and every one would open.

**"Where does the joining actually happen? There's no join code."**

Nowhere here. `"join"` is a **label on a decision**; nothing has been attached to anything. The actual joining is `append_event` in the case repository.

> **Decide in one place, act in another.** A function that both decides *and* writes can't be tested without a database. `route_signals` is tested with three made-up signals in four lines and no Postgres. You'll see the same split again when agents recommend and humans approve.

### 🧠 Concepts

**Accumulating dict / running state.** `current` is built as the loop runs and read by later iterations. **This makes the loop order-dependent and non-parallelisable** — worth recognising, because it's also why it can't be trivially sped up.

**Defensive copy.** `dict(x)` before mutating. Same family as `replace` on a frozen dataclass: **never modify what you were given.**

**`.get(k)` vs `[k]`** — `.get` for "might not be there", `[ ]` for "must be there". Using `[ ]` deliberately is a way of asserting an invariant in one character.

**`in ("open", "escalate")`** — membership on a small tuple. Clearer than `decision == "open" or decision == "escalate"`.

### Result

```
3,651 signals  →  2,161 open · 1,175 join · 315 escalate
```

**2,161 = exactly the number of flagged accounts.** Criterion 6.

---

## 3.3 · `engine/nightly.py`

### 📋 The ticket

**Story E3.4 — The nightly batch**
*Depends on: E2.3, E3.2, E3.3*

**Acceptance criteria**

1. First run on an empty case table opens 2,161 cases
2. **Running it again on the same date opens 0**
3. The run reports opened / joined / escalated counts
4. A failure part-way leaves no half-written batch

**Contract**

| | |
|---|---|
| Purpose | one command runs the whole batch: detect → route → persist |
| Interface | `run_nightly(conn, as_of: date) -> NightlyRun` |
| Invariants | **idempotent** · one transaction · the run object records counts |
| Forbidden | business logic. **It does not commit** |
| Tests | run twice on the same month → second opens zero |

### 🔍 Reading it

**Criterion 2 is the milestone of the entire epic.** It's the proof that suppression works *across runs*, not just within a batch — which is the only reason the case layer exists.

**Criterion 4 and "one transaction" are the same requirement.** If the loop dies at signal 2,000, nothing must be saved.

**"Forbidden: it does not commit" looks strange** — the function writes 3,651 rows and isn't allowed to save them? That's deliberate, and the reason is in the Tests line: the idempotency test needs to `delete from ews_case` first, and if `run_nightly` committed, that delete would be **real**.

**Questions before typing:**

- *This calls four other modules — what's the order?*
- *Persisting needs `case_id`, but `route_signals` works in `case_type`. Where does the id come from?*

### ⌨️ Writing it

**Step 1 — the run record.**

```python
@dataclass(frozen=True)
class NightlyRun:
    as_of: date
    accounts_scanned: int
    signals: int
    opened: int
    joined: int
    escalated: int
```

**A function that prints tells nobody anything.** This object is what gets written to a `batch_run` table, shown on the dashboard as "last night", and read at 9am to know whether the batch worked.

**Step 2 — the imports, and what's absent.**

```python
from nbfc_ews.db.repositories.cases import (
    append_event, create_case, escalate_case, open_cases,
)
from nbfc_ews.engine.detect import detect
from nbfc_ews.engine.route import route_signals
```

**No SQL, no psycopg, no signal rules.** `nightly.py` sequences other people's work — that's what "orchestrator" means, and why its Forbidden line says "business logic".

**Step 3 — the phases.**

```python
def run_nightly(conn, as_of: date) -> NightlyRun:
    """Detect, route and persist one month of cases."""
    run = detect(conn, as_of)                     # phase 1
    existing = open_cases(conn)                   # phase 2
```

**Step 4 — the second design decision: two dicts from one query.**

`route_signals` wants `{account: case_type}`. Persisting wants `{account: case_id}`. `open_cases` returns both in one shape.

**Call the database once, split in Python:**

```python
    case_types = {acct: ct for acct, (_cid, ct) in existing.items()}
    case_ids = {acct: cid for acct, (cid, _ct) in existing.items()}
```

*Two queries for the same rows would be the lazy version.*

**Step 5 — route, then persist.**

```python
    actions = route_signals(run.signals, case_types)     # phase 3

    opened = joined = escalated = 0

    for a in actions:                                     # phase 4
        if a.decision == "open":
            case_ids[a.account_id] = create_case(
                conn, a.account_id, a.case_type, a.signal, as_of
            )
            opened += 1

        elif a.decision == "escalate":
            escalate_case(conn, case_ids[a.account_id], a.case_type, a.signal, as_of)
            escalated += 1

        else:
            append_event(conn, case_ids[a.account_id], "signal_joined", a.signal, as_of)
            joined += 1

    return NightlyRun(
        as_of=as_of,
        accounts_scanned=run.accounts_scanned,
        signals=len(run.signals),
        opened=opened,
        joined=joined,
        escalated=escalated,
    )
```

**`case_ids[a.account_id] = create_case(...)` is the notebook trick again.** The new `case_id` goes straight into the dict, so the *next* signal for that account finds it on the join line below. **Without it, every same-batch join raises `KeyError`.**

**Same pattern, second module.** `current` in `route_signals`, `case_ids` here. Once you've seen it twice you stop having to think about it.

### 🔧 The design fix: moving the commit out

The first version ended with `conn.commit()`. Two problems:

1. **A function that commits can't be composed.** Nobody can wrap it in a bigger transaction.
2. **It can't be tested with the rollback fixture** — and criterion 2's test needs to delete every case first.

So the commit moved to `scripts/nightly.py`, the outermost caller:

```python
with connect() as conn:
    for m in months:
        print(run_nightly(conn, date.fromisoformat(m)))
    conn.commit()
```

> **The outermost caller owns the transaction.**

**The design change and the test becoming possible are the same fact** — usually a sign the change was right.

### 🧪 Testing against a real database, safely

```python
# tests/integration/conftest.py
@pytest.fixture
def conn():
    """A connection whose work is always rolled back, so tests leave no trace."""
    c = connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()
```

**Every test runs in a transaction that is never committed.** Insert, read back, assert — then `rollback()` throws it all away.

**`yield` instead of `return`:** pytest runs the test *at* the `yield`, then comes back for the `finally`. That's how a fixture does setup and teardown around a test.

**This is what makes criterion 2's test possible:**

```python
def test_nightly_is_idempotent(conn):
    conn.execute("delete from case_event")
    conn.execute("delete from ews_case")

    first = run_nightly(conn, date(2026, 6, 1))
    second = run_nightly(conn, date(2026, 6, 1))

    assert first.opened > 0
    assert second.opened == 0
    assert second.joined + second.escalated == second.signals
```

**The two `delete` lines look alarming and are safe** — the fixture never commits, so your 2,161 real cases are untouched. **And that's only true because the commit moved out.**

### ✅ The result

```
run 1:  accounts=9,951  signals=3,651  opened=2,161  joined=1,175  escalated=315
run 2:  accounts=9,951  signals=3,651  opened=0      joined=3,651  escalated=0
```

**`opened=0` on the second run.** `escalated=0` is right too — after run 1 each case is typed with that account's *worst* signal, so nothing outranks it.

---
---

# Part 4 · DSA index

Every pattern used, where it appears in **your** code, and the interview question it maps to.

| Pattern | Complexity | Where | Classic form |
|---|---|---|---|
| **Hash map as an index** | O(1) lookup | `bounce_map.get()` ×7 in `accounts.py`; `current` in `route_signals`; `case_ids` in `run_nightly` | Two Sum, Group Anagrams |
| **Composite key** | O(1) | `(state, event)` in `_TRANSITIONS` | any two-part cache key |
| **Exact vs range lookup** | O(1) vs O(k) | `_BUCKET_TO_CLASS` (dict) vs `_BUCKETS` (list) | binary search on a range table |
| **Rank table** | O(1) | `_SEVERITY` | custom comparator problems |
| **Counting** | O(n) | `Counter` in the cohort rule | Top K Frequent |
| **Set membership** | O(1) | `state not in VALID_STATES` | Contains Duplicate |
| **Set subtraction** | O(n) | `emitted - set(_SEVERITY)` | Difference of Two Arrays |
| **Uniqueness via set** | O(n) | `len(x) == len(set(x))` | Contains Duplicate |
| **Order-dependent single pass** | O(n), not parallelisable | `route_signals`, `run_nightly` | Running sum, stock buy/sell |
| **Generator expression** | O(1) extra memory | `(f.institution_id for f in flagged)` | streaming / constant-space |
| **Sliding window** | O(k) | `ratios[-2:]`, `days[0] < days[1] < days[2]` | Sliding Window Maximum |
| **Short-circuit** | early exit | `all(...)`, `and` / `or` | early-termination problems |

## The four lessons that generalise

**1 · Build the index once, look up in O(1).** One query + 10,000 dict lookups ≈ milliseconds; 10,000 queries ≈ minutes. The most valuable optimisation in ordinary application code.

**2 · A count needs a denominator.** 185 false positives → 4 true ones by dividing. A *modelling* insight, not a coding one — and the kind interviewers actually probe.

**3 · Improve the order, not the constants.** The cohort rule is O(N); the naive version O(I × N) — 250× slower. But collapsing two O(N) passes into one is **not** worth the readability. *Improve the order always; chase constants only after measuring.*

**4 · Know when you're already optimal.** O(N) is the floor for counting — you must look at every account once. *"It's O(N), and O(N) is the lower bound because every element must be examined"* is a stronger answer than any micro-optimisation.

---
---

# Part 5 · Backlog

| Epic | Status |
|---|---|
| **E1 · Pure domain** | ✅ classification · case state · 11 signal rules · routing |
| **E2 · Read the book** | ✅ config · connection · account-facts repository · detect |
| **E3 · Cases exist** | ✅ migrations · route_signals · case repository · nightly |
| **E4 · Access control** | principal + `SET LOCAL` · `authority.py` · PII registry |
| **E5 · Tools** | Tool protocol + registry · 4 tools · policy retrieval · **5.7 MCP server** |
| **E6 · Agents** | FakeChatModel · egress guard · graph · supervisor · 2 investigators · arbitration · citations · budget and cycle guards |
| **E7 · Surface** | case service · API + auth · Streamlit · case-scoped chat |
| **E8 · Evaluation** | Layer 1 checks · two-arm harness · second seeded book · the number |
| **E9 · Operations** | Langfuse tracing · cost per case · compose · CI |

## 📋 Next ticket — E5.1 · Tool protocol and registry

**Acceptance criteria**

1. Every tool exposes the same call shape and returns the same result shape
2. A tool called with a branch-1 principal returns nothing from branch 2
3. Every returned record carries `as_of`
4. Row limits are enforced and what was omitted is reported
5. A bad input returns `{ok: false, reason}` — **it does not raise**
6. The registry says which agent may use which tool

**Contract**

| | |
|---|---|
| Purpose | one shape every tool obeys, so agents cannot do anything unsafe by construction |
| Interface | `Tool` protocol: `__call__(principal, **params) -> ToolResult` where `ToolResult = {ok, data, as_of, omitted, reason}` |
| Invariants | scoped by the principal · every record carries `as_of` · limits enforced and omissions reported · bad input returns, never raises |
| Forbidden | any write, any external effect. **There must be no tool that *can* act** |
| Tests | the same five contract tests for every tool, the fifth being the scope test |

**Reading it ahead of time:** criterion 5 is the unusual one. Everywhere else in this codebase, bad input **raises** — `bucket_of` raises on a negative DPD, `apply_event` raises on an illegal move. Here it must **return**. Worth thinking about why before we build it.

---
---

# Part 6 · Habits

## From the domain layer

1. **Restart the REPL after editing a file.** Python loads a module once per session.
2. **Read the error message to the end.** It usually names the exact problem.
3. **Never guess at string values in data.** `select status, count(*) group by 1` before any `where status = ...`.
4. **A linter warning is a hypothesis.** Confirm with a second tool before silencing. Never add a `cast` to quiet a false positive.
5. **A trailing comma makes a tuple.** `x = 5,` is `(5,)`.
6. **Verify each layer against real data before adding the next.** All five signal bugs were found by looking at counts.
7. **Gather failures, assert once.**
8. **A count needs a denominator.**
9. **Build the index once, look up in O(1).**
10. **A test that goes green because you deleted the thing it tested is worse than a red test.**

## From persistence and batch

11. **Agree the contract before writing the body.** Every argument traces to an invariant written down first.
12. **A contract changes when a caller reveals a real need** — deliberately, like `open_cases`.
13. **Let the database enforce what the database can enforce.** A partial unique index cannot race.
14. **The outermost caller owns the transaction.**
15. **Integration tests roll back.**
16. **A guard test for every hand-maintained table.** `_TRANSITIONS`, then `_SEVERITY` — same bug twice.
17. **Anything CI runs, you should be able to run locally.**
18. **Declare dependencies in the package, not just a requirements file.**

## On learning this

19. **You are not supposed to hold this in your head.** Engineers keep the file they're in and the shapes either side, and press **F12** for everything else. Type hints, tests and small functions exist *because* nobody can remember it. What changes with experience isn't memory but pattern recognition — you stop reading `{k: v for k, v in x.items()}` word by word and see "build a dict".

20. **When a line confuses you, write the long version.** Four readable lines beat one clever line. You can shorten it later, or never.
