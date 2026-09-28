# MAX Research Agent — MTF Research Architecture V1 Roadmap

**Status:** PLANNED / NOT ACTIVE

**Planning base:** MAX Research Agent — ONNX Factory v1.4.5

**Current production authority remains:** single-timeframe Strategy Champion + current Model Research contracts. This roadmap does **not** change current PASS/FAIL, promotion, live trading, or ONNX authority until the relevant implementation phase passes its own cumulative acceptance and the Owner explicitly promotes a Strategy/Model Challenger.

---

## 1. Objective

Evolve MAX from a single-timeframe strategy/model pipeline into a causal, hierarchical multi-timeframe architecture where each timeframe has a distinct responsibility:

| Role | V1 example | Responsibility |
|---|---|---|
| `TF+2` | H4 | Trend / regime / volatility / long structure |
| `TF+1` | H1 | Setup / pullback / breakout / structure |
| `TF` | M15 | Primary BUY / SKIP / SELL decision |
| `TF-1` | M5 | Entry timing / execution quality |

Canonical decision flow:

`H4 context -> H1 setup -> M15 primary decision -> M5 entry timing -> risk execution`

The model research pipeline must eventually train on evidence from all four roles, but MAX must prove the incremental value of each role through ablation before additional complexity is allowed to become production authority.

---

## 2. Non-negotiable contracts

1. **No four-timeframe voting.** MTF is hierarchical, not majority voting.
2. **Primary direction remains `[P(SELL), P(SKIP), P(BUY)]`.** Existing final decision contract is preserved.
3. **M5 does not redefine direction after M15.** M5 may time or cancel an entry; it does not independently flip BUY to SELL.
4. **Closed-bar-only causal evidence.** At decision time `t`, no feature may use a bar that closes after `t`.
5. **No future M5 leakage.** M5 bars after the M15 decision timestamp are not directional features for that M15 decision.
6. **Current single-TF system remains the control.** MTF must beat or materially complement a contemporaneous single-TF control under the same scientific budget.
7. **No gate relaxation.** MTF is judged by the existing deterministic lifecycle: WFA -> CPCV -> Tournament -> Monte Carlo -> Fresh -> Challenger -> Owner Promotion.
8. **Manual promotion only.** MTF cannot auto-replace the current Strategy Champion or Model Champion.
9. **Fresh/Locked/Shadow remain protected.** No adaptive learning from protected stages.
10. **Every phase requires one-click acceptance, cumulative E2E, at least one negative/fail-closed case, machine-readable evidence, first failed gate, and docs sync.**

---

## 3. V1 scope decision

### Initial supported ladder

V1 implementation is scoped to one validated ladder:

`H4 / H1 / M15 / M5`

Roles are stored generically as `TF+2 / TF+1 / TF / TF-1`, but production support for additional ladders is deferred until this ladder proves value. This avoids multiplying data-alignment, label-horizon, purge, and EA-runtime combinations before the core contract is validated.

### Deferred from V1

- arbitrary timeframe graph search;
- more than four active timeframe roles;
- RL for timeframe allocation;
- RAG/embedder for research evidence;
- adaptive live timeframe switching;
- automatic Strategy or Model Champion replacement.

---

# 4. Phase roadmap

## Phase MTF-0 — Contract Freeze / Control Baseline

### Goal

Freeze the exact scientific question before changing data or strategy code.

### Deliverables

- `MTF_TIMEFRAME_ROLE_V1` contract with roles `TF+2`, `TF+1`, `TF`, `TF-1`.
- Initial ladder fixed to H4/H1/M15/M5.
- Current single-TF Strategy Champion captured as immutable control evidence.
- Current single-TF Model Research configuration captured as immutable control evidence.
- Explicit definition of decision timestamp, bar-close semantics, entry window, label horizon, and execution horizon.
- MTF feature/strategy/model code remains OFF behind fail-closed feature flags.

### Acceptance

- Current v1.4.5 behavior is byte-for-byte/scientifically unchanged with MTF disabled.
- Invalid or unsupported ladder fails closed.
- No current Champion artifact changes.

### Exit condition

Proceed only when the Owner accepts the MTF role contract and control baseline evidence is sealed.

---

## Phase MTF-1 — Canonical MTF Data Foundation

### Goal

Create one causal, auditable time axis for H4/H1/M15/M5.

### Data authority

