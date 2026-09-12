# 08 — Azure Coverage

Where Azure actually appears in this build, and where it deliberately doesn't. Sits alongside doc 04 rather than replacing it.

Figures marked ⚠ are free-tier allowances to confirm at provisioning.

---

## 1. Where we are today

**Azure is the model endpoint and nothing else.** Postgres, pgvector, the reranker, embeddings, Langfuse, Streamlit and the batch job all run locally.

That is the right call for the repo — local-first is what keeps it running after the credits lapse around 11 October, which is the week applications start. But as an Azure story it is thin, and AI-103 was supposed to be the same project.

## 2. The rule that makes this safe

**Every Azure service sits behind an interface with a local fallback**, exactly like the retriever.

```
Retriever          → PgVectorRetriever      | AzureSearchRetriever
PiiDetector        → RegexPiiDetector       | AzureLanguagePiiDetector
ContentGuard       → NullContentGuard       | AzureContentSafetyGuard
ChatModel          → LocalModel             | AzureOpenAIModel
```

Config decides which is live. Without this, credit expiry breaks the repo in the worst possible week.

## 3. What to add, in build order

| # | Service | What it does here | Effort | Exam domain | Priority |
|---|---|---|---|---|---|
| 1 | **Azure OpenAI** | Two deployments — a small model for routing and triage, a stronger one for narrative and policy reasoning. Model routing is also the cost story | done in W1 | Generative AI | **Core** |
| 2 | **Azure AI Language — PII detection** | Sits *inside* the egress gate: detects identifiers before anything leaves the boundary | half day, W2 | Text analysis | **Core** |
| 3 | **Azure AI Search** | Second retriever for the policy corpus, behind the interface. Produces the benchmark against pgvector | half day, W2 | Knowledge mining | **Core** |
| 4 | **Content Safety** | Guardrail on generated case narratives | 2 hours, W3 | Generative AI | **Core** |
| 5 | **Container Apps + Application Insights** | Deployment and traces. Needed for the demo anyway | W4 | Plan and manage | **Core** |
| 6 | **Foundry evaluations** | Run the eval set through Foundry's SDK alongside your own harness | 1 day, W4 | Generative AI | Optional |
| 7 | **Entra ID** | The auth provider we deferred | 1 day | Plan and manage | Optional — see below |

### Why #2 is the best of these

The egress gate has to find identifiers before anything crosses to the model. Right now that's a regex you'd have to write and then defend when someone asks what happens to an unusual format.

Swapping in a real PII detection service makes the **control genuinely stronger** and covers an exam domain at the same time. It isn't decoration — it's the one place where the Azure service is a better answer than the local one, and you can say so.

### Why #7 stays optional

Real Entra makes the repo unrunnable for anyone without your tenant. That's a bad trade for a portfolio piece. Build the identity provider behind an interface, document Entra as the production path, and add it only if time is genuinely spare.

## 4. What this project can never cover

**Computer vision and information extraction.** There are no documents in early warning — nothing to OCR, nothing to extract. Together those are roughly a quarter of AI-103.

That work stays in the course and the Microsoft Learn labs. Un-park whichever course sections cover them and treat those as pure exam prep, unconnected to the build. Better to know that now than on 7 October.

## 5. Cost

All of the core items sit inside free tiers or consumption pricing:

| Service | Cost |
|---|---|
| Azure OpenAI | Tokens only — ~70 cases/week on a small model is negligible |
| AI Search | **Free tier, ₹0** — 3 indexes, 50 MB, 0.5 GB vector. Never Basic at ₹9,277/month |
| AI Language | ⚠ free tier covers far more than 70 cases/week |
| Content Safety | ⚠ free tier |
| Container Apps | Consumption, scale to zero, monthly free grant |
| Application Insights | ⚠ first 5 GB/month free |

**Standard pay-per-token deployments only. Never provisioned throughput** — that's a reserved hourly commitment and the one mistake that turns a few hundred rupees into tens of thousands.

## 6. What this buys you in a room

Before: *"I called the Azure OpenAI API."*

After: *"Retrieval runs behind an interface with two implementations — pgvector and Azure AI Search — benchmarked on the same evaluation set, and here are the recall and latency numbers. PII detection at the egress boundary uses Azure AI Language rather than a regex, because I have to defend what happens to formats I didn't anticipate. Content Safety guards the generated narrative. Everything is behind an interface with a local fallback, so the repo runs without a subscription."*

The second is an Azure engineer describing trade-offs. The first is someone who has an API key.
