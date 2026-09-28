# MAX MTF — Product Requirements Document

Canonical project: **MAX MTF**  
Canonical version: **v2.0.1**

Document role: define product and scientific requirements. Current source/runtime status belongs in [BASELINE_CURRENT.md](BASELINE_CURRENT.md); implementation ownership belongs in [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Objective

MAX MTF evolves the inherited MAX single-timeframe quantitative research stack into a causal hierarchical multi-timeframe research and trading architecture while preserving deterministic scientific governance.

V1 role ladder:

- TF+2 / H4 — trend, regime, volatility, long structure;
- TF+1 / H1 — setup, pullback, breakout, structure;
- TF / M15 — primary SELL / SKIP / BUY decision;
- TF-1 / M5 — execution context and entry timing.

MTF is hierarchical, not timeframe voting. Additional timeframe complexity must prove incremental information before it may become production authority.

## 2. Non-negotiable authority model

1. Deterministic code owns candidate admission, validation, PASS/FAIL, lifecycle gates and promotion eligibility.
2. LLM Scientist may reason over authorized evidence, select among legal families/topologies and propose bounded experiments.
3. Scientist may never override LEGAL, RESOURCE or SCIENTIFIC ceilings or deterministic gate results.
4. Strategy and Model promotion remain Owner-only.
5. Protected Locked/Fresh/Shadow evidence cannot be used for adaptive tuning.
6. Every material phase requires cumulative acceptance, machine-readable evidence, fail-closed negative tests, source identity and documentation synchronization.
7. A local source PASS cannot substitute for an external runtime gate that requires the real Owner environment.

## 3. Decision contract

Canonical directional model output remains:

`[P(SELL), P(SKIP), P(BUY)]`

with shape `[N,3]`.

Later MTF execution timing may use a distinct ENTER/WAIT/CANCEL contract, but it must not alter the directional label semantics or leak future execution information into directional features.

## 4. Scientific lifecycle

Canonical lifecycle:

```text
Discovery
  -> Pool
  -> CPCV
  -> Tournament
  -> Monte Carlo
  -> Locked / Forward / Fresh
  -> Eligible Challenger
  -> Owner promotion decision
```

Required methodology includes:
- chronological validation;
- purge/embargo;
- nested threshold selection;
- label causality;
- leakage-safe hybrid OOF stacking;
- deterministic evaluator authority;
- exact candidate/data/strategy provenance;
- protected holdout/fresh boundaries;
- no automatic Champion promotion.

DL/hybrid CPCV seed confirmation follows the governed seed contract. Tree models remain deterministic/fixed-seed unless a specific accepted contract says otherwise.

## 5. Dynamic model capacity

```text
effective_capacity = min(LEGAL, RESOURCE, SCIENTIFIC)
```

- **LEGAL** — executable architecture/constructor support.
- **RESOURCE** — safe execution on the available machine/runtime.
- **SCIENTIFIC** — effective information/sample capacity justifies the model size.

Historical positive evidence may shift search preference inside legal bounds; it may not widen a hard ceiling.

Current legal headroom is defined by the executable model registry and model-capacity code, not by prose alone. Current accepted examples include GRU/LSTM/TCN, tree models, Transformer-family models, Transformer MoE and supported temporal-to-tree hybrids.

## 6. MTF data contract

V1 uses M5 as the lowest canonical market-data value authority. M15/H1/H4 are deterministically derived for Python research and must prove parity against broker-native higher-timeframe bars on accepted samples.

For each M15 primary-decision time `t`:

- H4 input = latest fully closed H4 bar with `close_time <= t`;
- H1 input = latest fully closed H1 bar with `close_time <= t`;
- M15 input = M15 bar closing at `t`;
- M5 directional context = only fully closed M5 information with `close_time <= t`;
- M5 after `t` may participate only in future execution-label/evaluation logic.

Missing required intervals, ambiguous broker-symbol resolution, unsupported source kinds, historical closed-bar mutation and causal-boundary violations fail closed.

No market-bar forward fill may silently repair missing authority.

## 7. MTF feature and label requirements

Role-specific features must be explicit and versioned.

Directional and execution labels are separate:
- M15 directional label: SELL / SKIP / BUY;
- optional later M5 execution label: ENTER / WAIT / CANCEL.

Every feature must have:
- timeframe role;
- source columns;
- lookback/dependency horizon;
- causal cutoff;
- schema identity.

Before expensive multi-encoder DL, comparable-budget tree ablations must measure incremental information from H1, H4 and M5 context.

## 8. Temporal dependency / leakage requirements

MTF research must move from ambiguous bar-count assumptions to exact dependency intervals:

- `dependency_start_time`;
- `decision_time`;
- `label_end_time`;
- `execution_end_time`.

No training dependency interval may overlap protected validation/test label or execution intervals.

Temporal encoders may use legal pre-boundary history only. Sequence construction must not bypass purge authority.

## 9. Strategy requirements

The target deterministic MTF strategy structure is:

```text
H4 context gate
  -> H1 setup gate
  -> M15 primary direction
  -> M5 timing gate
  -> existing risk/execution
```

Requirements:
- explicit parameter ownership by role;
- same-window/cost control comparisons;
- exact Strategy Challenger lineage;
- MT5/Python strategy-geometry parity where Python replays the strategy;
- missing required timeframe data fails closed;
- output is Challenger until explicit Owner promotion.

## 10. Model research requirements

Tree ablation comes before complex MTF temporal encoders.

If additional timeframe roles do not show reproducible WFA/CPCV information gain, the project must diagnose or stop rather than automatically escalate model complexity.

Multi-encoder temporal models must:
- keep timeframe sequences role-specific;
- preserve fold cutoff parity;
- record exact per-encoder/fusion/total parameter counts;
- pass resource/scientific capacity checks;
- preserve leakage-safe OOF hybrid stacking;
- prove deployment feasibility before large search budgets.

## 11. Runtime / ONNX / MT5 requirements

MT5 deployment must target a verified terminal data root and use the isolated `Max_MTF` namespace.

Runtime parity must preserve:
- exact feature order;
- normalization;
- input shape/role ordering;
- bar-close trigger semantics;
- model identity;
- output semantics.

Missing/stale timeframe input fails closed. Shadow cannot trade.

If learned M5 timing is introduced, it remains a distinct artifact/contract from the directional model.

## 12. Scientist tooling requirements

Scientist reasoning may use a separate governed Python analysis runtime.

Required boundary:
- separate interpreter/environment from MAX production/training Python;
- authorized analytical inputs only;
- deterministic/replayable analysis provenance;
- no production source/governance/acceptance mutation;
- no unrestricted shell/subprocess authority;
- explicit REASONING_ONLY fallback;
- failed computation may not become invented numerical evidence;
- deterministic Factory remains PASS/FAIL authority.

## 13. Promotion and rollback

Promotion must be:
- Owner-controlled;
- atomic;
- auditable;
- identity-bound;
- reversible to the previous accepted Champion.

Existing Champion artifacts are retained/demoted according to lifecycle policy; they are not silently deleted.

## 14. Definition of done — MTF V1

MTF V1 is complete only when all are accepted:

- causal H4/H1/M15/M5 alignment;
- role-specific feature schema;
- timestamp dependency/purge authority;
- deterministic MTF Strategy Challenger;
- single-TF versus MTF ablation evidence;
- at least one supported MTF model through the full lifecycle;
- ONNX/MT5 runtime parity;
- Shadow evidence;
- explicit Owner promotion;
- rollback;
- cumulative source + required external runtime acceptance.

Until explicit promotion, MTF remains research/challenger architecture rather than production authority.
