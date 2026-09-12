# 15 — Code Revision Log

A running record of every file written, what it does, why it exists, and the concepts behind it. Append a new day at the bottom each session.

---

# Day 1 — 11 September 2026

**Built:** `domain/classification.py`, `domain/models.py`, `domain/case_state.py`, `domain/signals.py`, `db/engine.py`, `db/repositories/accounts.py`, `engine/detect.py` · **62 tests passing**

---

## 1 · `src/nbfc_ews/domain/classification.py`

**Job:** turn days-past-due into a delinquency bucket and an IRACP asset class.

```python
Bucket = Literal["0", "1-30", "31-60", "61-90", "90+"]
AssetClass = Literal["standard", "SMA0", "SMA1", "SMA2", "NPA"]

_BUCKETS: list[tuple[int, Bucket]] = [
    (0, "0"), (30, "1-30"), (60, "31-60"), (90, "61-90"),
]

_BUCKET_TO_CLASS: dict[Bucket, AssetClass] = {
    "0": "standard", "1-30": "SMA0", "31-60": "SMA1",
    "61-90": "SMA2", "90+": "NPA",
}

def bucket_of(dpd: int) -> Bucket:
    if dpd < 0:
        raise ValueError(f"dpd cannot be negative: {dpd}")
    for upper, name in _BUCKETS:
        if dpd <= upper:
            return name
    return "90+"

def asset_class_of(dpd: int) -> AssetClass:
    return _BUCKET_TO_CLASS[bucket_of(dpd)]
```

**Why it's shaped this way**

| Decision | Reason |
|---|---|
| `Literal` types | the only legal values are these five strings — a typo elsewhere is a type error, not a silent wrong answer |
| `_BUCKETS` is a **list** | buckets are **ranges**, and ranges must be checked in order. A dict can't express "anything up to 30" |
| `_BUCKET_TO_CLASS` is a **dict** | bucket → class is an **exact lookup**, one key one value. Dict is O(1) and reads like a table |
| `raise` on negative | a negative DPD is impossible; failing loudly beats returning `"0"` and hiding a data bug |
| `asset_class_of` calls `bucket_of` | one source of truth for the boundaries |

**DSA content**

- **List scan, O(k)** — `for upper, name in _BUCKETS` walks at most 4 entries. Fine because k is tiny and fixed. If there were 10,000 ranges you'd use binary search (`bisect`), O(log k).
- **Dict lookup, O(1)** — `_BUCKET_TO_CLASS[...]` hashes the key and jumps straight to the value. No scanning.
- **The general rule:** *exact match → dict; range match → ordered list.*

**Bug caught in review:** an early version used `if/elif` and fell through to `"NPA"` for any unrecognised input — a silent wrong answer in the worst possible direction (a healthy loan classified as non-performing).

---

## 2 · `src/nbfc_ews/domain/models.py`

**Job:** the shared data shapes for case handling.

```python
CaseState = Literal["open", "investigating", "awaiting_review", "snoozed", "escalated", "closed"]
CloseOutcome = Literal["resolved_benign", "intervened", "escalated", "no_action_authorised"]
EventType = Literal["signal_joined", "investigation_started", ...]

@dataclass(frozen=True)
class Case:
    case_id: str
    state: CaseState
    case_type: str
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None
    closed_at: date | None = None

@dataclass(frozen=True)
class Event:
    type: EventType
    at: date
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None
```

**Concepts**

- **`@dataclass`** — writes `__init__`, `__repr__` and `__eq__` for you. Without it you'd hand-write 20 lines of boilerplate per class.
- **`frozen=True`** — the object cannot be modified after creation. `case.state = "closed"` raises. This is what makes the state machine safe: no function can secretly mutate a case that another function is holding.
- **`| None = None`** — the field may hold a value *or* nothing, and defaults to nothing. A brand-new case has no outcome yet.
- **Fields with defaults must come after fields without.** Python needs to know which arguments are required.

---

## 3 · `src/nbfc_ews/domain/case_state.py`

**Job:** the only place a case is allowed to change state.

