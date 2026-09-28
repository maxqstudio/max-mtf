# Repair v0.9.1 — MT5 Gap Repair + ONNX Audit/Terminal UI Synchronization

## Defect reproduced

Owner Data Quality reported source-backed missing CP32 bars, but `REPAIR MISSING FROM MT5` only opened/activated MetaTrader 5 and did not append the missing `Max_Training.csv` rows.

Two independent defects existed in v0.9.0:

1. The gap-repair INI omitted `ExpertParameters`. MT5 therefore fell back to canonical `MQL5/Profiles/Tester/Max.set`. The Champion preset intentionally contains `InpWriteTrainingData=false`, so even a successful tester run could not repair CP32.
2. The launcher treated `subprocess.Popen()` as repair success even when the exact target MT5 terminal was already running. MT5 startup `/config` tester jobs are not reliable against an already-running instance; the observed terminal kept its old tester dates/settings instead of the bounded repair job.

## v0.9.1 contract

- Gap repair creates `MQL5/Profiles/Tester/Max_GapRepair.set` from the exact canonical Champion `Max.set`.
- All Champion strategy parameters are preserved; dataset `SL_ATR`, `TP_ATR`, and `MaxHoldBars` must match the canonical preset before launch.
- The dedicated repair preset forces:
  - `InpWriteTrainingData=true`
  - `InpTrainingFile=Max_Training.csv`
  - `InpWriteTelemetry=false`
  - `InpAllowLiveTrading=false`
  - ONNX Champion/Challenger inference off for deterministic CP32 repair.
- The tester INI explicitly sets `ExpertParameters=Max_GapRepair.set`, `Optimization=0`, the bounded missing-bar envelope, local agent only, and automatic terminal shutdown.
- If the exact verified broker terminal is already running, repair **fails closed** and asks the Owner to close that terminal before retrying. It never reports a false successful launch.
- A tester process start is only `PENDING_AUDIT`. Repair becomes valid only after a fresh deterministic Data Quality audit proves `source_backed_missing_count == 0`.
- Mixed/stale CP32 geometry fails closed before any tester launch.
- No interpolation, forward-fill, synthetic candle, or Python-authored CP32 row is allowed.

## Retained contracts

- EA trading strategy and `Max.mq5` are unchanged.
- Champion EA/`Max.set` parity from v0.9.0 remains authoritative.
- Risk-cap repair and Max-only CSV naming remain unchanged.
- MAX Matrix UI hot patch is integrated without changing optimizer authority.

## Regression

`ModelLab/tests/v091_gap_repair_tester_selftest.py` proves:

- repair preset forces training writer ON;
- canonical `Max_Training.csv` is explicit;
- Champion geometry is retained and optimization disabled;
- tester INI explicitly loads `Max_GapRepair.set`;
- bounded dates and single-test mode are preserved;
- mixed dataset geometry fails closed.

## ONNX family identity + independent trade audit

- Champion and Shadow inputs expose the complete deployable model-family universe from `ModelLab/config/models/model_registry.json`. Hybrid topology is described generically as temporal→classical-tree policy; GRU is no longer hard-coded as the only temporal identity.
- Family selectors are identity/validation metadata. They do not change `[P(SELL), P(SKIP), P(BUY)]`, ONNX tensor execution, Strategy Optimizer authority, or deterministic risk.
- `Max_Champion_Trades.csv` is written from actual MT5 deal-add transactions owned by Max and is strictly audit-only. `OnTester()` history rebuild remains the only Strategy Optimizer Mean-R/Weighted-R accounting authority.
- `Max_Shadow_Trades.csv` records Challenger entry candidates only. Every row has `executed=0`; no Shadow path calls Buy/Sell/PositionClose. The file records the candidate entry, ATR-derived SL/TP, deterministic planned volume/risk, probabilities and policy reason for later audit/replay.
- Native optimization and Data Quality gap-repair presets disable Champion/Shadow trade-audit writers to prevent multi-agent/Common-Files contention.

## Optimizer terminal UI synchronization

- `CHAMPION_FOUND`, `NO_CHAMPION_MAX_ROUNDS`, `FAILED`, and `CANCELLED` remain terminal worker states and are never members of the active Optimizer set.
- The contextual lifecycle fragment retains its established 2-second heartbeat. A newly observed terminal state actively reruns that lifecycle fragment immediately, so the busy spinner/STOP control disappears and `START AUTO OPTIMIZER` becomes the lifecycle action again without requiring a manual page reload.
- MAX Matrix remains read-only observability from completed `Max_metrics.csv` rows and has no Champion-promotion authority.
