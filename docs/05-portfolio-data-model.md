# 05 — Portfolio Data Model

The book half of the schema — loans, parties, repayment, history, signals. Agent-independent, so it can be built now. The case half comes after the agentic design.

This is a specification, not DDL. Column lists are the ones that carry meaning; add the housekeeping ones as you build.

---

## 1. Reference

**`institution`** — the cohort anchor. Everything in the institution-risk story depends on this being a real table rather than a string on the loan.
`id` · `name` · `country` · `is_foreign` · `city` · `institution_type` · `accreditation_status` · `created_at`

**`institution_event`** — what makes an institution go bad, and when.
`id` · `institution_id` · `event_date` · `event_type` (`accreditation_lapse` | `closure` | `placement_decline` | `fee_hike`) · `severity` · `source` · `notes`

**`branch`** — carries the access-control scope.
`id` · `code` · `name` · `region`

## 2. Parties — and how PII is protected

**`party`** — one table, all attributes, identifying and not.
`id` · `party_type` · `full_name` · `pan` · `aadhaar_masked` · `phone` · `email` · `address` · `dob` · `gender` · `occupation` · `employer_name` · `monthly_income` · `created_at`

This matches reality: in a real LOS the customer master carries PII inline, and this system reads from it rather than redesigning it.

**Protection is by grant, not by schema shape.** The base table is owned by a restricted role. The application reads views:

- **`v_party`** — every column except the identifying ones. The default for all application code, every investigator, every batch job.
- **`v_party_full`** — includes identity. A separate grant, held only by roles that legitimately need it: the analyst UI showing who to call, and audit.

Views rather than column-level `GRANT SELECT (col…)` deliberately — column grants break `SELECT *` and will fight the ORM on every query. Views give the same property with none of that friction: **code without the grant cannot see identity, and the failure is a permission error rather than a silent leak.**

This is also the honest enterprise answer. PII stays in the customer master where it belongs; the risk system reads a masked view; the unmasked view is a separate grant tied to a role.

**A PII column registry lives in code** — an explicit list naming `full_name`, `pan`, `aadhaar_masked`, `phone`, `email`, `address` as identifying, and `monthly_income`, `dob`, `employer_name` as not. The tokenisation layer at the model boundary reads that registry. Deriving it from table membership would be a shortcut that stops being true the first time the schema changes.

**`loan_party`** — links parties to loans with a role. Not a `co_applicant_id` column on the loan; education loans can have more than one co-applicant, and a guarantor is a third shape.
`loan_id` · `party_id` · `role` (`borrower` | `co_applicant` | `guarantor`) · `is_primary_earner`

## 3. Loan and disbursement

**`loan`**
`id` · `loan_account_no` (unique, business key) · `branch_id` · `institution_id` · `product` (`domestic` | `foreign`) · `sourcing_channel` · `course_name` · `course_level` (`UG` | `PG` | `diploma`) · `course_duration_months` · `sanction_amount` · `interest_rate` · `tenure_months` · `sanction_date` · `moratorium_end_date` · `repayment_start_date` · `interest_servicing_required` (bool — drives the moratorium-interest signal) · `status` · `created_at`

`branch_id` is here because it is the row-level access scope. Every read of this table is filtered by it.

**`tranche`** — the source of the strongest early signal in the book.
`id` · `loan_id` · `sequence_no` · `expected_date` · `expected_amount` · `requested_date` (nullable) · `disbursed_date` (nullable) · `disbursed_amount` · `status` (`pending` | `requested` | `disbursed` | `lapsed`)

A null `requested_date` past `expected_date` is "tranche not requested". That single nullable column is worth more than most of the rest of the schema.

## 4. Repayment

**`repayment_schedule`**
`id` · `loan_id` · `installment_no` · `due_date` · `principal_due` · `interest_due` · `total_due`

**`presentation`** — every NACH attempt, successful or not. The bounce signals read from here.
`id` · `loan_id` · `schedule_id` · `presentation_date` · `amount` · `status` (`success` | `bounce`) · `bounce_reason` · `retry_sequence` · `mandate_id`

`bounce_reason` matters more than it looks — a mandate registration failure and insufficient funds are the same event with completely different meanings, and telling them apart is half the triage.