```python
class InvalidTransition(Exception):
    """Raised when an event is not legal for a case's current state."""

_TRANSITIONS: dict[tuple[CaseState, EventType], CaseState] = {
    ("open", "investigation_started"): "investigating",
    ("investigating", "investigation_completed"): "awaiting_review",
    ...  # 14 rows
}

def apply_event(case: Case, event: Event) -> Case:
    key = (case.state, event.type)

    if key not in _TRANSITIONS:
        raise InvalidTransition(f"{event.type} is not allowed for {case.state}")

    new_state = _TRANSITIONS[key]

    if event.type == "closed" and event.outcome is None:
        raise InvalidTransition("closing a case requires an outcome")

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

**The four ideas in this file**

**1 — The table is data, not code.** `_TRANSITIONS` maps `(current state, event) → new state`. The legal moves are a table you can print and show a compliance officer. An `if/elif` chain doing the same thing would be 40 lines and unreviewable.

**2 — Table answers *does this move exist*; code answers *is it allowed right now*.** A dict key can't express "…but only if an outcome was supplied", so guards live below the lookup.

**3 — `replace(case, **changes)` — new object, not mutation.** `frozen=True` blocks `case.state = x`. `replace` copies the case, overrides the named fields, and returns a **new** `Case`. The original survives untouched — proven in the REPL:

```python
after = apply_event(c, Event(type="investigation_started", at=date(2026, 9, 11)))
after.state   # 'investigating'
c.state       # 'open'  ← unchanged
```

**4 — `changes` is a dict of "what this event modifies".** Different events touch different fields, so you can't write one fixed `replace(...)` call. Build the dict first, call once at the end. `**changes` unpacks it into keyword arguments:

```python
{"state": "closed", "outcome": "recovered"}   →   replace(case, state="closed", outcome="recovered")
```

Fields **not** in the dict are copied over unchanged — which is why a snooze never has to think about `outcome`.

**DSA content**

- **Tuple as a composite dict key, O(1).** `(state, event)` hashes as one unit. The alternative — nested dicts or a scan through a list of rules — is slower and harder to read.
- **Why a tuple and not a list:** dict keys must be **hashable**, i.e. immutable. Lists are mutable, so `{[a, b]: c}` is a `TypeError`.

**Bugs caught, and the lesson from each**

| Bug | Lesson |
|---|---|
| `"investigatigation_started"` in the table | a misspelled string is a *valid dict key* — the row looks present but can never match. `Literal` does **not** catch this at runtime; it's only checked if you run a type checker |
| `event.outcome or None` | `x or None` is identical to `x` — a no-op that looks like a decision |
| SonarQube warning on `replace` | a linter warning is a **hypothesis, not a verdict**. Confirm with a second tool before silencing or contorting code. Never add a `cast` to quiet a false positive |

**The test that makes the typo class impossible:**

```python
VALID_STATES = set(get_args(CaseState))
VALID_EVENTS = set(get_args(EventType))

def test_transition_table_uses_only_valid_names():
    bad = []
    for (state, event), new_state in _TRANSITIONS.items():
        if state not in VALID_STATES:
            bad.append(f"bad from-state: {state!r}")
        ...
    assert not bad, "\n".join(bad)
```

`get_args()` reaches inside a `Literal` at runtime and returns the actual tuple of strings — turning a compile-time hint into data you can check against. Collecting failures into a list and asserting **once at the end** reports every problem in one run instead of stopping at the first.

---

## 4 · `src/nbfc_ews/domain/signals.py`

**Job:** the twelve detection rules. Pure functions — no database, no clock.

```python
@dataclass(frozen=True)
class AccountFacts:      # the input  — everything a rule may look at
    account_id: str
    dpd: int
    dpd_last_month: int
    bounces_last_3m: int = 0
    ...

@dataclass(frozen=True)
class Signal:            # the output — one account fired one rule
    account_id: str
    signal_type: str
    detail: str

@dataclass(frozen=True)
class CohortSignal:      # a different unit of work entirely
    institution_id: str
    signal_type: str
    detail: str
