# UI COMPONENT CHAT R4 HOTFIX1 — FIXED HEADER / HISTORY-ONLY SCROLL

Status: CANDIDATE

## First failed visual gate
Owner screenshot showed the Scientist header could participate in scrolling. This violates the hard UX contract that only message history may scroll.

## Root cause
The V2 component mounted with the default content height. Even though the inner grid used a bounded history region, the Streamlit component wrapper could content-size the component and become an outer scroll surface.

## Repair
- Mount Scientist V2 component with `width="stretch"`, `height="stretch"`.
- Force Streamlit drawer/component wrappers to `height:100%`, `min-height:0`, `overflow:hidden`.
- Component host/root use `height:100%` and `overflow:hidden`.
- Header and toolbar are sticky at the top inside the component.
- Composer is sticky at the bottom.
- `.scientist-history` remains the only `overflow-y:auto` region.
- No research/scientific authority changes.

## Required real-runtime proof
Scroll a long multi-turn Scientist history from top to bottom. Header, toolbar, and composer must not move by even one pixel.
