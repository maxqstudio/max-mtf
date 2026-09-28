# CPMF v0.7.3 R5 — Closed-Loop Research + Observability Repair

R5 is a bounded repair of the v0.7.3 scientific workflow after Owner runtime evidence reached `CPCV_NO_SURVIVOR` with Pool 12/12. The runtime evidence showed that WFA candidate supply was healthy while CPCV lower-tail survival failed, and also exposed observability/learning gaps.

## Repair authority

- One `Research` control room owns START/PAUSE/STOP/RESUME; stage pages are live inspectors of the same worker authority.
- Global/status fragments refresh every 2 seconds.
- Committed/pending/projected Pool telemetry is persisted from exact deduplicated Full-WFA PASS counts at completed safe-round boundaries; pending evidence never becomes Pool authority until the outer Factory atomically commits it.
- CPCV records each Pool candidate as WAITING/RUNNING/PASS/FAIL, persists dedicated failure topology, and exposes completed split metrics while the current candidate is still running.
- LLM Scientist produces reports at committed stage boundaries. Hybrid proposal rendering is family-aware (`gru_*` + `policy_*`) and no longer displays misleading generic `None` values.
- Pool/CPCV/Tournament/Monte-Carlo failure can inform a new Discovery cycle only through a committed bounded Scientist summary/hypothesis. Raw downstream evidence remains sealed.
- Feedback is scoped to an exact dataset contract that includes source-master SHA-256; dataset revision changes create a different exact research contract.
- Feedback exposure budgets bound repeated same-dataset learning. LLM/API failure does not spend an exposure; resume retries the Scientist report without rerunning the validation stage.
- Scientist `MODEL_ARCHITECTURE` hypotheses can specify legal per-family parameter ranges; Experiment Blocks enforce those ranges and freeze unrelated knobs. Training-memory and selectivity hypotheses are wired into actual next-Discovery execution.
- Hybrid LightGBM/XGBoost policy L1/L2 regularization is now searchable; LightGBM `subsample` activates bagging frequency.
- Spec identity and trained-candidate identity remain separate; trained identity includes seed and resolved threshold.
- Default active families remain GRU→LightGBM and GRU→XGBoost. Random Forest code paths remain dormant/reserve, not deleted.
- CPCV current implementation remains the existing combinatorial purged-split method. R5 corrects nomenclature and evidence visibility; it does **not** silently replace it with canonical reconstructed CPCV-path methodology.

KPI thresholds are unchanged.

## Local acceptance

41/41 local gate scripts PASS on exact R5 source, plus Python compileall PASS. External ONNX converter/runtime, MetaEditor compile, and Owner MT5 runtime remain external acceptance.

## Runtime Hotfix 1

Owner Windows runtime found one stale Supervisor call that passed keyword-only `dataset_header_context` metadata positionally. It is repaired and covered by `ModelLab/tests/r5_closed_loop_selftest.py`. See `ModelLab/docs/repairs/REPAIR_v0_7_3_R5_HOTFIX1.md`.
