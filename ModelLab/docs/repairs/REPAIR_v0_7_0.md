# CPMF v0.7.0 · Simplification + Scientist Agent

## Scope
- Simplify operator route to Data → Discovery → Pool → Tournament → Fresh → Champion.
- Move legacy Research/Pipeline/Guided mechanics out of top-level navigation into Advanced/audit authority.
- Add fixed right-side persistent Scientist Chat with independent scroll.
- Give Scientist read-only deterministic strategy/data/evidence context.
- Allow explicit operator commands to invoke only whitelisted research functions through deterministic Supervisor gates.
- Repair Fresh Forward to use AUTO_NEWEST and treat insufficient sample as non-terminal.
- Preserve v0.6.9 Champion Factory, Research Memory, AUTO sample authority, settings persistence, lineage, hybrid/GRU, and fail-closed gates.

## Governance
Scientist may recommend strategy changes/hypotheses but cannot directly mutate deterministic strategy, risk rules, acceptance gates, Champion authority, or live trading authority.

## Fresh state machine
`TOURNAMENT_WINNER_READY → FRESH_INSUFFICIENT_SAMPLE → (new master data) → FRESH check again → CHAMPION | NO_CHAMPION_FRESH_FAIL`.
No new data means recheck is rejected. Runner-up fallback remains forbidden.


## R3 · Persisted date boundary normalization
- Repair `datetime.date` versus persisted ISO-string comparison crash when Discovery starts directly from saved settings.
- Normalize Research/Factory date arguments at the dataset-integrity boundary before any chronological comparison or mask.
- Preserve ISO-string serialization on disk/manifests; runtime slicing uses `datetime.date`.
- Regression acceptance covers both `research_window_preview()` and `build_research_window_snapshot()` with ISO-string inputs.
