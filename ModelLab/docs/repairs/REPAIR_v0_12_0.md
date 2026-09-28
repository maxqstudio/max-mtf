# MAX Research Agent v0.12.0 — Golden Research E2E Workflow Lane

## Purpose
v0.12.0 adds a deterministic, isolated workflow-validation lane that proves the Research software can traverse the complete model lifecycle without using production evidence or touching the active production Champion.

## E2E profile
`E2E_WORKFLOW_TEST_V1` uses a generated CP32 golden dataset with current Strategy Champion geometry (`SL_ATR=3.2`, `TP_ATR=4.8`, `MaxHold=54`) and one exact small RandomForest candidate. Performance KPI floors are intentionally low so the test exercises workflow mechanics instead of trying to discover market alpha.

The lane still executes real deterministic authorities: Full WFA, CPCV, Tournament, Monte Carlo, Fresh Forward, ONNX export/parity, Challenger registration and sandbox promotion transaction.

Advanced performance/risk KPI may be disabled or relaxed **only inside this E2E profile**. Data shape, geometry, chronology, stage seals, artifact integrity, ONNX parity, lineage and promotion transaction integrity remain fail-closed.

## Isolation
Every E2E artifact is marked `E2E_ONLY_NOT_PRODUCTION_SCIENTIFIC_EVIDENCE`. The lane writes to `runtime/research_e2e/<run_id>` plus sandbox registry/terminal directories under the run. It must never write the production Champion registry or production MT5 model directory.

The runtime-promotion portion uses explicitly synthetic MT5/shadow evidence only to test the promotion transaction. It is not a replacement for Owner-machine MT5/Shadow acceptance.

## One-click runner
`ModelLab/tools/research/RUN_RESEARCH_E2E.ps1`

## Environment requirement
The full Golden E2E requires the normal ONNX conversion/runtime stack. If `onnx`, `onnxruntime`, converter packages, or another required production dependency is missing, the lane fails closed and reports the missing environment dependency rather than fabricating PASS.
