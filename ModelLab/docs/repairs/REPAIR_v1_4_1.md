# Repair v1.4.1 — Agentic Learning Audit Repair

## Scope

This repair closes defects found during the v1.4.0 handoff/source audit without changing Strategy Champion execution authority, deterministic KPI authority, promotion authority, or enabling RAG/Embedder/RL.

## D1 — Protected-stage canonicalization

`ModelLab/research/structured_research_memory.py` now canonicalizes runtime stage aliases before learning admission. `FRESH`/`FORWARD` map to `FRESH_FORWARD`; `LOCKED`/`LOCKED_TEST` map to `LOCKED_OOS`. Shadow, Promotion, Challenger, Champion and their known aliases are protected. Unknown stage identifiers fail closed.

The protection applies both to new hypotheses and to pre-existing experience-ledger rows during refresh, so a contaminated legacy/checkpoint row cannot survive replay merely because `protected_evidence_used=false`.

## D2 — Structured Research Experience V2

Authority is upgraded to `MAX_STRUCTURED_RESEARCH_MEMORY_V2` / `MAX_RESEARCH_EXPERIENCE_V2`.

When evidence exists, an experience preserves parent/experiment/candidate lineage, model families/topology, bounded hyperparameter action, feature/label/training-memory action, hypothesis/prediction, state before/after, KPI deltas, failed gates, failure margins, fold distribution, coverage, sample sufficiency and outcome observations. Missing legacy evidence remains explicit `null`/empty and is never fabricated.

Existing V1 rows are migrated structurally and revalidated against the current learning-stage contract.

## D3 — Scientist skill runtime context

All nine MAX Data Scientist skills must contain `TEST / REGRESSION FIXTURES`. Runtime routing now supplies the selected skill methodology sections—not only one-line doctrines—including decision procedure, failure patterns, allowed/forbidden actions, output schema and fixtures. Skill hashes remain manifest-verified and advisory-only.

## D4 — External runtime gate authority

`governance/EXTERNAL_RUNTIME_GATES.json` is the single canonical registry. Package governance and build acceptance consume/verify the same gate set. Runtime gates cannot be marked PASS by source/static acceptance.

## D5 — Governance synchronization

Current authority is v1.4.1. Historical v1.3.2/v1.3.3/v1.3.4 repairs are recorded as verified in the current cumulative source acceptance instead of `PENDING`. v1.4.0 remains historical foundation authority.

## Regression

`R55_V141_AGENTIC_LEARNING_AUDIT_REPAIR` tests protected aliases, unknown-stage fail-closed behavior, replay purification, V2 evidence richness, mandatory skill fixtures, and full selected-methodology runtime context.

Cumulative local source/contract target: **132/132** from the exact final tree. External LangGraph/CUDA/ONNX/MT5/UI runtime gates remain separate.
