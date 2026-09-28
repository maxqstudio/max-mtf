# Repair v0.7.8 — Canonical Optimizer EA + Single-Click Lifecycle

## Owner defects repaired

1. v0.7.7 incorrectly interpreted the Strategy Optimizer EA authority as an arbitrary compatible EA already present under the selected terminal `MQL5/Experts` tree.
2. The navigation workspace and fixed lifecycle footer could rerun independently, allowing a stale Research/Optimizer footer after navigation and causing a first click to refresh state while a second click actually started the Optimizer.
3. MetaEditor can return a non-zero process code even when the compiler reports `0 errors, 0 warnings` and produces the expected EX5.

## v0.7.8 authority

- Canonical source: `EA_v1_06/Max.mq5`.
- The request freezes canonical source SHA-256.
- Worker copies that exact source byte-for-byte to `MQL5/Experts/MaxResearch` because MT5 Strategy Tester requires an Expert under the selected terminal data directory.
- Deployment hash must equal the frozen canonical hash before compile/tester execution.
- No unrelated EA selector and no generated replacement EA are permitted.
- Compile PASS = explicit MetaEditor zero-error summary + expected EX5 artifact; process exit code is diagnostic only.
- Streamlit 1.63 keyed fragment rerun atomically refreshes `workspace` + `contextual_lifecycle` on navigation.
- Optimizer start executes in one callback and refreshes both fragments in that same interaction.
- Scientist drawer is intentionally not rerun by navigation/start, preserving its independent state/draft contract.

## Acceptance

Dedicated gate: `R22_STRATEGY_OPTIMIZER_V078_RUNTIME_REPAIR` (`ModelLab/tests/v078_strategy_optimizer_repair_selftest.py`).

Full cumulative closure target: **99/99 PASS** on the exact v0.7.8 source tree. Owner MT5 runtime remains an external gate until real-machine evidence is collected.
