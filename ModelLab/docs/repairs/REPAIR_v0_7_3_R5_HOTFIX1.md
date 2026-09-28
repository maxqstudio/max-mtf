# CPMF v0.7.3 R5 — Runtime Hotfix 1

Owner runtime on Windows exposed a post-label crash immediately after the R5 closed-loop release:

`TypeError: dataset_header_context() takes 1 positional argument but 4 were given`

## Root cause

R5 changed `dataset_header_context()` so dataset metadata beyond `columns` is keyword-only, but one legacy Supervisor call still passed `feature_contract`, `feature_count`, and `research_contract_hash` positionally. Local acceptance exercised the header-only helper and Factory-level caller but did not execute that exact Supervisor + runtime path.

## Repair

- `ModelLab/factory/supervisor_agent.py` now calls `dataset_header_context()` with explicit keyword arguments.
- `ModelLab/tests/r5_closed_loop_selftest.py` contains an explicit regression gate for the Supervisor keyword-only call contract.
- A static AST sweep of ModelLab found no remaining keyword-only functions called with excess positional arguments.
- LLM Research Director pre-flight timeout remains non-fatal. The UI now labels pre-flight API failure explicitly as non-fatal because deterministic research continues; mandatory downstream failure-learning remains fail-closed when Scientist evidence is required.
- The family-aware hybrid Scientist proposal renderer remains unchanged and continues to display `gru_*` and `policy_*` values instead of misleading generic `None` columns.

KPI, CPCV mathematics, model families, dataset contract semantics, research feedback policy, and lifecycle authority are unchanged by this hotfix.
