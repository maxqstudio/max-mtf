# MAX Research Agent v0.12.1 — Golden E2E Fresh Forward Data Quality Isolation

## Defect
`E2E_WORKFLOW_TEST_V1` uses a synthetic CP32 dataset. Fresh Forward called production `audit_dataset(..., broker_reconcile=True)` and therefore failed with `BROKER_RECONCILIATION_REQUIRED`, incorrectly coupling software workflow acceptance to an MT5 broker feed.

## Repair
- Production Fresh Forward remains unchanged and still requires broker reconciliation.
- Synthetic Golden E2E Fresh Forward uses deterministic local Data Quality only when **all** E2E identity guards match: profile `E2E_WORKFLOW_TEST_V1`, `e2e_only=true`, `production_evidence=false`, authority `SYNTHETIC_GOLDEN_CP32_WORKFLOW_ONLY_NOT_PRODUCTION_EVIDENCE`, filename `CP32_E2E_GOLDEN.csv`, and symbol `E2E_XAUUSD`.
- The local proof never sets broker `verified=true`; no fake broker evidence is written to cache.
- Any E2E identity drift fails closed.
- Local hard Data Quality failures or observed timestamp discontinuities still block Fresh Forward.

## Regression
`ModelLab/tests/v0121_e2e_forward_local_dq_selftest.py` proves E2E-only local Forward DQ, no forged broker proof, production exclusion, and fail-closed profile mismatch.
