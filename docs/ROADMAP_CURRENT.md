# MAX MTF — Canonical Roadmap

Canonical version: **MAX MTF v2.0.1**

Document role: define phase order, dependencies, acceptance intent and stop rules. For current proof/status use [BASELINE_CURRENT.md](BASELINE_CURRENT.md) and [CURRENT_STATE.md](CURRENT_STATE.md).

## Current phase boundary

```text
MTF-0 : established
MTF-1 : source/data implementation accepted; external closure pending
MTF-2 : BLOCKED
MTF-3+: planned / dependency-blocked
```

The roadmap does not itself prove runtime PASS.

## MTF-0 — Contract freeze / control baseline

**Goal:** freeze the scientific question and preserve the single-timeframe control before MTF changes.

Deliverables:
- TF+2 / TF+1 / TF / TF-1 role contract;
- H4/H1/M15/M5 V1 ladder;
- immutable single-TF strategy/model control;
- explicit decision timestamp, bar-close, label and execution horizons;
- MTF disabled/fail-closed until accepted.

Status: **established**.

## MTF-1 — Canonical MTF data foundation

**Goal:** create one causal, auditable H4/H1/M15/M5 time axis.

Authority:
- M5 lowest canonical value authority;
- deterministic M15/H1/H4 derivation;
- native MT5 parity on broker samples;
- closed-bar-only as-of alignment;
- no future-M5 directional leakage;
- exact lineage hashes;
- missing interval/historical mutation/source-kind violations fail closed.

Status:
- source implementation/hardening accepted;
- local cumulative acceptance exists;
- final Owner MT5 + MetaEditor closure remains required.

Exit: MTF-1 may become CLOSED/FROZEN only after accepted final closure evidence and parent seal.

## MTF-2 — Role-specific feature and label contract

**Goal:** build compact role-specific features instead of naive four-timeframe duplication.

Roles:
- H4 — context/regime/trend/volatility;
- H1 — setup/pullback/breakout/structure;
- M15 — primary SELL/SKIP/BUY decision;
- M5 — execution context/timing.

Constraints:
- hierarchical authority, not voting;
- M15 owns direction;
- M5 cannot flip direction or resurrect M15 SKIP;
- directional and execution labels remain separate;
- every feature has registered causal metadata.

Status: **BLOCKED until MTF-1 closure**.

## MTF-3 — Time-based dependency / purge authority

**Goal:** replace ambiguous bar-count assumptions with exact sample dependency intervals.

Per sample:
- `dependency_start_time`;
- `decision_time`;
- `label_end_time`;
- `execution_end_time`.

WFA/CPCV must prove that train dependencies do not overlap protected validation/test label or execution intervals.

Exit: MTF leakage CI passes before Strategy or Model research uses MTF features.

## MTF-4 — Deterministic MTF EA Strategy Challenger

Architecture:

```text
H4 context gate -> H1 setup gate -> M15 primary signal -> M5 timing gate -> risk/execution
```

Requirements:
- explicit parameter ownership by role;
- single-TF control and MTF Challenger on comparable windows/costs;
- exact parameter-vector lineage;
- MT5/Python geometry parity;
- missing required timeframe blocks execution/research;
- no automatic promotion.

Output: Strategy Challenger only.

## MTF-5 — Tree baseline / ablation first

Comparable-budget matrix:

- A — M15 only;
- B — H1 + M15;
- C — H4 + H1 + M15;
- D — H4 + H1 + M15 + M5 directional context.

Tree families first where scientifically justified: LightGBM, XGBoost, RandomForest.

Stop rule: no reproducible incremental MTF information => diagnose/stop; do not automatically escalate to larger DL.

## MTF-6 — Multi-encoder temporal models

**Goal:** learn timeframe-specific temporal dynamics without pretending unequal intervals form one homogeneous sequence.

Requirements:
- role-specific encoder/input path;
- legal fold cutoffs;
- per-encoder/fusion/total parameter counts;
- resource/scientific capacity enforcement;
- leakage-safe OOF hybrid stacking;
- ONNX feasibility before large search budgets.

Start with the simplest viable temporal family before broader Transformer-family expansion.

## MTF-7 — Dedicated M5 entry-timing layer

At each legal M15 directional decision:
- SKIP terminates;
- BUY/SELL may open a bounded M5 timing window;
- legal M5 closes may emit ENTER / WAIT / CANCEL;
- expiry/cancel closes the intent.

Constraints:
- no direction flip inside timing window;
- deterministic restart recovery;
- no future execution-label path into directional features.

Use the simplest timing mechanism that demonstrates robust incremental benefit.

## MTF-8 — Full scientific lifecycle integration

Lifecycle:

```text
MTF Discovery
 -> Full WFA
 -> Pool
 -> CPCV
 -> Tournament
 -> Monte Carlo
 -> Fresh
 -> Eligible Challenger
```

No MTF-specific gate relaxation.

Additional evidence includes role ablations, timeframe coverage, alignment loss, effective sample count, dependency/purge statistics, timing conversion and cost/latency sensitivity.

## MTF-9 — ONNX / MT5 runtime contract

Direction output remains `[P(SELL), P(SKIP), P(BUY)]`.

Freeze one executable input contract based on actual parity evidence:
- explicit multi-input tensors per timeframe; or
- packed role-aware tensor/vector with immutable ordering.

Acceptance includes Python->ONNX parity, ONNX Runtime->MT5 parity, normalization/order parity, bar-close parity, restart recovery, Shadow no-trade and stale/missing input fail-closed behavior.

## MTF-10 — Shadow / promotion / production migration

Shadow evidence binds:
- H4 regime/context;
- H1 setup;
- M15 probabilities;
- M5 timing;
- intended/actual entry;
- costs/spread;
- strategy/model hashes;
- contemporaneous control behavior.

Promotion remains Owner-only, atomic, auditable and reversible.

## Mandatory implementation order

```text
MTF-0 -> MTF-1 -> MTF-2 -> MTF-3 -> MTF-4 -> MTF-5
```

Only after tree-level incremental information is understood:

```text
MTF-6 -> MTF-7 -> MTF-8 -> MTF-9 -> MTF-10
```

## Scientific stop rules

1. Stop before model research if causal alignment/purge cannot be proved.
2. Stop before MTF model training if deterministic MTF strategy cannot achieve execution parity.
3. Do not escalate to larger DL when tree ablations show no stable incremental MTF information.
4. Remove learned M5 timing if it adds cost/turnover without robust OOS benefit.
5. Reduce model capacity rather than relax validation when sample capacity is insufficient.
6. Failed Fresh/Shadow does not mutate the accepted Champion.
7. Every production migration retains rollback.
