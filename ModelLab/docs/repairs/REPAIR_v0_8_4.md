# REPAIR v0.8.4 — Durable Optimizer settings and canonical Max runtime names

v0.8.4 preserves the v0.8.3 champion-stop / automatic no-winner continuation contract and closes two Owner-runtime defects.

## Durable Strategy Optimizer settings

Streamlit removes widget keys when a page is not rendered. The previous persistence path rebuilt `ui_state` only from currently present session keys, so navigating away from Strategy Optimizer could erase its saved form state. v0.8.4 adds a durable shadow-state: live rendered values overlay the prior durable state; missing hidden-page keys are retained. Strategy Optimizer rehydrates missing `strategy_opt_*` keys before rendering. Active jobs still use only their frozen request.

## Canonical runtime filenames

Canonical runtime names are `Max.mq5` / `Max.ex5`, `Max.set`, and `historical external: Max.xml`. Round identity and freshness belong to the job checkpoint plus pre-launch file fingerprint, not to an `R1/R2/R3` filename suffix. New jobs exclude `historical external: Max.xml`, legacy `historical external: Max_R<N>.xml`, and `MAX_StrategyOptimizer_*` from cross-job bootstrap evidence.

## Custom Expectancy-R genetic fitness

MT5 Fast Genetic now uses `OptimizationCriterion=6` (Custom max). legacy `Max.mq5`, symbol `OnTester()` returns mean realized Expectancy R/trade, so native `Result` is Expectancy R instead of duplicating Recovery Factor. PF, RF, Expectancy R, and minimum trades remain independent hard gates after report parsing. Recovery Factor must come from the dedicated MT5 Recovery Factor statistic; `Result` is never an RF fallback under this contract.

## Acceptance

The existing cumulative suite remains mandatory and includes the strengthened settings persistence regression and Strategy Optimizer runtime naming/freshness regression.
