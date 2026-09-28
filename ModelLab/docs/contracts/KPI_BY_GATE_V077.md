# Max v0.7.7 — KPI by Gate Contract

## Scope

v0.7.7 separates Strategy Optimizer acceptance from ModelLab Research acceptance and separates Research statistical thresholds by gate. Deterministic code remains the only PASS/FAIL authority.

## Upstream Strategy Optimizer

Strategy Optimizer is an MT5 EA parameter-search tool before ModelLab Research. It is not Discovery and does not run WFA, CPCV, Tournament, Monte Carlo, or Fresh Forward.

Hard eligibility is frozen into each optimizer request:

- Profit Factor >= 1.00
- Recovery Factor >= 0.00
- Expectancy >= 0.00 R/trade
- minimum closed trades = AUTO from exact optimization range
- H1 baseline = 20 trades/month

The timeframe engine is shared with Research but the baseline is not. For `tf_minutes`, the raw factor is `sqrt(60 / tf_minutes)`, clamped to `[0.20, 4.00]`. The scaled monthly trade rate is rounded up to an integer. The exact evaluated duration is then prorated using that integer rate and the final required closed-trade count is rounded up again.

## Research trade-sample authority

ModelLab Research uses H1 baseline = 8 trades/month. The same timeframe scaling and integer round-up rule applies. Discovery/CPCV may apply an explicit evaluation-exposure fraction; Tournament and Fresh Forward use their full evaluated window. There is no hidden 75% sufficiency haircut in v0.7.7.

## Research KPI profiles

`gate_kpis` is part of the frozen scientific contract and is hashed into the Factory stage contract.

1. **Discovery** — Full chronological WFA qualification. Owns WFA survival/economic/time/stress/risk-adjusted thresholds.
2. **CPCV** — Owns aggregate/worst-path/sample and canonical CPCV risk thresholds. PBO is `NOT_COMPUTABLE` unless a canonical cross-strategy matrix exists; pseudo-PBO is forbidden.
3. **Tournament** — Owns hard eligibility thresholds. Ranking may order PASS survivors but cannot rescue FAIL and does not impose Top-K elimination.
4. **Monte Carlo** — Owns bootstrap tail thresholds: P05 PF, P05 expectancy, P95 max DD, P05 recovery, and configured probability loss/ruin/survival.
5. **Fresh Forward** — Owns untouched Forward statistical thresholds. Thresholds are frozen before Fresh data is opened. v0.7.7 does not activate a hidden degradation gate.
6. **Champion Promotion** — not a sixth market/statistical test. It verifies upstream PASS, artifact integrity, no post-Fresh scientific-contract mutation, ONNX export, and ONNX parity.

## Immutability

Changing a gate profile after Research has started must not mutate the active Factory. The frozen Factory contract contains the complete gate-profile snapshot. A changed profile is applicable only to a new Factory/generation.

## Evidence

Gate evidence must expose the threshold actually used and the observed metric whenever the metric is computable. Existing compatibility booleans may be retained, but they are not a second threshold authority.

## Scientist contract

Scientist Chat receives `gate_kpis`, Research trade-sample policy, and the separate Strategy Optimizer KPI profile as read-only context. KPI recommendations must be made per gate. Champion must be described as promotion/integrity/runtime authority, not as a sixth statistical gate.

## v0.7.7 presentation/ownership clarification

- Advanced groups related controls into `Research`, `Scientist`, `KPI & Evaluation`, `Compute & hardware`, and `Legacy diagnostics`; statistical ownership is unchanged.
- Each Research gate is rendered as one visual section. Risk-adjusted metrics do not create extra gate separators.
- CPCV exposes PBO as a first-class threshold/status block. It remains non-authoritative while canonical cross-strategy computation is unavailable.
- PSR benchmark Sharpe is rendered in the PSR row instead of as an orphan full-width field.
- Strategy Optimizer KPI is configured on the Strategy Optimizer page, not mixed into Research gate KPI.
