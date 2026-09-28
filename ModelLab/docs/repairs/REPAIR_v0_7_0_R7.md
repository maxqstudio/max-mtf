# CPMF v0.7.0 R7 — Hybrid-Only Research Continuity Repair

## Owner-observed failure

With only `hybrid_gru_xgboost`, `hybrid_gru_lightgbm`, and `hybrid_gru_random_forest` enabled, round 1 completed and produced strong evidence, then the Factory worker failed before scheduling round 2.

## Root cause

The adaptive planner retained the legacy staged-unlock rule that filtered hybrid families until a standalone `gru` experiment existed. In an intentional hybrid-only configuration, standalone GRU is disabled, so the eligible family-weight map became empty and `_weighted_family()` raised an opaque `StopIteration`.

## Repair

- Hybrid-only mode is now a first-class planner state.
- If every enabled deployable family is `hybrid_gru_*`, hybrids are immediately eligible in all rounds.
- Standalone GRU remains an optional temporal seed, not a dependency.
- The per-round hybrid CPU cap applies only when non-hybrid alternatives exist; hybrid-only mode preserves the requested round budget.
- Empty eligible-family state now raises an explicit configuration error instead of opaque `StopIteration`.
- LLM Scientist family priorities may bias allocation among the three hybrids but the minimum-family-weight floor preserves exploration.

## Regression authority

`HYBRID_ONLY_RESEARCH_CONTINUITY` proves a config with exactly the three hybrid families can generate round 1, consume positive hybrid evidence, and generate a full round 2 without standalone GRU or non-hybrid fallback.
