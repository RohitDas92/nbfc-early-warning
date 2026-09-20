# 26 — Open Items

Things found but deliberately not fixed yet, with the episode that should fix
them. Delete a row when it lands. If a row is still here at the end of E9, it
was never real — delete it then too.

Opened 18 Sep 2026.

---

## Fix now — typos with consequences

**`agents/investigate.py`, `_as_text`**

```python
return json.dumps({"ok": False, "resson": result.reason})
```

`resson` → `reason`. Silent failure: the model receives a key it has never seen
in any schema and has to guess what it means. Every failed tool call in the
whole system is affected.

**`agents/investigate.py`, `_SYSTEM`**

```python
" and say so plainly if the evidence is this."
```

`is this` → `is thin`. It sits in the system prompt, so the model reads the
broken sentence on every single turn of every investigation.

---

## E6.4 — blocker for the real model client

### The assistant turn loses its tool calls

`llm/base.py` — `Message` carries `role`, `content`, `tool_call_id`. There is no
field for the tool calls an assistant turn *made*.

So `investigate()` builds this:

```
assistant: ""                        ← the ToolCalls were dropped here
tool:      {...} tool_call_id="c1"   ← points at a call not in the transcript
```

`FakeChatModel` never notices, because it reads from a script and ignores
`messages` entirely. **Every current test passes and will keep passing.**

A real Anthropic or OpenAI client will reject it. Both protocols require a
`tool_result` to reference a `tool_use` / `tool_call` block in the immediately
preceding assistant turn. Sending an empty assistant turn followed by tool
results is a malformed conversation.

Fix: add a `tool_calls: tuple[ToolCall, ...] = ()` field to `Message`, populate
it from `reply.tool_calls` when appending the assistant turn, and have the real
client serialise it into the provider's block format.

**Why this is worth writing down:** when 6.4 fails, it will look like the new
client is broken. It isn't. The loop has been subtly wrong since it was written,
and the fake model was too permissive to say so. This is the general lesson —
*a fake that accepts anything tests nothing about protocol.*

---

## E6.8 — budget and cycle guards

### Context growth is unbounded

Each turn of `investigate()` appends one assistant message plus one message per
tool result, and the entire list is resent to the model on every `complete()`
call. Nothing ever removes anything.

At `max_turns=6` this is survivable — worst case perhaps 20 messages. It is
still quadratic in turns: turn *n* pays for every message from turns 1..*n*.

The token counters already make it visible. Watch `input_tokens` climb turn over
turn once the real client is in; that curve is the thing being described here.

Standard fixes, in order of how much they cost to build:

1. Cap the number of retained tool results, keeping the most recent
2. Truncate large tool results before they enter `messages`
3. Summarise older turns into a single message

Do not build any of them before E6.8, and do not build one at all without a
token measurement showing it is needed.

---

## E8 — evaluation may or may not justify these

### Retrieval benchmark set and metrics

50–100 question/answer pairs over the policy corpus with the correct chunk
marked for each. Needed before any retrieval tuning decision can be made on
evidence rather than taste.

Then measure recall@k, MRR and context precision across: chunk size,
structure-aware vs parent-child chunking, and hybrid vs vector-only retrieval.
Change one variable at a time and record the failures as well as the wins.

The hybrid-vs-vector-only delta is the single most valuable number this project
can produce — it is the quantitative version of the SMA-1/SMA-2 argument.

See `27-chunking-and-retrieval-eval.md` §5.

### Reranking

A cross-encoder reranking stage between hybrid retrieval and the prompt. Real
improvement to retrieval precision, real operational cost — a second model to
host and keep running.

Do not build speculatively. Build evaluation first, measure retrieval precision,
and add the reranker only if it is the bottleneck. The measured before/after
delta is worth more than the feature.

See `25-rag-architectures.md` §4.

---

## RESOLVED 18 Sep 2026 — citations re-derived

All 26 sections now cite the current NBFC Master Directions, verified against the
PDFs in `resources/policy/rbi-source/`. Four sections needed **substantive**
rewrites, not just a new reference:

