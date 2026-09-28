# R4 Hotfix8 — Async START RESEARCH Preflight

## Evidence / first failed behavior
Owner runtime screenshot showed the lifecycle footer stuck indefinitely on `STARTING…` / `Preflight · Data Quality · freezing research plan…`. The Factory had not yet become an owned active job, so STOP/PAUSE authority was not available during the expensive broker reconciliation.

## Root cause
legacy `ModelLab/ui/app.py`, symbol `_start_auto_background()` executed `audit_dataset(..., broker_reconcile=True)` synchronously on the Streamlit fragment thread **before** `start_factory_job(...)`. MT5 initialization/history reconciliation can be slow or block. Therefore the UI could remain in the paint-only pending state even though no Factory worker had been launched yet.

## Repair
- `STARTING…` now only means **launching the Factory worker**.
- `_start_auto_background()` no longer executes broker reconciliation. It writes the frozen runtime config/payload and spawns the owned Factory worker immediately.
- `ModelLab/factory/factory_worker.py` performs the exact same mandatory Data Quality gate as the first `AUTO` stage:
  1. emit `data_quality_preflight` progress,
  2. run `audit_dataset(..., broker_reconcile=True)`,
  3. apply `research_readiness(...)`,
  4. fail closed on any readiness reason,
  5. atomically freeze `llm_data_quality_context` + source SHA into the runtime config,
  6. only then enter `run_auto_factory(...)`.
- Because the preflight now runs inside the owned worker, the lifecycle UI can show live progress and **STOP can terminate the worker even if MT5 reconciliation stalls**.
- Worker-side preflight failures are surfaced in the lifecycle footer instead of disappearing into an endless STARTING state.

## Scientific authority
No KPI, Discovery, model-family, CPCV, capacity, creativity, or validation contract was changed. The Data Quality gate is still broker-backed and fail-closed; only its execution owner moved from the UI thread to the Factory worker.

## Validation
PASS:
- `ModelLab/tests/research_start_async_preflight_selftest.py` (including executable PASS/BLOCK fixtures)
- `ModelLab/tests/lifecycle_loader_layout_selftest.py`
- `ModelLab/tests/ui_event_state_selftest.py`
- `ModelLab/tests/responsive_shell_selftest.py`
- `ModelLab/tests/data_quality_authority_selftest.py`
- `ModelLab/tests/factory_background_selftest.py`
- `ModelLab/tests/factory_preflight_selftest.py`
- `ModelLab/tests/factory_job_io_selftest.py`
- `ModelLab/tests/factory_windows_lifecycle_selftest.py`
- `ModelLab/tests/abort_lifecycle_selftest.py`
- `ModelLab/tests/deterministic_discovery_parity_selftest.py`
- `ModelLab/tests/family_size_priority_selftest.py`
- `ModelLab/tests/family_size_priority_e2e_selftest.py`
- `ModelLab/tests/cpcv_seed_confirmation_selftest.py`
- `ModelLab/tests/creativity_parity_selftest.py`
- `ModelLab/tests/research_engine_v3_selftest.py`
- `ModelLab/tests/scientist_context_parity_selftest.py`

Research-core preservation: **21/21 byte-identical** against Hotfix7.

## Runtime expectation
After pressing START:
1. brief `Launching research worker…` / disabled `STARTING…`;
2. transition to active lifecycle with PAUSE/STOP controls;
3. status becomes `Data Quality Preflight · reconciling dataset with broker history`;
4. either Data Quality PASS and research continues, Data Quality BLOCKED and a concrete error is shown, or operator STOP terminates the owned worker.

Hotfix8 remains a candidate until Owner verifies the real Windows/MT5 runtime transition.
