# Repair v0.8.7 — Strategy Optimizer → Model Research Authority Boundary

## Scope

v0.8.7 removes duplicated execution-geometry authority from Model Research and adds a trade-weighted Overall OOF Mean R hard gate. It does not change v0.8.6 EA R-accounting.

## Locked authority flow

`Strategy Optimizer Champion → Max.mq5 → Owner MT5 training-data backtest → uniform CP32 sl_atr/tp_atr/max_hold_bars → Research labels/evaluation`

- `SL ATR`, `TP ATR`, and `MaxHold` are owned upstream by Strategy Optimizer/CP32.
- Canonical `config.json.label` contains only `min_edge_r`, `min_margin_r`, and `ambiguous_policy`.
- Research UI exposes no SL/TP/Horizon duplicate controls.
- Research START verifies uniform CP32 geometry and, when present, the latest Strategy Optimizer Champion authority. Mixed/stale geometry fails closed.
- Effective runtime strategy geometry is stored separately under `strategy_geometry`; it is not a Model Research search knob.
- Purge and embargo are automatically lifted to at least upstream `MaxHold`.

## Label-policy boundary

Model Research may study only target-separation policy (`Min edge R`, `Min margin R`, ambiguous handling). Scientific methodology remains fixed: sizing-neutral R normalization, first-barrier/timeout outcome, canonical SELL/SKIP/BUY semantics. Adaptive lot/risk/equity remain excluded from model features and targets.

## WFA Mean-R acceptance

Discovery/WFA now requires all three independently:

- `Overall OOF Mean R >= cv_min_overall_expectancy_r`
- `Median Fold Mean R >= cv_min_median_expectancy_r`
- `Worst Fold Mean R >= cv_min_worst_expectancy_r`

Overall OOF Mean R is `total_validation_r / total_validation_trades`, not an unweighted average of folds. Thresholds remain Owner-editable before START and become frozen runtime authority after START.

CPCV retains median/worst path robustness semantics; no pseudo-overall metric is introduced across overlapping CPCV paths.

## Preservation

- v0.8.6 deterministic `OnTester()` history reconstruction remains unchanged.
- Strategy Optimizer Mean R + Weighted R + PF + RF + minimum trades remain independent upstream gates.
- Weighted R remains a system/capital-allocation metric and is not injected into model features or training labels.
- Locked/Fresh forward remains excluded from same-snapshot tuning.

## Acceptance

Local closure target: `historical external: BUILD_ACCEPTANCE_v0_8_7.json` **108/108 PASS**, `first_failed_gate=null`, matching the exact shipped source-tree signature. MetaEditor/MT5 and other Owner-machine external gates remain separate.
