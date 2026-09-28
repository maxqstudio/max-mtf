# Hardware-Adaptive Model Research V1 — CPMF v0.7.4 R1

## Authority

New Factory cycles are **model-agnostic and hardware-adaptive**. R6 fixed family toggles remain only for exact legacy resume compatibility.

```text
Hardware Profiler
    -> Model Capability Registry
    -> Dataset / Research Memory / Compute Budget
    -> LLM Research Director
    -> declarative Research Plan
    -> deterministic compiler
    -> Discovery / Full-WFA / Pool / CPCV / Tournament / Monte Carlo / Locked Forward
```

The LLM may choose model families, compatible temporal-to-policy hybrids, research allocation and parameter envelopes. It cannot override chronology/leakage rules, deterministic PASS/FAIL, locked-forward isolation, resource safety, evidence lineage or experiment budgets.

## Registry

Base ML policy families include LightGBM and XGBoost, with Random Forest retained. Temporal DL families include GRU, LSTM, TCN, vanilla causal Transformer Encoder, PatchTST, iTransformer, observed-covariate TFT, and Transformer MoE. The registry is extensible; new families are added through the capability/search contract rather than UI hardcoding.

Compatible hybrids are generated from roles using `hybrid::<temporal>::<policy>`, e.g. `hybrid::tcn::lightgbm` or `hybrid::transformer::xgboost`. Legacy `hybrid_gru_*` aliases remain accepted for old evidence.

## Hardware preflight

Each new Factory captures CPU, core/thread count, RAM, disk, NVIDIA/VRAM and PyTorch CUDA availability before Generation 1. The deterministic capability catalog is passed to the Research Director. The LLM does not invent hardware facts.

Parameter registry bounds are broad legal envelopes. Hardware-aware envelopes are recommendations. Compute budgets (RAM, VRAM and experiment time) are deterministic safety authorities.

## LLM quota / provenance

The ordered LLM stack keeps per-model health. Quota/rate-limit, timeout, model-unavailable and provider-5xx may fall back. Authentication/configuration/validation errors fail closed. A model in active quota cooldown is skipped until the cooldown expires.

Each successful Scientist report persists selected provider/model, route, attempts, input/output/total token usage and optional configured cost estimate. Historical entries without provenance are explicitly shown as `Actual model unavailable`; configured primary is not presented as the model that actually answered.


## R2 Owner family universe

`AUTO` exposes all registered families subject to deterministic hardware feasibility. `MANUAL` uses `research_architecture.allowed_families` as the hard base-family universe. Dynamic hybrids may only use permitted components. Compute presentation is registry-driven; temporal torch families inherit the verified temporal accelerator, while XGBoost/LightGBM retain independent backend probes.


## R10 Owner topology allocation

`research_architecture.hybrid_priority` is independent of family selection. AUTO/MANUAL determines the legal base-family universe; the 0..1 topology slider determines SINGLE versus HYBRID candidate-count allocation inside that universe. A compiled Factory persists the value in `historical external: research_plan.json`. Scientist may select families/compositions but cannot override this Owner allocation. Compute-time share is measured/reported separately.


## R6 per-family model-size priority
Every base model family has an Owner `Small 0.00 ↔ 1.00 Large` search preference. It is frozen at Factory start and propagated to Scientist/Supervisor context, but it does not hard-slice executable bounds. Temporal candidates are admitted by actual executable parameter count under `min(LEGAL, RESOURCE, SCIENTIFIC)` dynamic capacity; Large may reach the upper justified region while never overriding those hard ceilings.