**`payment`** — money actually received, including outside NACH.
`id` · `loan_id` · `payment_date` · `amount` · `mode` · `principal_allocated` · `interest_allocated` · `paid_by_party_id` (nullable — a third party paying is itself a signal)

## 5. Monthly state — the most important table here

**`loan_month_state`** — one row per loan per month.
`loan_id` · `as_of_month` (first of month) · `pos` · `overdue_principal` · `overdue_interest` · `dpd` · `bucket` · `asset_class` (`standard` | `SMA0` | `SMA1` | `SMA2` | `NPA`) · `is_in_moratorium` · `avg_monthly_balance` · `installments_due_to_date` · `installments_paid_to_date`

10,000 loans × 48 months is about 480,000 rows. Postgres will not notice. **Do not partition it.**

Everything roll-related derives from this table: roll-forward and roll-back rates, the transition matrix, flow rates by segment.

**Deliberately absent: a roll-rate table.** Derive transitions with a window function over `loan_month_state` — comparing each loan's bucket to its own previous month. Storing them creates a second source of truth that will disagree with the first. Materialise later only if a query is actually slow.

## 6. External observations

**`bureau_snapshot`** — point-in-time, per party. Never overwrite; a new row each time.
`id` · `party_id` · `as_of_date` · `score` · `active_accounts` · `enquiries_last_60d` · `total_monthly_obligations` · `worst_dpd_elsewhere` · `pull_type` (`periodic` | `on_demand`)

Score *movement* is the signal, which is only computable if you keep history. This is why it's a snapshot table, not columns on `party`.

**`contact_attempt`**
`id` · `loan_id` · `attempt_date` · `channel` · `outcome` (`connected` | `no_answer` | `invalid_number` | `bounced`)

## 7. Signals and interventions

**`signal`** — output of the deterministic engine.
`id` · `signal_type` · `loan_id` (nullable) · `institution_id` (nullable) · `as_of_date` · `severity` · `detail` (jsonb) · `case_id` (nullable, filled by the router) · `created_at`

One of `loan_id` or `institution_id` is set — account signals and cohort signals both live here.

**`intervention`** — build this now, in the first migration, even though cases don't exist yet.
`id` · `loan_id` · `case_id` (nullable) · `action_type` · `actioned_by` · `actioned_at` · `authority_level` · `notes`

`case_id` is nullable because the generator produces years of historical interventions that predate any case. Those are what the recommendation engine learns from on day one — which is exactly why this table cannot wait.

## 8. Conventions

- **Money is `NUMERIC(15,2)`. Never float.** A rounding error in a provisioning figure is not a bug you get to explain away.
- Timestamps are `TIMESTAMPTZ`; business dates are `DATE`.
- `as_of_month` is always the first of the month, so month comparisons are date comparisons.
- Surrogate `BIGINT GENERATED ALWAYS AS IDENTITY` primary keys; business keys (`loan_account_no`) are unique constraints, not primary keys.
- Every table gets `created_at`.
- Enumerations as Postgres enum types or check constraints — not free text.

## 9. Indexes that will matter

`loan_month_state (loan_id, as_of_month)` and `(as_of_month, bucket)` · `presentation (loan_id, presentation_date)` · `tranche (loan_id, expected_date) where requested_date is null` · `signal (as_of_date, signal_type)` and `(case_id)` · `bureau_snapshot (party_id, as_of_date desc)` · `loan (branch_id)` for the RLS predicate.

Add them with the tables, not after a slow query.

## 10. What to build

1. Alembic set up, with this as **migration 001** — including `intervention`.
2. The tables above, with constraints and indexes.
3. RLS enabled on `loan` and anything joining to it, with the branch/region predicate.
4. `v_party` and `v_party_full`, with the base `party` table not granted to the application role at all.
5. A seed script proving the model holds: one domestic loan and one foreign loan, each with tranches, a schedule, presentations, and 48 months of state.

**Acceptance:** you can answer these three with SQL alone, no application code.

- Bucket counts and POS by asset class for a given month
- The roll-forward and roll-back rate between two months
- Every loan whose next tranche was expected more than 30 days ago and never requested

If any of those is awkward to write, the model is wrong and it's cheaper to find out now.
