# REPAIR v1.3.4 — Legacy CVaR Sign Migration

## Scope

Hotfix only. No model-family, label, execution, Challenger, Champion, LangGraph, or Strategy geometry semantics are changed.

## Defect

v1.3.2 correctly defined daily CVaR / Expected Shortfall 95% as the average R of the worst 5% active trading days and made a positive hard floor fail closed unless `allow_positive_tail_floor=true`.

Persisted pre-repair per-gate configurations could still carry positive values such as Discovery `+0.80`, CPCV `+1.00`, Tournament `+1.25`, and Fresh Forward `+1.50` while `allow_positive_tail_floor=false`. The v1.3.2 sign guard then correctly raised `CVAR_SIGN_SEMANTICS`, but migration did not translate those stale legacy values.

## Repair

`ensure_gate_kpi_profiles()` now migrates only this stale combination:

- CVaR threshold > 0
- `allow_positive_tail_floor=false`

The effective stage floors become:

- Discovery: `-2.0 R/day` (diagnostic by default)
- CPCV: `-2.5 R/day`
- Tournament: `-2.0 R/day`
- Fresh Forward: `-1.5 R/day`

Migration provenance is retained in the CVaR spec using `migrated_legacy_positive_tail_floor_from` and `migration_reason=V134_CVAR_SIGN_SEMANTICS_LEGACY_REPAIR`.

An explicitly acknowledged positive floor (`allow_positive_tail_floor=true`) is preserved unchanged. The low-level `CVAR_SIGN_SEMANTICS` guard remains fail-closed for invalid direct configurations.

## Regression

`R53_V134_CVAR_LEGACY_SIGN_MIGRATION`

The test reproduces the exact legacy positive-threshold pattern observed in Owner run evidence, proves migration to stage-safe negative floors, proves explicit positive acknowledgement is retained, and proves the canonical low-level guard is still active.
