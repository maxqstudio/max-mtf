# Repair v1.4.2 — Model Size Advisor / KPI Visibility

## Scope

v1.4.2 adds advisory-only model-size guidance and restores KPI visibility without changing deterministic qualification authority.

### AUTO Research

- Existing per-family `0.00..1.00` size-priority sliders are preserved unchanged.
- `Suggested 0.xx` is derived from the current Discovery-window data capacity and existing MAX capacity heuristics. It is advisory only and never moves a slider.
- The `?` control beside each AUTO family reports the **current Owner slider's** executable size-controlled parameter envelope. It resolves through the same `model_registry.effective_bounds()` engine used by candidate generation; it is not a second UI-side slider calculator.
- Temporal/DL families also show an estimated executable trainable-parameter-count range using the actual model constructor. Tree families intentionally report trainable-parameter count as N/A because fitted tree/node count is data-dependent.
- A compiled Scientist Research Plan may further narrow a pre-start deterministic safe envelope, but may not widen Owner/dataset/hardware limits.

### MANUAL Research

- Exact numeric Owner inputs remain exact; AUTO sliders do not narrow MANUAL candidates.
- Every numeric parameter receives a `?` control showing its suggested range and legal contract range.
- Suggestions never apply values and never change MANUAL Owner input.
- Dynamic hybrid MANUAL candidates inherit advisory ranges from their exact temporal and policy components.

### Suggestion basis

- Advisor uses the selected Discovery window, not Fresh/Locked/Shadow/Promotion evidence.
- WFA feasibility uses the canonical configured `split.min_train_rows` authority.
- Historical `capacity_governor` internal `min_train_rows=200` heuristic is intentionally **unchanged**; it is not the actual WFA training-row authority and this repair does not reinterpret it.
- The advisor reuses MAX's existing engineering capacity prior and is explicitly `ADVISORY_ONLY_NEVER_AUTO_APPLY`; it is not a scientific PASS/FAIL gate.

### Exp R visibility

- New Factory telemetry emits `Exp R` from `overall_expectancy_r` directly.
- UI rendering remains backward compatible with historical events that stored the same metric as `Overall R` (then `Median R` only as legacy fallback), preventing ambiguous `None` display when evidence exists.

### Research minimum-trades KPI setup

- Research H1 baseline setup is restored to the KPI area.
- Default Research authority remains **8 closed trades/month on H1**.
- Existing deterministic timeframe scaling, exact-window prorating and integer round-up remain unchanged.
- Strategy Optimizer remains a separate authority at **20 closed trades/month on H1**; changing Research never changes Optimizer.

## Non-changes

- No AUTO slider semantics changed.
- No deterministic KPI thresholds were changed by this repair.
- No promotion authority changed.
- RL, RAG and Embedder remain OFF/fail-closed.
- External LangGraph/CUDA/ONNX/MT5/Streamlit/broker runtime gates remain separate and must not be inferred from source acceptance.

## Regression

`R56_V142_MODEL_SIZE_ADVISOR_UI` verifies advisory immutability, canonical slider-range resolution, temporal parameter-count estimates, no fabricated tree parameter count, MANUAL suggested-range legality, Exp R mapping, Research H1=8 and Optimizer H1=20 separation.

Cumulative local source/contract target: **133/133 exact-tree PASS**.
