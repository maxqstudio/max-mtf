# MAX Research Agent v0.12.3 — Challenger Workspace + E2E Evidence Parity

## Scope

UI/lifecycle observability + Golden E2E evidence fidelity only. Trading strategy, model decision contract, KPI production policy, optimizer objective, and promotion authority are unchanged.

## Repairs

- Dedicated `Challengers` navigation page owns Strategy and Model Challenger registries and promotion/shadow/delete actions already supported by their respective authorities.
- `Champion` page shows current Strategy Champion and current Model Champion separately from non-production Challengers.
- Strategy Optimizer points eligible winners to the Challengers page instead of duplicating the registry.
- Golden E2E Challenger locked KPI values are copied from actual Forward winner evidence; no placeholder win-rate/payoff/CVaR values.
- Synthetic sandbox promotion proofs carry `evidence_source=SYNTHETIC_E2E`; propagated Golden Forward KPI evidence carries `evidence_source=GOLDEN_FORWARD_EVIDENCE`.

## Non-goals

No production scientific gate is weakened. No production Champion is auto-promoted.
