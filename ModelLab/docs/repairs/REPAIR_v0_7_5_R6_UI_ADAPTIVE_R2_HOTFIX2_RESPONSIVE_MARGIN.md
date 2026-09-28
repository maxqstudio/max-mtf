# v0.7.5 R6 UI Adaptive R2 Hotfix2 — Tablet Slide-Over Margin Authority Repair

## Owner real-runtime evidence

Adaptive R2 Hotfix1 completed **67 PASS gates** before the first real UI failure. The first failed gate was:

`tablet_768x1024_center_margins`

Observed at 768×1024:

- left drawer width: 236 px;
- Scientist drawer width: 420 px;
- `stMain` margin-left: 236 px;
- `stMain` margin-right: 420 px;
- expected slide-over main margins: 0 / 0.

The same real Streamlit 1.63 run had already passed 1920×1080, 1440×900, 1280×720 and 1024×768 shell geometry; Scientist history-only scrolling; fixed header/composer; dark toolbar; navigation/draft persistence; left show/hide; Scientist show/hide; and long-reply containment.

## Root cause

The base responsive stylesheet correctly declared `stMain` margins as zero at `max-width:900px`. However, `_shell_state_fragment()` emits a later `<style>` block with the same selectors and direct dynamic desktop margins. Because the injected ShellState rule occurs later in the cascade, it overrode the tablet media rule.

This was a **single-authority implementation bug**: ShellState visibility state was also unintentionally overriding viewport geometry.

## Repair

ShellState now separates the two responsibilities:

- left/right drawer transforms and restore-control visibility remain dynamic at every viewport;
- center reflow margins are emitted only inside `@media (min-width:901px)`;
- `@media (max-width:900px)` explicitly forces `margin-left:0`, `margin-right:0`, `width:100%`, and `max-width:100%`.

The mobile/tablet viewport policy therefore wins regardless of whether left and/or Scientist drawers are open.

A cumulative contract self-test now fails if the late ShellState block loses this media scoping.

## Acceptance

- Owner Hotfix1 real runtime: **67 PASS / 1 FAIL**, first failed gate `tablet_768x1024_center_margins`.
- Hotfix2 local cumulative acceptance: **80/80 PASS**, first failed gate `null`.
- Hotfix2 static adaptive browser acceptance: **84/84 PASS across 10 viewports**.
- Scientific core preservation: **22/22 byte-identical** to Hotfix1.
- Real Streamlit Hotfix2 runtime: **PENDING OWNER RERUN**.

## Promotion

Hotfix2 remains a candidate until `ModelLab/acceptance/runners/RUN_UI_RUNTIME_ACCEPTANCE.ps1` completes with `overall_status = PASS`.
