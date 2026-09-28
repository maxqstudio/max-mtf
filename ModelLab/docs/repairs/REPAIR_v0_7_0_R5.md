# CPMF v0.7.0 R5 — Champion Factory ONNX Preflight Progress Repair

## Defect
Champion Factory Discovery could appear frozen at ~5% before the first candidate. The progress mapping identified this as the ONNX converter preflight. R4 executed the full deployability preflight inside every Supervisor generation and exposed no per-family heartbeat while conversion/training was running.

## Repair
- Champion Factory runs ONNX deployability preflight exactly once before Generation 1.
- The PASS report is frozen as `historical external: factory_onnx_preflight.json`.
- Every Discovery generation receives that report as explicit fail-closed `onnx_preflight_authority` and copies the evidence into its run directory.
- Preflight reports per-family progress to the Streamlit Factory progress UI.
- No deployability gate is weakened or skipped: missing/non-PASS authority aborts the generation.

## Acceptance
`FACTORY_ONNX_PREFLIGHT_ONCE` verifies one-time authority, evidence reuse, and visible progress wiring.
