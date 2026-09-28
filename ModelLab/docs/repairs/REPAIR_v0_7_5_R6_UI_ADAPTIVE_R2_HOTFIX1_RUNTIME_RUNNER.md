# v0.7.5 R6 UI Adaptive R2 Hotfix1 — Runtime Acceptance Runner API Repair

## Owner runtime evidence

Adaptive R2 was executed on the Owner machine with Streamlit 1.63.0, Playwright 1.57.0, and Microsoft Edge. The report recorded **40/40 executed runtime gates PASS** before the acceptance harness itself crashed. The application under test matched the R2 package exactly (`ModelLab/ui/app.py` SHA-256 `12c702dfe384742d0cc69be0326d00f7ba9f271e078080f73c0f62e3e069c747`).

Proven real-runtime PASS evidence before the crash includes:

- 1920×1080 shell geometry, fixed Scientist drawer, history-only scroll, fixed header/composer;
- 1440×900 shell geometry and reflow;
- complete navigation and single lifecycle control;
- DOM-adaptive Model/Context detection;
- dark Scientist toolbar styling;
- compact composer;
- unsent draft persistence across Data → Discovery → Pool → CPCV;
- Scientist DOM node persistence across page navigation;
- model/context persistence across navigation;
- draft persistence and no Scientist reinitialization when left navigation hides;
- no reserved left gutter after hide.

The report did **not** record a failed UI gate. `first_failed_gate` is `null`.

## Root cause

The runner called Playwright 1.57 `Page.wait_for_function()` with the JavaScript function argument as a second positional argument. In Playwright 1.57 the sync signature is:

`wait_for_function(expression, *, arg=None, timeout=None, polling=None)`

Therefore the harness raised:

`TypeError: Page.wait_for_function() takes 2 positional arguments but 3 positional arguments ... were given`

This is an acceptance-runner defect, not scientific/backend or UI evidence failure.

## Repair

Both responsive `wait_for_function()` calls now use `arg=(width <= 900)` explicitly. The cumulative `UI_RUNTIME_ACCEPTANCE_CONTRACT` self-test now parses the runner AST and rejects any future `wait_for_function()` call with more than one positional argument.

`ModelLab/ui/app.py` and scientific/backend source are intentionally unchanged from Adaptive R2.

## Promotion

Hotfix1 remains a candidate until the Owner reruns the real Streamlit acceptance to completion. A terminal `overall_status = PASS` is still required.
