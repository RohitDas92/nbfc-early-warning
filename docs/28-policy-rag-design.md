# 28 — Policy RAG: HLD and LLD

Settled 18 Sep 2026, after design review. Supersedes the first draft.

**Scope of this build (E5):** everything up to and including the agent's
`search_policy` tool. No AI-generated answers — that is the human surface, it
needs the real model client, and it is designed here but built later.

Companions: `25-rag-architectures.md` (how retrieval works),
`27-chunking-and-retrieval-eval.md` (chunking and metrics),
`24-rbi-source-pack.md` (the regulatory sources the corpus cites),
`26-open-items.md` (the E6.4 blocker on the human surface).

---

# Part A — High Level Design

## A1. One core, two doors

| Consumer | Asks | Gets back | Who generates |
|---|---|---|---|
| **Investigator agent** | a fixed question from `_QUESTIONS` | passages + metadata | the investigator |
| **Human analyst, in chat** | anything, freely phrased | an answer with citations | this system |

The agent already has a model and a loop. A tool that *answers* would mean two
models generating in sequence, each free to drift from the source. So the tool
finds; the investigator reasons.

The human has no model of their own, so something must generate for them.

```
                      ┌──────────────────┐
  investigator ──────▶│  SearchPolicy    │  passages only
                      │  (tools/policy)  │
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │  rag/cache       │  version-invalidated
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │  rag/retrieve    │  hybrid + RRF + filters + timing
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │  policy_chunk    │  pgvector + tsvector
                      └──────────────────┘
                               ▲
                      ┌────────┴─────────┐
  human chat ────────▶│  rag/answer      │  DEFERRED — needs real model client
                      └──────────────────┘
```

`rag/answer` calls `rag/retrieve` directly. It never calls `SearchPolicy` — the
tool is the agent's wrapper, not a shared entry point.

## A2. The corpus is authored, not scraped

One section per file, `resources/policy/<doc_id>/<section>.md`, YAML
frontmatter:

```yaml
---
doc_id: sop-collections
section: "4.2 Field visit eligibility"
rule_key: field_visit.min_dpd
source_ref: "RBI/2022-23/108 para 2"
version: 3
effective_from: 2024-01-01
effective_to: null
department: collections
sensitivity: 2
acl_groups: []
---

Field visits may be initiated once an account has crossed 45 days past due...
```

Consequences: metadata is written by someone who knows the domain rather than
inferred; a policy change is a reviewable git commit; and `rule_key` exists,
which is what makes the contradiction guard possible.

Writing discipline: one subject per section, name the subject in the first
sentence, never open with "In such cases".

## A3. `rule_key` — what the contradiction guard hangs off

A `rule_key` names **the thing being decided**, not the document deciding it.

```
field_visit.min_dpd        settlement.min_dpd
waiver.interest.slab       waiver.principal.prohibition
contact.permitted_hours    handover.min_dpd
```

Many sections may *mention* field visits. Only one may **govern**
`field_visit.min_dpd` at a given date. That is checkable in SQL with no model.

### A3.1 Does this scale?

It scales for a corpus we **author**. It does not scale for a corpus we
**ingest**. Both halves need saying.

**The cost is per rule, not per document.** `rule_key` is nullable and most
sections are null — it goes only on sections that *decide* something. A
collections policy has perhaps 30–40 such rules; a hundred sections might carry
twelve keys. Another 500 pages adds almost no new keys.

**It is not new work.** Somebody in credit policy already has to know which
section governs field visits. `rule_key` writes down a fact the organisation
must already possess. If nobody can say which document governs a rule, this
system is revealing a governance gap, not creating one.

**The scaling path.** Move the values into a table — the same split already
forced on `action_policy`:

```
rule_registry (rule_key pk, description, owner_team)
policy_chunk.rule_key  →  fk
```

Maintenance becomes *keep a registry of ~40 rules* rather than *tag 10,000
sections*. An unknown key fails ingestion.

