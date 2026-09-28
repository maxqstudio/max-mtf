# UI Component Chat R4 Hotfix7 — Research Policy Layout + Main Scroll Authority

Authority: **v0.7.5 R6**. This is a bounded UI repair. Scientific/research core semantics are unchanged.

## Owner-observed defects

1. `Advanced > Research authority > Research policy` was visually over-nested: a large policy card/expander inside the Research authority card, with too many controls exposed at once.
2. Long Advanced content could intermittently become non-scrollable, especially after shell drawer hide/show interactions.

## Repair

### Research Policy flattening
- Removed the nested `Research policy` expander/card.
- Kept `Research authority` as the single outer conceptual group.
- Reorganized all existing controls into five persistent policy groups:
  - **Execution** — trade sample authority, CPU threads, WFA folds, seed, experiment budget/patience.
  - **Labels** — horizon, ATR barriers, edge/margin.
  - **Survival** — locked/fresh holdout gates and WFA DD/recovery survival gates.
  - **Validation** — WFA economics, CPCV finalist gates, locked-test concentration/stability, stress robustness.
  - **Promotion** — fresh-shadow promotion gates.
- Only the selected policy group is rendered, reducing visual density and page height without removing any Owner setting.
- Policy group selector wraps on narrow widths.

### Single scroll-owner repair
- `stMain` is now the explicit bounded vertical scroll owner (`100dvh`, `overflow-y:auto`).
- AppView outer shell is non-scrolling to prevent competing/nested page scroll owners.
- `.block-container` grows naturally and remains `overflow:visible` inside `stMain`.
- Left navigation and Scientist retain their separate intentionally bounded scroll regions; this repair does not alter their fixed-region contracts.

## Acceptance

Targeted source/runtime-contract tests:
- `python -m py_compile app.py` — PASS
- `ModelLab/tests/advanced_policy_layout_selftest.py` — PASS
- `ModelLab/tests/responsive_shell_selftest.py` — PASS
- `ModelLab/tests/lifecycle_loader_layout_selftest.py` — PASS
- `ModelLab/tests/ui_event_state_selftest.py` — PASS
- `ModelLab/tests/scientist_chat_ui_selftest.py` — PASS
- `ModelLab/tests/scientist_chat_reset_selftest.py` — PASS

Representative scientific regression tests also passed: topology priority, deterministic Discovery parity, family-size priority/E2E, CPCV seed confirmation, Data Quality authority, Scientist context parity.

## Preservation

`historical external: UI_COMPONENT_CHAT_R4_HOTFIX7_BACKEND_PRESERVATION.json` proves **21/21 research-core files byte-identical** to Hotfix6.

## Owner visual acceptance still required

Open `Advanced > Research authority`, switch through every Research Policy group, then hide/show LeftNav and Scientist while the page is long. Main content must remain scrollable from top to bottom. No inner Research Policy scrollbar/card should appear.
