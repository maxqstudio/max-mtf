# Max Research Agent — ONNX Factory v0.7.5 R6 Repair7

## Scope
Repair7 adds a read-only Scientist Chat workspace without changing deterministic research, Factory lifecycle, validation gates, candidate admission, Champion authority, or MT5/ONNX execution paths.

### Added
- right-side show/hide Scientist Chat workspace;
- manual chat model selector independent from autonomous Scientist routing;
- fallback OFF by default, optional ordered retryable fallback;
- AUTO/bounded evidence context selector;
- per-Factory chat history outside Factory research evidence;
- internal evidence-source provenance;
- locked/fresh Forward isolation consistent with active Scientist governance;
- explicit `READ ONLY · NO EXECUTION` UI and backend contract.

### Security/authority design
`ModelLab/scientist/chat/scientist_chat.py` contains no Factory/Champion/job execution imports and exposes no tool schema. The LLM receives ordinary chat messages plus a bounded evidence snapshot only.

### Preserved
Repair6 hardware truth, deterministic compiled-bound authority, fixed batch=1 temporal ONNX contract, latest Max UI, Data Quality authority, LLM resilience, CPCV/WFA/KPI governance, STOP/ABORT lifecycle, and all existing research functionality remain unchanged.

## Acceptance
Full cumulative acceptance: **78 / 78 PASS**, `first_failed_gate = null`.
