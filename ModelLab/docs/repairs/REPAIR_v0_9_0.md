# Repair v0.9.0 — Champion Tester Preset Synchronization

## Defect

Champion selection updated canonical EA optimizer defaults and compiled/deployed `Max.ex5`, but the canonical Strategy Tester preset `MQL5/Profiles/Tester/Max.set` remained the optimization-range preset. MT5 manual Backtest could therefore show/run stale settings while attaching the newly compiled EA to a chart exposed the Champion defaults.

## Repair

- Champion commit writes exact Champion values to canonical `Max.set`.
- Every Strategy Optimizer-owned `.set` row is fixed (`start=value`, `step=0`, `stop=value`, optimize=`N`).
- EA default ↔ Champion ↔ `Max.set` parity is verified before `CHAMPION_FOUND`.
- Python runtime strategy authority remains intentionally limited to SL ATR / TP ATR / MaxHold geometry and is verified against the same Champion.
- EA, Tester preset, and strategy authority are one fail-closed transaction: failure restores all previous states.
- Existing v0.8.9 cache/frame evidence rules remain unchanged.
- Existing EA risk-cap repair is retained: exact planned risk uses `OrderCalcProfit()` and over-cap minimum/rounded volume is skipped.
- Canonical CSV names remain `Max_Training.csv`, `Max_Telemetry.csv`, `Max_metrics.csv`.

## Regression

`ModelLab/tests/v090_champion_tester_preset_sync_selftest.py` reproduces stale-preset risk and verifies exact fixed-point Champion parity plus rollback wiring.
