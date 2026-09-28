# v0.6.6 · Hybrid Temporal Policy Build

## Why this revision exists

Research evidence showed two recurring patterns: edge quality changed materially with the historical window, and broader trade coverage often diluted median PF/expectancy while selective candidates could still fail catastrophically in a hostile fold. v0.6.6 does not lower survival gates. It expands the model architecture so temporal direction, trade selection, and deterministic risk can be separated and audited.

## Implemented

1. **Hybrid GRU→classical families**
   - GRU→XGBoost;
   - GRU→LightGBM;
   - GRU→RandomForest optional.
2. **Direction-only temporal authority**
   - GRU output is DOWN/UP only;
   - final SELL/SKIP/BUY is owned by the classical policy model.
3. **OOF stacking**
   - classical policy training uses only chronological out-of-fold GRU signals;
   - final GRU refit occurs after OOF policy fit is frozen.
4. **Causal fold context repair**
   - standalone GRU and hybrid validation use real authorized rows before the fold as temporal history.
5. **Two-model ONNX contract**
   - temporal `[1,T,32] -> [1,2]`;
   - policy `[1,36] -> [1,3]`;
   - manifest records atomic runtime contract and hashes.
6. **EA v1.06 hybrid inference**
   - rolling CP32 sequence;
   - exact four temporal meta-features;
   - independent Champion/Challenger hybrid controls;
   - partial failed ONNX initialization releases any already-created hybrid handle.
7. **Bounded staged planner**
   - initial round excludes hybrid stacks;
   - hybrid unlock requires standalone GRU evidence;
   - temporal hyperparameters seed from the best GRU;
   - default hybrid cap = 2 candidates/round.
8. **Existing v0.6.4/v0.6.5 repairs retained**
   - duplicate-free first-write-wins live/tester CSV;
   - tester gap fill;
   - legacy duplicate fail-closed cleanup with backup;
   - operator Research From/To snapshot authority;
   - fresh label-maturity diagnostics;
   - training-memory/selectivity search;
   - fold/regime forensics.

## Acceptance

`ModelLab/acceptance/runners/run_acceptance.py` executes these cumulative local gates:

1. `HYBRID_GRU_CLASSICAL_STACK`;
2. `GRU_SEQUENCE_SELECTIVITY`;
3. `CUMULATIVE_AUTHORITY`;
4. `DATA_INTEGRITY_GAP_FILL_RANGE`;
5. `POST_LOCKED_OOF`;
6. `GUIDED_FEATURE_LABEL_E2E`.

Machine-readable output: `historical external: BUILD_ACCEPTANCE_v0_6_6.json` with first-failed-gate semantics.

## Explicit external gates

Not claimed by the build environment:

- ONNX converter + ONNX Runtime parity, because those packages are unavailable here;
- MetaEditor compile;
- real MT5 hybrid ONNX runtime;
- real Owner-machine live + Strategy Tester concurrency/gap-fill acceptance.

See `historical external: ../OWNER_RUNTIME_ACCEPTANCE_v0_6_6.md`.
