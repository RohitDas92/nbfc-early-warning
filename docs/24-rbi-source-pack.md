# 24 — RBI Source Pack

Primary-source extract for the `search_policy` corpus (E5.6).

Everything below was read from rbi.org.in. Each clause carries its circular
number and paragraph so a retrieved chunk can cite where it came from. Nothing
here is paraphrased from a law-firm blog or a news article — those are useful
for orientation and useless as a citation.

Scope: the regulatory areas the surveillance agent touches — DLG, collections
conduct, DPD / asset classification, the EWS mandate, penal charges, credit
information reporting, and borrower data handling.

---

## 1. Default Loss Guarantee (DLG)

**RBI (Digital Lending) Directions, 2025** — RBI/2025-26/36,
DOR.STR.REC.19/21.07.001/2025-26, 8 May 2025.
Applies to commercial banks, UCBs, StCBs, CCBs, NBFCs (incl. HFCs), AIFIs.

This supersedes the standalone June 2023 DLG guidelines — DLG is now a chapter
inside the consolidated Digital Lending Directions.

| Item | Provision | Para |
|---|---|---|
| Definition | Contractual arrangement where a counterparty guarantees the RE against loss from default, up to a specified percentage of the loan portfolio. Implicit guarantees with the same performance linkage also count. | 4(ii) |
| Who may provide | An LSP, or another RE acting as an LSP. Must be incorporated under the Companies Act, 2013. | 18(i) |
| Cap | Total DLG cover on any outstanding portfolio **shall not exceed 5% of the total amount disbursed**. Fixed at portfolio inception; does not move as loans mature or default. | 23 |
| Permitted form | Cash with the RE; FD at a scheduled commercial bank with lien marked to the RE; bank guarantee in favour of the RE. Nothing else. | 22 |
| Tenor | Agreement must run **not less than the longest tenor** of any loan in the underlying portfolio. | 26(ii) |
| Invocation | RE shall invoke DLG within a **maximum overdue period of 120 days**, unless the borrower clears dues first. | 26(i) |
| Non-reinstatement | Once invoked, the DLG amount **shall not be reinstated** — including out of subsequent recovery. | 24(iv) |
| NPA responsibility | The RE remains solely responsible for NPA classification and provisioning **regardless of DLG availability**. | 24(i) |
| Capital | If the DLG provider is itself an RE, it deducts the full outstanding DLG from its capital. | 25(ii) |
| Disclosure | LSP publishes monthly, within 7 working days of month-end: number of portfolios under DLG and the amount of each. Naming the RE is optional. | 27 |
| Not permitted at all | Revolving credit via digital lending; credit cards; loans under CGTMSE / CRGFTLIH / NCGTC government guarantee schemes; NBFC-P2P loans. | 20 |

**Why this matters to the project.** Two clauses have teeth for a surveillance
agent:

- Para 24(i) — DLG cover does **not** change the asset classification. An agent
  must never reason "covered by DLG, so lower risk". Provisioning is unaffected.
- Para 26(i) — the 120-day invocation ceiling is a hard deadline that sits
  *inside* the DPD timeline (NPA lands at 90). Any DLG-backed account crossing
  ~90 DPD is on a clock, and that is a legitimate early-warning trigger.

**Scoping honesty.** These Directions bind *digital lending*. Whether our
education-loan book falls inside depends on origination channel. The corpus
should state the applicability test rather than assume it applies.

---

## 2. Collections conduct

**Outsourcing of Financial Services — Responsibilities of regulated entities
employing Recovery Agents** — RBI/2022-23/108, DOR.ORG.REC.65/21.04.158/2022-23,
12 August 2022.

Para 2, verbatim prohibitions. Agents shall not:

- call the borrower **before 08:00 or after 19:00** for recovery of overdue loans
- engage in intimidation or harassment of any kind, verbal or physical
- publicly humiliate, or intrude upon the privacy of, the borrower's family
  members, referees or friends
- send inappropriate messages by mobile or social media
- make threatening or anonymous calls
- persistently call the borrower
- make false and misleading representations

Para 1–2: the ultimate responsibility for outsourced activity **vests with the
RE**. The RE is answerable for the acts of its service providers, recovery
agents included. Outsourcing the work does not outsource the liability.

**Why this matters.** This is the rule set behind every `FIELD_VISIT`,
`CONTACT_BORROWER` and `HANDOVER_TO_COLLECTIONS` recommendation the agent can
make. "Persistently calling" is not defined numerically — which is exactly why
the recommender needs a documented internal SOP threshold, and why a contact
history showing repeated no-answer attempts is a conduct signal, not just a
reachability signal.

