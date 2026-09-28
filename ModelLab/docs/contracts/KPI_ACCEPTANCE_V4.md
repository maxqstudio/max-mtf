# KPI Acceptance V4

v0.5.9 separates three authorities that must not be conflated:

1. **Walk-forward ranking score**: `CV_SCORE_V2_ALL_KPI`.
2. **Acceptance gates**: walk-forward and locked-test hard/quality gates.
3. **Promotion authority**: current-policy revalidation + MT5 parity + Strategy Tester + fresh shadow + Champion-relative comparison.

## Walk-forward composite score

The score is policy-centered and approximately bounded to `-100..+100`. Zero means the candidate sits around the current policy/reference surface. Positive is stronger; negative is weaker.

All 28 CV-observable KPI components contribute. Category weights sum to 100:

- Economic edge: 28
- Risk / survival: 20
- Fold robustness: 10
- Trade quality: 8
- Time / regime: 10
- Stress robustness: 16
- Classification / calibration: 8

The score includes PF, median/worst expectancy, total R, trades, recovery, DD, CVaR, losing/underwater behavior, positive folds, dispersion, win/payoff/median trade, profit concentration, monthly/quarterly stability, regime concentration, spread stress, take-threshold plateau, balanced accuracy, macro-F1, log loss, Brier score, and calibration error.

**Locked-test evidence is never used in this score before the holdout is opened.** That would convert the locked test into another validation set and invalidate the governance design.

## Acceptance remains fail-closed

A high score cannot compensate for a failed hard/quality gate. The Supervisor only opens the locked test for a candidate that passes the current walk-forward acceptance policy.

## Promotion

Promotion continues to re-evaluate historical CV and locked-test evidence under the current policy and requires current deployment/shadow evidence. Changing policy after a run can invalidate an old PASS.
