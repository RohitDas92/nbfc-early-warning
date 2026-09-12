# 09 — Evaluation Design

Designed alongside the system, not after it. If you can't say how a run would be scored, the design isn't finished.

Companion diagram: `09-evaluation-design.svg`.

---

## 1. The headline: two arms, one book

Every evaluation runs the **same portfolio, as of the same date, twice**:

- **Rules-only arm** — the deterministic engine alone. Signals fire, cases open, no investigation, no recommendation beyond the signal itself.
- **Full arm** — rules plus the agentic layer.

The difference between them is the measured contribution of the agents. Without this, every number you quote is unanchored and the honest answer to "how do you know the agents helped?" is that you don't.

**This is the single most valuable thing in the evaluation.** Build the rules-only arm first — it's also the simpler half.

## 2. Datasets

| Dataset | What it is | Rule |
|---|---|---|
| **Book A** — seed `20260910` | Development. Loaded and in use | Tune freely |
| **Book B** — different seed | Held out | **Not opened until W4.** One look and it stops being held out |
| `eval.labels` | The answer key: pattern, onset month, whether it reached NPA and when | The pipeline must never read it |
| **Golden case set** | ~60 fixed cases sampled across every pattern and both confounder types | The regression suite |
| **Trajectory fixtures** | Recorded model and tool responses for ~20 cases | Makes CI deterministic and free |

## 3. Metrics, defined precisely

Vague metrics are worse than none. Each of these has an exact numerator and denominator.

### Outcome metrics

**Early detection rate** *(primary)*
Of loans that reached NPA, the share where a case was opened **≥90 days before** `first_npa_month`.
Report twice: **overall**, and **excluding `random_default`** — the second is the detectable subset, and the gap between them is your realistic ceiling.

**Precision**
Of cases where the recommendation was to act, the share whose loan actually reached 30+ or NPA within six months.

**Confounder false-positive rate** — *the sharpest number you have*
Of the 200 confounder loans (`mandate_failure`, `salary_shift`, `self_funded`), the share that received an "act" recommendation. These are designed to look exactly like deterioration and to resolve on their own. **A system that can't tell them apart is producing noise**, and this single number says whether it can.

**Cohort discovery**
For each of the four planted institutions: was a cohort case raised, and how many days after the institution event? Four data points, but it's the capability nothing else has.

**Suppression ratio**
Signals raised ÷ cases created. Should land near the modelled 240 → 60–80.

### Trajectory metrics — deterministic, every case

| Check | Passes when |
|---|---|
| `citation_present` | Every conclusion carries at least one evidence item |
| `citation_resolvable` | Every evidence item's `tool_call_id` exists in the trace |
| `budget_respected` | Steps and tool calls within limits |
| `action_permitted` | Recommendation is in the allowed set for the case type and authority |
| `terminated_cleanly` | Final status is complete, complete-with-gaps, or escalated — never dangling |
| `no_egress_violation` | The PII gate never had to refuse anything |

These cost nothing, run on every case, and catch most regressions. **They are what gates CI.**

### Operational metrics

Cost per case, tokens by node, p50 and p95 latency, share of cases escalated, share completed with gaps.

## 4. The three layers, in build order

**Layer 1 — deterministic checks.** The trajectory table above. Build first, run always.

**Layer 2 — labelled golden set.** Join case outcomes to `eval.labels`, compute the outcome metrics. Build second.

**Layer 3 — LLM as judge.** Only for what the other two can't reach: is the narrative coherent, is the reasoning defensible, does the recommendation follow from the evidence.

**Validate the judge before trusting it.** Score 30 cases yourself, run the judge on the same 30, and report the agreement rate. If it agrees with you less than ~80% of the time, the judge's numbers are decoration. Almost nobody does this step, and saying you did is a strong signal.

## 5. How a run works

1. Choose dataset, as-of date, and arm.
2. Run the pipeline. Cases and traces are produced.
3. Score Layer 1 on every case.
4. Join to labels; compute Layer 2.
5. Sample for Layer 3.
6. **Write a run record** capturing: git SHA, dataset seed, arm, model versions, prompt versions, all metrics.

Step 6 is what makes results reproducible and comparable. A metric without the run record behind it is an anecdote.

## 6. Evaluation schema

Separate `eval` schema. The pipeline reads none of it.

| Table | Holds |
|---|---|
| `eval.labels` | The answer key *(already loaded)* |
| `eval.run` | id, started_at, git_sha, dataset_seed, as_of_date, arm, model_versions, prompt_versions |
| `eval.run_case` | run_id, case_id, loan_id, recommendation, confidence, status, steps, cost, latency_ms |
| `eval.check` | run_id, case_id, check_name, passed, detail — Layer 1 results |
| `eval.metric` | run_id, metric_name, value, numerator, denominator — Layer 2 |
| `eval.judgement` | run_id, case_id, criterion, score, rationale — Layer 3 |

## 7. The CI gate

On every pull request, against the 20-case fixture set with recorded responses:

- **All Layer 1 checks must pass.** Any failure fails the build.
- **Layer 2 regression thresholds:** early detection must not fall more than 3 points; confounder false-positive rate must not rise more than 3 points.

Deterministic, free, and fast — because it runs on fixtures, not live models.

This is also what makes `git bisect` work. When a number moves and you don't know which commit did it, the eval gate is a valid bisect predicate.

## 8. Ways to fool yourself

Worth writing down, because all of them are easy and all of them are tempting.

- **Tuning on the held-out book.** One look and Book B is just Book A with extra steps.
- **Reporting recall without precision.** Flag everything and early detection hits 100%.
- **Excluding the hard cases.** `random_default` belongs in the denominator — it's what keeps a perfect score impossible.
- **An unvalidated LLM judge.** Numbers with no known relationship to human judgement.
- **A single number with no control arm.** "87% detection" means nothing without the rules-only figure beside it.
- **Scoring only final answers.** A right answer reached by a broken path breaks tomorrow.

## 9. What you'll be able to say

> *"Same book, same date, two arms. Rules-only detects X% of eventual NPAs 90 days out; rules plus agents detects Y%. On the 200 planted confounders — accounts engineered to look like deterioration and then self-cure — the agentic arm recommends action on Z% against the rules arm's W%. Every case carries six deterministic trajectory checks that gate CI, and the LLM judge was validated against 30 of my own labels before I used any of its scores."*

That is a different conversation from showing someone a demo.