**Where it genuinely breaks.** The external regulatory corpus (E5.8) cannot be
hand-tagged. So `rule_key` is null there, and **the contradiction guard does not
apply to it**. Two external circulars that conflict will not be flagged by this
mechanism. The guard covers the corpus where we decide, not the corpus where we
only read. Any claim beyond that fails in an audit.

## A4. Permission — three leaks, not one

**Leak 1 — retrieval.** The filter must be in the same `where` clause as the
search. Filter afterwards and you silently return fewer rows than asked for.

**Leak 2 — generation.** If the model reads a restricted passage and writes from
it, **the answer is the leak**, even though the passage was never shown. So the
filter runs before retrieval, not before display. There is no "retrieve
everything, show some".

**Leak 3 — the cache.** Two analysts with different clearances ask the same
question; the second gets the first one's cached results. **The cache key must
carry the permission set**, or caching becomes a permission bypass.

### Labels on every chunk

| Column | Meaning |
|---|---|
| `department` | `collections`, `credit`, `legal`, or `all` |
| `sensitivity` | 1 public, 2 internal, 3 restricted |
| `acl_groups` | empty array = no extra restriction |

Classification is the floor; the ACL is the exception. Both filtered in-query.

### Two callers, two rules

| | Department | Clearance | Groups |
|---|---|---|---|
| **Human** | any | `principal.clearance` | `principal.groups` |
| **Agent** | its own, declared at registration | its own, declared | none |

The agent does **not** inherit the human's clearance. If it did, the same case
would produce different findings for a senior and a junior analyst — the case
file stops being reproducible and the audit trail becomes "depends who clicked."

The agent acts for the institution. Its finding is a property of the case.

So the collections investigator registers as `(collections, 2)` and **cannot
read sensitivity 3 even when the document is tagged `collections`** — otherwise
its output, shown to a junior analyst, is leak 2 through the back door. A case
that genuinely needs a restricted policy escalates to a human. Agents on the
flow, humans on the exceptions.

### Two permission systems in one tool call

Worth writing down, because it looks wrong otherwise:

| What | Governed by |
|---|---|
| account rows (payment, bureau, contact) | RLS, via `principal.branch_ids` |
| corpus rows (policy chunks) | the agent's declared scope |

`principal` is still injected into `search_policy` — not because the corpus uses
it, but because every tool has the same signature and `dispatch` injects
uniformly. The corpus ignores it.

## A5. Cache and invalidation

| Path | Key |
|---|---|
| Agent | `(corpus_version, agent_name, query, as_of, limit)` |
| Human | `(corpus_version, clearance, sorted(groups), query, as_of, limit)` |

`corpus_version` is one integer in `corpus_meta`, **bumped by every ingestion,
in the same transaction as the writes**. Update a policy and every cached entry
becomes unreachable. No per-key invalidation, no staleness window, no eviction
logic.

The cache lives in a table, not in process. In-process is fine for one worker
and wrong the moment there are two.

## A6. Timing

`retrieve` returns a `Timing` alongside the passages —
`embed_ms`, `vector_ms`, `keyword_ms`, `total_ms` — logged on every call.

This is how you learn when an index is needed, instead of guessing. At ~50
chunks a sequential scan is exact and sub-millisecond; HNSW starts earning its
keep somewhere north of 100,000 rows. **Knowing when not to add the index is the
production skill.**

## A7. Guardrails — designed now, built with the human surface

| | Guard | Mechanism |
|---|---|---|
| G1 | **Grounding** | model emits structured claims with citations; verification is set membership against retrieved ids. Failure → refusal, not a low score. |
| G2 | **Contradiction** | two passages sharing a `rule_key` with overlapping effective windows. Deterministic, SQL, no model. Answer still goes out, both passages shown. |
| G3 | **Confidence** | band + reasons, never a float. Any conflict forces LOW. One passage can never be HIGH. |
| G4 | **Refusal** | vector search never returns nothing, so refusal must be constructed: nothing above `min_score`, or grounding failed twice. |

