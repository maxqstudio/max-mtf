# REPAIR v1.3.3 — Challenger Retention Lifecycle

## Problem

v1.3.2 LangGraph AUTO Factory could reach sealed `FACTORY_WINNER` and terminate without automatically registering that winner in the persistent Model Challenger registry. The registry itself was append/retain and promotion was Owner-only, but the AUTO graph did not enforce the required `FACTORY_WINNER -> ELIGIBLE_CHALLENGER` bridge.

## Contract

1. Every sealed AUTO Factory `FACTORY_WINNER` must pass through `REGISTER_MODEL_CHALLENGER` before terminal success.
2. The bridge creates a persistent Model run under `ModelLab/runs/`, copies sealed ONNX/runtime artifacts with byte-parity verification, writes an `ELIGIBLE_CHALLENGER` manifest, and appends it to `ModelLab/governance/challenger_registry.json`.
3. Registration is idempotent across retry/resume. Replaying the same Factory winner must not duplicate the Challenger.
4. New Model Challengers never delete or replace older Challengers. `PROMOTED`/`RETIRED` registry status is preserved on replay.
5. Factory/LangGraph has no Champion promotion authority. Promotion remains explicit Owner action through Governance/UI only.
6. Registration failure is fail-closed as `MODEL_CHALLENGER_REGISTRATION_FAILED`; sealed Factory winner evidence remains preserved.
7. Strategy Optimizer lifecycle remains unchanged: eligible winner is appended as Strategy Challenger, current Strategy Champion is not replaced automatically, and promotion remains explicit Owner action. Explicit Challenger deletion retains tombstone lineage.

## Evidence

- `ModelLab/factory/factory_challenger_bridge.py`
- `ModelLab/max_graph/factory_graph.py`
- `ModelLab/tests/v133_challenger_retention_lifecycle_selftest.py`
- cumulative gate `R52_V133_CHALLENGER_RETENTION_LIFECYCLE`

## Release boundary

v1.3.3 changes lifecycle persistence/registration only. It does not change Strategy Champion parameters, scientific model KPI, label semantics, execution replay, or promotion gates established by v1.3.2.