```

**The eleven account rules**

| Rule | Threshold |
|---|---|
| `dpd_bucket_movement` | bucket this month ≠ bucket last month |
| `bounce_pattern` | 2 bounces in 3 months, or 1 bounce with ≥2 retries |
| `moratorium_ending` | `0 <= days_to_end <= 75` |
| `payment_date_drift` | payment day strictly increasing 3 months **and** ≥7 days total |
| `part_payment` | last 2 months paid <95% but >0, **and not in moratorium** |
| `drift_with_bounce` | drift fires **and** ≥1 bounce |
| `interest_not_serviced` | in moratorium and ≥2 months unserviced |
| `bureau_deterioration` | score drop ≥40, **or** ≥3 enquiries in 60 days |
| `tranche_not_requested` | ≥30 days past expected request date |
| `contactability_decay` | ≥2 failed contacts in 60 days |
| `adverse_event` | event present — no threshold, it either happened or didn't |

**Design decisions worth remembering**

**`signal_type` is the rule name, not the specific transition.** `"dpd_bucket_movement"`, never `"std_to_SMA0"`. Ten rules must stay ten types — otherwise suppression, case typing and evaluation counts all have to group them back together.

**Guard clauses first.** Handle the absent case up front so the rest of the function can assume real data:

```python
    if facts.days_to_moratorium_end is None:
        return None
```

**Name the business conditions.** `repeat` and `struggling` rather than one unreadable `if` — the code then reads like the policy document.

**Don't hardcode a threshold that lives elsewhere.** The DPD rule calls `bucket_of()` instead of comparing to `30`. Two copies of a threshold will drift.

**Rules reuse rules.** `check_drift_with_bounce` calls `check_payment_date_drift`. One definition of "drift".

**One concern per rule.** A zero payment is a *bounce* (rule 2), never a *part payment* (rule 5). Two rules on one fact means two signals, two cases, double-counted work.

**The evaluator — rules as a list of functions:**

```python
_RULES = [check_dpd_bucket_movement, check_bounce_pattern, ...]

def evaluate(facts: AccountFacts) -> list[Signal]:
    fired = []
    for rule in _RULES:
        signal = rule(facts)
        if signal is not None:
            fired.append(signal)
    return fired
```

In Python a **function is a value** you can store in a list. Adding rule 12 means adding one name to `_RULES`; `evaluate` never changes.

**Why `CohortSignal` is a separate type.** `Signal` requires an `account_id`. A cohort signal isn't about one account — you'd have to leave that field blank, and a blank required field is a lie in your data. *Different unit of work, different type.*

**Bugs caught against real data**

| Symptom | Cause | Fix |
|---|---|---|
| `moratorium_ending` fired 7,000 times | `days <= 75` is **true for negative numbers** — every loan whose moratorium ended years ago | `0 <= days <= 75` |
| `part_payment` fired 2,027 times | moratorium accounts pay interest only, so paid ÷ EMI ≈ 0.35 | skip the rule during moratorium |
| `bureau_deterioration` fired every month | bureau data is **quarterly**; the same comparison was re-reported in April, May and June | only read a snapshot from the last month — a signal from periodic data fires on the **refresh**, not on every batch run |
| `institution_event` fired 185 times | a **count with no denominator**. 5 of 400 is normal; 5 of 12 is a story | compare the institution's flag rate to the portfolio's, require ≥2× |

That last fix took cohort signals from 185 to **4 — exactly the four institutions seeded with problems** (103, 142, 172, 238), with nothing in the code knowing which they were.

**DSA content**

- **`Counter`** — counts occurrences in **O(N)**, one pass.
- **Set for de-duplication.** `len(types) == len(set(types))` checks uniqueness in O(N); comparing every pair would be O(N²).
- **Generator expression** `(f.institution_id for f in flagged)` produces values one at a time instead of building an intermediate list — O(1) extra memory instead of O(N).
- **Negative indexing** `ratios[-2:]` — last two items, no length arithmetic.
- **`all(...)`** short-circuits: stops at the first `False`.

---

## 5 · `src/nbfc_ews/db/engine.py` and `config.py`

```python
# config.py
DATABASE_URL = os.environ.get("EWS_DATABASE_URL", "postgresql://...")