**Watch item (not yet law).** RBI floated draft directions in February 2026
proposing uniform recovery norms across all lender categories. Reported but not
verified against the primary text here. Do **not** put it in the corpus until
the final Directions issue.

---

## 3. DPD, SMA and asset classification

**Prudential norms on Income Recognition, Asset Classification and Provisioning
pertaining to Advances — Clarifications** — RBI/2021-2022/125,
12 November 2021.

### SMA buckets (Para 3)

| Category | Loans other than revolving | Cash credit / overdraft |
|---|---|---|
| SMA-0 | Any amount overdue up to 30 days | Outstanding exceeds limit/DP up to 30 days |
| SMA-1 | > 30 and ≤ 60 days | > 30 and ≤ 60 days |
| SMA-2 | > 60 and ≤ 90 days | > 60 and ≤ 90 days |
| NPA | > 90 days | > 90 days |

### The day-end rule (Para 4)

> "Classification of borrower accounts as SMA as well as NPA shall be done as
> part of day-end process for the relevant date and the SMA or NPA
> classification date shall be the calendar date for which the day end process
> is run."

Worked example given in the circular, due date 31 March 2021:

| Event | Date |
|---|---|
| Flagged overdue | 31 Mar 2021 (at day-end) |
| SMA-1 | 30 Apr 2021 |
| SMA-2 | 30 May 2021 |
| NPA | 29 Jun 2021 |

### Upgradation (Para 10)

> "Loan accounts classified as NPAs may be upgraded as 'standard' asset only if
> entire arrears of interest and principal are paid by the borrower."

Part-payment does not upgrade. Neither does bringing DPD back under 90.

**Why this matters.** This is the single most important document for the
project, and it lands on three places in the code:

1. The DPD arithmetic in the signal rules must use the **day-end calendar date**,
   not a naive `today - due_date`. The circular's own example is the test case.
2. Para 10 kills any "cured" heuristic based on DPD alone. Our
   `find_similar_alerts` outcome labels (`cured` / `stable` / `worsened`) are an
   *internal* analytic construct and must not be worded as if they were asset
   classification.
3. `as_of` discipline maps directly onto the day-end rule — classification is a
   fact *as at a calendar date*, which is precisely the invariant every tool
   already enforces.

---

## 4. The EWS mandate itself

**RBI (Fraud Risk Management in NBFCs) Directions, 2024** — RBI/DOS/2024-25/120,
15 July 2024.

- Applies to NBFCs (including HFCs) in the **Upper Layer, Middle Layer, and
  Base Layer with asset size ≥ ₹500 crore** (Para 1.2.1).
- An EWS framework is **mandatory for Upper and Middle Layer NBFCs only**
  (Para 3.1.1). Base Layer NBFCs are not required to maintain one.
- The framework must set "appropriate early warning indicators for monitoring
  credit facilities / loan accounts", using quantitative and qualitative
  indicators (Para 3.1.3). The Directions deliberately do not publish a closed
  list — the indicator set is the RE's to design and defend.
- Natural justice, Para 2.1.1–2.1.4: a detailed **Show Cause Notice** with
  complete details of the transactions; **not less than 21 days** to respond; a
  **reasoned Order** conveying the decision with the facts and reasons.
- Reporting to RBI immediately and **not later than 14 days** from the date of
  classification (Para 6.2.1).

The parallel Directions for banks and AIFIs — RBI/DOS/2024-25/118, same date —
add the Red Flagged Account construct and a **180-day** outer limit to conclude
the classification-or-clearance process (Para 4.1.5). The NBFC Directions do not
carry an RFA framework.

**Why this matters.** This is the regulatory justification for the entire
project, and it should be the first thing an interviewer hears. Three
consequences for the build:

1. The indicator set being open-ended is a *feature* — it means a defensible,
   documented, versioned rule set is the deliverable, which is what
   `action_policy` and the signal rules already are.
2. "Reasoned Order" and "complete details of transactions" is the regulatory
   name for what the citation guard does. A recommendation the agent cannot
   evidence is not merely poor engineering — it fails Para 2.1.4.
3. The layer test means applicability is a stated assumption of the project:
   our fictional NBFC is Middle Layer. Say so once, in the README, rather than
   implying every NBFC must build this.

---

## 5. Penal charges

**Fair Lending Practice — Penal Charges in Loan Accounts** — RBI/2023-24/53,
18 August 2023, effective 1 January 2024. Applies to banks, UCBs, **all NBFCs
including HFCs**, and AIFIs.