G4's first half — the `min_score` floor — is built **now**, in `retrieve`. The
rest waits for the model client.

## A8. Never

1. Never answer from model knowledge. Not in a retrieved passage, not in the answer.
2. Never return a passage outside the `as_of` window.
3. Never let `SearchPolicy` generate.
4. Never emit a numeric confidence.
5. Never silently drop a conflict.
6. Never bypass `dispatch`.
7. Never post-filter. Ever, on anything.

## A9. Build order and layout

| # | File | Ends |
|---|---|---|
| 1 | `alembic/versions/xxxx_policy_chunk.py` | |
| 2 | `rag/chunks.py` | |
| 3 | `rag/embed.py` | |
| 4 | `rag/read.py` | |
| 5 | `rag/split.py` | |
| 6 | corpus files under `resources/policy/` | |
| 7 | `rag/ingest.py` | |
| 8 | `rag/retrieve.py` | |
| 9 | `tools/policy.py` | **E5 complete** |
| 10 | `rag/cache.py` | optional; skip to close E5 sooner |

Deferred to the human surface: `rag/contradict.py`, `rag/confidence.py`,
`rag/ground.py`, `rag/answer.py`.

`rag/` depends on `db/` and nothing else. `tools/policy.py` depends on
`rag/retrieve`. Nothing in `rag/` imports from `agents/`.

---

# Part B — Low Level Design

Contract format throughout: **purpose / interface / invariants / forbidden / tests.**

---

## B1. Migration — `policy_chunk` and `corpus_meta`

**Purpose.** One row per chunk, carrying text, vector, keyword index, and the
metadata that filters, cites and debugs. Plus a single-row table holding the
corpus version.

```sql
create extension if not exists vector;

create table corpus_meta (
    id      integer primary key default 1,
    version integer not null default 0,
    check (id = 1)
);
insert into corpus_meta (id, version) values (1, 0);

create table policy_chunk (
    id             text primary key,     -- doc_id:section_slug:v{version}:{chunk_index}
    doc_id         text    not null,
    section        text    not null,
    heading_path   text    not null,
    chunk_index    integer not null,
    chunk_count    integer not null,
    rule_key       text,
    source_ref     text,
    version        integer not null,
    effective_from date    not null,
    effective_to   date,
    department     text    not null,
    sensitivity    integer not null check (sensitivity between 1 and 3),
    acl_groups     text[]  not null default '{}',
    text           text    not null,
    embedding      vector(768) not null,
    embed_model    text    not null,
    tsv            tsvector generated always as (to_tsvector('english', text)) stored,
    ingested_at    timestamptz not null default now()
);

create index policy_chunk_tsv_idx  on policy_chunk using gin (tsv);
create index policy_chunk_eff_idx  on policy_chunk (effective_from, effective_to);
create index policy_chunk_scope_idx on policy_chunk (department, sensitivity);
```

**Invariants.**

- `corpus_meta` holds exactly one row — `check (id = 1)` enforces it.
- `id` is deterministic, so re-ingesting the same corpus produces the same rows. Ingestion is an upsert, not an append, and a crashed run resumes by simply re-running.
- `effective_to` null means still in force. Half-open: `effective_from <= as_of < effective_to`.
- `embed_model` per row, so a model change is detectable rather than silently mixing two vector spaces.
- **No vector index.** ~50 rows; a sequential scan is exact and sub-millisecond. Revisit above ~100,000.

**Forbidden.** No account or branch column — the corpus is institutional.
`ingested_at` is observability only, never a filter. Two clocks, same rule as
`recorded_at`.

**Tests.** Duplicate `id` conflicts. `tsv` fills automatically. `sensitivity = 4`
is rejected. A second row in `corpus_meta` is rejected.

---

## B2. `rag/chunks.py`

**Purpose.** The types crossing module boundaries. No behaviour.