# db/engine.py
def connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
```

**Why config is separate:** production, staging and your laptop point at different databases. The code stays identical; only the environment differs. A hardcoded password in a file that goes into git is how credentials leak.

**Why one `connect()`:** when you later add pooling or `SET LOCAL` for row-level security, you change **one file** and nothing else.

**Packaging note.** `pytest` finds `nbfc_ews` because of `pythonpath = ["src"]` in `pyproject.toml` — but that's pytest-only. For the REPL and for scripts you need a real install:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

```
pip install -e .      # -e = editable: points at your source, no reinstall after edits
```

---

## 6 · `src/nbfc_ews/db/repositories/accounts.py`

**Job:** turn database rows into `AccountFacts`. This is the only place SQL exists.

**The shape — one main query plus six lookup maps:**

```python
def load_account_facts(conn, as_of) -> list[AccountFacts]:
    bounce_map   = load_bounce_facts(conn, as_of)     # {loan_id: (bounces, retries)}
    payment_map  = load_payment_facts(conn, as_of)    # {loan_id: (days, ratios)}
    bureau_map   = load_bureau_facts(conn, as_of)     # {loan_id: (score, prev, enq)}
    tranche_map  = load_tranche_facts(conn, as_of)    # {loan_id: days_past}
    contact_map  = load_contact_facts(conn, as_of)    # {loan_id: failed}
    interest_map = load_interest_facts(conn, as_of)   # {loan_id: months}

    cur = conn.execute(_FACTS_SQL, {"as_of": as_of})

    facts = []
    for loan_id, account_no, institution_id, dpd, dpd_last, in_mor, days_to_end in cur.fetchall():
        bounces, retries = bounce_map.get(loan_id, (0, 0))
        ...
        facts.append(AccountFacts(...))
    return facts
```

**Why this shape and not one big join**

Eight `left join`s over 2 million rows, written blind, will be wrong somewhere and you won't know which part. Each query is small, separately runnable, and separately verifiable against the real book.

**The join key.** Every helper is keyed by `loan_id`, so the main query must also select `l.id`. *When you merge two result sets, both must carry the same key.* That's why `l.id` appears in the select list even though no rule uses it.

**Why helpers return plain dicts, not `AccountFacts`.** A bounce query knows nothing about DPD. To build an `AccountFacts` there you'd have to invent the other fields. **Build a domain object once, when every field is known.** Everything before that is plain data.

**SQL techniques used**

| Technique | What it does |
|---|---|
| `%(as_of)s` | a **parameter placeholder**. psycopg sends the value separately from the SQL text. Never build SQL with f-strings — that's SQL injection |
| `left join` + `coalesce(x, 0)` | keep rows that have no match, and turn the resulting `NULL` into a usable default |
| `group by` + `count/max/sum` | collapse many child rows into one row per loan |
| `with x as (...)` — **CTE** | a named temporary result, so a complex query reads top-to-bottom instead of inside-out |
| `date_trunc('month', d)` | 14-Mar → 01-Mar, so a whole month groups together |
| `extract(day from d)` | 14-Mar → `14` |
| `array_agg(x order by m)` | collect values into a list in a chosen order |
| `distinct on (k) ... order by k, d desc` | **latest row per group** — the single most useful Postgres pattern |
| `nullif(emi, 0)` | turn a zero into `NULL` so a division can't crash |
| `>=` and `<`, never `between` | half-open ranges avoid a boundary date landing in two windows |

**DSA content — this is the important one**

```python
bounces, retries = bounce_map.get(loan_id, (0, 0))     # O(1)
```

versus the naive alternative:

```python
for f in facts:
    row = conn.execute("select ... where loan_id = %s", [f.loan_id])   # 10,000 queries
```

**One query + 10,000 dict lookups ≈ milliseconds. 10,000 queries ≈ minutes.**

This is the *hash map instead of repeated search* pattern, and it's the same idea behind the classic "two-sum" interview question. Build the index once, then look up in O(1).

`.get(key, default)` matters too: most loans aren't in most maps, and `.get` handles that without an `if`.

---

## 7 · `src/nbfc_ews/engine/detect.py`

**Job:** run the whole book for one month.

```python
@dataclass(frozen=True)
class DetectionRun:
    as_of: date
    accounts_scanned: int
    signals: list[Signal]
    cohort_signals: list[CohortSignal]