| Rule | Provision | Para |
|---|---|---|
| Charge, not interest | Penalty for non-compliance with material terms shall be treated as **penal charges** and **shall not be levied in the form of penal interest added to the rate of interest**. | 3(i) |
| No capitalisation | **No capitalisation of penal charges** — no further interest computed on such charges. | 3(i) |
| No rate component | REs shall not introduce any additional component to the rate of interest. | 3(ii) |
| Reasonableness | Quantum shall be reasonable and commensurate with the non-compliance, without discrimination within a loan category. | 3(iv) |
| Retail parity | For loans to **individuals for purposes other than business**, penal charges shall not exceed those applicable to non-individual borrowers. | 3(v) |
| Disclosure | Disclosed in the loan agreement and on the website; the borrower is communicated each time a charge is levied. | 3(vi)–(vii) |

**Why this matters.** An education loan to a student is an individual borrower,
non-business — para 3(v) applies directly. More usefully for the build: because
penal charges cannot be capitalised, **the outstanding balance and the arrears
figure must not silently absorb them**. If our seeded book or any derived
`paid_ratio` mixes penal charges into EMI dues, the arithmetic is not just wrong,
it is describing something the regulation forbids. Worth one assertion in the
data-model tests.

---

## 6. Credit information reporting

**RBI (Credit Information Reporting) Directions, 2025** — RBI/DoR/2024-25/125,
6 January 2025. Applies to banks, AIFIs, **NBFCs, HFCs**, ARCs and CICs.

| Item | Provision | Section |
|---|---|---|
| Reporting frequency | CIs and CICs keep credit information updated on a **fortnightly basis** — as on the 15th and the last day of each month — submitted within **7 calendar days** of the reporting fortnight. | 6(1)(b) |
| CIC ingestion | CICs ingest the data received into their databases within **5 calendar days** of receipt. | 16(6) |
| Access alert | CICs send SMS/email alerts to customers when their CIR is accessed by a Specified User. | 16(1) |
| Default alert | **CIs send SMS/email alerts to customers when submitting default / days-past-due information to CICs.** | 16(1) |
| Complaint resolution | Within **30 calendar days** of filing. | 17(1) |
| Compensation | **₹100 per calendar day** beyond the 30-day window. | 17(1) |

**Why this matters — this is the most build-relevant document after IRACP.**
It governs `get_bureau_history` directly:

1. **Bureau data is stale by construction.** Fortnight close + 7 days to submit
   + 5 days to ingest means a bureau score can lag reality by up to ~22 days.
   Our `as_of` discipline already refuses to read forward in time, but the tool's
   *description* should say the score is an as-at-pull-date fact, so the model
   does not treat a score as current-day truth.
2. **A score drop is an event with a knowable date.** `prev_score` / `prev_date`
   and the derived `delta` are exactly the shape the regulation's pull-date model
   implies. The design was right for the wrong reason; now it has a citation.
3. **The default alert in §16(1) is a borrower-facing consequence.** Reporting a
   DPD is not a silent internal act — the borrower gets told. That is a real
   argument for the agent surfacing a bureau-reporting consequence in its
   narrative, and a real reason the evidence behind it has to be right.

---

## 7. Digital lending — borrower protection

Same Directions as §1 (RBI/2025-26/36, 8 May 2025), different chapters. Relevant
where our contact and PII handling is concerned.

| Item | Provision | Para |
|---|---|---|
| Device access | DLAs shall **desist from accessing mobile phone resources** — file and media, contact list, call logs, telephony functions. One-time camera/microphone/location access permitted for onboarding/KYC with explicit consent. | 12(i) |
| Data minimisation | LSPs may store only **basic minimal data** — name, address, contact details. Data-privacy responsibility stays with the RE. | 13(i) |
| Data localisation | Data processed outside India shall be deleted from foreign servers and brought back within **24 hours**. | 13(iv) |
| Granular consent | The borrower can give or deny consent per data item, restrict third-party disclosure, limit retention, and **revoke consent already given**. | 12(ii) |
| Third-party sharing | **Explicit consent before sharing personal information with any third party**, statutory requirements excepted. | 12(iv) |
| Cooling-off | Exit by paying principal and proportionate APR without penalty; minimum one day, board-determined. | 10(i) |
| Key Fact Statement | Per the 15 April 2024 KFS circular, as amended. | 8(i) |
| Credit limit | **No automatic increase** without an explicit borrower request, evaluated and recorded. | 7(ii) |
| Grievance | Nodal officers at both RE and LSP, contact details prominently displayed. | 11(i)–(ii) |
| Ombudsman | Borrower may approach the RBI Ombudsman on rejection, partial rejection, or **no reply within 30 days**. | 11(iv) |