```python
@dataclass(frozen=True)
class Scope:
    department: str
    sensitivity: int
    acl_groups: tuple[str, ...] = ()

@dataclass(frozen=True)
class Piece:                 # splitter output, not yet embedded
    heading_path: str
    chunk_index: int
    chunk_count: int
    text: str

@dataclass(frozen=True)
class Chunk:                 # ingest side
    id: str
    doc_id: str
    section: str
    heading_path: str
    chunk_index: int
    chunk_count: int
    rule_key: str | None
    source_ref: str | None
    version: int
    effective_from: date
    effective_to: date | None
    scope: Scope
    text: str

@dataclass(frozen=True)
class Passage:               # retrieval side
    id: str
    doc_id: str
    section: str
    heading_path: str
    rule_key: str | None
    source_ref: str | None
    text: str
    score: float
    rank: int

@dataclass(frozen=True)
class Timing:
    embed_ms: float
    vector_ms: float
    keyword_ms: float
    total_ms: float
```

**Invariants.** All frozen — a retrieved passage is evidence, and evidence is not
edited in place. `Chunk` has no score; `Passage` has no dates. The type tells you
which side of the pipeline you are on.

**Forbidden.** No `embedding` field on any of them. The vector lives in the
database and appears in application code only as a local variable during
ingestion.

**Tests.** Assignment raises on each.

---

## B3. `rag/embed.py`

**Purpose.** Text → vector. Protocol first, fake first, real second — the
`ChatModel` / `FakeChatModel` pattern that already works.

```python
class Embedder(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def dimensions(self) -> int: ...
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class OllamaEmbedder:    # nomic-embed-text, 768 dims, 8192-token context
class FakeEmbedder:      # deterministic from a hash; offline
```

**Invariants.**

- `embed_documents` prepends `search_document: `; `embed_query` prepends `search_query: `. The asymmetry lives in code, never in the corpus files.
- Every vector has length `dimensions`.
- `FakeEmbedder` is deterministic, so tests need no running Ollama.

**Forbidden.** **No single `embed(text)` method.** One method makes the prefix
the caller's job, and the caller forgets. A missing prefix degrades retrieval
with no error — exactly the silent failure this split prevents.
`FakeEmbedder` never touches the network.

**Tests.**

1. `FakeEmbedder` returns the same vector twice for the same text.
2. **`embed_documents(["x"])[0] != embed_query("x")`** — the prefix test, and the one that catches the real bug.
3. Every vector has length `dimensions`.
4. `embed_documents([])` returns `[]`.

---

## B4. `rag/read.py` — the seam

**Purpose.** File → header + structured body. This is the file that makes
"scales to 500" true rather than aspirational.

```python
@dataclass(frozen=True)
class Section:
    level: int          # 2 for ##, 3 for ###
    heading: str
    body: str

@dataclass(frozen=True)
class RawDoc:
    path: Path
    meta: dict[str, Any]
    sections: tuple[Section, ...]

class Reader(Protocol):
    def read(self, path: Path) -> RawDoc: ...

class MarkdownReader:
    """YAML frontmatter, then headings."""
```

**Invariants.** A reader only extracts. It never validates, never splits, never
embeds. A file with no headings yields one `Section` at level 2 with an empty
heading.

**Forbidden.** No inference. A missing header key stays missing; it is not
guessed from the text.

**Tests.** Frontmatter parses into `meta`. `sections` excludes the frontmatter.
Two `##` headings yield two sections. A file without frontmatter raises.

*Later, `PdfReader` implements the same protocol and nothing downstream changes.*

---

## B5. `rag/split.py` — hybrid chunking

**Purpose.** Structure first, size as a backstop.

```python
def count_tokens(text: str) -> int:
    """Approximate. Swap for the embedder's tokenizer when it matters."""

def split(
    doc: RawDoc, *, max_tokens: int = 800, min_tokens: int = 120, overlap: int = 80,
) -> list[Piece]:
```

