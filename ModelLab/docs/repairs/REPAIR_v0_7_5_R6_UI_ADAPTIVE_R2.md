# REPAIR v0.7.5 R6 — UI ADAPTIVE R2

## Scope

Bounded UI/runtime-acceptance repair only. Scientific authority remains **v0.7.5 R6**.

## Owner real-runtime evidence

Adaptive R1 real Streamlit 1.63 acceptance reached live browser rendering and proved:

- Streamlit 1.63.0 exact runtime PASS.
- Edge runtime PASS.
- 1920×1080 shell geometry PASS.
- 1440×900 shell geometry PASS.
- left width/reflow PASS.
- Scientist fixed drawer PASS.
- history-only scroll PASS.
- fixed Scientist header/composer PASS.
- navigation list present PASS.
- lifecycle duplicate-control gate PASS.

The first failed gate was:

`scientist_model_context_controls_render`

The failure detail reported `select_count = 0`, but the owner screenshot visibly rendered **Mock Model** and **DATA** controls. Root cause: the acceptance runner was coupled to the old internal selector `[data-baseweb="select"]`. Streamlit 1.63 rendered the controls with a different DOM structure.

The same screenshot exposed a separate real visual defect: Scientist model/context/options controls retained light/white field backgrounds against the dark shell.

## Repair

1. Runtime acceptance no longer depends on one framework-internal BaseWeb selector.
2. Model/context presence is accepted through semantic widget roles/testids or Streamlit widget-key roots.
3. Runtime evidence now captures:
   - Scientist toolbar DOM diagnostics;
   - pre-interaction page HTML;
   - actual control styles/geometry.
4. New hard visual gate: `scientist_toolbar_dark_theme`.
5. Scientist toolbar CSS now styles:
   - legacy BaseWeb select markup;
   - Streamlit `stSelectbox` markup;
   - semantic `[role="combobox"]` controls;
   - the options button;
   - responsive/short-screen sizes.
6. Research/scientific backend is unchanged.

## Acceptance

- Python compile: PASS.
- Scientist Chat read-only selftest: PASS.
- Scientist Chat UI selftest: PASS.
- Responsive shell selftest: PASS.
- Static adaptive browser acceptance: **84/84 PASS** across 10 viewports.
- Full cumulative deterministic/backend acceptance: **80/80 PASS**.
- Scientific-core preservation: **22/22 byte-identical** versus Adaptive R1.
- Real Streamlit R2 runtime acceptance: **NOT RUN HERE — OWNER-MACHINE REQUIRED**.

## Promotion rule

R2 remains a candidate until `historical external: ModelLab\runtime_ui_acceptance\RUNTIME_UI_ACCEPTANCE.json`
returns `overall_status = PASS` on the Owner machine.