- **2.1** — the SMA table is no longer in IRACP. It is now Stressed Assets para 18. The day-end rule and Illustration I are IRACP paras 18–19; the 90-day NPA test is IRACP para 51.
- **2.2** — upgrade is IRACP para 24, and para 25 adds that a multi-facility borrower upgrades only on clearing arrears across *all* facilities.
- **7.1** — **the reporting cycle changed.** No longer fortnightly. Credit information is now submitted as on the 9th, 16th, 23rd and last day of the month (CIR para 6(2), substituted w.e.f. 1 Jul 2026): full file by the 5th of the next month, incremental within 4 calendar days. The staleness window shrank from ~22 days to 4–11.
- **6.2** — penal charges are RBC para 30. Para 30(1) also *permits* interest on unpaid interest at the contracted rate; that is compounding, not a penal charge, and the section now says so.

The 8am–7pm rule and the prohibited-practices list moved from the withdrawn
recovery agents circular into **RBC para 100**, which also carves out
microfinance loans. Recovery-agent liability is **Outsourcing para 17**;
**Outsourcing para 100** is the repeal.

Old circular references are kept in `docs/24-rbi-source-pack.md` as a record of
what the rules said before the restructure. They are not citations any more.

## Superseded — the problem this replaced

### Every `source_ref` in the policy corpus points at a withdrawn circular

On 28 Nov 2025 the RBI withdrew ~9,445 circulars and re-issued the framework as
Master Directions per entity type; supervisory directions followed 31 Jul 2026.
All 26 SOP sections cite the old circulars.

The paragraph numbers moved too, so this is not a find-and-replace. Each
provision has to be located again in the new text. Two shifts already
confirmed:

- **Upgradation moved out of IRACP.** NBFC IRACP Directions para 22 defers to
  the NBFC – Resolution of Stressed Assets Directions, 2025 for the conditions.
- **Recovery agent responsibility is now Outsourcing Directions para 17**, and
  para 100 repeals the earlier outsourcing guidance outright.

Next step: download the seven Master Directions listed in
`resources/policy/rbi-source/README.md`, then re-derive every citation from
them. The PDF endpoints refuse automated fetches, so the download is manual.

Until that is done, the corpus is usable for building and testing retrieval —
the *rules* are right, they match `action_policy` — but no `source_ref` in it
should be quoted to anyone as a live citation.

## E6 — authority model is missing a rule the corpus found

### Settlement approver independence is not modelled

`policy-settlement/1.2` records RBI (NBFC – Resolution of Stressed Assets)
Directions, 2025 para 16(5)(i): the authority approving a compromise settlement
must be **at least one hierarchy level above** the authority that sanctioned the
exposure, and **no official who took part in sanctioning may take part in
approving the settlement of that same account, in any capacity**.

`authority.py` does not model this. It resolves a settlement's approver purely
from `waiver_slab` by amount. That makes the slabs a **floor, not the answer**:
a Rs 20,000 interest waiver falls to `manager` under slab 2.1, but if a manager
sanctioned the loan the approval must escalate regardless of amount.

To model it, `ActionFacts` needs the sanctioning authority for the account, and
`Policy.check` needs a rule that lifts the required authority one level when they
collide. The rank ordering (`analyst < manager < head < committee`) already
exists implicitly in the slabs and would have to become explicit.

Not urgent — no test currently exercises it — but the corpus and the code now
disagree, and the corpus is right.

## Unrelated, still outstanding

- Four protected git files to add by hand: `.pre-commit-config.yaml`, PR
  template, CODEOWNERS
- Second synthetic book with a different seed, held out until W4
- E4.3 PII registry
- Fair Practices Code paragraph numbers — the rbidocs PDF endpoint serves a
  CAPTCHA to automated fetches, so the text must be read from the downloaded PDF
  by hand before anything from it enters the corpus. See
  `24-rbi-source-pack.md` §8.
- Line-by-line walkthrough of `authority.py` and `policy.py` — asked for, started,
  abandoned when the class explanation went badly. Still owed.
