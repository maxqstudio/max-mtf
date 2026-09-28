# Trade Sample AUTO V1 · CPMF v0.6.9

`Trade Sample = AUTO` is the default authority for minimum closed-trade sample sufficiency.

The threshold is declared before candidate performance is observed and is derived from:

- exact evaluated date range;
- MT5 timeframe;
- H1 baseline opportunity rate: 4 trades/month;
- square-root timeframe scaling;
- 75% sufficiency floor;
- actual OOF exposure for Discovery rather than the whole outer period.

Formula:

`expected = effective_months × 4 × sqrt(60 / timeframe_minutes)`

`minimum = max(stage_absolute_floor, ceil(expected × 0.75))`

The timeframe factor is bounded to avoid absurd requirements on extreme timeframes.

## H1 examples

- Discovery 2020–2022 full three-year expected activity: ~144 trades.
- Discovery OOF exposure ~50%: minimum ~54 trades.
- Tournament 2023–2025 full three-year evaluation: minimum 108 trades.
- Fresh 2026-01-01 → 2026-09-09: minimum 25 trades.

The exact Discovery threshold is recalculated from the real walk-forward validation-row exposure and stored in each candidate result as `auto_min_validation_trades` plus `auto_trade_sample` metadata.

`AUTO` exists to prevent two opposite errors: forcing a selective H1 system to overtrade just to hit a fixed number, or allowing too few observations after changing timeframe/range.
