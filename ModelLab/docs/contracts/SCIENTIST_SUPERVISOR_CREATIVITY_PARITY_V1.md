# CPMF v0.7.5 R5 — Scientist/Supervisor Creativity Parity

## Authority

Creativity controls **what to test next**, never whether evidence passes. The following remain deterministic and immutable: KPI gates, temporal chronology/leakage contracts, Owner Single↔Hybrid topology priority, hard capacity ceiling, fixed CPCV seed set, locked/fresh Forward, execution/risk gates and PASS/FAIL.

## Adaptive Creativity Governor

Owner config `agent.search.scientific_creativity` is a bounded `0..1` research-breadth preference. It feeds `CP_ADAPTIVE_CREATIVITY_GOVERNOR_V1`, which combines that preference with committed evidence:

- near-miss Full-WFA evidence → `LOCAL_REFINEMENT`;
- repeated/dominant failure topology → `STRUCTURAL_ESCAPE`;
- multi-round stagnation → `BROADEN_SEARCH`;
- CPCV seed instability → `STABILITY_REPAIR`;
- otherwise → `BALANCED`.

The governor emits target exploration, local-refinement share, architecture/family breadth, ablation breadth, backlog-idea share and mutation-scale multiplier. It does not emit gate thresholds or authorization changes.

## Phase-aware LLM use

Raw `Scientist temperature` is no longer the Owner creativity control. Temperatures are phase-aware: connection/forensic/policy interpretation stay conservative while hypothesis generation gets bounded headroom from scientific creativity. The legacy config temperature remains fallback compatibility only.

`agent.search.llm_research_influence` consistently blends Scientist family priorities and exploration proposals toward or away from deterministic-neutral authority. `0` means LLM research preference has no weighting effect; `1` admits the bounded Scientist preference in full.

## Scientist context parity

Factory Director and round Scientist receive the same classes of research context before proposing experiments:

- deterministic hardware profile and available backends;
- dataset capacity/effective training rows;
- effective per-family parameter bounds and hard capacity authority;
- current Owner Single↔Hybrid topology allocation;
- estimated/actual compute allocation;
- CPCV fixed-seed policy and committed seed-confirmation evidence;
- research memory/failure topology and current model registry.

Deterministic compilation remains mandatory after any LLM proposal.

## Executable HYBRID_ABLATION

`HYBRID_ABLATION` is no longer a backlog-only idea. The Experiment Block compiler creates matched temporal standalone and temporal→policy hybrid arms when Owner topology authority permits both. The planner holds the temporal architecture as consistently as possible and evaluates both arms under the same final `[P(SELL),P(SKIP),P(BUY)]` authority.

Full-WFA proxy support requires the hybrid arm to achieve a strictly higher hard-gate survival rate than its standalone control. A passing candidate in either arm alone cannot mark the hybrid hypothesis supported. Downstream-origin hypotheses still require their originating downstream authority before decisive closure.

## CPCV seed-stability learning

R4 fixed seed confirmation `42 → 11 → 77` remains unchanged. R5 propagates planned seeds, completed seeds, per-seed PASS/FAIL and failed-seed counts into Scientist-visible CPCV failure topology. A seed-instability failure deterministically compiles an executable `SEED_STABILITY` hypothesis constrained to stability-oriented treatments such as smaller capacity, stronger regularization, lower learning rate/dropout changes or reduced router complexity. The Scientist cannot select a new favorable seed set.

## Supervisor scientific loop

`Evidence → Failure Topology → Creativity Governor → Scientist Hypothesis → Deterministic Experiment Block → Candidate Admission/Capacity Compiler → Full-WFA → CPCV/Downstream → Research Memory`

The Supervisor may broaden or narrow search according to evidence, but it cannot weaken qualification authority.


## R6 per-family model-size priority
Every base model family has a frozen Owner `Small 0.00 ↔ 1.00 Large` search preference. Scientist/Supervisor may use it to choose where to explore, but actual temporal candidates remain subject to the shared dynamic `min(LEGAL, RESOURCE, SCIENTIFIC)` capacity admission and actual executable parameter count.
