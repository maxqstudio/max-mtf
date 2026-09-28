# MAX Research Agent v1.2.6 — Authority/Lifecycle Repair

Scope is intentionally narrow. No Strategy Champion parameter, KPI, trading logic, risk sizing, R accounting, model KPI, or Scientist Chat authority is changed.

## D1 Strategy authority fail-closed
Model Research requiring runtime authority now rejects missing, unreadable, malformed/invalid, or geometry-mismatched `ModelLab/runtime/strategy_authority.json`. The authority file is included in acceptance tree hashing.

## D2 Factory winner terminology
New Model Factory terminal writes use `FACTORY_WINNER` and `FACTORY_WINNER_RUNTIME_BLOCKED`. `CHAMPION` remains only as historical stage/artifact naming and legacy evidence read compatibility. Production Model Champion still requires explicit Owner promotion.

## D3 Governance synchronization
`governance/CURRENT_AUTHORITY.json`, `governance/PACKAGE_MANIFEST.json`, `governance/PROJECT_HANDOFF_CURRENT.md`, `governance/CONTRACT_AUDIT_INDEX.md`, README and acceptance metadata point to v1.2.6.

## D4 Strategy Optimizer stop state
Explicit Owner stop is canonical `STOPPED`; Scientist Chat cancellation semantics are unchanged.

## Acceptance
New R47 regression proves D1-D4 and cumulative acceptance target becomes 124/124 on exact matching tree. External Windows/MT5/ONNX gates remain separate.
