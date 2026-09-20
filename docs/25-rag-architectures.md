# 25 — RAG Architectures, in depth

Written to be read slowly. Every term is defined where it first appears, and
every example uses this project's own corpus so nothing is abstract.

Read §1 first even if you want to skip ahead. Every architecture after it is a
fix for a problem §1 creates.

---

## 0. The one sentence

Retrieval-Augmented Generation means: **before the model answers, go and fetch
the relevant text, and put it in the prompt.** That is all. Everything called
an "architecture" is a different answer to one question — *how do you decide
what is relevant?*

---

## 1. The thing underneath: embeddings

### What an embedding is

An **embedding model** is a neural network that takes a piece of text and
returns a fixed-length list of numbers. Not a summary — a position.

```
"field visit is allowed after 45 days"  →  [0.031, -0.412, 0.887, ... ]
                                            (1024 numbers, say)
```

That list is called a **vector**. Think of it as coordinates. With 2 numbers
you'd have a point on a page. With 1024 numbers you have a point in a space with
1024 directions, which nobody can picture — and you don't need to. The only
thing that matters is this:

**Texts that mean similar things land near each other.**

The model was trained on enormous amounts of text with an objective that pushed
related passages together and unrelated passages apart. It is not looking up
words. It has learned a geometry of meaning.

### How "near" is measured

The standard measure is **cosine similarity** — the angle between two vectors,
ignoring their length.

- angle 0° → similarity 1.0 → identical direction → same meaning
- angle 90° → similarity 0.0 → unrelated
- angle 180° → similarity -1.0 → opposite

Postgres/pgvector gives you **cosine distance** instead, which is `1 - similarity`.
Smaller is better. The operator is `<=>`:

```sql
select text
from policy_chunk
order by embedding <=> %(query_vector)s   -- nearest first
limit 5;
```

That single line is 90% of what a vector database does.

### Why this is powerful

The question and the passage need share no words at all.

| Question | Passage that matches | Shared words |
|---|---|---|
| "can we send someone to his house?" | "Field visits may be initiated once the account crosses 45 days past due." | none |

A keyword search returns nothing here. The embedding model knows "send someone
to his house" and "field visit" occupy nearly the same point in meaning-space.
**This is the entire reason RAG uses embeddings.**

### Why it fails — and this is the part people skip

The same property that makes embeddings good at meaning makes them **bad at
exact strings**.

To an embedding model, `SMA-1` and `SMA-2` are nearly the same point. They're
both short alphanumeric tokens appearing in the same regulatory context, doing
the same grammatical job. The model has no mechanism that says "the digit at the
end is the whole meaning."

Try these, all of which will retrieve near-identical results:

- `SMA-1` vs `SMA-2`
- `RBI/2022-23/108` vs `RBI/2023-24/53`
- `30 days` vs `90 days`
- `para 26(i)` vs `para 24(i)`

For a general knowledge base this is a rounding error. **For a regulatory
corpus it is a catastrophe**, because your entire corpus is made of exactly
these tokens, and getting SMA-1 when you asked for SMA-2 is not a near-miss —
it's a wrong answer delivered confidently with a citation attached.

Hold on to this. It is why §3 exists and why you will build it.

### A second failure: chunk isolation

An embedding is computed from the chunk's text alone. A chunk reading

> "In such cases the approval of the Regional Credit Head is required."

has no idea which cases. The surrounding document said so; the chunk doesn't.
Embed that and you get a vector for a sentence about approvals in general.
Retrieve it, hand it to the model, and the model will confidently apply it to
whatever case it happens to be looking at.

This is the chunking problem. §8 has the fix.

---

## 2. Architecture 1 — Naive RAG

### The mechanism

```
question
  → embed it                      (same model used at ingestion)
  → nearest-neighbour search      (order by embedding <=> q, limit k)
  → paste the k chunks into the prompt
  → model answers
```

One retrieval. No decisions. No second look.

### Concretely, in SQL

```sql
select doc_id, section, text
from policy_chunk
order by embedding <=> %(q)s
limit 5;
```

### What "top-k" means and why k matters

`k` is how many chunks you take. It is a budget, not a quality setting.

- **k too small** (1–2): you miss the passage that had the answer. Called *low recall*.
- **k too large** (20+): the right passage is buried among 18 irrelevant ones, and the model's attention is diluted. Called *low precision*. It also costs tokens.

