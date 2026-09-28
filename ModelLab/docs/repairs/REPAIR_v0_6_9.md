# CPMF v0.6.9 · Champion Factory + Dynamic Trade Sample

## Scope

- Add Champion Factory lifecycle: Discovery pool 12 → untouched Tournament → one frozen winner → Fresh Forward.
- Add `Trade Sample = AUTO`, dynamically resolved from timeframe + exact date range + actual OOF exposure.
- Preserve v0.6.8 Research Memory / LLM Scientist behavior.
- Preserve persistent settings/API under `%LOCALAPPDATA%\ComplexPolicy\ModelLab` with DPAPI secret storage.
- Add Streamlit port fallback 8501→8502…8510 instead of aborting when 8501 is occupied.
- EA runtime contract remains v1.06; no MQL5 execution change in this revision.

## Fail-closed rules

- Factory split must be chronological and non-overlapping.
- Discovery must reach exactly 12 qualified unique candidate fingerprints before Tournament.
- Bounded search budget may terminate with insufficient pool; thresholds are never relaxed automatically.
- Tournament can be opened once per Factory lineage.
- Only one Tournament winner can enter Fresh.
- Fresh runner-up fallback is forbidden.
- AUTO sample threshold is calculated before candidate performance and stored in evidence.

## Local acceptance

New gates:

- `AUTO_TRADE_SAMPLE`
- `CHAMPION_FACTORY_CONTRACT`
- `LAUNCHER_PORT_FALLBACK`

All prior cumulative acceptance gates remain mandatory.


## Training-memory CV invariant

`training_memory_months` now restricts only each fold's training history. It never shortens the OOF validation chronology. This prevents short-memory candidates from receiving an easier sample gate or a shorter screening exam.
