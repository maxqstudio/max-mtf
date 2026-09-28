# v0.6.4 · CSV Integrity, Gap Fill, Research Window, Fresh Readiness

## Defects closed

1. EA v1.03 only deduplicated the current in-memory bar. Restarting live or rerunning Strategy Tester could append the same `signal_time` again.
2. Python `load_training_csv()` silently used `drop_duplicates(signal_time)`, hiding physical duplicate corruption and choosing a surviving row without provenance evidence.
3. A historical backtest used for gap fill could overlap live data without an explicit first-write-wins contract.
4. Fresh validation only reported `Tidak ada labeled row baru setelah source cutoff`, hiding whether raw fresh rows existed but had not matured through the configured label horizon.
5. Research always consumed the selected CSV as a whole; the operator could not reserve later dates for genuinely unseen validation.
6. Downstream Policy Discovery / Feature+Label Audit / Guided Research asked the operator to select a CSV again, creating a leakage path around the original research cutoff.
7. Existing v0.6.3 cumulative acceptance was FAIL because `ModelLab/config/config.json` still carried the older strict KPI profile and an incomplete Policy Discovery regime list, while KPI V5 docs/tests expected the H1 authority.

## Repair

### EA v1.04 writer

- Added an exclusive Common-Files writer lock (`<training.csv>.lock`).
- Training CSV write handle intentionally omits `FILE_SHARE_WRITE`.
- Maintains an in-memory sorted timestamp index and refreshes only newly appended tail rows from other cooperating v1.04 writers.
- Checks the identity timestamp before every append.
- **First-write-wins:** pre-existing live data is never overwritten by tester data.
- A later overlapping Strategy Tester run therefore fills only missing H1 gaps.
- Legacy v1.03 concurrent writer is fail-closed rather than silently accepted.

### Physical CSV integrity

- Added `ModelLab/data/dataset_integrity.py`.
- `model_lab.load_training_csv()` now fails closed when physical duplicate identity keys exist.
- Removed silent `drop_duplicates()` behavior.
- Added UI repair action `CLEAN LEGACY DUPLICATES · BACKUP FIRST`:
  - serializes against the same EA writer lock;
  - creates a timestamped backup;
  - applies first-write-wins dedup;
  - sorts by `signal_time`;
  - verifies zero duplicate keys before completion.

### Research date authority

- Research UI exposes a date range using only dates present in the master CSV.
- UI previews selected research rows, exact cutoff, later raw reserve, mature fresh rows, and pending horizon rows.
- `START RESEARCH` creates a deterministic snapshot and records `CP_RESEARCH_WINDOW_V1` lineage.
- Supervisor copies that snapshot to each base run as immutable `source_window.csv`.
- Downstream OOF Policy Discovery, Feature+Label Audit, Guided Research, and new-generation research resolve the exact lineage snapshot instead of asking for the growing master CSV again.
- Fresh Validation remains the only stage allowed to read newer master rows after `source_raw_end`.

### Fresh validation diagnostics

Fresh readiness is now classified as:

- `NO_FRESH_ROWS`
- `WAITING_LABEL_HORIZON`
- `NO_VALID_LABELS`
- `READY`

The UI and validator expose raw-new, mature-raw, labeled-fresh, pending-horizon, configured horizon, and newest source timestamp.

### Acceptance authority repair

`ModelLab/config/config.json` is synchronized to the already documented H1 KPI V5 authority:

- profile `SURVIVAL_H1_V1`
- locked PF 1.35, expectancy +0.15R, max DD 12R, recovery 2.0, trades 50
- CV PF 1.25, expectancy +0.10R, worst expectancy -0.03R, validation trades 90
- worst-fold DD 18R, worst-fold recovery 1.0
- stress x1.25 +0.08R, x1.50 +0.05R
- transition regime modes restored to Policy Discovery

## Local acceptance

`ModelLab/RUN_ACCEPTANCE.cmd` -> `ModelLab/acceptance/runners/run_acceptance.py` executes, fail-fast:

1. cumulative governance / KPI / workflow acceptance;
2. v0.6.4 CSV-integrity + live/tester gap-fill + research-window self-test;
3. post-locked OOF smoke;
4. guided Feature/Label E2E smoke.

Machine-readable aggregate: `historical external: BUILD_ACCEPTANCE_v0_6_4.json` with `first_failed_gate`.

Local Python acceptance: **PASS**.

## External gates not claimed

- `MQL5_METAEDITOR_COMPILE`: NOT RUN in this build environment.
- Owner MT5 runtime scenario with live v1.04 + overlapping Strategy Tester v1.04: required after compile.
