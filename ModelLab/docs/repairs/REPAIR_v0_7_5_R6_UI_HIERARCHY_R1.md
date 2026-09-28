# Repair — UI Hierarchy R1

Generated: 2026-09-13T10:45:58.412305+00:00

## Owner request

Audit cards from Data through Advanced, skip already-clean surfaces, remove card-in-card composition, reduce visual density, strengthen hierarchy/whitespace, and simplify Scientist Connection.

## Bounded source scope

- `ModelLab/ui/app.py` — presentation hierarchy only.
- `ModelLab/tests/ui_information_hierarchy_selftest.py` — regression contract updated to the new hierarchy.
- Living docs/Scientist knowledge manifest synchronized.

No scientific algorithm authority is intentionally modified.

## Changes

- Data identity/windows flattened.
- Discovery/Pool/CPCV/Tournament/Monte Carlo/Forward/Champion primary summaries/results flattened.
- Optional forensic evidence retained as first-level disclosures.
- Advanced replaced simultaneous configuration expanders with one-level concern navigation.
- Scientist settings split into Connection/Routing/Chat profile/Cost; zero inner expanders.
- Expander visual treatment reduced to transparent, low-noise disclosure styling.

## Acceptance truth

Targeted UI/state checks PASS. Fresh exact-tree cumulative acceptance is **86/86 PASS** with `first_failed_gate = null` in `historical external: BUILD_ACCEPTANCE_v0_7_5_R6.json`.

The final cumulative run exposed an acceptance-infrastructure stall in the synthetic Guided/Lineage ML smoke processes on the constrained build container. This was not a production research defect: the smoke had already produced terminal PASS evidence. The harness is now deterministic by (a) disabling machine CPU calibration inside the synthetic Guided smoke lineage, (b) bounding native BLAS/OpenMP threads only for the two terminal smoke gates, and (c) launching those gates through the platform shell. Production CPU calibration and research runtime remain unchanged.

Owner real Streamlit visual review remains required and is never inferred from source/static tests.
