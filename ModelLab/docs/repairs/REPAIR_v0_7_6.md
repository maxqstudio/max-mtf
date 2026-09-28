# Max Research Agent — ONNX Factory v0.7.6

## Scientific change

v0.7.6 replaces active Factory-wide statistical KPI reuse with independent gate profiles and raises the Research H1 minimum-trade baseline to 8/month. Strategy Optimizer remains an upstream MT5 tool with its own H1 baseline of 20/month.

## Changes

- Added `MAX_GATE_KPI_PROFILES_V1` for Discovery, CPCV, Tournament, Monte Carlo, Fresh Forward, and Champion Promotion.
- Added the complete gate-profile snapshot to the immutable scientific contract.
- Discovery, CPCV, Tournament, Monte Carlo, and Fresh Forward now resolve their own threshold profile.
- Monte Carlo no longer reuses Shadow/Fresh promotion thresholds.
- Factory Fresh Forward no longer reuses legacy `shadow_acceptance()`; that function remains for legacy deployment governance only.
- Champion Promotion records deterministic upstream/integrity/no-retune/ONNX/parity checks and performs no new market test.
- Research AUTO sample baseline: H1 = 8 trades/month, no 75% haircut.
- Strategy Optimizer AUTO sample baseline: H1 = 20 trades/month.
- Both sample authorities reuse the same timeframe scaling engine and use integer round-up for the timeframe-scaled monthly rate and final exact-range requirement.
- Optimizer KPI/sample policy is frozen into each optimizer request.
- Advanced UI separates Execution/Labels from a single KPI-by-Gate surface; global active KPI controls are removed to prevent dual authority.
- Scientist Chat/Knowledge receives per-gate KPI and separate Optimizer KPI context.

## Preserved boundaries

- Strategy Optimizer is not part of ModelLab Research.
- Pool remains inventory/transition only.
- Tournament ranking cannot rescue hard-gate FAIL and does not Top-K eliminate survivors.
- PBO remains non-computable until canonical cross-strategy input exists; no proxy PBO is fabricated.
- Legacy Shadow/governance acceptance remains isolated from Factory Fresh Forward.

## Acceptance requirement

Release is not CLOSED until targeted self-tests and the cumulative exact-tree acceptance runner PASS on the final source tree. Real Owner MT5 optimizer runtime remains an external acceptance gate.