There is no correct k in the abstract. You find it by evaluation (§9).

### What breaks

1. **Exact terms.** §1's failure, in production.
2. **Multi-part questions.** "What's the DPD threshold for a field visit, and who approves it?" is two retrievals pretending to be one. One search finds one of them.
3. **No escape hatch.** If the top-5 are all wrong, naive RAG has no way to notice and no way to try again. It hands the model five wrong passages and the model, being agreeable, writes an answer from them.

### Verdict for you

This is the baseline you measure everything against. Build it first. Do not
ship it.

---

## 3. Architecture 2 — Hybrid search

**The highest-value upgrade for your corpus. Build this one.**

### The idea

Run two searches that fail in *different* ways, and merge them.

- **Vector search** understands meaning, misses exact strings.
- **Keyword search** matches exact strings, understands nothing.

Neither is a superset of the other. Together they cover each other's holes.

### The keyword half: BM25

**BM25** is the keyword ranking function used by essentially every search engine
built before 2020, and still the default today. Postgres implements a close
relative natively in `tsvector` / `ts_rank`.

It scores a document against a query using three ideas:

**1. Term frequency (TF)** — a document mentioning "moratorium" six times is
more about moratoriums than one mentioning it once.

But with **saturation**: the jump from 1 mention to 2 matters a lot; from 20 to
21, almost nothing. BM25 applies a curve that flattens out, so a document can't
win by keyword-stuffing.

**2. Inverse document frequency (IDF)** — a term appearing in *every* document
tells you nothing. A term appearing in three documents is a strong signal.

In your corpus: "loan" appears everywhere → near-zero weight. `SMA-2` appears in
two chunks → enormous weight. **This is precisely the property vectors lack.**

**3. Length normalisation** — a 2,000-word chunk will naturally contain more
terms than a 100-word chunk. BM25 divides out that advantage, so a short chunk
that is *about* the term beats a long chunk that merely *contains* it.

### Why the combination is more than the sum

Take the question: **"What does SMA-2 mean for field visit eligibility?"**

| Search | What it finds | Why |
|---|---|---|
| Vector | chunks about visiting borrowers, escalation, contact conduct | it understands "field visit eligibility" |
| BM25 | the two chunks containing the literal string `SMA-2` | it doesn't understand anything, but it can't miss an exact token |

Vector alone: plausible-sounding chunks, wrong bucket.
BM25 alone: the right definition, no operational context.
Together: both.

### Merging the two lists: Reciprocal Rank Fusion

Now the real problem. Vector search returns a **distance** (0.23). BM25 returns
a **score** (7.41). These are different units on different scales. You cannot
add them, and normalising them is fragile — the ranges shift with every query.

**Reciprocal Rank Fusion (RRF)** solves this by throwing the scores away and
keeping only the **positions**.

```
RRF score for a chunk  =  sum over each list of   1 / (k + rank in that list)
```

where `rank` is 1 for first place, 2 for second, and `k` is a constant — 60 by
convention, and the choice barely matters.

Worked example. Suppose:

- Vector list: `[A, B, C, D]`
- BM25 list: `[C, E, A, F]`

| Chunk | Vector rank | BM25 rank | RRF score | |
|---|---|---|---|---|
| A | 1 | 3 | 1/61 + 1/63 = 0.0323 | **1st** |
| C | 3 | 1 | 1/63 + 1/61 = 0.0323 | **1st (tie)** |
| B | 2 | — | 1/62 = 0.0161 | 3rd |
| E | — | 2 | 1/62 = 0.0161 | 3rd |
| D | 4 | — | 1/64 = 0.0156 | 5th |
| F | — | 4 | 1/64 = 0.0156 | 5th |

Read what happened. **A and C win because each appeared high in one list and
respectably in the other.** Anything both methods liked floats up. Anything only
one method liked sits mid-table. Nothing needs calibrating, and adding a third
retrieval method later requires no re-tuning.

That robustness is why RRF is the default in production systems despite being
almost embarrassingly simple.

### In your stack

Postgres does both halves natively:

