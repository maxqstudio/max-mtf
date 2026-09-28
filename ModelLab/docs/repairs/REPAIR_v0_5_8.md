# v0.5.8 — Strict KPI and Promotion Authority Repair

## Owner-requested defaults
- Min test trades 100
- Min PF 1.50
- Min expectancy 0.50R
- Max DD 15R
- Min recovery 3.00

## Coherent upstream/downstream tightening
- CV trades 150, PF 1.30, Exp 0.25R, worst Exp 0.00R, positive folds 0.66, recovery 1.50.
- Spread x1.25 Exp 0.20R, x1.50 Exp 0.10R, threshold plateau 0.75.
- Shadow promotion mirrors PF 1.50 / Exp 0.50R / DD 15R / Recovery 3.00.
- Rich locked-test quality gates: positive month/quarter ratios, regime concentration, top-win concentration.

## Governance defect repaired
Previously promotion trusted `manifest.status == ELIGIBLE_CHALLENGER`, so a candidate accepted under an older looser policy could remain promotable after thresholds were raised. v0.5.8 revalidates saved CV and KPI evidence against current policy on every Governance assessment.

## UI
Results KPI cards now surface win rate, payoff, CVaR95, time stability, regime concentration, stress x1.50 expectancy, threshold plateau, median trade, losing streak, underwater duration and top-win concentration.

## Acceptance
`ModelLab/RUN_ACCEPTANCE.cmd` executes `ModelLab/tests/acceptance_selftest.py`, including a negative fail-closed test that tightens policy after a synthetic candidate was eligible and verifies promotion becomes blocked.

## Build evidence

`historical external: BUILD_ACCEPTANCE_v0_5_8.json` is machine-readable and records `first_failed_gate`. Local acceptance includes a negative fail-closed path where an eligible synthetic run becomes non-promotable after policy is tightened.