Use **M5 as the lowest canonical market-data authority** for the V1 ladder. Derive M15/H1/H4 deterministically for Python research. At runtime, MT5 may read native timeframe bars, but parity must prove they match the deterministic aggregation for the same broker/feed/window.

### Required contracts

- first-write-wins source identity preserved;
- same broker/symbol/feed authority;
- UTC/broker-time conversion explicit;
- deterministic OHLCV resampling;
- bar boundaries explicit;
- missing-bar detection per role;
- no forward filling of market bars;
- each derived bar records source interval and close timestamp;
- exact dataset lineage hashes include all four timeframe views.

### Alignment rule

For each M15 primary-decision timestamp `t`:

- H4 input = latest **fully closed** H4 bar with `close_time <= t`;
- H1 input = latest **fully closed** H1 bar with `close_time <= t`;
- M15 input = the M15 bar closing at `t`;
- M5 directional context = latest fully closed M5 history with `close_time <= t`.

M5 bars after `t` belong only to future execution-label/evaluation logic and must never enter directional features at `t`.

### Acceptance

- Python resampling parity against MT5 native H4/H1/M15 on a fixed broker sample.
- Causal as-of join test at boundary timestamps.
- Missing/interrupted M5 interval fails closed.
- DST/session/timezone edge tests where relevant to the broker feed.
- Deliberate future-M5 injection must be detected by adversarial leakage CI.

### Exit condition

Zero timestamp/alignment ambiguity across the sealed test windows.

---

## Phase MTF-2 — Role-Specific Feature and Label Contract

### Goal

Prevent the naive `4 x CP32 = 128 duplicated features` design from becoming architecture by default.

### Feature roles

**H4 — Context / regime**
- trend state and slope;
- volatility regime / ATR percentile;
- long-range structure;
- regime persistence;
- broad relative context.

**H1 — Setup**
- pullback depth;
- breakout distance/quality;
- swing/structure state;
- setup momentum;
- range position;
- setup quality.

**M15 — Primary decision**
- retain the strongest current CP32-compatible decision features;
- local momentum/structure;
- directional probabilities/policy features where applicable;
- exact `[SELL, SKIP, BUY]` target authority remains here.

**M5 — Execution context**
- short momentum;
- micro pullback;
- spread/cost state;
- local ATR/shock;
- wick/body/microstructure proxies available from OHLC;
- distance-to-entry / timing quality.

### Label separation

Two distinct labels are allowed:

1. **Directional label** at M15 decision time -> `SELL / SKIP / BUY`.
2. **Execution label** after a directional intent exists -> `ENTER / WAIT / CANCEL`.

The execution label must not be back-propagated as future information into directional feature construction.

### Acceptance

- every feature has role, timeframe, lookback horizon, source columns, and causal cutoff metadata;
- duplicate/correlated feature audit by role;
- permutation/ablation evidence per role;
- deliberate future-bar feature fails leakage CI;
- feature schema versioned and hashed.

### Exit condition

A compact MTF feature schema is frozen. No model implementation may invent additional unregistered timeframe features.

---

## Phase MTF-3 — Time-Based Dependency / Purge Authority

### Goal

Replace bar-count assumptions that become ambiguous in MTF research with absolute-time dependency authority.

### New dependency contract

For each sample, compute:

`dependency_start_time`

`decision_time`

`label_end_time`

`execution_end_time`

The purge/embargo safety horizon is derived from actual timestamp overlap, conceptually:

`purge_duration = max(feature_dependency_horizon, label_horizon, execution_horizon)`

but the implementation must operate on exact sample intervals rather than a single guessed bar count.

### WFA/CPCV requirements

- fold boundaries are defined on primary M15 decision timestamps;
- no train sample dependency interval may overlap a validation/test label or execution interval;
- temporal encoders may use only pre-boundary history that is legal for that validation sample;
- CPCV purge remains deterministic and auditable for all 15 N=6,k=2 splits.

### Acceptance

- adversarial overlap tests across H4 lookback + M5 execution horizon;
- old single-TF behavior remains unchanged when MTF is OFF;
- MTF fold evidence records purged sample IDs and exact timestamp reason;
- no sample can silently cross a protected boundary.

### Exit condition

MTF leakage CI passes before Strategy or Model research may use MTF data.

---

## Phase MTF-4 — Deterministic MTF EA Strategy Challenger

### Goal

Prove the strategy geometry before asking ML/DL to exploit it.

