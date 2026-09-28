# CPMF v0.7.2 R1 — Research Kernel Consolidation

## Why this revision exists

The prior research stack had valid robustness components but inconsistent temporal/evaluation semantics between WFA, CPCV, hybrid inner OOF, Policy Discovery, and Guided/Audit paths. Adding new models on top of those seams would make attribution worse. This revision repairs the kernel first.

## Repaired

- Added one `TemporalIndexContract` authority.
- CPCV temporal training preserves original discontinuous row topology; GRU/hybrid sequences cannot cross held-out gaps.
- Hybrid GRU→classical inner OOF is purged/indexed before classical-policy fitting.
- Training-memory truncation is train-side only in normal WFA and Policy Discovery.
- Policy Discovery temporal prediction uses causal historical context consistent with WFA/live semantics.
- Factory Feature/Label Audit and Guided Research share the full Discovery OOF region; legacy internal split is explicit compatibility only.
- No-op single-layer GRU dropout parameters canonicalize before validation/fingerprinting/model construction.
- `HYBRID_ABLATION` is no longer advertised as executable without deterministic wiring.
- Tournament/Monte Carlo/Forward failure evidence is sealed in Evaluation Vault instead of feeding active Discovery memory.
- Added cumulative `RESEARCH_KERNEL_CONSOLIDATION` acceptance gate.

## Intentionally unchanged

- Existing model families and KPI authority.
- Existing risk/trading contracts.
- Existing Master Orchestrator lifecycle.
- LLM Supervisor pre-flight and global START/STOP are deferred to the next feature revision.

## Acceptance intent

This release is accepted only if the full existing acceptance suite plus `ModelLab/tests/research_kernel_selftest.py` passes. External ONNX runtime parity, MetaEditor compile, and Owner MT5 runtime remain external gates when not available in the build environment.
