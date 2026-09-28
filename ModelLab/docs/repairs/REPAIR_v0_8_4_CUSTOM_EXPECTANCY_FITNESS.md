# v0.8.4 — Custom Expectancy-R Fitness Repair

## Defect

Strategy Optimizer configured MT5 Fast Genetic with `OptimizationCriterion=4` (Recovery Factor max). This made native `Result` duplicate Recovery Factor while Max Expectancy R lived only in `Custom`, creating misleading operator semantics and steering genetic selection with RF rather than the Max objective.

## Repair

- `OptimizationCriterion=6` — MT5 Custom max.
- legacy `Max.mq5`, symbol `OnTester()` remains mean realized `R/trade`; this is now the native genetic fitness and the visible MT5 `Result`.
- Profit Factor, Recovery Factor, Expectancy R and minimum trades remain independent deterministic hard gates after report parsing.
- Recovery Factor must be read from the dedicated `Recovery Factor` column. `Result` may never be used as RF under the Custom-max contract.
- Frozen request evidence records the criterion code/name/fitness/result-column authority.

## Fail-closed parser rule

A report without a dedicated Recovery Factor column is rejected under the current Custom-max contract; silently falling back to `Result` would convert the RF hard gate into another Expectancy-R check.
