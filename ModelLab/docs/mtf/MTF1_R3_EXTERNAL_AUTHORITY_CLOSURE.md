# MTF-1 R3 External Authority Closure

## Scope

MTF-1 R3 repairs governance/flow only. MTF-2 remains blocked. Scientific evaluators, search, CPCV, Strategy Optimizer and MTF-2 feature/model logic are unchanged.

## Canonical external runtime authority

`governance/EXTERNAL_RUNTIME_GATES.json` is the single registry. `ModelLab/acceptance/runners/run_acceptance.py`, `governance/PACKAGE_MANIFEST.json`, and `governance/CURRENT_AUTHORITY.json` consume/reference that registry. The registry is part of the exact source-tree signature.

The MTF-1 Owner closure gates are:

- `OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION`
- `OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY`

`METAEDITOR_MAX_MTF_V2_COMPILE` remains a separate Owner-machine external gate required by Control Room before final MTF-1 close.

## One-click Owner MTF-1 runtime evidence

Run `ModelLab\RUN_MTF1_OWNER_ACCEPTANCE.cmd`. It reads `historical external: owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json`, connects to MT5, verifies `terminal_info().data_path` as a terminal data root, collects native M5/M15/H1/H4 for one broker/symbol/window, rebuilds higher TF from M5, audits OHLCV parity and causal alignment, and writes machine-readable evidence to `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_RUNTIME_ACCEPTANCE.json`. Any exception writes FAIL evidence and exits non-zero.

## Source-kind fail closed

Production sealing accepts only `DIRECT_MT5_NATIVE_RATES` and `IMPORTED_M5`. `IMPORTED_M5` additionally requires exact native-M5 continuity proof at seal time. Empty/unknown kinds fail closed. `SYNTHETIC_TEST` is accepted only when the explicit test-only environment flag `MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE=1` is present.

## Closure rule

Local 44/44 PASS is necessary but not sufficient. MTF-1 may be declared CLOSED only after required Owner-machine evidence is PASS.
