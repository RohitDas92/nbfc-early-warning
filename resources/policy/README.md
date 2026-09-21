# Policy corpus

The source of truth for the `search_policy` RAG corpus.

## Layout

```
<doc_id>/<section>.md     one section per file, YAML frontmatter + body
pdf/                      generated PDFs, one per document
rbi-source/               real RBI circulars, downloaded by hand — see its README
_build/                   throwaway build intermediates; never ingested
```

**The section files are the source of truth.** The PDFs are generated from them
by `scripts/build_policy_pdfs.py` and exist so the `PdfReader` path has something
realistic to parse. Never edit a PDF; edit the section and rebuild.

## Frontmatter

```yaml
doc_id: sop-collections
section: "4.2 Field visit eligibility"
heading: "Field visit eligibility"
rule_key: field_visit.min_dpd        # or null
source_ref: "RBI/2022-23/108 para 2" # or "Internal"
version: 1
effective_from: 2019-01-01
effective_to: null                    # null = still in force
department: collections
sensitivity: 2                        # 1 public, 2 internal, 3 restricted
acl_groups: []
```

## Rules

- One subject per section, 150–400 words, subject named in the first sentence.
- Never open a section with "In such cases" or "This applies when".
- **Exactly one in-force section per `rule_key`.** A rule_key names one decision.
  Three approval slabs are three decisions, so they carry three distinct keys
  (`waiver.interest.upto_25k`, `.25k_to_1l`, `.above_1l`) — not one shared key.
- Every threshold here must match `action_policy` / `waiver_slab` in the database.
  The table decides; this corpus explains. If they disagree, the table wins and
  the disagreement is a defect.
- Ingestion skips any directory whose name starts with `_`.

## Updating a policy

Never edit an in-force section's text. Close it and add a new one:

1. Set `effective_to` on the current file to the change date.
2. Add a new file with the next `version` and `effective_from` = the change date.
3. Re-run ingestion.
4. Change `action_policy` in the **same commit**.

Asking as at a past date then returns the rule that was actually in force then.
Forgetting step 1 leaves two sections sharing a `rule_key` — which the
contradiction guard is there to catch.

### The worked example in this corpus

`sop-collections/7.1-bureau-reporting-v1.md` and `-v2.md` are a real
supersession, with real dates and real citations.

| | v1 | v2 |
|---|---|---|
| in force | 2019-01-01 → 2026-07-01 | 2026-07-01 → (open) |
| cycle | fortnightly: 15th and last day, submit within 7 days | 9th, 16th, 23rd and last day; full file by the 5th, incremental within 4 days |
| lag | up to ~22 days | 4–11 days |
| cites | RBI (Credit Information Reporting) Directions, 2025 s.6(1)(b) | MD-NBFC-CreditInformationReporting-2025 para 6(2) |

The change is genuine: para 6(2) was substituted with effect from 1 July 2026 by
the Amendment Directions dated 4 December 2025.

Both carry `rule_key: bureau.reporting_cycle`, and that is **not** a conflict —
their effective windows do not overlap. It is the case the contradiction guard
must *not* fire on, which makes it the more useful of the two tests.

Superseded sections stay in the corpus and are excluded from the generated PDFs;
the handbook shows what is in force, the corpus remembers what was.