```sql
with vec as (
    select id, row_number() over (order by embedding <=> %(q)s) as rank
    from policy_chunk
    where effective_from <= %(as_of)s
      and (effective_to is null or effective_to > %(as_of)s)
    limit 50
),
kw as (
    select id, row_number() over (order by ts_rank(tsv, plainto_tsquery(%(q_text)s)) desc) as rank
    from policy_chunk
    where tsv @@ plainto_tsquery(%(q_text)s)
      and effective_from <= %(as_of)s
      and (effective_to is null or effective_to > %(as_of)s)
    limit 50
)
select c.id, c.text,
       coalesce(1.0 / (60 + vec.rank), 0) + coalesce(1.0 / (60 + kw.rank), 0) as rrf
from policy_chunk c
left join vec on vec.id = c.id
left join kw  on kw.id  = c.id
where vec.id is not null or kw.id is not null
order by rrf desc
limit 5;
```

Note the `effective_from` / `effective_to` filter appears in **both** halves.
Miss it in one and that half leaks superseded policy. Same pre-filter rule as
before — and now you can see why it has to be repeated: two searches, two places
to forget it.

No new infrastructure. pgvector is already in your Docker image and `tsvector`
ships with Postgres.

### Verdict for you

**Build it.** Your corpus is made of exact tokens. This is not an optimisation,
it is a correctness requirement.

---

## 4. Architecture 3 — Reranking

### The problem it solves

Hybrid search gives you 50 candidates. Only 5 fit in the prompt. Which 5?

The ranking you have is cheap and approximate. Reranking replaces it with an
expensive and accurate one — but only for the 50 that survived, never for the
whole corpus.

### Bi-encoder vs cross-encoder — the actual insight

This is the concept worth understanding, because it explains why reranking
works at all.

**Bi-encoder** — what every vector search uses:

```
embed(question)  →  vector A          ┐
                                      ├→  compare A and B (cosine)
embed(chunk)     →  vector B          ┘
```

The question and the chunk are encoded **separately, never seeing each other**.
The chunk's vector was computed at ingestion time, months ago, with no knowledge
of any question.

That separation is what makes it fast — you precompute every chunk's vector once
and search millions in milliseconds. It is also what makes it approximate: the
model compressed the chunk into 1024 numbers before it knew what you'd ask.

**Cross-encoder** — what a reranker uses:

```
[question] [SEP] [chunk]  →  one model pass  →  relevance score
```

Both texts go in **together**. Every word of the question can attend to every
word of the chunk. The model can notice that the question says `SMA-2` and the
chunk says `SMA-1`, which no pair of precomputed vectors could ever notice.

The cost: no precomputation. You must run the model once per candidate, at query
time. 50 candidates = 50 forward passes. For a whole corpus of 50,000 chunks
that is impossible; for 50 it's ~100ms.

Hence **two stages**: cheap-and-wide, then expensive-and-narrow.

```
50,000 chunks
   → hybrid search (cheap, approximate)     → 50
   → cross-encoder rerank (expensive, sharp) → 5
   → prompt
```

### What it costs you

A second model to host, load into memory, and keep running. That is a real
operational burden — a new deployment, new latency, new failure mode.

### Verdict for you

**Skip for now. Revisit in E8.** Build hybrid, build evaluation, then look at
the numbers. If retrieval precision is your bottleneck, add it and *measure the
improvement* — that measured delta is worth more in an interview than having
built it speculatively.

---

## 5. Architecture 4 — Query transformation

The question is the weakest link. It's written by a human in a hurry, or by a
model paraphrasing one. Fix the question before searching.

Three techniques, increasing in cleverness.

### 5.1 Query rewriting

A cheap model rewrites the question into search-friendly form.

> "can we visit him?"
> → "field visit eligibility DPD threshold borrower contact"

Expands pronouns, drops filler, adds domain vocabulary. Cheap, and it helps most
when questions come from humans typing casually.

### 5.2 Multi-query

Generate several phrasings, search all of them, fuse the results with RRF (§3 —
same mechanism, more lists).

> "What's the approval for a settlement?"
> → "settlement approval authority"
> → "who can approve a one-time settlement"
> → "settlement waiver slab sanction"

Three searches, three rankings, one fused list. Catches the case where one
phrasing happened to sit in a bad part of the vector space. Costs 3× the
retrieval — which is cheap — plus one model call to generate the variants.

### 5.3 HyDE — Hypothetical Document Embeddings

The cleverest of the three, and worth understanding even though you won't build
it.

