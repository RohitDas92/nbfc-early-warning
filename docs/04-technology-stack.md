# 04 — Technology Stack

One technology per box in the architecture diagram, and why. Everything here runs locally with `docker compose up` — Azure is used where it earns its place, never as a dependency for someone reviewing the repo.

---

## 1. The stack

| Architecture box | Technology | Why this one |
|---|---|---|
| Language / runtime | **Python 3.11**, pinned in the Dockerfile | Your strength, and where the agent ecosystem lives. 3.11 over 3.12 deliberately — see §2 |
| Application API | **FastAPI** | Async, typed, auto-generated OpenAPI. Also the gap you wanted to close |
| Portfolio + derived + case + audit stores | **PostgreSQL 16** | One database for all four. Relational fits every one of them |
| Row-level access control | **Postgres RLS** | The database refuses out-of-scope rows. A forgotten `WHERE` cannot leak |
| Knowledge store | **pgvector + Postgres full-text** | Same database. Vector search and BM25 without a second system |
| Reranking | **Local cross-encoder** (`bge-reranker-base` class) | Deterministic, free, CPU-only. Keeps eval scores stable |
| Embeddings | **Local sentence-transformer** (`bge-small-en` class) | Free forever, no Azure dependency, quality difference is negligible at this corpus size |
| Agent orchestration | **LangGraph** | Explicit nodes and edges, Postgres checkpointing, human-in-the-loop interrupts. Runs in your process — the client-side control you wanted |
| Model service | **Azure OpenAI**, two deployments | A small model for routing and classification, a stronger one for narrative and policy reasoning |
| Schema validation | **Pydantic v2** | Tool outputs, API schemas, config — one validation story |
| Migrations | **Alembic** | Risk #2 requires outcome tables in the first migration; you need real migrations for that to mean anything |
| Observability | **Langfuse, self-hosted** | Traces at case granularity, prompt versioning, cost per case. Self-hosted so traces never leave |
| UI | **Streamlit** | Thin client over the API. No business logic |
| Nightly run | **A CLI command in a container** | `python -m ews.batch nightly`. One scheduled job does not need an orchestrator |
| Data generation | **Faker (en_IN) + NumPy**, seeded | Reproducible book, committed seed, no committed PDFs |
| Tests | **pytest** | Plus the architecture test, the authz matrix, and recorded model fixtures |
| Packaging | **Docker + docker compose** | Postgres, Langfuse, API, Streamlit. One command to run everything |
| Lint / format | **ruff** | Already in the pre-commit config |

## 2. The five choices where a reasonable person would disagree

**Python 3.11, not 3.12.** By now everything in this stack supports 3.12 — the wheel and build problems that made 3.12 painful in its first year are long resolved. But 3.11 costs nothing here: no feature in this project needs 3.12, it has security support into late 2027, and it's the version most documentation and answers still assume. Against a 12 October deadline, the correct tiebreaker is "the version I will never have to think about."

**The version is pinned in the Dockerfile and the work happens inside the container**, so whatever Python is on the laptop is irrelevant, and CI runs the identical image. That matters more than the version number — on Windows, installing the torch-based reranker locally is fiddly at any version, and the container removes the problem entirely.


**LangGraph, not plain Python function-calling.** Plain Python gives more control and no framework churn. LangGraph gives you checkpointing and interrupts for free, and those are requirements here — a case must be resumable and must pause for a human. Writing that yourself is a week you don't have. It's also the framework most likely to come up in an interview.

**pgvector, not Azure AI Search — by default.** Search Basic is ~₹9,277/month for a service that sits idle. pgvector costs nothing and runs on any reviewer's laptop. **But keep a `Retriever` interface with both implementations**: build the Azure one in half a day for AI-103, then benchmark both on the same eval set. "I measured both" is a far better answer than either choice alone.

**Local embeddings, not Azure embeddings.** Embedding cost is trivial either way — this is about the repo running without a subscription after your credits expire around 11 October.

**Local JWT with OIDC-shaped claims, not Entra ID.** Real Entra makes the repo unrunnable for anyone without your tenant, and it isn't the interesting part — the interesting part is permission × scope enforced by RLS. Build the identity provider behind an interface and document Entra as the production path.

## 3. What we are deliberately not using

No Airflow or Prefect — there is one nightly job. No Kubernetes — there is one application. No dedicated vector database — Postgres does it at this size. No message queue — nothing is asynchronous between components. No microservices — one service, one database.

Being able to say *"10,000 loans, one nightly job, one user-facing app — none of that infrastructure would have earned its keep"* is a better signal than having used any of it.

## 4. What this costs

Everything except model calls runs locally at zero cost: Postgres, pgvector, the reranker, embeddings, Langfuse, Streamlit, the batch job.

Azure spend is model tokens only — small-model routing plus a stronger model on the narrative and policy nodes, on roughly 60–80 cases a week. Optionally Container Apps on consumption with scale-to-zero for a hosted demo.

Standard pay-per-token deployments only. **Never provisioned throughput** — that is a reserved hourly commitment and the one mistake that turns a few hundred rupees into tens of thousands.

## 5. Local topology

`docker compose` brings up four services: **postgres** (with pgvector), **langfuse**, **api** (FastAPI), **ui** (Streamlit). The batch job runs as a one-off command against the same database.

Tests run against recorded model fixtures, not live calls — so CI is free and the suite is deterministic.

---

**One housekeeping note:** the `nbfc_credit_ops` folder was named when we were still building the credit-file system. Rename it to match what this actually is — `ews` or `nbfc_ews` — before anything imports from it.