**Why this matters.** Para 12(iv) is the regulatory name for our egress guard.
A tool that returns a borrower's phone number to a model hosted by a third party
is a third-party disclosure. That is why `get_contact_history` returns **counts
and outcomes only** — no numbers, no names, no `loan_id`. The design decision
you made this morning on `EXPECTED_KEYS` has a citation behind it.

Para 12(i) is also a good interview line: the regulator's instinct and ours are
the same — *collect the minimum that answers the question.*

---

## 8. Fair Practices Code — status note

The NBFC Fair Practices Code lives in the **Master Direction – RBI (Non-Banking
Financial Company – Scale Based Regulation) Directions, 2023** (RBI/DoR/2023-24/106,
19 October 2023, updated 17 July 2025). It carries the familiar language on undue
harassment, odd hours, muscle power, training of recovery staff, and the
repossession clause in the loan agreement.

**The primary text could not be read from rbi.org.in in this pass** — the PDF
endpoint serves a CAPTCHA to automated fetches. Nothing from the FPC is quoted
in this pack, and nothing should enter the corpus until the text is read from
the PDF by hand.

In practice this costs little: the 12 August 2022 recovery agents circular (§2)
is more recent, more specific, and operative on the same conduct. Use it. Add
the FPC paragraph numbers later, by hand, from the downloaded PDF.

---

## 9. What is deliberately out of scope

- **FREE-AI framework, DPDP Act** — relevant to the NBFC generally, not to the
  five tools being built. Keep for the interview narrative, not the corpus.
- **Priority sector / education loan interest subsidy schemes** — a product
  matter, not a surveillance matter.
- **Feb 2026 draft recovery norms** — draft. See §2.
- **Release of property documents on closure (Sep 2023)** — secured lending;
  our book is unsecured education loans.
- **Large Exposures Framework (NBFC-UL)** — concentration risk at entity level,
  not account-level surveillance.

---

## 10. How this feeds E5.6

This document is *source material*, not the corpus. The corpus is the internal
SOP prose that an analyst would actually cite, and each SOP section should name
the regulation it derives from using the reference numbers above.

Two layers, deliberately kept apart:

| Layer | Artefact | Job |
|---|---|---|
| Machine-readable | `action_policy`, `waiver_slab` | **Decides.** Effective-dated, versioned, queried by the authority gate. |
| Prose | `search_policy` corpus | **Explains.** Retrieved and cited so a human can see why. |

The table denies the action. The corpus tells the analyst which paragraph of
which circular stands behind the denial. Neither one substitutes for the other,
and the agent must never be able to reach the second without having passed the
first.

### Provisional SOP section list

Each maps to at least one citation above. This is the E5.6 corpus outline.

| # | SOP section | Derives from |
|---|---|---|
| 1 | Contact conduct and permitted hours | §2 — RBI/2022-23/108 para 2 |
| 2 | Escalation ladder and DPD thresholds | §3 — RBI/2021-2022/125 para 3 |
| 3 | What a DPD number means and when it is stamped | §3 — para 4 |
| 4 | Cure, upgrade and what does not count as either | §3 — para 10 |
| 5 | Waiver authority and the absolute prohibitions | internal; penal-charge limits from §5 |
| 6 | Penal charges — what may and may not be added | §5 — RBI/2023-24/53 para 3 |
| 7 | Bureau data — freshness, pull dates, what a drop means | §6 — RBI/DoR/2024-25/125 §6, §16 |
| 8 | Borrower data handling and third-party disclosure | §7 — RBI/2025-26/36 para 12 |
| 9 | DLG-backed accounts — what changes and what does not | §1 — paras 24(i), 26(i) |
| 10 | Why this system exists: the EWS mandate | §4 — RBI/DOS/2024-25/120 para 3.1.1 |
| 11 | Evidence and reasoned orders | §4 — paras 2.1.1–2.1.4 |
| 12 | Grievance and ombudsman escalation | §7 — para 11 |

---

## Sources

- RBI (Digital Lending) Directions, 2025 — https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0
- Outsourcing of Financial Services – Recovery Agents, 12 Aug 2022 — https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=12378&Mode=0
- IRACP Clarifications, 12 Nov 2021 — https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12194&Mode=0
- RBI (Fraud Risk Management in NBFCs) Directions, 2024 — https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12704
- RBI (Fraud Risk Management in Commercial Banks and AIFIs) Directions, 2024 — https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12702
- Fair Lending Practice – Penal Charges in Loan Accounts, 18 Aug 2023 — https://rbi.org.in/Scripts/NotificationUser.aspx?Id=12527&Mode=0
- RBI (Credit Information Reporting) Directions, 2025 — https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12764
- Master Direction – NBFC Scale Based Regulation Directions, 2023 (FPC; text not yet read) — https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12550
