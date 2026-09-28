# REPAIR v0.7.5 R6 — UI Component Chat R4 Hotfix4 Interaction State

## Scope
Bounded UI/event-state repair. Scientific authority remains v0.7.5 R6.

## Defects repaired
- START RESEARCH did not visibly disable immediately during deterministic preflight.
- Long startup/stop operations had weak or missing progress feedback.
- Scientist Chat LLM call blocked the Streamlit run, which could leave an apparently infinite thinking state and offered no real cancellation path.
- Assistant bubbles did not always identify which model actually answered.
- Left header still rendered the CP icon and clipped the product/version text.

## Repair
### Research lifecycle
- START is now a two-phase UI event: ARMED -> EXECUTE.
- The ARMED frame completes first, painting a grey disabled `STARTING…` control and animated loader before Data Quality/preflight begins.
- STOP uses the same two-phase pattern (`STOPPING…`) before verified worker-tree termination.
- Existing factory_jobs STOP/ABORT scientific lifecycle authority is unchanged.

### Scientist Chat generation
- LLM generation runs in a dedicated background process (`ModelLab/scientist/chat/scientist_chat_worker.py`).
- API key is passed out-of-band through process environment and is not written to request JSON.
- Scientist drawer polls the job at 1-second cadence without rebuilding research pages.
- Thinking state has a visible Stop control that terminates the owned chat worker process.
- Active chat jobs fail closed if the process disappears or exceeds hard timeout.
- Provider failure is shown as an explicit error state instead of leaving infinite thinking.

### Assistant bubble provenance
- Every assistant reply shows the actual `answered_by` model.
- Fallback replies are additionally marked `fallback`.

### Left header
- CP icon removed.
- Header now renders `Max`, `Research Agent · ONNX Factory`, and `v0.7.5 R6` without ellipsis/cropping.

## Acceptance
- Python compileall: PASS
- interaction_state_selftest: PASS
- Scientist Chat UI/AI UX/read-only/settings/context tests: PASS
- responsive shell + UI event state: PASS
- factory background + Windows lifecycle + ABORT lifecycle: PASS
- topology priority / deterministic Discovery / creativity / family sizing / CPCV seed / Data Quality / LLM fallback: PASS
- Scientific-core preservation: 21/21 byte-identical vs Hotfix3 source candidate.

## Runtime truth
Visual/runtime acceptance on Owner Windows remains the final UI authority. This package is a candidate, not a visual-acceptance claim.
