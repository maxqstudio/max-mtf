# KPI Acceptance V2

## Principle

`selection_score` ranks experiments. It does not authorize a Challenger.

Authority is fail-closed and staged:

`research ranking -> walk-forward KPI gate -> locked test once -> locked-test KPI gate -> ONNX parity -> MT5 parity -> Strategy Tester -> fresh shadow -> Champion-relative gate -> explicit promotion`

## Walk-forward gate (before locked test)

Default thresholds:

| KPI | Default |
|---|---:|
| Total validation trades | >= 120 |
| Median PF | >= 1.00 |
| Median expectancy | > 0.00 R |
| Worst-fold expectancy | >= -0.10 R |
| Positive fold ratio | >= 0.66 |
| Median Recovery Factor | >= 0.75 |

The Supervisor picks the highest-ranked candidate that passes these gates. If none pass, the locked test remains sealed and the generation is `RESEARCH_REJECTED`.

## Locked-test acceptance

Default gates:

| KPI | Default |
|---|---:|
| Trades | >= 100 |
| PF | >= 1.05 |
| Expectancy | > 0.00 R |
| Max DD | <= 40 R |
| Recovery Factor | >= 1.00 |
| Python/ONNX max abs error | <= 1e-4 |
| Spread x1.25 expectancy | >= -0.02 R |
| Spread x1.50 expectancy | >= -0.05 R |
| Profitable take-threshold variants | >= 0.66 |

Recovery Factor is `Total Net R / Max Drawdown R`.

## Rich diagnostics (not hard gates by default)

- win rate, average win/loss, payoff ratio, median trade R;
- max losing streak and max underwater trade duration;
- CVaR 95%, downside deviation, top-win concentration;
- positive month/quarter ratios, worst month/quarter, negative-month streak;
- TREND/RANGE/SHOCK/TRANSITION performance and regime concentration;
- balanced accuracy, Macro-F1, log loss, multiclass Brier score, ECE;
- confidence-bucket trading outcomes;
- per-fold PF/expectancy/DD/recovery/trades and dispersion.

These metrics diagnose fragility without making every descriptive number a hard gate.

## Shadow and Champion-relative promotion

Absolute shadow gates add Recovery Factor. When a Champion exists, same-window comparison evaluates:

- PF;
- expectancy R;
- max DD R;
- Recovery Factor.

Default policy requires non-inferiority on all four within bounded tolerances and improvement in at least 2 of the 4 dimensions. This prevents a tiny PF gain from authorizing a candidate with materially worse drawdown or recovery.
