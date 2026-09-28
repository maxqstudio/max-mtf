# CPMF v0.6.8 · Learning Research + Persistent Settings

## Fixed

1. New Guided generations no longer restart from a blank research board.
2. OOF-only Research Memory carries elites, failure gates, coverage, memory-window evidence, Guided winner, and Scientist agenda across generations.
3. Round 1 of a learning generation rechecks prior elites under the new contract before spending the remaining budget on exploration.
4. LLM Scientist V2 can formulate scientific hypotheses beyond hyperparameters; deterministic Supervisor remains the only execution authority.
5. Scientist label/feature hypotheses can feed bounded Guided OOF research; selectivity/regime hypotheses can extend bounded OOF Policy Discovery.
6. Settings persist outside version folders under `%LOCALAPPDATA%\ComplexPolicy\ModelLab`.
7. API key persistence uses Windows DPAPI; primary settings have backup recovery.

## Acceptance

New local gates:

- `RESEARCH_MEMORY_LEARNING_SCIENTIST`
- `SETTINGS_PERSISTENCE_DPAPI`

All cumulative local gates PASS. MetaEditor / real MT5 / ONNX runtime remain Owner-machine gates.
