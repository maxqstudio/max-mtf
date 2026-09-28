# Research Kernel V2 — CPMF v0.7.2 R1

Status: **canonical scientific architecture for this release**.

## Scope

v0.7.2 R1 is a consolidation release. It intentionally adds **no new model family**. Active research families remain XGBoost, LightGBM, GRU, GRU→XGBoost, and GRU→LightGBM (Random Forest remains optional where already supported). The purpose is to make the existing results scientifically comparable before expanding model capacity.

## Single temporal authority

`TemporalIndexContract` in `ModelLab/core/temporal_index.py` is the chronology authority for research evaluation. It owns original row identity, contiguous chunks, expanding folds, train-side training-memory truncation, purge boundaries, and hybrid inner-OOF folds. Temporal models must never infer adjacency from compressed index arrays.

All active research paths use the same semantics:

`ResearchSpec/Candidate → temporal index authority → fit on legal train indices → causal prediction context → WFA/OOF → CPCV → evidence`.

- **WFA/OOF:** training memory changes only the fit history; it does not change the validation horizon.
- **CPCV:** complement train sets may be discontinuous. GRU/hybrid sequence construction resets at every excluded gap and therefore cannot bridge held-out groups.
- **Hybrid GRU→classical:** inner direction-model OOF is indexed and purged before policy fitting. OOF temporal features are the only training features for the classical policy layer.
- **Policy Discovery:** uses the same train-side memory rule and the same causal pre-validation history convention as normal WFA.
- **Feature/Label Audit + Guided Research:** in Factory full-OOF mode they use the same Discovery research region rather than a second implicit 80/20 authority. Legacy internal locked split remains only as an explicit compatibility mode.

## Effective candidate identity

Candidate fingerprints represent the **effective model**, not inert configuration text. For PyTorch GRU with one recurrent layer, dropout is effectively zero; therefore single-layer GRU/hybrid dropout variants canonicalize to zero and cannot masquerade as novel experiments.

## Evaluation boundary

The sealed **Evaluation Vault** (`evaluation_vault`) is downstream-only. Active Discovery memory may learn only from legal research evidence. Tournament, Monte Carlo, and Forward outcomes are stored in a sealed `evaluation_vault` for auditability and **must not influence future Discovery while those windows remain evaluation authority**. An evaluation window may become research evidence only after it is formally retired and replaced by a new untouched evaluation window.

## Scientist boundary

LLM/Scientist proposals never create scientific authority by themselves. A hypothesis is executable only when a deterministic compiler/wiring exists. `HYBRID_ABLATION` is explicitly backlog in this release instead of being falsely marked executable.

## Deliberately deferred

The following requirements are **not implemented in this consolidation release** because they belong above the cleaned kernel and must not be mixed into scientific repair:

- Supervisor LLM pre-flight research thesis before the initial plan.
- Global persistent START / PAUSE / STOP controls on every top-level page.
- Transformer, TCN, larger neural families, new embedding/fusion modes, or GPU-cloud execution.

These can be added after identical-candidate before/after validation shows that the consolidated evaluator is stable.

## Required regression evidence

`ModelLab/tests/research_kernel_selftest.py` must prove at minimum:

1. temporal sequences reset across CPCV gaps;
2. hybrid inner OOF purges the label-overlap boundary;
3. single-layer no-op dropout variants fingerprint identically;
4. discontiguous hybrid fitting preserves original train chunks;
5. Factory research-region authority is shared;
6. unwired Scientist hypotheses remain backlog;
7. downstream evaluation failure is sealed from Discovery learning memory.


## v0.7.3 workflow note

Research Kernel V2 chronology semantics are unchanged. The orchestration order changed: Discovery generations stop at WFA/OOF; the same temporal-indexed CPCV implementation is invoked only by the separate frozen-finalist CPCV stage after Pool 12.
