# 03 — Risks and Mitigations

Things that could go wrong later, and what to do now so they don't. Each mitigation is something that gets *built*, not something to remember.

---

| # | Risk | What it looks like | Mitigation | Do it when |
|---|---|---|---|---|
| 1 | Case routing drifts into the agentic layer | Someone says "let the agent handle edge cases"; nightly cost and runtime blow up | Router lives in a module with **no access to the model client**. Add a build test that fails if that module imports it. Write routing as pure functions with a table of test cases. | First week |
| 2 | Outcome learning never gets built | W4 runs short, the learning loop is dropped, recommendations become plain policy lookup | Split it. **Capture** (interventions + outcomes) goes in the **first database migration**, with a constraint rejecting a closed case that has no outcome. **Consumption** (reading history) is scheduled in **W3, not W4**. Make it a visible dashboard screen so its absence is obvious. | First migration; consumption W3 |
| 3 | PII escapes through the back door | Traces contain the whole case; a hosted observability tier ships it to a third party | One egress gate covering **both** model calls and trace export. Self-host observability. Add a test asserting a call carrying a raw PAN throws. | Before the first model call |
| 4 | The agent becomes a way around access control | Analyst can't see an account in the UI but the case chat answers about it | Tools execute under the **caller's** identity, never a service account. Test matrix of role × endpoint × scope asserting the refusals. New endpoint without an authz test fails the build. | With the first tool |
| 5 | Synthetic data is too easy | Everything scores well; the first real dataset breaks it | Plant deterioration at realistic strength (~3× base rate, not 100%). Include confounders that look real but aren't. | With the generator |
| 6 | Evaluation gets tuned to its own test set | Scores improve, real performance doesn't | Two books from different seeds. The second is **not opened until W4**. | With the generator |
| 7 | Cost runs away | A looping agent, or eager investigation of everything | Hard step budget per case. Cost logged per case from day one. Cloud budget alert at 50%. | First week |
| 8 | The queue fills with duplicates | Same struggling account raises a fresh alert every month; analysts stop trusting it | Suppression: a signal on an account with an open case joins it. ~240 signals/week should resolve to ~60–80 cases. Test the ratio. | With the router |

---

**The pattern in all eight:** each mitigation is a constraint, a test, or a scheduling decision — never a rule someone has to remember. Discipline decays over four weeks; a failing build does not.
