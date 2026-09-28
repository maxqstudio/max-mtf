# v0.6.5 · Temporal GRU + Adaptive Memory + Selectivity Forensics

## Why this revision exists

Recent research evidence showed two structural patterns: candidate quality changed materially with historical window length, and headline PF/expectancy tended to dilute as trade coverage increased. v0.6.5 does not weaken survival gates to manufacture PASS results. It expands research so the system can discover **when to learn, when to trade, and when to abstain** while preserving locked/fresh holdout isolation.

## Implemented

### Temporal GRU

- Replaced the former GRU `NotImplementedError` stub with a PyTorch `GRUClassifier`.
- Causal CP32 sequence builder with exact warmup padding shared conceptually with EA.
- Search space: sequence length 8–24, hidden 16–48, 1–2 layers, dropout, LR, batch, epochs, weight decay.
- GRU participates in Supervisor candidate generation, walk-forward CV, locked/fresh validation, frozen joblib lineage, and ONNX export path.
- EA v1.05 adds rolling feature history and independent Champion/Challenger sequence-length contracts.

### Training-memory discovery

- Every family searches `training_memory_months` from 6–72 months.
- Memory slicing is nested **inside** the operator-selected immutable research window.
- If a requested memory slice is too small for legal walk-forward construction, it falls back to the full authorized source window and records the fallback.
- Locked and fresh holdouts remain inaccessible to candidate memory selection.

### Selectivity / coverage

- Base take-threshold CV grid now extends to 0.90.
- Every candidate records total validation rows and `trade_coverage_ratio`.
- This allows sparse high-edge candidates to be studied without optimizing blindly toward minimum trade count. Minimum-trade and temporal robustness gates remain active.

### Fold / regime forensics

- Exact validation start/end per fold.
- Worst fold by expectancy and by drawdown.
- Failed survival gates per fold.
- TREND/RANGE/TRANSITION/SHOCK breakdown and hostile-regime attribution.
- `historical external: fold_forensics.json` is written by Supervisor research.

### GRU Feature/Label Audit

Tree models retain native feature importance. GRU/non-tree models use deterministic bounded permutation log-loss importance on the OOF validation tail, preventing false all-zero feature audit output.

## Preserved v0.6.4 invariants

- CSV physical duplicate keys fail closed.
- EA writer is first-write-wins; live rows are not replaced by overlapping tester runs.
- Tester fills missing H1 gaps.
- Research date range freezes into `source_window.csv`.
- Rows after cutoff remain fresh-validation-only.
- Fresh label maturity is explicit.

## Acceptance

`ModelLab/RUN_ACCEPTANCE.cmd` runs cumulative authority, CSV gap-fill/range, post-locked OOF, guided E2E, and GRU/sequence/selectivity/window-discovery tests. `historical external: BUILD_ACCEPTANCE_v0_6_5.json` is the aggregate local evidence with first-failed-gate semantics.

External gates remain: MetaEditor compile and Owner-machine MT5 live/tester + GRU ONNX runtime/parity.
