# 27 — Chunking Strategies and Retrieval Evaluation

Filed 18 Sep 2026 as a learning item. Not all of this gets built in this
project — §6 is deliberately deferred to E8 — but the whole of it is
interview material, and the metrics in §5 are the vocabulary for talking about
retrieval quality at all.

Companion to `25-rag-architectures.md`. That doc covers *how you search*; this
one covers *what you search over*, and *how you know it worked*.

---

## 1. The tension everything is built around

Chunking is one trade-off. Every strategy is a different way of cheating it.

- **Small chunks** → the embedding is sharp, retrieval is precise, but the chunk arrives without the context needed to use it.
- **Large chunks** → context is intact, but the embedding is an average of everything in the chunk. A vector for a chunk about five things points strongly at none of them.

There is no size that is right in the abstract. There is a size that is right
for *your documents and your questions*, and the only way to find it is §5.

---

## 2. The strategies, in order of sophistication

### 2.1 Fixed-size

Cut every N tokens. Nothing else.

Trivially fast, and it will cut `"...approval of the Regional"` | `"Credit Head
is required..."` straight down the middle. Use it once, as the baseline you
measure improvements against, and never ship it.

### 2.2 Fixed-size with overlap

Same, but each chunk repeats the last ~10–15% of the previous one. The sentence
you severed survives whole in the next chunk.

Cheap insurance. Costs storage and some duplicate retrieval. Still completely
blind to what the document means.

### 2.3 Recursive splitting

Try to split on paragraph breaks. If a piece is still too large, split on
sentences. Still too large, split on words. Each fallback is more destructive
than the last, so you only descend when you must.

`RecursiveCharacterTextSplitter` in LangChain. A reasonable floor for arbitrary
text, and the right default when you don't control the documents.

### 2.4 Structure-aware

Split on the document's own structure — Markdown `##`, HTML `<h2>`, numbered
clauses — and keep the heading path as metadata.

Only works where structure exists. Where it does, it beats everything cleverer,
because the author already decided where the topic boundaries were and the
headings are a free, exact record of that decision.

### 2.5 Parent–child (small-to-big)

**The idea worth understanding, because it dissolves the tension in §1 rather
than trading against it.**

> Search over small chunks. Return the big one.

Index small child chunks — a sentence, a tight paragraph — so the embedding is
sharp. Store each child's pointer to its parent section. On a hit, return the
**parent**.

The model gets a precise match *and* the surrounding context. The answer to
"small or large?" turns out to be "both, at different stages of the same
lookup."

A variant is the **sentence window**: index single sentences, return the
sentence plus N sentences either side.

### 2.6 Semantic chunking

Embed each sentence. Walk the document comparing consecutive sentence vectors.
Where cosine similarity drops below a threshold, the topic has shifted — cut
there.

The split follows where the *meaning* turns rather than where the formatting
does. Genuinely clever.

Costs an embedding call per sentence at ingestion. And on a well-structured
document it largely rediscovers the headings that were already there — you pay
a model to infer a boundary the author wrote down explicitly.

Worth it when documents are long, unstructured, and topic-drifting. Not worth it
on a handwritten SOP with headings.

### 2.7 Propositional chunking

An LLM decomposes the document into discrete, self-contained facts.

```
Source:
  "Field visits may be initiated once the account crosses 45 days past due,
   subject to prior approval by the Branch Credit Manager."

Propositions:
  1. A field visit requires the account to be more than 45 days past due.
  2. A field visit requires prior approval from the Branch Credit Manager.
```

Each proposition is atomic and stands alone, so its embedding is unambiguous and
retrieval is extremely precise.

**The highest-precision option, and the most expensive by a distance.** An LLM
pass over the entire corpus at ingestion, repeated whenever a document changes,
with extraction errors you silently inherit for as long as the chunk lives.

Real practice in legal, medical and finance — which does make it relevant to
this domain. Understand the mechanism, and understand why the cost is only
justified when a retrieval miss is expensive enough to pay for it.

---

## 3. Chunk size, as a starting point

These are starting points to be validated by §5, not settings to adopt.

| Document type | Rough range | Why |
|---|---|---|
| FAQs | 100–200 tokens | a Q&A pair is already atomic; more just adds noise |
| Research papers | ~400 tokens | paragraph-scale argument |
| General prose | 200–800 tokens | the common sweet spot |
| **Legal and regulatory** | **400–1000+ tokens** | cross-references. A clause that says "subject to paragraph 12" is useless if paragraph 12 is in another chunk |

That last row is the one that matters here. **Regulatory text needs bigger
chunks than almost anything else**, because its sentences are load-bearing on
other sentences. Cutting a clause away from its proviso does not merely lose
context — it can reverse the meaning.

---

## 4. Metadata is not optional

Covered in the session, restated because it belongs with chunking: metadata is
captured while chunking, in §2, and it does three jobs.

1. **Filter** — narrow the search before it runs
2. **Cite** — tell the analyst where the answer came from
3. **Debug** — when retrieval is wrong, find out why

And the rule that matters: **filter inside the query, not after it.**
Post-filtering silently shrinks the result set — ask for 10, filter, get 3.
Pre-filtering always returns 10 valid rows.

For this corpus: `doc_id`, `section`, `source_ref`, `effective_from`,
`effective_to`, `doc_version`, `chunk_index`.

