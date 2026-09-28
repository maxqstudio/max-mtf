# CPMF KPI / CPCV Governance V6

## v0.7.6 ownership override

This document remains the formula/default-history reference for the R6 risk metrics. **Current Factory threshold ownership is `gate_kpis` under `ModelLab/docs/contracts/KPI_BY_GATE_V076.md`, not one global `acceptance` registry.** On first migration, legacy Owner values are copied into the relevant gate profiles; after migration the profiles are independent.

## Hard-gate authority

R6 keeps stage-specific gates explicit and never lets Ranking Score compensate for a failed hard gate.

- Full-WFA worst expectancy: **`cv_min_worst_expectancy_r = 0.00R`**.
- CPCV worst aggregate validation expectancy: **`cpcv_min_worst_expectancy_r = 0.00R`**.
- A shared numerical epsilon is used only for floating-point noise; the business floor remains exactly `0.00R`.
- Ranking Score never compensates for a failed hard gate.

## Advanced risk & research KPI — default ACTIVE hard gates

The seven metric definitions/defaults originate from the R6 registry. In v0.7.6, each applicable Research gate owns its own `gate_kpis.<gate>.risk_kpis` copy; `acceptance.risk_kpis` is legacy compatibility/migration input, not active cross-gate threshold authority. Advanced renders the per-gate registries; thresholds are not hidden in UI code.

| Metric | Default hard gate | Authority basis |
|---|---:|---|
| Sharpe | **>= 0.30** | non-annualized per-trade R |
| Sortino | **>= 0.40** | per-trade R, MAR = 0.00R |
| Calmar/MAR | **>= 1.00** | linear annualized total R / Max DD R using the full evaluation window |
| PSR | **>= 0.95** | probability Sharpe exceeds benchmark **0.20** |
| DSR | **>= 0.95** | deflated Sharpe using the predeclared current-cycle research budget unless explicitly overridden |
| Ulcer Index | **<= 5.00R** | RMS drawdown of chronological equity path |
| CVaR / Expected Shortfall 95% | **>= -2.00R/day** | worst 5% of daily aggregated strategy R |

Legacy per-trade CVaR remains available as a diagnostic but is **not** the R6 CVaR hard-gate authority because a roughly fixed `-1R` stop can make per-trade tail loss nearly degenerate.

## CPCV methodology and KPI authority

### Current stress-split view

- 6 chronological groups.
- 2 test groups per split.
- 15 purged combinatorial splits.
- Existing CPCV economic/stress gates (PF, expectancy, worst expectancy, DD, recovery, positive-split/sample requirements) remain evaluated on this view.

### Canonical reconstructed-path view

For `N=6,k=2`, R6 deterministically partitions the 15 group pairs into 5 reconstructed chronological paths. Each reconstructed path covers every chronological group exactly once.

The seven Advanced KPI use **canonical reconstructed chronological paths** as their CPCV hard-gate evidence. This avoids treating a non-contiguous two-segment stress split as a canonical equity path for path-dependent metrics.

Canonical DD/recovery do not silently replace the existing stress-split DD/recovery gates; those legacy gates remain separate until a later explicit governance decision.

### Per-group attribution

R6 also emits group-level trade metrics so recurrent weak pairs can be decomposed into the individual chronological regions that drive the failure.

## Scientist visibility

All seven KPI are included in deterministic candidate evidence supplied to the Scientist. LLM reasoning cannot override any KPI PASS/FAIL result.
