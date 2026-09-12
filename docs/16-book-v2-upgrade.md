# Book v2 — what changed and how to load it

Regenerated 11 Sep 2026 so that the four rules that could not fire now have data
to find. Same seed, same size, same AUM — but four behaviours are now present.

---

## 1. What changed in the generator

| # | Change | Why |
|---|---|---|
| 1 | **Mandate day spread across the month** (2nd, 3rd, 5th, 7th, 10th, 12th) instead of every loan paying on the 30th | payments now land on 31 distinct days. Drift is only visible if there is somewhere to drift *to* |
| 2 | **New `payment_drift` pattern (5% of the book)** — the borrower's payment lands 2, 6, 10, 14 days later each month, then starts bouncing after month 4. Stressed borrowers under any pattern also drift a little before they bounce | makes `payment_date_drift` and `drift_with_bounce` fire, and gives them genuine lead time over `bounce_pattern` |
| 3 | **Unserviced moratorium interest** — when an interest-servicing presentation fails during moratorium, the amount is carried as an arrear in `loan_month_state.overdue_interest`. It deliberately does **not** move DPD | makes `interest_not_serviced` fire while keeping DPD structurally zero — the blind spot the project exists to close |
| 4 | **Part payments** — a stressed borrower whose NACH bounced sometimes pays 35–85% of the EMI by hand (`payment.mode = 'manual'`). The arrear is **not** cured, so DPD keeps running | makes `part_payment` fire. Servicing without solvency |
| 5 | **New `adverse_event` table** — `visa_rejected`, `student_returned`, `course_discontinued`, reported by institution, co-applicant, borrower or field visit | makes `adverse_event` fire. These are reported facts, not inferences, and they arrive years before DPD |
| 6 | `loan.mandate_day` column added | the NACH presentation day, needed to reason about drift |
| 7 | Retries capped at 2 on high-stress accounts (was always 3) | a hopeless mandate is not re-presented three times |
| 8 | `eval.labels` now carries `adverse_event_type` and `adverse_event_date` | the answer key must know which accounts had a reportable event |
| 9 | Indexes added on `payment(loan_id, payment_date)`, `contact_attempt(loan_id, attempt_date)`, `adverse_event(loan_id, event_date)` | the repository queries hit these every run |

**Re-tuned** so the book still looks like a real NBFC: `BASE_BOUNCE_P` 0.040 → 0.028,
stress coefficient 0.45 → 0.55.

---

## 2. Book characteristics

| Metric | v1 | v2 | Target |
|---|---|---|---|
| Loans | 10,000 | 10,000 | 10,000 |
| AUM (sanctioned) | ₹1,006 cr | ₹1,006 cr | ~₹1,000 cr |
| Foreign share | 20% | 20% | 20% |
| In moratorium | 30% | 30% | 30% |
| Bounce rate | 10.7% | **9.8%** | 9–11% |
| GNPA | 2.51% | **3.16%** | realistic for education loans |
| Payment days used | 2 | **31** | spread |
| Adverse events | — | **293** | — |
| Manual part payments | — | **2,120** | — |

---

## 3. How to load it

The schema changed, so this is a **drop and reload**, not a migration.

```
docker exec -it <container> psql -U postgres -c "drop database ews"
docker exec -it <container> psql -U postgres -c "create database ews"

python load.py --dsn "postgresql://postgres:postgres@localhost:5432/ews" --schema --data
```

Unzip both parts into the same folder first — `gen/out/` must contain all 17 `.csv.gz` files.

---

## 4. One code change you need

`adverse_event` is a new table, so `accounts.py` needs a query for it.

```python
_ADVERSE_SQL = """
select distinct on (a.loan_id)
    a.loan_id,
    a.event_type
from adverse_event a
where a.event_date <= %(as_of)s
  and a.event_date >  (%(as_of)s::date - interval '12 months')
order by a.loan_id, a.event_date desc
"""


def load_adverse_facts(conn, as_of) -> dict[int, str]:
    """The most recent reported adverse event per loan, within the last year."""
    cur = conn.execute(_ADVERSE_SQL, {"as_of": as_of})
    return {loan_id: event_type for loan_id, event_type in cur.fetchall()}
```

Wire it in exactly like the others:

```python
    adverse_map = load_adverse_facts(conn, as_of)
    ...
                adverse_event=adverse_map.get(loan_id),
```

**Two things worth noticing in that query.** `distinct on (a.loan_id) ... order by a.loan_id, a.event_date desc` is the same *latest row per group* pattern as the bureau query. And the 12-month window stops a visa rejection from 2023 flagging an account forever — a reported event is news when it is reported, not for the rest of the loan's life.

---

## 5. What you should see after reloading

```
=== 2026-06-01  accounts=9,951  signals=3,651  cohort=4
   bounce_pattern              1,421
   dpd_bucket_movement           617
   moratorium_ending             556
   contactability_decay          463
   tranche_not_requested         326
   interest_not_serviced         108     ← new
   adverse_event                  62     ← new
   part_payment                   44     ← new
   payment_date_drift             41     ← new
   drift_with_bounce              13     ← new
   bureau_deterioration            —     (quarterly; fires in the scrub month)

   COHORT 238: 85 of 137 (62% vs 22%)
   COHORT 142: 83 of 131 (63% vs 22%)
   COHORT 172: 94 of 152 (62% vs 22%)
   COHORT 103: 96 of 145 (66% vs 22%)
```

All eleven account rules fire, and the cohort rule still finds **exactly** the four
seeded institutions with nothing in the code knowing which they are.

Verified end to end against PostgreSQL 16 before shipping: schema applied, 2.1M rows
loaded, every foreign key and check constraint held, and the full pipeline run for
three consecutive months.

---

## 6. Still to do

**A second book with a different seed**, held out until W4 so the evaluation has a
book the rules were never tuned against. Change `SEED` at the top of `generate.py`
and regenerate — nothing else needs to change.
