# MAX MTF v2.0.1 — Per-Family Dynamic Model Capacity Priority

## Owner control
Every registered base model family has a `Small 0.00 ↔ 1.00 Large` Owner preference. The control chooses **where to search**, not a hard executable size slice and not an acceptance gate.

## Three capacity ceilings
Temporal/DL admission separates three authorities:

1. **LEGAL** — registry/implementation architecture limits.
2. **RESOURCE** — frozen hardware plus architecture-specific RAM/VRAM/runtime preflight.
3. **SCIENTIFIC** — candidate-aware effective information from minimum chronological fold rows, candidate training memory, sequence length, label horizon/purge overlap, and hybrid inner-OOF information where applicable.

For every temporal candidate, the executable parameter-count ceiling is `min(LEGAL, RESOURCE, SCIENTIFIC)`. Actual parameter count is measured from the executable model/config. Historical recommended parameter envelopes remain **recommended starting guidance only**.

## Small / Balanced / Large
- `0.00 Small`: bias generation toward the lower admitted region.
- `0.50 Balanced`: broad/central exploration inside current admitted capacity.
- `1.00 Large`: permit exploration toward the upper currently justified/extended region.

Large never means registry maximum, and Small/Large never widen or replace hard capacity ceilings. Evidence from committed WFA results may bias later search toward expansion, hold, or contraction, but cannot override LEGAL/RESOURCE/SCIENTIFIC admission.

Capacity evidence is cumulative inside the **current exact Factory / research-contract lineage**. Only committed rows whose `fidelity_stage` starts with `FULL_WFA` are eligible; CHEAP_SCREEN, provisional/incomplete telemetry, and downstream CPCV/Tournament/Monte Carlo/Forward outcomes are excluded. Resume/evidence mirrors are deduplicated by authoritative `experiment_fingerprint` where available, while distinct same-size experiments remain independent observations. Evidence authority is `CUMULATIVE_COMMITTED_FULL_WFA_CURRENT_FACTORY`.

## Family semantics
The common dynamic-capacity concept applies to GRU, LSTM, TCN, Transformer, PatchTST, iTransformer, TFT, Transformer MoE, and the temporal leg of temporal→tree hybrids. Architecture-specific parameter count and resource cost remain different by family. Tree models keep their family-specific complexity controls rather than receiving neural parameter-count rules.

## Hybrid semantics
Hybrid temporal encoders use the same temporal capacity authority, while resource preflight also accounts for repeated inner OOF fitting and policy-head cost. An encoder that fits once standalone is not automatically admitted if hybrid OOF execution exceeds the frozen resource contract.

## Manual / AUTO / Scientist
- **AUTO** samples inside executable registry ranges and emits only candidates that pass dynamic capacity.
- **Scientist** receives the same capacity authority/bands and may reason about larger or smaller experiments only inside admitted hard ceilings.
- **MANUAL** preserves exact Owner parameter identity and may use a candidate above the historical recommended starting envelope when it remains legal, resource-safe, and scientifically admitted.

Candidate evidence records actual parameter count, all three ceilings, effective ceiling, preferred/extended band, training memory, sequence length, minimum fold rows, effective-sample estimate, size priority, capacity band, and explicit rejecting authority when admission fails.

## Safety
Capacity preference never changes WFA/CPCV chronology, purge/embargo, fixed DL/hybrid CPCV seeds, nested threshold selection, label causality, hybrid OOF stacking, DL early-stop purge, MoE routing/diagnostics, KPI gates, locked Forward, or promotion authority.
