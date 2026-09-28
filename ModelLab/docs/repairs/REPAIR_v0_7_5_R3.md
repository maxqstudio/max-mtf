# CPMF v0.7.5 R3 — Topology Priority + Decision Contract

R3 extends the accepted v0.7.5 R2 Transformer-family baseline without changing stage order or KPI thresholds.

## Changes

- Owner `Single ↔ Hybrid` slider in Advanced, range `0.00..1.00`, default `0.50`, step `0.05`.
- Slider controls candidate-count allocation only; it is not an ensemble/prediction blend.
- Compiled research plan persists immutable topology authority for the Factory.
- Adaptive planner and deterministic fallback generator both enforce the same allocation.
- Scientist can choose families/compositions inside the allocation but cannot override it.
- Planner evidence records target/actual topology counts and estimated compute share separately.
- Compatible hybrid composition is auto-added minimally when needed to make a requested hybrid share executable inside the Owner-permitted family universe.
- Canonical final probability contract is `[SELL, SKIP, BUY]` for standalone and hybrid candidates.
- Hybrid cooperation remains `temporal DOWN/UP -> CP32+4 -> policy SELL/SKIP/BUY` with purged OOF stacking.

## New acceptance authority

- `R10_TOPOLOGY_PRIORITY`
- `R10_STANDALONE_HYBRID_DECISION_CONTRACT`

All R9/R8/R7/R6 and cumulative historical gates remain required.
