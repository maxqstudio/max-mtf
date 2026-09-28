# Champion Factory V1 · CPMF v0.6.9

## Chronological authority

Default contract:

1. **Discovery / Screening**: 2020-01-01 → 2022-12-31
2. **Tournament**: 2023-01-01 → 2025-12-31
3. **Fresh Forward**: 2026-01-01 → newest selected row

All three windows are frozen before Discovery begins. Overlap or non-chronological ranges fail closed.

## Discovery

Discovery is OOF-only and may use Research Memory, LLM Scientist, Guided hypotheses, model-family exploration, training-memory, feature/label/selectivity hypotheses, and bounded policy search.

Target is **exactly 12 unique qualified candidates**. Research generations continue automatically until either:

- 12 qualified candidate fingerprints are collected; or
- the bounded experiment/generation budget is exhausted.

If the budget ends below 12, state is `INSUFFICIENT_QUALIFIED_POOL`. Tournament cannot open and gates are not weakened.

Candidate fingerprints include family + frozen model parameters. Duplicate winners do not increase pool count.

## Tournament

The 12-candidate pool is frozen before Tournament is opened. The Tournament window may be opened only once for that Factory lineage.

Each frozen candidate is trained from Discovery authority under its frozen contract and evaluated on the same untouched Tournament dataset. Tournament hard gates include sample sufficiency, DD, recovery, PF, expectancy, time/regime/stress stability, and non-negative expectancy in every Tournament year.

Survivors are ranked survival-first. Exactly one winner is frozen.

Tournament results are not fed back to Scientist for retuning in the same Factory epoch.

## Fresh Forward

The exact Tournament winner contract is refit on all known pre-Fresh history (Discovery + Tournament) without changing architecture, features, labels, selectivity, thresholds, or hyperparameters. This is a standard train+validation refit after model selection; Fresh remains untouched.

Only the single Tournament winner is evaluated on Fresh. If Fresh fails, result is `NO_CHAMPION_FRESH_FAIL`.

Runner-up fallback is explicitly **FORBIDDEN**. Trying candidate #2 after candidate #1 fails would convert Fresh into another selection set.


## Training-memory CV invariant

`training_memory_months` now restricts only each fold's training history. It never shortens the OOF validation chronology. This prevents short-memory candidates from receiving an easier sample gate or a shorter screening exam.
