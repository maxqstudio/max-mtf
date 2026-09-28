# Repair v0.7.9 — Scientist KPI Semantics + Native MT5 Task Transparency

## Scope

v0.7.9 keeps the v0.7.8 canonical-EA and single-click lifecycle repair intact. It closes two interpretation gaps found during real Owner MT5 use:

1. MT5 `Tasks / Passed` counts could be mistaken for Max creating many optimizer rounds. Max now exposes that one Max round owns one native MT5 optimization and that MT5 itself schedules genetic passes across tester agents.
2. Scientist knew the per-gate schema but not enough of the scientific role of each gate. This allowed advice such as copying all risk KPIs across gates, treating Tournament as unseen OOS, or placing DSR/PSR as generic Monte Carlo metrics.

## Scientist semantic contract

- Discovery: early screen + Full 3-fold WFA; preserve diversity and distinguish diagnostics from hard gates.
- CPCV: purged-combinatorial robustness; PBO CPCV-only and `NOT_COMPUTABLE` without canonical cross-strategy matrix.
- Tournament: hard eligibility + ranking of CPCV survivors; not Fresh/OOS; no Top-K elimination.
- Monte Carlo: path/tail robustness; PSR/DSR are not native Monte Carlo metrics.
- Fresh Forward: untouched final generalization; no post-result threshold relaxation.
- Champion: promotion/integrity/runtime only.
- DSR requires defensible trial-universe/effective-trials accounting.
- Owner policy references known to Scientist: Optimizer H1=20 trades/month, Research H1=8 trades/month, Fresh production target Expectancy >=0.50R, PF >=1.50, RF >=3.00, Max DD <10%. Runtime unit differences must be flagged, not silently converted.

## MT5 scheduling contract

`search_space_cardinality()` reports only the full Cartesian grid size. It is explicitly marked `RAW_CARTESIAN_GRID_ONLY_NOT_MT5_GENETIC_TASK_COUNT`. Fast Genetic population/job scheduling remains MT5-native authority.

## Acceptance

Dedicated v0.7.9 gate: `R23_SCIENTIST_KPI_NATIVE_MT5_TASK_SEMANTICS`.
