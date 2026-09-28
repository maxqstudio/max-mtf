# Repair v0.8.6 — Strategy Optimizer History-Rebuild R Accounting

## Trigger

Real Owner MT5 Fast Genetic optimization on v0.8.5 produced normal trade statistics but the Custom `Result` column collapsed to the fail-closed sentinel `-1000000000.00` for essentially every pass.

## Root defect

v0.8.5 scientific R accounting mutated fitness state from `OnTradeTransaction()`. MQL5 does not guarantee trade-transaction arrival priority, and tester/broker-generated SL/TP plus tester-end liquidation can be observed independently of the assumptions made by a single global event-driven risk slot. One accounting mismatch poisoned the whole pass by design, therefore widespread sentinel results were possible even when the underlying strategy tester completed normal trades.

## Repair

`Max.mq5` now reconstructs Mean R and Weighted R in `OnTester()` from complete tester history after the pass is finished.

Authority:

- `HistorySelect()` creates the complete order/deal history view once.
- Owned positions are seeded only from entry deals matching `_Symbol` and `InpMagic`.
- `DEAL_POSITION_ID` becomes the ownership key after the entry is established.
- All deals belonging to an owned position contribute to net P/L; exit-deal magic is not required.
- Initial risk is reconstructed per entry fill from actual `DEAL_PRICE`, historical entry-order `ORDER_SL` (with entry `DEAL_SL` fallback), executed `DEAL_VOLUME`, and `OrderCalcProfit()`.
- Partial entry fills accumulate initial risk.
- Position net P/L includes `DEAL_PROFIT + DEAL_COMMISSION + DEAL_SWAP + DEAL_FEE` across the owned position.
- Per-position R = position net P/L / summed position initial risk.
- Mean R = arithmetic mean of closed-position R values.
- Weighted R = total owned-position net P/L / total owned-position initial risk.
- `OnTradeTransaction()` no longer mutates scientific fitness state.

## Fail-closed invariants

A pass remains invalid unless all are true:

- reconstructed closed positions > 0;
- `R-accounted trades == TesterStatistics(STAT_TRADES)`;
- accounting errors == 0;
- total initial risk > 0;
- Mean R and Weighted R are finite;
- seven-family Strategy Optimizer contract remains valid.

Failure still returns `-1e9`; sentinel removal is not accomplished by weakening the gate.

## Python / model boundary

No model-training authority changes in v0.8.6:

- adaptive lot/risk/equity remain excluded from CP32 features and training targets;
- Optimizer Champion `SL/TP/MaxHold` remains the single geometry authority inherited by dataset metadata, Python labels, and model evaluation;
- Python Strategy Optimizer still requires independent PF, RF, Mean R, Weighted R, and minimum-trade hard gates;
- Weighted R sidecar hash/nonce/pass/trade-parity validation remains mandatory.

## Acceptance

New cumulative gate: `R30_STRATEGY_OPTIMIZER_HISTORY_REBUILD_V086`.

Local release closure requires `historical external: BUILD_ACCEPTANCE_v0_8_6.json` to report 107/107 PASS on the exact shipped tree. MetaEditor compile and fresh Owner MT5 optimization remain external runtime gates.