### Strategy structure

`H4 context gate -> H1 setup gate -> M15 primary signal -> M5 timing gate -> existing risk/execution`

### Parameter ownership

Parameter groups must be explicit:

- H4 regime/trend/volatility parameters;
- H1 setup/structure parameters;
- M15 decision parameters;
- M5 entry-timing parameters;
- existing SL/TP/MaxHold/risk authority.

No parameter may have ambiguous ownership across multiple roles.

### Strategy Optimizer

The existing Strategy Optimizer remains upstream. Add MTF parameters only after Phase MTF-1..3 acceptance.

Research baseline remains separate:

- Strategy Optimizer H1-equivalent sample authority remains its own profile;
- Model Research sample authority remains separate;
- no shared mutable KPI store is introduced.

### Promotion contract

MTF result terminates as **Strategy Challenger**. Current Strategy Champion remains unchanged until explicit Owner promotion.

### Acceptance

- one-click MTF Strategy acceptance;
- single-TF control and MTF Challenger backtest on identical windows/costs;
- exact parameter-vector lineage;
- MT5/Python strategy-geometry parity where Python replays strategy authority;
- negative test: missing any required timeframe blocks trade/research fail-closed;
- no auto-promotion.

### Exit condition

An MTF Strategy Challenger exists with clean evidence. It does not need to beat Champion yet to permit baseline model research, but it must be executable, causal, and internally consistent.

---

## Phase MTF-5 — MTF Tree Baseline / Ablation First

### Goal

Test whether the extra timeframe information adds signal before building expensive multi-encoder DL.

### Mandatory ablation matrix

Using the same primary M15 decisions and comparable search budget:

- **A:** M15 only — control;
- **B:** H1 + M15;
- **C:** H4 + H1 + M15;
- **D:** H4 + H1 + M15 + M5 directional context.

Tree families first:

- LightGBM;
- XGBoost;
- RandomForest where computationally justified.

### Scientific comparison

Do not choose a winner from in-sample score. Compare:

- Full WFA gate survival;
- CPCV stability;
- failure topology;
- Exp R/PF/RF/DD distributions;
- coverage/trade sample;
- regime concentration;
- stress degradation;
- feature/role importance stability.

### Stop rule

If B/C/D provide no reproducible WFA/CPCV information gain over A and the role ablation shows no stable incremental value, **do not proceed automatically to multi-encoder DL**. Diagnose data/feature roles first.

### Exit condition

At least one MTF configuration shows defensible incremental information under deterministic validation, or the project records a justified MTF-no-gain result and pauses complexity expansion.

---

## Phase MTF-6 — Multi-Encoder Temporal Models

### Goal

Allow temporal families to learn timeframe-specific dynamics without mixing unequal intervals into one fake sequence.

### Architecture

Each timeframe has its own encoder or explicitly role-aware input path:

`H4 encoder --\`

`H1 encoder ----> fusion -> [P(SELL), P(SKIP), P(BUY)]`

`M15 encoder ---/`

`M5 context ---/`

Start with the simplest temporal family that can validate the contract (GRU/LSTM) before broader Transformer-family expansion.

### Parameter-count authority

Model Size Advisor must be extended to report:

- parameter count per encoder;
- fusion/policy parameter count;
- total trainable parameter count;
- dataset-capacity envelope using effective MTF training samples;
- hard compute ceiling.

### Hybrid compatibility

MTF temporal -> tree policy hybrids remain allowed, but OOF temporal meta-features are mandatory and in-sample stacking remains forbidden.

### Acceptance

- each encoder receives only its declared timeframe sequence;
- sequence cutoff parity at folds;
- exact trainable-parameter count;
- CPU/GPU resource preflight;
- OOF hybrid stacking tests;
- ONNX-exportability feasibility test before large search budget is consumed.

### Exit condition

Temporal MTF candidates can complete Full WFA without violating capacity, chronology, or OOF contracts.

---

## Phase MTF-7 — Dedicated M5 Entry-Timing Layer

### Goal

Separate directional quality from execution quality if evidence supports it.

### Runtime state machine

At each M15 close:

- Direction model outputs SELL/SKIP/BUY.
- SKIP terminates immediately.
- BUY/SELL opens a bounded M5 execution window.
- Each new closed M5 bar produces `ENTER / WAIT / CANCEL` or deterministic timing logic.
- Expiry/cancel closes the intent without a trade.

Direction cannot reverse inside the M5 timing window. A reverse direction requires a new legal M15 decision event.

### Ablation

Compare:

- D1: M5 used as directional input only;
- D2: M5 removed from direction, deterministic execution timing;
- D3: M5 removed from direction, learned ENTER/WAIT/CANCEL timing;
- D4: no M5 timing — immediate M15-close execution control.

### Acceptance

- no duplicate entry from repeated M5 bars;
- max timing window explicit;
- deterministic state restoration after restart;
- entry delay/cost stress;
- no direction flip by timing layer;
- execution label has no causal path into directional training features.

### Exit condition

Use the simplest execution layer that produces robust incremental benefit. A learned M5 model is not mandatory if deterministic timing performs as well or better.

---

## Phase MTF-8 — MTF WFA / CPCV / Tournament / MC / Fresh Integration

### Goal

Run MTF candidates through the exact MAX scientific lifecycle rather than a parallel shortcut.

### Lifecycle

`MTF Discovery -> Full WFA -> Pool 12 -> CPCV -> Tournament -> Monte Carlo -> Fresh -> Eligible Challenger`

Existing KPI authority remains Owner-configurable and deterministic. No MTF-specific relaxation is introduced merely because the architecture is more complex.

### Additional evidence, not substitute gates

- per-role ablation lineage;
- timeframe availability/coverage;
- alignment-loss count;
- effective MTF sample count;
- dependency/purge statistics;
- M5 timing conversion: intents -> entered / waited / cancelled;
- latency/cost sensitivity.

### Acceptance

- protected stages excluded from adaptive learning;
- exact candidate/feature/timeframe hashes sealed at Pool;
- CPCV uses exact MTF dependency intervals;
- MC includes cost/delay stress relevant to M5 execution;
- Fresh remains untouched during candidate selection.

### Exit condition

At least one MTF candidate may become an Eligible Model Challenger only after the same deterministic gates required of the existing architecture.

---

## Phase MTF-9 — ONNX / MT5 Runtime Contract

### Goal

Deploy MTF inference without silently changing model meaning.

### Direction model

Output remains:

`[P(SELL), P(SKIP), P(BUY)]`

### Input contract

The implementation must choose and freeze one of:

- explicit multi-input tensors per timeframe, or
- a packed role-aware tensor/vector with immutable ordering metadata.

The choice must be made by executable ONNX/MT5 parity prototype, not convenience alone.

### Execution layer

If learned M5 timing is enabled, it is a separate artifact/contract with output:

`[P(ENTER), P(WAIT), P(CANCEL)]`

or an equivalent deterministic three-state decision contract.

### Acceptance

- Python -> ONNX parity;
- ONNX Runtime -> MT5 ONNX parity;
- exact input shapes and role order;
- exact feature normalization parity;
- bar-close trigger parity;
- restart/state recovery;
- Shadow mode cannot trade;
- missing/stale timeframe input fails closed.

### Exit condition

MTF Model Challenger can run in Shadow with auditable prediction and execution-timing logs.

---

## Phase MTF-10 — Shadow / Promotion / Production Migration

### Goal

Replace the single-TF production authority only when evidence justifies it.

### Shadow evidence

Log at minimum:

- H4 regime state;
- H1 setup state;
- M15 directional probabilities;
- M5 timing state;
- intended and actual entry time;
- spread/cost at intent and entry;
- strategy/model identity hashes;
- whether the current Champion would have acted on the same primary decision clock.

### Promotion

- Strategy Champion promotion remains Owner-only.
- Model Champion promotion remains Owner-only.
- Existing Champion is retained/demoted to Challenger; never deleted.
- Promotion requires runtime parity, artifact integrity, upstream scientific gates, and Shadow evidence required by current policy.

### Rollback

Production must retain a one-action rollback path to the previous single-TF Champion artifacts/settings.

### Exit condition

MTF becomes production authority only after explicit Owner promotion. Until then, single-TF remains production authority.

---

# 5. Recommended implementation order

Do **not** build all phases in parallel.

Recommended dependency order:

`MTF-0 -> MTF-1 -> MTF-2 -> MTF-3 -> MTF-4 -> MTF-5`

Only after tree-level information gain is understood:

`MTF-6 -> MTF-7 -> MTF-8 -> MTF-9 -> MTF-10`

This order intentionally delays the most expensive DL/ONNX work until data alignment, causal purge, strategy geometry, and MTF information gain are already proven.

---

# 6. Mandatory experiment matrix

Before MTF can be called superior or promoted, compare at least:

| ID | Context | Setup | Decision | Timing | Purpose |
|---|---|---|---|---|---|
| A | — | — | M15 | immediate/control | single-TF control |
| B | — | H1 | M15 | immediate | setup contribution |
| C | H4 | H1 | M15 | immediate | higher-TF context contribution |
| D | H4 | H1 | M15 + M5 context | immediate | M5 directional-context contribution |
| E | H4 | H1 | M15 | deterministic M5 | execution-only contribution |
| F | H4 | H1 | M15 | learned M5 | learned timing contribution |

Ablations must use comparable research budgets and the same immutable market window. More features/model parameters may not receive a larger validation advantage simply because they are more complex.

---

# 7. Evidence and lineage additions

Every MTF candidate must persist:

- timeframe-role mapping;
- per-role data hashes;
- primary decision clock;
- feature schema version/hash;
- per-role lookback horizons;
- effective dependency interval;
- exact purge/embargo evidence;
- candidate setup;
- per-encoder parameter counts where applicable;
- total parameter count;
- M5 timing-window contract;
- ablation/control identity;
- Strategy Champion authority used for execution geometry;
- WFA/CPCV/Tournament/MC/Fresh evidence as already required.

No MTF candidate is scientifically comparable if these identities are missing.

---

# 8. UI roadmap

### Data

Show MTF data readiness as one compact grouped section:

- H4 / H1 / M15 / M5 coverage;
- latest closed bar per role;
- alignment status;
- missing interval count;
- exact primary decision timeframe.

### Advanced -> Research

Expose:

- MTF enabled/disabled;
- validated ladder selector (V1 only H4/H1/M15/M5);
- role-specific feature groups;
- M5 execution mode: off / deterministic / learned;
- MTF ablation mode.

### Model Detail Inspector

Extend existing inspector with:

- timeframe roles consumed;
- per-role sequence/lookback;
- per-role parameter count;
- fusion parameter count;
- total trainable parameters;
- MTF feature schema hash;
- ablation identity.

### Strategy Optimizer

Group parameters by H4/H1/M15/M5 role. Do not create separate Optimizer pages per timeframe.

---

# 9. One-click acceptance plan

Each implementation phase must add exactly one cumulative regression gate family and a one-click launcher. Required machine-readable evidence:

```text
phase
status
first_failed_gate
source_tree_signature
suite_signature
control_baseline_hash
mtf_contract_hash
negative_test_status
external_runtime_gates
```

Required negative/fail-closed tests across the roadmap include:

- future M5 leakage;
- incomplete H4/H1 bar at M15 decision;
- missing M5 interval;
- unsupported ladder;
- train/validation dependency overlap;
- mismatched role feature order;
- wrong ONNX input shape;
- M5 timing direction flip attempt;
- stale timeframe at live inference;
- automatic promotion attempt.

No phase is complete when only the happy path passes.

---

# 10. Scientific stop / rollback rules

1. If MTF alignment or purge cannot be proven causal, stop before model research.
2. If deterministic MTF strategy cannot achieve execution parity, stop before MTF model training.
3. If tree ablations show no stable incremental MTF information, do not automatically escalate to larger DL models.
4. If M5 timing adds turnover/cost without robust OOS benefit, remove M5 from learned timing and retain the simpler execution authority.
5. If multi-encoder capacity exceeds dataset-effective sample guidance, reduce model size rather than relaxing validation.
6. If MTF Challenger fails Fresh/Shadow, preserve current Champion; never tune against protected evidence.
7. Every production migration must be reversible to the immediately previous Champion.

---

# 11. Definition of done

MTF Research Architecture V1 is complete only when all are true:

- H4/H1/M15/M5 data alignment is causally accepted;
- role-specific feature schema is frozen;
- timestamp dependency/purge authority is accepted;
- deterministic MTF Strategy Challenger can run and be optimized;
- single-TF vs MTF ablation evidence exists;
- at least one supported MTF model family completes the full scientific lifecycle;
- ONNX/MT5 runtime parity passes;
- Shadow evidence exists;
- Owner explicitly promotes the selected Strategy/Model Challenger;
- rollback remains available;
- cumulative source + external runtime acceptance is complete for the promoted release.

Until then, **MTF is research/challenger architecture, not production authority**.
