# Repair v0.8.5 — Strategy Geometry + Weighted R Authority

## Locked contract

1. Strategy Optimizer Champion `InpSL_ATR`, `InpTP_ATR`, and `InpMaxHoldBars` become one execution-geometry authority shared by `Max.mq5`, CP32 dataset metadata, Python label construction, and Research evaluation. Mixed or stale geometry fails closed.
2. Adaptive lot/risk remains an EA/system layer and is not a model feature or training target.
3. Strategy Optimizer KPI V2 freezes five independent gates: PF, RF, arithmetic Mean R, capital-weighted R, and minimum trades.
4. `OnTester()` returns arithmetic Mean R as MT5 Custom-max genetic fitness. `Weighted R = sum(net P/L) / sum(initial risk)` is exported per pass using MT5 optimization frames and written to `Max_metrics.csv` by terminal-side frame handlers.
5. R accounting must satisfy `R-accounted trades == TesterStatistics(STAT_TRADES)`, zero accounting errors, finite sums, and positive summed initial risk. Otherwise the pass is fail-closed.
6. Python recomputes Weighted R from `sum_net / sum_initial_risk` and rejects sidecar arithmetic/parity mismatches.
7. A pass is Champion-eligible only when every frozen KPI gate passes. Among eligible passes, ranking prioritizes Weighted R, then Mean R, PF, RF, then deterministic pass-number tie-break.
8. XML-only legacy Optimizer evidence is not v0.8.5 Champion-compatible. External bootstrap requires an explicitly paired `<stem>.metrics.csv`. Same-job recovery uses its own checkpointed XML + metrics evidence.
9. Strategy Optimizer UI includes a durable `Min Weighted R` setting; navigation/reload/app restart may not erase it. Active jobs use only their frozen request.

## Model-training audit

Python model training remains sizing-neutral: adaptive lot/risk/equity is not a CP32 feature or training target. Labels use strategy geometry inherited from the Optimizer/EA authority rather than adaptive P/L money.

10. R denominator is the actual initial stop risk in account currency: Max captures the entry deal/position fill and attached initial SL, then uses `OrderCalcProfit()` for the executed volume. Tick-value/ATR approximations are not accepted as scientific R evidence. Any missing/invalid risk capture increments accounting errors and makes the pass fail closed.
