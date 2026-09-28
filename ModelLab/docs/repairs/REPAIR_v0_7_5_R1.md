# Repair / Build v0.7.5 R1

Scope: Scientist-driven dataset-aware capacity sizing and executable Transformer MoE, preserving v0.7.4 R2 Hotfix3 governance and UI-state hardening.

Implemented:
- dataset/WFA training-row capacity profiler;
- hardware + dataset capacity guidance to Research Director;
- compiled per-family parameter envelopes consumed by candidate generation;
- parameter-count and effective-train-row evidence;
- Transformer MoE temporal family with learned Top-K router, load-balance loss and utilization evidence;
- dynamic `hybrid::transformer_moe::<policy>` compatibility;
- generation-review capacity revision path;
- dedicated self-tests and cumulative acceptance.

External Owner gates remain CUDA/ONNX converter parity, MetaEditor and MT5 runtime on the new PC.
