# LLM Scientist V2 · Scientific Agenda

The LLM Scientist is not restricted to hyperparameter mutation.

It may propose two different outputs:

1. **Concrete candidate proposals** inside deterministic model-registry bounds.
2. **Scientific hypotheses** that change the research question.

Supported hypothesis classes:

- `LABEL_GEOMETRY` — horizon / SL ATR / TP ATR / label edge geometry;
- `FEATURE_ABLATION` — CP32 zero-mask ablations without changing runtime feature order;
- `TRAINING_MEMORY` — recent-history memory hypotheses;
- `SELECTIVITY_POLICY` — OOF TAKE/SKIP threshold hypotheses;
- `REGIME_POLICY` — OOF regime/abstention hypotheses;
- `MODEL_ARCHITECTURE` — family emphasis within supported engines;
- `HYBRID_ABLATION` — compare temporal/classical combinations;
- `OBJECTIVE_RESEARCH` — scientifically valid ideas not yet executable by the current engine.

Unsupported ideas are retained as explicit backlog, never silently discarded or auto-executed.

## Authority boundary

The Scientist never receives locked/fresh holdout evidence and cannot:

- change acceptance gates;
- reopen a retired locked holdout;
- promote a Champion;
- set live capital/risk;
- bypass deterministic validation.

Executable hypotheses are translated by deterministic code and evaluated OOF-only at the legal stage.
