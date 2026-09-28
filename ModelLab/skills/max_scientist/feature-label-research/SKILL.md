# Feature and Label Research

## PURPOSE
Ensure supervised targets teach behavior aligned with executable trading utility while preserving causal temporal context.

## INPUT EVIDENCE
Current label contract, execution eligibility, feature schema/lineage, source_row_id continuity, label distribution, coverage, supervised weights, execution simulator contract, feature ablation evidence and KPI objectives.

## DECISION PROCEDURE
1. Verify feature[t] is available at decision time.
2. Separate context rows from supervised/actionable rows.
3. Check label horizon/barriers against exact execution semantics and purge/embargo.
4. Compare label objective with economic KPI objective; flag direction-classification vs sparse utility mismatch.
5. Audit class balance, actionable prevalence, censoring and ambiguity rules.
6. Prefer bounded label-separation experiments before changing execution geometry.
7. Use ablations to detect duplicated rule signal or redundant features.

## FAILURE PATTERNS
Label says BUY/SELL on structurally non-executable rows; reset index destroys temporal gaps; future price leakage; high classification accuracy with poor R; label prevalence far above executable trade coverage; rule signal used redundantly without ablation.

## ALLOWED ACTIONS
Feature ablation, bounded min-edge/min-margin label experiments, context/target masks, diagnostic class/coverage analysis.

## FORBIDDEN ACTIONS
Change Strategy SL/TP/MaxHold or execution policy, use Fresh labels for tuning, invent triple-barrier semantics outside a versioned label contract.

## OUTPUT SCHEMA
{feature_label_observation, mismatch_type, causal_risk, utility_alignment, proposed_ablation_or_label_test, falsification, protected_boundary}

## TEST / REGRESSION FIXTURES
- **Executable masking:** Structurally non-executable rows may provide context but must carry zero supervised weight.
- **Objective alignment:** A classification improvement that worsens stateful trading utility does not prove label improvement.
- **Geometry authority:** Label research must not mutate Strategy Champion SL/TP/MaxHold execution geometry.

## REFERENCES
MAX v1.3.2 scientific workflow parity repair and current label/execution contracts.
