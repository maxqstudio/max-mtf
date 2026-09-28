# Repair v0.8.0 — Strategy Optimizer Result/RF + Champion-to-EA Stop

## Defects closed

1. Custom `OnTester()` sentinel `-1e9` was being used as Fast Genetic fitness, making the MT5 Result column useless and starving genetic selection.
2. Recovery Factor was a hard Optimizer KPI but was not visible as the selected native MT5 Result criterion.
3. Champion flow exported presets and stopped without applying the winning parameters to the existing EA, while Owner intent is: champion → update EA → stop → Owner manual training-data backtest → Owner starts Research.

## Contract

- Historical v0.8.0 choice: **Recovery Factor max** (`OptimizationCriterion=4`). **Superseded by v0.8.4:** current authority is Custom max (`OptimizationCriterion=6`), where `Result = Expectancy R`; RF remains a dedicated hard gate.
- `OnTester()` custom statistic: **Expectancy R/trade**, independent hard KPI.
- Exit deal must be selected into history before properties are consumed. Entry position identity is anchored to `CTrade::ResultDeal()` with position fallback.
- An all-sentinel Custom result set is invalid and fails closed.
- Champion apply may modify only `ABSOLUTE_BOUNDS` input default literals in the existing `EA_v1_06`; normalized strategy logic must hash-identically before/after.
- Pre/post source, hashes, selected champion and apply manifest are evidence.
- Updated EA is deployed/compiled. Optimizer then stops.
- No automatic backtest, training-data generation, Data Quality transition, or Research start.
