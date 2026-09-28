# Scientist Capacity + Transformer MoE V1

## Authority

CPMF v0.7.5 R1 profiles the actual dataset snapshot and hardware before Scientist planning. The LLM may choose a family/topology and propose a bounded parameter envelope, but deterministic code compiles and validates the plan.

## Dataset capacity profile

The profile records snapshot rows, feature count, sequence hint, chronological WFA training-row estimates, training-memory scenarios, and a deliberately conservative overlap-adjusted effective-sample heuristic. The heuristic is an engineering prior only; it is never a PASS/FAIL gate and never claims to compute the statistically independent sample size.

For a representative ~35k H1-row / five-year snapshot with sequence 128, the conservative 18-month reference estimates roughly 10.5k training rows and recommends a starting temporal-model band around 0.16M–0.42M parameters. The exact profile is recomputed from the actual snapshot.

## Scientist capacity role

Research Director receives hardware profile, capability registry, dataset-capacity profile, prior research evidence, and legal registry ranges. It may propose:

- family selection;
- pure or compatible hybrid topology;
- training-memory window;
- model-width/depth/sequence envelope;
- Transformer MoE experts, Top-K routing and regularization;
- a capacity rationale and target parameter range.

Generation review may revise the parameter envelope using actual parameter count, effective training rows, fit cost and WFA generalization evidence.

## Deterministic compiler

LLM proposals cannot bypass:

- registry/type compatibility;
- causal/chronological validation;
- leakage rules;
- legal parameter bounds;
- hardware/resource safety;
- experiment budget;
- deterministic acceptance gates;
- locked-forward governance.

## Transformer MoE

`transformer_moe` is a temporal family with shared Transformer blocks and learned router/expert feed-forward modules. The experts are **latent learned experts 0..N-1**. Strategy names such as TREND/RANGE/TRANSITION/SHOCK are descriptive priors/metadata only: they do **not** supervise the router and there is no contract mapping Expert 0=TREND, Expert 1=RANGE, Expert 2=TRANSITION, or Expert 3=SHOCK. `top_k` is learned from router scores.

For ONNX-friendly deterministic graphs, the current implementation materializes all expert outputs and masks/weights non-selected experts. Therefore Top-K routing is logically sparse but must not be described as true sparse-FLOP execution.

Routing-health authority is **per MoE block** because each block owns independent router/expert parameters. A whole-model aggregate may be shown for telemetry, but it is not allowed to mask a collapsed/dead-gradient block. Dispatch/soft-probability diagnostics and deterministic router-gradient probes are bound to the restored best early-stopping checkpoint.

## Evidence

Model size is a starting envelope, not an optimum. Capacity must still prove itself through Full WFA, CPCV, Tournament, Monte Carlo and locked Forward under existing governance.
