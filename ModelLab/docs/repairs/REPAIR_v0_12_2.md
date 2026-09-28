# MAX Research Agent v0.12.2 — Golden E2E Promotion Diagnostics

## Defect
Real Windows Golden E2E reached sandbox promotion but failed with `Supervisor promotion gates are not all PASS under current KPI policy`. The E2E harness built an incomplete locked/current-policy KPI evidence object and left legacy stress thresholds at production-like values. The runner also did not guarantee a compact diagnostic package for every PASS/FAIL.

## Repair
- Keep production promotion policy unchanged.
- E2E-only acceptance now sets spread stress floors to `-0.05R` consistently across current-policy revalidation.
- E2E Challenger evidence now includes complete ONNX parity, temporal, regime, stress, concentration and locked KPI fields required by `governance.assess_promotion()`.
- `assess_promotion()` is executed before promotion and its exact gates are persisted as `historical external: promotion_precheck.json`.
- Add `ModelLab/tools/research/RUN_RESEARCH_E2E.cmd` one-click launcher.
- Every run creates `runtime/research_e2e/diagnostic_evidence/<run_id>/` on PASS or FAIL, including summary JSON, traceback for exceptions, progress, config/evidence snapshots, and promotion evidence when available.

## Authority
All E2E artifacts remain `E2E_ONLY` / `production_evidence=false`; no E2E KPI or synthetic runtime evidence can be promoted into production scientific authority.