The insight: **a question and its answer don't look alike.** A question is
short and interrogative; a passage is long and declarative. When you embed a
question and compare it to passages, you're comparing two different kinds of
object.

HyDE's move: ask the model to *hallucinate an answer first*, then embed that
fake answer and search with it.

> Question: "When can we do a field visit?"
> Fake answer the model invents: "Field visits may be initiated once an account has crossed 45 days past due, subject to prior approval and provided contact attempts have been exhausted."
> → embed **that**, search with it

The fake answer may be factually wrong — doesn't matter. It is *shaped* like a
real policy passage, so it lands in the right neighbourhood of the vector space.
You then retrieve real passages from that neighbourhood and answer from those.

**Why not for you:** it adds a model call to every retrieval, and it is
worthless for exact-token questions (the hallucinated text won't contain the
right circular number). Hybrid search solves your actual problem more directly.

### Verdict for you

Skip all three. Your questions come from an investigator agent using a fixed
`_QUESTIONS` map, not from a human typing loosely — the phrasing is already
controlled, and controlling it yourself is better than paying a model to guess
at it.

Know HyDE for interviews. It's a favourite question because the idea is
counter-intuitive.

---

## 6. Architecture 5 — Agentic RAG

**What you already have.**

### The mechanism

Retrieval stops being a fixed pipeline stage and becomes **a tool the model may
choose to call**. The loop:

```
1. model receives the question and the list of available tools
2. model either answers, or emits a tool call
3. system executes the tool, appends the result to the conversation
4. back to 2, until the model answers or the turn budget is spent
```

This is **ReAct** — *Reason + Act*. The name is just "think, then do, then look
at what happened, then think again."

Your `agents/investigate.py` is exactly this. The `while turns < max_turns` loop
is the loop above. `dispatch` is step 3.

### What it buys

**Conditional retrieval.** The model can decide not to search. If a case needs
no policy lookup, no policy lookup happens. A fixed pipeline always searches,
whether or not it helps.

**Iterative retrieval.** Search, read, notice the answer is incomplete, search
again with a better query. Naive RAG gets exactly one attempt.

**Composition.** Retrieval sits beside your four SQL tools. The model can pull a
payment history *and* the SOP paragraph governing what to do about it, and
reason across both. That composition is the thing a pipeline cannot express at
all.

### What it costs — and this is the part the diagrams never show

**Non-determinism.** Same case, same data, two runs, two different tool
sequences. That's a fact about the architecture, not a bug you can fix.

For a chat assistant, who cares. For a credit decision, it's the central
engineering problem, and it's why your build has the shape it has:

| Risk | Your mitigation | Where |
|---|---|---|
| Unbounded loops | turn budget in the loop condition | `investigate.py` |
| Tool the agent shouldn't have | permission checked before registry lookup | `dispatch.py` |
| Injected system arguments | `_INJECTED` set refuses, never overwrites | `dispatch.py` |
| Time leakage | `as_of` required, injected, not model-supplied | every tool |
| Unreproducible run | every call recorded with arguments and result | `context.py` |

None of those boxes appear on the Agentic RAG diagram. They are the difference
between the diagram and a system that can be audited.

### Verdict for you

Already built. `search_policy` slots in as tool five and you get agentic RAG for
free — because the agent came first and retrieval is joining it, rather than the
other way round.

Say that in an interview exactly that way. Most people bolt an agent onto a RAG
pipeline. You're adding retrieval to an agent that already has a permission
model, a clock, and an audit trail.

---

## 7. Architecture 6 — Graph RAG

### The mechanism

Instead of (or alongside) chunks, you extract **entities** and **relationships**
into a graph, then traverse it.

```
(RBI/2022-23/108) --[governs]--> (recovery agent conduct)
(RBI/2022-23/108) --[supersedes]--> (older FPC guidance)
(SOP §4.2) --[derives from]--> (RBI/2022-23/108)
(SOP §4.2) --[amended by]--> (SOP §4.2 v3)
```

A question then becomes a walk: start at a node, follow edges, collect what you
pass.

### What it solves: multi-hop questions

> "Which of our SOP sections are affected if RBI/2022-23/108 is superseded?"

No single chunk contains that answer. It requires: find the circular → find
every SOP section deriving from it → return those. Vector search cannot do this,
because the answer isn't *written down anywhere* — it's implied by the
relationships.

