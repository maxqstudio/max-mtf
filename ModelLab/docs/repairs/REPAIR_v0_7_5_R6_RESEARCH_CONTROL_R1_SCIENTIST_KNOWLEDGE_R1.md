# Repair / Control Extension — Scientist Knowledge R1

## Problem

Research Control R1 gave Scientist Chat rich current settings/evidence, but no mandatory static capability map of Max itself. This allowed scientifically reasonable but duplicate recommendations, such as suggesting Single-vs-Hybrid capability that Max already implements.

There was also no release gate forcing Scientist knowledge/handoff documentation to move with code or contract changes.

## Repair

1. Add generated machine-readable `ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json`.
2. Add generated human-readable `ModelLab/docs/contracts/SCIENTIST_KNOWLEDGE_BASE.md`.
3. Add explicit `ModelLab/docs/contracts/MAX_WORKFLOW_CONTRACT_E2E.md`.
4. Add machine-readable `historical external: WORKFLOW_CONTRACT_AUDIT_R1.json`.
5. Scientist Chat always receives a compact `max_knowledge` capability/workflow context.
6. Scientist prompt must perform novelty classification before substantive feature/workflow recommendations.
7. Add source/doc hash synchronization gate `ModelLab/tests/scientist_knowledge_sync_selftest.py` to cumulative acceptance.
8. Update room-transfer handoff and contract index.

## Scientific boundary

This extension changes Scientist knowledge/grounding and release governance only. It does not change Data Quality, candidate generation math, model training, WFA/CPCV/Tournament/Monte Carlo/Forward acceptance, KPI thresholds, Capacity Governor or ONNX runtime semantics.

Scientist may still recommend new/out-of-contract ideas. It is prohibited only from acting as though an existing Max capability does not exist.
