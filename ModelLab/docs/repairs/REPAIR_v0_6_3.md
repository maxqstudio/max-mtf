# v0.6.3 · Feature/Label Audit + Guided Research Routing Repair

## Defects repaired

1. `FEATURE_LABEL_AUDIT` existed only as a text next-step and had no executable stage.
2. Guided Research navigation could fall back into Label/Advanced UI instead of opening its own workflow page.
3. Streamlit tab routing had no reliable programmatic page authority.
4. MQL5 `PERIOD_H1` value `16385` rendered as `P16385`.
5. A new research generation after postmortem diagnosis could accidentally treat the historical locked period as a new holdout.

## Repair

- Added `ModelLab/host/workflow_router.py` as single route authority.
- Replaced top-level `st.tabs` workflow with stateful route navigation.
- Added `ModelLab/data/feature_label_audit.py` and executable `RUN FEATURE + LABEL AUDIT`.
- Added `ModelLab/research/guided_research.py` and dedicated `Guided Research` page.
- Added bounded OOF Guided Research and `START NEW GENERATION RESEARCH`.
- Added `agent.skip_locked_test` fail-closed route for post-audit generations.
- Added MT5 enum timeframe decoding including H1/H2/H3/H4/H6/H8/H12/D1/W1/MN1.
- Added cumulative acceptance and Guided-flow smoke tests.

## Acceptance

`ModelLab/RUN_ACCEPTANCE.cmd` runs:

1. cumulative `ModelLab/tests/acceptance_selftest.py`;
2. `ModelLab/research/post_locked_smoke.py`;
3. `ModelLab/research/guided_flow_smoke.py`.

Machine-readable evidence records the first failed gate.