### What it costs — honestly

- **Extraction.** Something must read every document and pull out entities and relationships. Usually an LLM, over the whole corpus, which is slow and expensive and makes mistakes you then inherit.
- **Schema.** You must decide what an entity is and what an edge is, up front. Get it wrong and re-extract everything.
- **Maintenance.** Every document update means re-extraction and edge reconciliation.
- **Infrastructure.** A graph store, or a painful graph-shaped schema in Postgres.

### Verdict for you

**Do not build this.** Your corpus is ~12 SOP sections. The relationships fit on
one sheet of paper — and if you ever need them, a `derives_from` column on the
chunk table gives you the useful 5% for none of the cost.

Know what it is and when it pays: when the *relationships are the product*
(fraud rings, supply chains, org charts, citation networks), not when documents
merely reference each other.

---

## 8. Sidebar: contextual retrieval

Not an architecture — a fix for the chunk-isolation problem in §1.

Before embedding a chunk, prepend a sentence of context generated from the
parent document:

```
original chunk:
    "In such cases the approval of the Regional Credit Head is required."

contextualised chunk:
    "From SOP §5.3, Waiver Authority, on interest waivers above ₹50,000:
     In such cases the approval of the Regional Credit Head is required."
```

The embedding is now computed over text that says what it's about. Retrieval
accuracy improves substantially for the price of one cheap model call per chunk,
**paid once at ingestion** — not per query.

**For your corpus you get this almost for free**, because you are writing the SOP
yourself. Write each section to be self-contained: name the subject in the first
sentence, never open with "in such cases" or "this applies when". Good technical
writing and good chunking turn out to be the same discipline.

---

## 9. The decision table

| Architecture | Fixes | Costs | You |
|---|---|---|---|
| Naive | nothing — it's the baseline | none | build first, as the floor to measure against |
| **Hybrid (BM25 + vector, RRF)** | **exact tokens, acronyms, citations** | **none — Postgres does both** | **build** |
| Rerank (cross-encoder) | precision within candidates | a second model to host | E8, if evaluation says so |
| Query rewriting | sloppy human phrasing | one model call per query | skip — your questions are fixed |
| Multi-query | unlucky phrasing | 3× retrieval | skip |
| HyDE | question/answer shape mismatch | one model call per query | skip — know it for interviews |
| **Agentic (ReAct)** | conditional + iterative + composed retrieval | **non-determinism** | **already built** |
| Graph | multi-hop relational questions | extraction, schema, maintenance | don't build — know when it pays |
| Contextual chunks | chunk isolation | one cheap call per chunk at ingest | get it free by writing well |

---

## 10. What you are building

**Agentic RAG over hybrid search, with effective-dated pre-filtering, inside an
existing permission boundary.**

Unpacked:

- **Agentic** — retrieval is a tool the investigator may call, not a fixed stage. Already true.
- **Hybrid** — vector and BM25 fused with RRF, because the corpus is full of exact tokens.
- **Effective-dated pre-filtering** — the `as_of` window is in the `where` clause of both halves, so a question asked as at a past date gets the policy as it stood then.
- **Inside a permission boundary** — `search_policy` goes through the same `dispatch` gate as every other tool and returns the same `ToolResult`. It is not special.

And one thing it deliberately is **not**: `search_policy` does not generate. It
retrieves and returns passages. The investigator generates. Keeping those apart
is what lets the citation guard in E6 check that every claim traces to a
retrieved passage — if the tool answered, there would be nothing to check it
against.

---

## 11. The interview answer

Compressed, for when someone asks "what RAG architecture did you use?":

> Agentic RAG over hybrid retrieval. The agent decides when to search rather
> than searching on every turn, because most cases don't need a policy lookup.
> Retrieval is hybrid — vector plus BM25 fused with reciprocal rank fusion —
> because a regulatory corpus is full of exact tokens like SMA-2 and circular
> numbers that embeddings can't distinguish. The corpus is effective-dated and
> the date filter runs inside the query, not after it, so asking the same
> question as at an earlier date returns the policy as it stood then. Retrieval
> is a tool behind the same permission gate as the SQL tools, and it returns
> passages rather than answers, so the citation check has something to verify
> against.

Every clause in that paragraph is a decision you can defend, and each one has a
failure it prevents. That is what separates it from a list of technologies.
