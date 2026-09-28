# REPAIR — v0.7.5 R6 UI Adaptive R1

Authority date: 2026-09-12

## Trigger

Owner real-runtime screenshot demonstrated that the previous UI recovery candidate was not adaptive: the Scientist drawer's fixed/internal grid assumptions did not match the real Streamlit DOM, causing message/history/composer overlap.

## Root cause

The Scientist drawer depended on a fragile parent `stVerticalBlock` grid selector. When that wrapper did not match the real Streamlit DOM hierarchy, header, toolbar, history and composer returned to normal Streamlit flow and could overlap. Shell widths were also hard-coded (`224px` / `390px`) instead of viewport-responsive.

## Repair

- Preserved v0.7.5 R6 research/backend authority.
- Replaced fixed shell widths with CSS variables using `clamp()`.
- Wide desktop (`>1240px`): adaptive 3-panel reflow.
- Compact desktop (`901..1240px`): compressed left/right widths while retaining 3-panel reflow.
- Tablet (`<=900px`): main workspace owns full viewport; left and Scientist become slide-over drawers.
- Phone (`<=640px`): Scientist becomes full-width; controls remain single-row and compact.
- Short height (`<=700px`): header/toolbar/composer heights shrink deterministically.
- Removed the Scientist parent-grid dependency. Topbar, toolbar, history and composer are now independently viewport-anchored with absolute positioning inside the fixed drawer.
- History is explicitly bounded between toolbar and composer and is the only vertical scroll surface.
- Shell `st.columns` rows use `wrap=False` so close buttons/model/context/composer do not stack unexpectedly.
- Hide/show still reruns `shell_state` only; Scientist remains mounted to preserve draft/history/model/context.

## Acceptance

- Cumulative deterministic/backend suite: **80/80 PASS**, `first_failed_gate = None`.
- Adaptive static browser matrix: **84/84 PASS** across **10 viewport sizes** from 1920×1080 down to 390×844, including an Owner-like 1792×856 view.
- Real Streamlit 1.63 runtime render of this new Adaptive R1 candidate remains an Owner-machine gate.

## Non-goals

No research KPI, model universe, topology allocation, capacity governor, CPCV seed authority, Data Quality, LLM routing, Forward/Champion authority, or MT5 execution semantics were changed.
