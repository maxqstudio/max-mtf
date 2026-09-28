# Max Research Agent — ONNX Factory v0.7.5 R6 Repair6

Scope: closure of three defects observed in a real partial Factory run.

## 1. Hardware profile truth
- Windows RAM now has a psutil-independent `GlobalMemoryStatusEx` fallback.
- Windows physical core discovery uses CIM/WMIC fallbacks.
- Logical SMT threads are never relabelled as physical cores.
- When physical topology is unavailable, `planning_cores` is a conservative scheduling estimate and is provenance-labelled.
- Unknown RAM remains unknown; it is not represented as `0.0 GiB` authority.

## 2. Scientist numeric-bound truth
- Research Director prose may no longer present uncompiled numeric architecture ranges as executable authority.
- Numeric proposals remain allowed only under `strategy.parameter_envelopes`.
- Every committed Director report now carries `compiled_authority.parameter_bounds`, frozen family-size priorities, topology authority, and resource capacity.
- Deterministic compiled effective bounds remain authoritative over LLM narrative/proposals.

## 3. GRU/temporal ONNX runtime batch authority
- Temporal ONNX runtime is explicitly fixed to batch=1 for MT5 sequence inference.
- Export asserts dummy batch=1 and post-export ONNX input batch=1.
- Hybrid temporal export applies the same contract.
- Runtime parity evidence records `runtime_batch_size=1` and `batch_contract=FIXED_1`.
- Only PyTorch's generic recurrent variable-batch warning is suppressed, and only behind explicit batch=1 assertions; all other exporter warnings remain visible.

No KPI, chronology, topology, model-size, CPCV seed, locked Forward, risk, or existing strategy authority was relaxed.