def detect(conn, as_of: date) -> DetectionRun:
    facts = load_account_facts(conn, as_of)

    signals, flagged = [], []
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

**Why return an object, not a list.** A batch run needs `as_of` and `accounts_scanned` next to its output — for the run record, for tracing, for the evaluation harness. A bare list loses all of that.

**`extend` vs `append`.** `append` adds **one item**; `extend` adds **every item** of a list. `evaluate` returns a list, so `extend`.

**`flagged` is the cohort input.** Accounts that fired *anything*. Five flagged accounts at one institution is a pattern; five accounts merely existing there is not.

**The cohort rule and its Big-O**

```python
flagged_counts = Counter(f.institution_id for f in flagged)        # O(F)
total_counts   = Counter(f.institution_id for f in all_accounts)   # O(N)
base_rate      = len(flagged) / len(all_accounts)

for institution_id, n in flagged_counts.items():                   # O(I)
    total = total_counts[institution_id]                           # O(1)
    rate = n / total
    if n >= 5 and rate >= 2 * base_rate:
        ...
```

**Total: O(N).** The naive version —

```python
total = len([f for f in all_accounts if f.institution_id == institution_id])
```

— rescans all 9,939 accounts for **every** institution: O(I × N) ≈ 2.5 million steps versus 10,000. **250× slower for the same answer.**

**O(N) is the floor.** You must examine every account at least once to count it, so no algorithm can do better. Collapsing two passes into one is still O(N) — a constant-factor change not worth the loss of readability.

> Improve the **order** always. Chase constants only after measuring.

---

## Day 1 results, on the real 10,000-loan book

```
as_of 2026-06-01
9,939 accounts scanned  →  2,960 signals  →  4 cohort cases

bounce_pattern        1,184
moratorium_ending       552
dpd_bucket_movement     513
contactability_decay    385
tranche_not_requested   320
part_payment              6
bureau_deterioration      — (fires only in the month the quarterly scrub lands)

103   86 of 136 flagged (63% vs portfolio 19%)
142   95 of 145 flagged (66% vs portfolio 19%)
172   67 of 134 flagged (50% vs portfolio 19%)
238   93 of 130 flagged (72% vs portfolio 19%)
```

The four cohort cases are **exactly the four institutions seeded with problems**. Nothing in the code was told which they were.

---

## Known gaps carried into Day 2

Four rules cannot fire — all **data** gaps, not code gaps:

| Rule | Missing |
|---|---|
| `payment_date_drift` | the generator always pays at month end |
| `drift_with_bounce` | depends on drift |
| `interest_not_serviced` | `overdue_interest` is never > 0 during moratorium (163,426 eligible months, zero unserviced) |
| `adverse_event` | no source table exists |

These are the **behavioural** signals — the ones that see trouble years before DPD moves. A demo without them shows a system that only catches what conventional EWS already catches. **Action: regenerate the book with these behaviours present.**

---

## The ten habits from Day 1

1. **Restart the REPL after editing a file.** Python loads a module once per session. A stale module produced two confusing debugging sessions today.
2. **Read the error message to the end.** `AttributeError: 'Event' object has no attribute 'types'` names the exact problem.
3. **Never guess at string values in data.** `select status, count(*) group by 1` before writing any `where status = ...`.
4. **A linter warning is a hypothesis.** Confirm with a second tool before silencing it, and never add a `cast` to quiet a false positive.
5. **A trailing comma makes a tuple.** `x = 5,` is `(5,)`. The most common invisible Python bug.
6. **Verify each layer against real data before adding the next.** Every one of today's five signal bugs was found by looking at counts, not by reading code.
7. **Gather failures, assert once.** An `assert` inside a loop stops at the first problem; a list of failures reports them all.
8. **A count needs a denominator.** 185 false positives became 4 true ones by dividing.
9. **Build the index once, look up in O(1).** The difference between milliseconds and minutes.
10. **A test that goes green because you deleted the thing it tested is worse than a red test.**
