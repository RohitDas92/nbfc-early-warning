# 10 — Testing Strategy

What gets tested, at which level, for every part of this system. Written before the code so the tests aren't retrofitted.

---

## 1. The problem specific to this project

Most of this system is ordinary software and tests normally. One part doesn't: **you cannot unit test a language model.** Same input, different output, and the output is prose.

The resolution is the single most important idea here:

> **You don't test the model. You test the machinery around it.**

Did the supervisor pick the right investigators? Did an evidence-free finding get rejected? Did the budget stop a runaway? Did two contradicting findings trigger arbitration? Did the gate withhold an uncited recommendation? Every one of those is deterministic — *if you can control what the model returns*.

Which you can, with a fake.

## 2. The five levels

| Level | Runs against | Speed | Count |
|---|---|---|---|
| **Unit** | Nothing — pure functions | milliseconds | many |
| **Contract** | Test database, tool layer only | fast | one per tool |
| **Integration** | Real Postgres, small fixture book | seconds | tens |
| **Agent** | The graph, with a fake model | fast | tens |
| **Eval** | Fixture cases, Layer 1 checks | fast | gates CI |

```
tests/
  unit/           pure logic, no I/O
  contract/       tool schemas and limits
  integration/    needs Postgres
  agents/         the graph, with FakeChatModel
  eval/           Layer 1 checks on fixtures
  fixtures/       fixture book, cassettes, golden cases
  conftest.py
```

`pytest -m "not integration"` is the loop you run every few minutes and it must stay under five seconds. The full suite runs in CI.

## 3. Unit tests — table-driven, and most of your coverage

Everything here is a pure function. No database, no clock, no randomness.

| Module | Test |
|---|---|
| **Classification** | `dpd → bucket → asset_class`. A table with the boundaries: 0, 1, 30, 31, 60, 61, 90, 91. Off-by-one at a bucket edge is a real bug with regulatory consequences |
| **Signal rules** | Each of the ten rules gets a **fires** case and a **does not fire** case, at the threshold and just under it |
| **Case router** | `(signal, open_cases) → open | join | escalate`. The full decision table as one fixture, including a signal arriving on a snoozed case |
| **State machine** | `(from_state, event) → to_state`, **including every illegal combination, which must raise** |
| **Tokenisation** | `detokenise(tokenise(x)) == x`, and `tokenise(x)` contains no PII pattern |
| **Authority rules** | `(action, role, amount) → permitted | denied`, and `recommender != approver` |
| **Finding validation** | A finding with no evidence is rejected. Evidence with no `as_of` is rejected |

**Write these as parameterised tables, not as separate test functions.** Twenty rows in one table beats twenty near-identical functions, and adding the twenty-first case costs one line.

## 4. Contract tests — one per tool

Every tool gets the same five assertions:

1. Returns the declared schema
2. Respects its row limit and reports what it omitted
3. Every returned record carries `as_of`
4. On a bad input it returns `{ok: false, reason}` — **it does not raise**
5. Called with a principal scoped to branch 1, it returns nothing from branch 2

Number five is the one that matters. It's the test that proves the agent isn't a way around access control.

## 5. Integration tests — real Postgres, small book

**Use a fixture book, not the real one.** Generate ~50 loans with the same generator at small `N` and a fixed seed. Two million rows in a test suite is how a suite becomes something people skip.

| What | Assertion |
|---|---|
| Nightly batch | Over the fixture book, produces the expected signal counts per type |
| Suppression | N signals across M accounts produce the expected number of cases |
| RLS | `app_rw` scoped to branch 1 sees only branch 1; unset sees **zero** |
| PII grant | `app_rw` selecting from base `party` raises a permission error |
| Migrations | Apply cleanly to an empty database, and a closed case with no outcome is **rejected by the constraint** |
| API | The role × endpoint × scope matrix, asserting each 403 |

**CI rule: a new endpoint without an authz test fails the build.** Authorization that isn't tested is an intention, not a control.

## 6. Agent tests — the fake model is the unlock

```
FakeChatModel(responses=[...])   # returns them in order, deterministically
```

With that, every path becomes testable:

| Scenario | Assertion |
|---|---|
| Case type X | Supervisor selects the expected investigators |
| Model returns invalid JSON | One repair attempt, then finding = `inconclusive`. **Never coerced** |
| Two findings contradict | Conflict detected, arbitration node runs |
| Budget exceeded | Case escalates with partial findings — does **not** silently truncate |
| Same investigator, same input hash | Cycle guard refuses the second invocation |
| Tool returns an error | Recorded as a gap; the case continues |
| Policy finds no clause | Refuses to recommend, escalates |
| Recommendation lacks a citation | Gate withholds it |
| Interrupt fires | State checkpoints; resuming continues rather than restarting |

Nine tests, no API calls, no cost, and they cover every failure mode in the design.

**Record-and-replay for the realistic runs.** Capture real model and tool responses once into cassettes, replay them in CI. That gives you end-to-end runs that are deterministic and free — and it's what the eval fixture set is built on.

## 7. The architecture test

From risk #1, and it's ten lines:

```
the deterministic engine module must not import the model client,
directly or transitively — fail the build if it does
```

This is what stops someone quietly moving case routing into the agentic layer in three weeks, long after this conversation is forgotten.

## 8. What not to test

**Never assert on generated prose.** Not the narrative wording, not the case note phrasing. Assert that citations exist, that the recommendation is in the permitted set, that the structure is valid. Test the wording and every prompt improvement breaks the suite, so people stop improving prompts.

Also skip: third-party library behaviour, and the model's judgement quality — that's what the evaluation is for, and it's a different thing from a test.

## 9. Coverage that means something

Percentage coverage is a weak target. These are the rules worth holding:

- Every signal rule: one firing, one not-firing test
- Every state transition, **including the illegal ones**
- Every tool: happy path and error-as-value
- Every role × endpoint × scope combination
- Every agent failure path in §6

If those hold, the percentage takes care of itself.

## 10. Order of writing

Tests come with the code, in the same PR — that's what the "Eval impact" section of the PR template is for.

Start with the **state machine** and the **classification** tables. Both are pure, both are quick, and both are where a silent bug is most expensive.