**Rules, in order.**

1. Cut on headings. Structure wins where it exists.
2. A section **over** `max_tokens` → split again on paragraphs, then sentences, carrying `overlap` tokens between consecutive pieces.
3. A section **under** `min_tokens` → merge forward into its next sibling.
4. **Never merge across a higher-level heading.** A `###` may merge with the next `###`; never into a different `##`.
5. Every piece carries its `heading_path`.

`max_tokens=800` follows the regulatory guidance in
`27-chunking-and-retrieval-eval.md` §3 — clauses reference each other, so larger
is safer here than in general prose.

**Invariants.**

- Pure. Same document, same pieces, every time.
- `chunk_index` is 0-based and contiguous; `chunk_count` equals `len(result)`.
- Concatenating the pieces of one section, minus overlap, reproduces the section.
- **`heading_path` is prepended to `text` before embedding.** With one chunk per file this was optional; with hybrid chunking piece 3 of 5 may open mid-thought, so it is now required. This is contextual retrieval, obtained free.

**Forbidden.** No model call. No reordering. No dropping content — every word of
the source appears in at least one piece.

**Tests.**

1. A short section yields exactly one piece.
2. A section over `max_tokens` yields more than one, each within budget.
3. Consecutive pieces of one section share `overlap` text.
4. A section under `min_tokens` merges with its sibling.
5. A `###` never merges across a `##` boundary.
6. `chunk_index` is 0..n-1 and `chunk_count == n` on every piece.
7. No content is lost.

---

## B6. `rag/ingest.py`

**Purpose.** Corpus files → rows, and bump the version. Runs offline.

```python
class CorpusError(Exception): ...

@dataclass(frozen=True)
class IngestResult:
    rows_written: int
    corpus_version: int

def load_corpus(root: Path, reader: Reader) -> list[Chunk]
def ingest(conn, chunks: Sequence[Chunk], embedder: Embedder) -> IngestResult
```

**Invariants.**

- **Validate at load, not at use.** Required frontmatter keys present; `rule_key` matches `^[a-z_]+(\.[a-z_]+)+$` when present; `effective_to` null or strictly after `effective_from`; `sensitivity` in 1–3; `department` from the known set; body non-empty. First failure raises `CorpusError` **naming the file**.
- `ingest` is idempotent. Twice over an unchanged corpus writes the same rows and changes nothing observable but `ingested_at`.
- Embedding is **one batched call**, not one per chunk.
- `corpus_version` increments in the **same transaction** as the writes. A failed ingestion leaves both the rows and the version untouched.

**Forbidden.** No partial ingestion — all of it loads or nothing is written. A
half-ingested corpus is a corpus with invisible holes. No inference of absent
metadata.

**Tests.**

1. A file missing `doc_id` raises `CorpusError` naming that file.
2. `rule_key: FieldVisit` raises.
3. `effective_to` before `effective_from` raises.
4. `sensitivity: 4` raises.
5. Ingesting twice leaves the row count unchanged.
6. The embedder is called **once**, not once per chunk (assert on a counting fake).
7. `corpus_version` increases by exactly 1 per successful run.
8. A failure mid-run leaves `corpus_version` unchanged.

---

## B7. `rag/retrieve.py` — the core

**Purpose.** Question → ranked passages, or nothing.

```python
def retrieve(
    conn, query: str, as_of: date, embedder: Embedder, scope: Scope, *,
    candidates: int = 50, limit: int = 5, min_score: float = MIN_SCORE,
) -> tuple[list[Passage], Timing]
```

**Mechanism.** Two branches, identically filtered, fused by RRF:

```sql
with vec as (
    select id, row_number() over (order by embedding <=> %(qv)s) as rank
    from policy_chunk
    where effective_from <= %(as_of)s
      and (effective_to is null or effective_to > %(as_of)s)
      and sensitivity <= %(clearance)s
      and department in (%(dept)s, 'all')
      and (acl_groups = '{}' or acl_groups && %(groups)s)
    limit %(candidates)s
),
kw as (
    select id, row_number() over (
               order by ts_rank(tsv, plainto_tsquery('english', %(qt)s)) desc
           ) as rank
    from policy_chunk
    where tsv @@ plainto_tsquery('english', %(qt)s)
      and effective_from <= %(as_of)s
      and (effective_to is null or effective_to > %(as_of)s)
      and sensitivity <= %(clearance)s
      and department in (%(dept)s, 'all')
      and (acl_groups = '{}' or acl_groups && %(groups)s)
    limit %(candidates)s
)
select c.*,
       coalesce(1.0 / (60 + vec.rank), 0) + coalesce(1.0 / (60 + kw.rank), 0) as score
from policy_chunk c
left join vec on vec.id = c.id
left join kw  on kw.id  = c.id
where vec.id is not null or kw.id is not null
order by score desc;
```

**Invariants.**

- **Every filter appears in both branches.** Two searches, two places to forget it.
- Returns `[]` when nothing clears `min_score`. An empty list is a valid, meaningful result.
- **Deduplicated on `(doc_id, section, version)`, keeping the best score.** This was tidiness before hybrid chunking; it is now a correctness requirement — a section split into three pieces would otherwise present as three passages sharing one `rule_key`, which the contradiction guard would read as a conflict of our own making.
- `rank` is 1..n, assigned after fusion and dedupe.
- Order is descending score. Never re-sorted by date or section.
- `Timing` returned on every call, success or empty.

**Forbidden.** No post-filtering. No generation, summarisation or truncation of
`text`. No fallback that widens the date window when results are thin — a
question about today is answered with today's policy or not at all.

**Tests.**

1. A query matching nothing returns `[]`, not five weak rows.
2. A chunk whose `effective_to` precedes `as_of` never appears.
3. A chunk whose `effective_from` follows `as_of` never appears.
4. **`SMA-2` ranks the SMA-2 section above the SMA-1 section.** Write this first and watch it fail on vector-only — it is the proof hybrid search is a correctness requirement here, not an optimisation.
5. A `sensitivity: 3` chunk is invisible to a clearance-2 scope.
6. A `department: legal` chunk is invisible to a collections scope.
7. A chunk with `acl_groups: ['fraud']` is invisible to a scope without that group.
8. Two pieces of one section never both appear.
9. `len(result) <= limit`; ranks are 1..n; scores non-increasing.
10. `Timing.total_ms > 0` even when the result is empty.

---

## B8. `tools/policy.py` — `SearchPolicy`

**Purpose.** The agent's door to `retrieve`. A thin adapter.

```python
class SearchPolicy:
    name = "search_policy"
    description = ...
    @property
    def parameters(self) -> dict[str, Any]: ...
    def __call__(self, conn, principal, *, query: str, as_of: date, limit: int = 5) -> ToolResult
```

**Invariants.**

- Scope comes from `scope_for(agent)` in `registry.py`, **not** from `principal`.
- `success(data=[passage dicts], as_of=as_of, omitted=...)`. Empty `data` with `ok=True` when the corpus does not address the question — **not a failure**.
- `omitted` counts candidates fused but cut by `limit`.
- Registered for the `policy` agent only.

**Forbidden.** No answer text. No filtering of the corpus by `principal` — it is
in the signature for uniformity and ignored here. Never raises on an empty
corpus.

**Tests.**

1. `parameters` exists. (Learned the hard way.)
2. Empty result → `ok=True`, `data == []`.
3. An out-of-window chunk never appears.
4. Returned dicts contain no `embedding`.
5. `dispatch` refuses it for an agent that does not have it.
6. All 171 existing tests still pass.

---

## B9. `rag/cache.py` — optional, last

**Purpose.** Avoid re-running an identical search. Correct under concurrency.

```python
def make_key(corpus_version: int, agent: str, query: str, as_of: date, limit: int) -> str
def get(conn, key: str) -> list[Passage] | None
def put(conn, key: str, passages: Sequence[Passage]) -> None
```

