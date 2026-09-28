# Robustness and Overfitting

## PURPOSE
Detect edges that are artifacts of parameter choice, trial multiplicity, one regime, one seed or one favorable fold.

## INPUT EVIDENCE
Trial ledger, WFA/CPCV distributions, failure topology, sensitivity results, seed confirmation, stress degradation, PSR/DSR/PBO diagnostics when sample-qualified, and parameter neighborhoods.

## DECISION PROCEDURE
Check worst-fold and dispersion, not only median. Inspect parameter cliffs. Account for number of attempts. Use DSR/PBO only from canonical MAX calculations. Separate robustness failure from insufficient evidence. Demand replication across fixed seeds for stochastic families. Stress costs/delay using declared scenarios.

## FAILURE PATTERNS
Best-of-many selection without trial accounting; high PF from few trades; metric collapse under tiny parameter perturbation; seed instability; positive average hiding bad lower tail; post-hoc stress definitions.

## ALLOWED ACTIONS
Sensitivity analysis, fixed-seed stability tests, preregistered stress tests, complexity reduction, controlled replication.

## FORBIDDEN ACTIONS
Recompute authoritative DSR/PBO with alternate definitions, lower gates after failure, hide failed attempts, mine seeds.

## OUTPUT SCHEMA
{robustness_observation, multiplicity_risk, sensitivity_risk, seed_risk, tail_risk, evidence_sufficiency, next_test}

## TEST / REGRESSION FIXTURES
- **Lower tail:** Strong average metrics with a negative worst fold are diagnosed as instability/regime risk, not robust success.
- **Multiplicity:** Trial count and repeated search must be considered before interpreting apparent edge; DSR/PBO authority remains deterministic MAX implementation.
- **Small sample:** Unsupported risk metrics should produce insufficient-evidence semantics rather than a fabricated model-quality verdict.

## REFERENCES
Deflated Sharpe Ratio, Probability of Backtest Overfitting, CPCV/CSCV concepts and MAX canonical implementations.
