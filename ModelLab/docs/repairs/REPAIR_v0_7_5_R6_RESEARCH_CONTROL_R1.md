# Repair / Revision Record — v0.7.5 R6 Research Control R1

**Generated:** 2026-09-13T06:44:43.643230+00:00

## Owner intent

Add two explicit research authorities (AUTO and MANUAL), make Scientist Chat a stronger read-only scientific advisor with per-model settings and streaming/progress UX, and synchronize living documentation so a new room can audit defects from contract instead of reconstructing history.

## Intentional source changes

- `ModelLab/ui/app.py` — Research Control UI, MANUAL start path, per-model Chat profiles, streaming/idempotent Chat integration.
- `ModelLab/research/research_control.py` — mode authority, exact MANUAL runtime compiler, provenance.
- `ModelLab/factory/supervisor_agent.py` — exact Owner candidate intake and no proposal generation in MANUAL.
- `ModelLab/factory/champion_factory.py` — MANUAL orchestration provenance/terminal semantics while retaining validator stages.
- `ModelLab/factory/factory_orchestrator.py` — one-pass MANUAL validator chain.
- `ModelLab/factory/factory_worker.py` — MANUAL action path through owned worker/Data Quality preflight.
- `ModelLab/host/provider_catalog.py` — provider streaming transport.
- `ModelLab/scientist/chat/scientist_chat.py`, `ModelLab/scientist/chat/scientist_chat_worker.py`, `ModelLab/scientist/chat/scientist_chat_jobs.py`, `ModelLab/scientist/chat/scientist_chat_component.py` — streaming/profile/process/idempotency behavior.
- `ModelLab/acceptance/runners/run_acceptance.py` — Research Control gates added to cumulative acceptance.

## New gates

- `R19_RESEARCH_CONTROL_MODE_AUTHORITY`
- `R19_MANUAL_EXACT_CANDIDATE_CONTRACT`
- `R19_MANUAL_ORCHESTRATOR_VALIDATION_CHAIN`
- `R19_SCIENTIST_CHAT_STREAMING_MODEL_PROFILES`

## Explicit non-changes

The revision does not relax production KPI, Data Quality, capacity ceilings, chronology, CPCV seed set, Forward isolation, decision class contract, model math/evaluation metrics, or deterministic PASS/FAIL.

## Known external acceptance

Owner-machine visual/runtime, ONNX Runtime/CUDA, MetaEditor/MQL5 and broker reconciliation evidence remain external and must stay NOT RUN unless executed.
