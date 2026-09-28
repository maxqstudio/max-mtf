# v0.5.7 — Rich KPI Acceptance

## Authority split

`selection_score` remains a research ranking signal only. It is not acceptance authority.

Acceptance now has two deterministic stages:

1. **Walk-forward gate before holdout**. The Supervisor selects the highest-ranked candidate that also passes the CV gates. If no candidate passes, the locked test is not opened.
2. **Locked-test gate**. After the one-time locked test, economic/risk/stress/parity gates decide `ELIGIBLE_CHALLENGER` vs `REJECTED`.

## Walk-forward quality gates

- total validation trades
- median PF
- median expectancy R
- worst-fold expectancy R
- positive fold ratio
- median Recovery Factor

Fold diagnostics additionally retain expectancy/PF dispersion, recovery, win rate, payoff, max losing streak, DD and total R.

## Locked-test hard/quality gates

- minimum trades
- minimum PF
- positive expectancy
- maximum DD
- minimum Recovery Factor (`Total R / Max DD R`)
- Python-native ↔ ONNX parity
- spread ×1.25 and ×1.50 stress expectancy floors
- take-threshold plateau stability around the selected threshold

## Diagnostics, not hard gates by default

- win rate, average win/loss, payoff ratio, median trade R
- max losing streak, max underwater trades
- CVaR 95%, downside deviation, top-win concentration
- positive month/quarter ratios and worst periods
- TREND/RANGE/SHOCK/TRANSITION performance concentration
- balanced accuracy, Macro-F1, log loss, multiclass Brier, ECE
- confidence-bucket trading outcomes

## Champion-relative shadow governance

Same-window Challenger and Champion evidence now carries `Total R` and `Recovery Factor` in addition to PF, expectancy, and DD.

Promotion requires:

- all shadow absolute gates PASS;
- non-inferiority bounds across PF/expectancy/DD/Recovery;
- improvement in at least 2 of the 4 dimensions by default.

The comparison is auditable in `historical external: supervisor_state.json`.

## New artifacts

- `historical external: cv_acceptance.json`
- `historical external: kpi_report.json`
- `historical external: kpi_acceptance.json`

Locked-test results remain unavailable when the CV gate rejects the research generation.