---

## 5. How you tell whether any of it worked

**This is the part that separates an engineer from someone who watched a
tutorial.** Every strategy above sounds reasonable. The only way to choose is to
measure.

### 5.1 The benchmark set

50–100 question/answer pairs over your own corpus, with the **correct chunk
marked for each question**. That marking is the expensive part and there is no
way around it — it has to be done by someone who knows the domain.

For this project, that person is you, and the questions are the ones an analyst
actually asks: *when can we do a field visit, who approves an interest waiver of
₹80,000, what does SMA-2 mean for escalation.*

### 5.2 Retrieval metrics — is the right chunk coming back?

| Metric | Definition | The question it answers |
|---|---|---|
| **Recall@k** | of all the chunks that *are* relevant, what fraction appeared in the top k | **Did we find it at all?** |
| **Precision@k** (context precision) | of the k chunks we returned, what fraction are actually relevant | **Is what we returned clean?** |
| **MRR** (Mean Reciprocal Rank) | `1 / rank of the first relevant chunk`, averaged over all questions | **How near the top was it?** |

MRR deserves a worked example, because the reciprocal is what makes it useful:

| First relevant result at rank | Reciprocal rank |
|---|---|
| 1 | 1.00 |
| 2 | 0.50 |
| 3 | 0.33 |
| 5 | 0.20 |
| 10 | 0.10 |

The steep fall from 1.00 to 0.50 is the point. **Being second is much worse than
being first**, and the metric says so, because a model reads the first passage
most attentively. Recall alone would score rank 1 and rank 10 identically.

> **Careful with recall vs precision — they get swapped constantly, including in
> tutorials.** Recall is *did we find the needle*. Precision is *how much hay
> came with it*. Both have "fraction of chunks" in the definition, which is why
> people muddle them; the difference is entirely in the denominator. Recall
> divides by the relevant chunks that exist; precision divides by the chunks you
> returned. Getting this right in an interview is a small, cheap signal that you
> have actually measured something.

### 5.3 Generation metrics — is the answer any good?

| Metric | Definition | The failure it catches |
|---|---|---|
| **Faithfulness** | is every claim in the answer supported by the retrieved context | hallucination |
| **Answer relevance** | does the answer address the question that was asked | a true, well-sourced answer to a different question |

Faithfulness is the one that matters most here, and it is the same property the
E6 citation guard enforces — with the difference that the guard enforces it at
runtime while the metric measures it in aggregate offline.

### 5.4 How to actually run the comparison

Not "try all strategies and pick the best". That's a grid search over a space
with no gradient and it teaches you nothing about *why*.

The method:

1. Build the benchmark set **first**, before tuning anything.
2. Measure the naive baseline. Write the numbers down.
3. **Change exactly one thing.** Chunk size, or strategy, or retrieval method — never two.
4. Re-measure. Keep the change only if the numbers moved.
5. Record what you tried and what happened, including the failures.

Step 5 is the one people skip and the one worth the most. *"We tried semantic
chunking and it gave us +2% recall for 40× the ingestion cost, so we stayed with
structure-aware"* is a far stronger interview answer than *"we use semantic
chunking"*.

---

## 6. What this project does, and what it defers

### Now (E5.6)

**Structure-aware chunking, one chunk per SOP section.**

The reasoning is unusual and worth stating plainly: **we are writing the source
documents ourselves.** That makes chunking a writing problem rather than an
algorithm problem.

The rules that follow:

- One subject per section, 150–400 words. If a section needs two chunks, it is really two sections — split it in the document, not in the splitter.
- Name the subject in the first sentence. Never open with "In such cases" or "This applies when". This is the free version of contextual retrieval (`25-rag-architectures.md` §8).
- Keep `doc_id` + `section` + `source_ref` so the parent is one lookup away if small-to-big is ever wanted.
- Every section names the circular it derives from, using the references in `24-rbi-source-pack.md`.

Semantic or propositional chunking over a 12-section handwritten SOP is
engineering theatre. The author already knows where the boundaries are.

### Later (E8)

The benchmark set and the metrics in §5, applied to:

- chunk size, against the 400–1000 token guidance for regulatory text
- structure-aware vs parent–child
- hybrid retrieval vs vector-only — *the measured delta here is the most
  valuable number this project can produce*, because it is the quantitative
  version of the SMA-1/SMA-2 argument
- whether a reranker earns its operational cost

### Never, here

Propositional chunking. The mechanism is understood, the domain genuinely
justifies it in a real deployment, and the corpus in this project is far too
small to pay for it.

---

## 7. The interview answer

> Chunking is a trade-off between embedding sharpness and retained context, and
> the strategy depends on whether you control the documents. We do, so we chunk
> on structure — one chunk per SOP section — and write the sections to be
> self-contained, which gets us contextual retrieval for free. Regulatory text
> needs larger chunks than most, 400 to 1000 tokens, because clauses reference
> each other and cutting a proviso away from its clause can reverse the meaning.
> If I were ingesting documents I didn't control I'd start with recursive
> splitting and evaluate parent–child, where you embed small children for
> precision and return the parent for context. Which of those wins is an
> empirical question — you build a 50 to 100 question benchmark with the correct
> chunk marked, measure recall at k, MRR and context precision, and change one
> variable at a time.
