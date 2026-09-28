# CPMF v0.6.7 — Immutable Lineage Hash + Fresh Cutoff Authority Repair

## Defect reproduced from Owner runtime

A rejected Fresh Holdout could route to Feature+Label Audit and fail with:

`CSV bukan dataset source lineage ini. Hash berbeda.`

Root cause: v0.6.6 overloaded `source_csv_sha256` with two incompatible meanings:

1. immutable research `source_window.csv` hash; and
2. mutable master/fresh-input CSV hash after Fresh Holdout validation.

The audit correctly resolves `source_window.csv`, but a v0.6.6 Fresh manifest could carry the mutable master hash, causing a false lineage mismatch.

## Repair

- `source_csv_sha256` remains a backward-compatible alias for the immutable research source hash.
- Added explicit `research_source_csv_sha256`.
- Added explicit `research_source_raw_end`.
- Added `fresh_input_csv_sha256` and `fresh_input_provenance`; fresh/master identity no longer overwrites research identity.
- Feature+Label Audit can recover the immutable research hash through ancestry for already-created v0.6.6 Fresh runs, so research does not need to be repeated merely because of this bug.
- Post-locked Policy Discovery now carries the source research window and verifies that the manifest cutoff exactly equals the maximum timestamp in the immutable `source_window.csv`.
- Fresh-validation UI resolves and shows the original research From/To and the exact exclusive fresh cutoff through lineage.

## Cutoff semantics

The Fresh Holdout cutoff is the last timestamp of the operator-selected immutable research snapshot. It is **not** candidate training-memory start/end and is **not** the internal locked/CV split boundary.

If the UI shows `2025-02-28 23:00:00`, the authoritative `source_window.csv` for that lineage must end at that timestamp. If the Owner intended a different Research To date, that is a range-selection issue and the research run itself must be regenerated with the intended window.

## Acceptance

- New `LINEAGE_HASH_CUTOFF_AUTHORITY` gate.
- Reproduces the v0.6.6 legacy fresh-manifest shape and proves the repair resolves the immutable ancestor hash rather than accepting the mutable fresh hash.
- Cumulative gates remain required.