**Invariants.** The key **always begins with `corpus_version`**, so ingestion
invalidates everything at once. A miss is never an error. Stored in a table, not
in process — in-process is fine for one worker and wrong for two.

**Forbidden.** No key without a permission component. That is how one analyst's
results reach another.

**Tests.** Same inputs hit. Bumping `corpus_version` misses. Two agents never
share an entry. A miss returns `None`, never raises.

---

## B10. Deferred — the human surface

Designed, not built. Blocked on the real model client and its `Message`
tool-calls gap (`26-open-items.md`, E6.4).

| Module | Contract |
|---|---|
| `rag/contradict.py` | `find_conflicts(passages) -> list[Conflict]`. Pure, groups on `rule_key`, ≥2 is a conflict, `None` never conflicts, no model. |
| `rag/confidence.py` | `assess(passages, conflicts) -> Confidence`. Band + reasons, never a float. Any conflict forces LOW. One passage is never HIGH. `reasons` never empty. |
| `rag/ground.py` | `verify(claims, passages) -> list[GroundingFailure]`. Set membership against retrieved ids. No partial credit. Reports, never repairs. |
| `rag/answer.py` | `answer(...) -> Answer \| Refusal`. Errors as values. Exactly one retry on grounding failure. `Refusal` carries what was retrieved, for the audit trail. |

---

# Part C — Stories

### S1 — The store exists
- [ ] `alembic upgrade head` creates `policy_chunk` and `corpus_meta`; downgrade removes both
- [ ] `corpus_meta` rejects a second row
- [ ] `tsv` populates without being written
- [ ] `sensitivity: 4` is rejected

### S2 — Text becomes vectors, two ways
- [ ] `FakeEmbedder` is deterministic and offline
- [ ] `embed_documents("x") != embed_query("x")`
- [ ] All vectors have length `dimensions`
- [ ] Nothing in `rag/` embeds except through these two methods

### S3 — Files are read, then split
- [ ] Frontmatter parses; body excludes it
- [ ] Two `##` headings give two sections
- [ ] A long section splits into budget-sized pieces with overlap
- [ ] A tiny section merges forward, never across a higher heading
- [ ] `chunk_index` 0..n-1, `chunk_count == n`, no content lost
- [ ] `heading_path` is prepended before embedding

### S4 — The corpus exists
- [ ] 12 sections under `resources/policy/`, per `24-rbi-source-pack.md` §10
- [ ] Complete frontmatter on every file, including `department` and `sensitivity`
- [ ] Every section names its circular in `source_ref`
- [ ] Exactly one in-force section per `rule_key`
- [ ] At least one `sensitivity: 3` section, so the permission tests have something to hide

### S5 — Files become rows
- [ ] Invalid file raises `CorpusError` naming it; nothing is written
- [ ] Twice leaves the row count unchanged
- [ ] The embedder is called once
- [ ] `corpus_version` increases by exactly 1, and not at all on failure

### S6 — Retrieval finds the right passage, and only the allowed ones
- [ ] Nothing relevant → `[]`
- [ ] Out-of-window chunks never appear, in either branch
- [ ] **`SMA-2` outranks `SMA-1`** — the hybrid-search proof
- [ ] Sensitivity, department and ACL each hide a chunk
- [ ] Two pieces of one section never both appear
- [ ] `Timing` returned on every call

### S7 — The agent can search policy — **E5 complete**
- [ ] `search_policy` in `tools_for("policy")` and nowhere else
- [ ] `parameters` exists and is valid JSON schema
- [ ] Empty result is `ok=True`
- [ ] `dispatch` refuses it for other agents
- [ ] No `embedding` in the returned data
- [ ] All 171 existing tests still pass

### S8 — Cache (optional)
- [ ] Same inputs hit; bumped `corpus_version` misses
- [ ] Two agents never share an entry
