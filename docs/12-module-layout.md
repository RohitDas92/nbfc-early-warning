# 12 — Folder and Module Layout

Where every piece of code lives, what belongs in each folder, and — more importantly — the dependency rules that keep the design from eroding.

---

## 1. The tree

```
azure_project/
├── docs/                      design documents (done)
├── resources/                 the generator and the data (done)
│
├── src/nbfc_ews/
│   ├── config.py              settings, env, which implementation is live
│   │
│   ├── domain/                PURE — no I/O, no database, no model client
│   │   ├── models.py          Signal, Case, Finding, Evidence, Recommendation
│   │   ├── classification.py  dpd → bucket → asset_class, provisioning
│   │   ├── signals.py         the ten rules and their thresholds
│   │   ├── routing.py         (signal, open_cases) → open | join | escalate
│   │   ├── case_state.py      apply_event — the state machine
│   │   ├── authority.py       action × role × amount → permitted
│   │   └── pii.py             the PII column registry, tokenise / detokenise
│   │
│   ├── db/
│   │   ├── engine.py          connections, sessions, SET LOCAL principal
│   │   ├── repositories/      one per aggregate: loans, cases, signals, interventions
│   │   └── migrations/        alembic
│   │
│   ├── engine/                THE DETERMINISTIC PIPELINE
│   │   ├── classify.py        writes loan_month_state and derived metrics
│   │   ├── detect.py          runs the signal rules over the book
│   │   ├── route.py           suppression and case creation
│   │   └── nightly.py         the batch orchestrator
│   │
│   ├── llm/
│   │   ├── base.py            ChatModel interface
│   │   ├── azure_openai.py
│   │   ├── local.py           the fallback that keeps the repo alive after credits lapse
│   │   └── fake.py            FakeChatModel — the one that makes agents testable
│   │
│   ├── guard/
│   │   ├── egress.py          THE single choke point. Fails closed.
│   │   ├── pii_detector.py    interface: regex | Azure AI Language
│   │   └── content_safety.py
│   │
│   ├── retrieval/
│   │   ├── base.py            Retriever interface
│   │   ├── pgvector.py        the default
│   │   ├── azure_search.py    the benchmark comparison
│   │   └── rerank.py
│   │
│   ├── tools/                 what agents may call — read-only by construction
│   │   ├── base.py            Tool protocol: takes a principal, returns ToolResult
│   │   ├── payment.py         get_payment_behaviour, get_balance_trend
│   │   ├── external.py        get_bureau_history
│   │   ├── context.py         get_institution_profile, get_tranche_history
│   │   ├── cohort.py          find_similar_alerts
│   │   ├── policy.py          search_policy, get_intervention_outcomes
│   │   └── registry.py        name → tool, and which agent may use which
│   │
│   ├── agents/
│   │   ├── state.py           CaseInvestigationState
│   │   ├── supervisor.py
│   │   ├── investigators/     repayment · external · context · cohort · policy
│   │   ├── arbitrate.py
│   │   ├── compose.py
│   │   ├── graph.py           nodes and edges only — no business logic
│   │   └── prompts/           versioned prompt text
│   │
│   ├── services/              the operations the API exposes
│   │   ├── case_service.py    open / join / snooze / close — calls domain.case_state
│   │   ├── portfolio_service.py
│   │   └── chat_service.py
│   │
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py            auth, principal resolution, require(permission)
│   │   └── routers/           cases · portfolio · chat · admin
│   │
│   ├── obs/
│   │   ├── tracing.py         case-level traces
│   │   └── cost.py
│   │
│   └── cli.py                 entry points: nightly, eval, seed
│
├── ui/                        Streamlit — imports nothing from src, calls the API
├── eval/                      never imported by src
├── tests/                     unit · contract · integration · agents · arch
├── infra/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## 2. The dependency rule — this is the actual design

Imports flow **one way only**:

```
domain/      imports nothing from this project
db/          → domain
retrieval/   → domain
engine/      → domain, db          ← NOT agents, NOT llm, NOT tools
tools/       → domain, db, retrieval
agents/      → domain, tools, llm, guard
services/    → domain, db, engine, agents
api/         → services
ui/          → nothing. HTTP only.
eval/        → domain, db. Never imported BY src.
```

**Two lines in there carry most of the architecture:**

`engine/` must not import `llm/`, `agents/` or `tools/`. That is the determinism boundary expressed as code. It is also the architecture test that fails your build if someone quietly moves case routing into the agentic layer three weeks from now.

`ui/` imports nothing from `src`. That is "thin client" made structural rather than aspirational. If the dashboard can't import your services, it can't accidentally hold business logic.

## 3. What belongs in each folder — and what must never

| Folder | Belongs | Never |
|---|---|---|
| **domain/** | Pure functions and data shapes. Given inputs, return outputs | A database call, a clock read, `random`, an HTTP request. If you need "now", pass it in as an argument |
| **db/** | Queries, sessions, mapping rows to domain objects | Business rules. A repository that decides something is in the wrong folder |
| **engine/** | The nightly pipeline, calling domain functions | Anything that reasons. No model, no agent, no tool |
| **llm/** | Model clients behind one interface | Prompts. Those live with the agents that use them |
| **guard/** | The egress gate, PII detection, content safety | Anything else. This folder is small on purpose |
| **tools/** | Read queries shaped as answers to questions | Any write, any external effect. There should be no tool that *can* act |
| **agents/** | Node functions, prompts, the graph wiring | SQL. Agents call tools; they never touch the database |
| **services/** | Operations that combine domain + db + engine + agents | Request parsing, HTTP concerns |
| **api/** | Routing, auth, serialisation | Business logic. If a router has an `if` about lending, it belongs in a service |
| **eval/** | Scoring, metrics, the harness | Being imported by `src`. One-way street |

## 4. Two rules of thumb for files

**One reason to change.** `classification.py` changes when RBI changes a threshold. `routing.py` changes when the suppression policy changes. If one file changes for both reasons, split it.

**About 200 lines.** Not a law, a smell. Past that, ask what two things the file is doing.

## 5. Where to start — the first three files

In this order, because each is pure, testable in isolation, and needed by everything after:

**1. `domain/classification.py`** — `dpd → bucket → asset_class`, with the boundary table test (0, 1, 30, 31, 60, 61, 90, 91). Thirty lines of code, forty of tests, and it's the foundation of the whole engine.

**2. `domain/case_state.py`** — `apply_event`, with the full transition table including the illegal moves that must raise.

**3. `domain/signals.py`** — the ten rules as data plus a pure evaluator. Each rule gets a fires and a does-not-fire test.

All three are pure Python. No database, no Docker, no Azure. You could write them on a train.

Then `db/repositories/` and `engine/detect.py` to run those rules over the real book — and at that point you have the rules-only arm, which is the control for the entire evaluation.

## 6. One housekeeping note

The existing `nbfc_credit_ops` folder was named before the project changed direction. The package should be `src/nbfc_ews/`. Rename it now, before anything imports from it.
