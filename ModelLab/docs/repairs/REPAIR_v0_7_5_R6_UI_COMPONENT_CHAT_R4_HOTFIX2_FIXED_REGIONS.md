# R4 Hotfix2 — Fixed Regions Repair

Authority: v0.7.5 R6 scientific backend remains unchanged.

## Runtime visual defects repaired

Owner evidence showed two shell defects:

1. Scientist composer could fall below the visible drawer instead of remaining in the footer.
2. Left sidebar header participated in the panel scroll, producing visible scrollbars/brand clipping.

## Repair

### Scientist

The custom component remains one isolated V2 component, but its root is now viewport-anchored inside the Streamlit component host:

- `:host` is a relative, overflow-hidden 100% surface.
- `.scientist-root` is `position:absolute; inset:0`.
- root grid rows remain `auto auto minmax(0,1fr) auto`.
- Header, toolbar and composer remain normal grid rows; they do not scroll.
- `.scientist-history` is the only `overflow-y:auto` region.
- Composer height remains bounded and cannot consume the history region.

This removes reliance on content-derived component height that could push the composer below the browser viewport.

### Left navigation

Left navigation is now a true three-region shell:

- fixed header/brand;
- nav-only scroll region;
- fixed lifecycle footer.

The panel itself is `overflow:hidden` and uses `grid-template-rows:auto minmax(0,1fr) auto`. Only `left_nav_nav` may scroll.

## Regression guards

Updated source self-tests require:

- Scientist viewport anchoring;
- history-only scrolling;
- no fixed-position message/composer hacks;
- left fixed header/footer with nav-only scrolling;
- responsive desktop/tablet/mobile shell authority.

Targeted checks PASS:

- Python compile
- `ModelLab/tests/scientist_chat_ui_selftest.py`
- `ModelLab/tests/responsive_shell_selftest.py`
- `ModelLab/tests/scientist_chat_readonly_selftest.py`
- `ModelLab/tests/scientist_context_parity_selftest.py`

Cumulative acceptance was rerun and progressed through the repaired UI gates and the R6 scientific suite without a discovered failure before the local execution timeout. No scientific-core production file was intentionally modified.

## Remaining visual authority

This candidate is not declared visually accepted until the Owner confirms in actual Streamlit runtime that:

- Scientist header and toolbar remain fixed;
- Scientist composer is always visible and fixed at the bottom;
- only Scientist history scrolls;
- left header remains fixed;
- only left navigation scrolls;
- lifecycle controls remain fixed at the bottom.
