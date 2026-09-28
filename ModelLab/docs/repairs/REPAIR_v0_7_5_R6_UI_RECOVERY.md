# v0.7.5 R6 — UI Recovery Candidate

## Status

**CANDIDATE / NOT RUNTIME-ACCEPTED.** The scientific baseline remains v0.7.5 R6. Repair9 remains FAILED.

## Recovery choice

The recovery source is the full Repair7 package, with Repair6 used as an upstream sanity reference. Repair7 was selected because the research core remained byte-identical across the relevant Repair6→Repair7 lineage while Repair7 already contained the read-only Scientist Chat backend. Repair9 is used only to identify failed shell changes.

## Proven Repair9 failure topology

1. Multiple shell authorities competed for left/right geometry.
2. Native/sidebar-era CSS remained active while new fixed/drawer CSS was layered on top.
3. Fragment/rerun surgery changed layout execution without adequate render evidence.
4. Cosmetic/source self-tests were treated as visual acceptance even though the Owner runtime showed missing navigation, duplicated lifecycle controls and a degraded Scientist drawer.

## Recovery implementation

- one `ShellState` authority for drawer transforms and center margins;
- fixed persistent LeftNav without executable `st.sidebar`;
- LeftNav not wrapped in a named fragment; lifecycle heartbeat alone remains periodic;
- named `workspace` fragment for center navigation isolation;
- named `scientist` fragment for Scientist interactions;
- hide/show callbacks target only `shell_state`, leaving Scientist and draft mounted;
- global radiogroup/sidebar CSS authorities removed;
- compact bounded user/Scientist bubbles and fixed composer;
- manual Scientist fallback default remains OFF;
- Streamlit runtime pinned to 1.63.0 because named event-scoped fragment reruns and session widget persistence are part of the shell contract.

## Evidence

- `historical external: UI_RECOVERY_BACKEND_PRESERVATION.json` — scientific-core hash comparison against Repair7.
- `historical external: ui_static_acceptance/STATIC_BROWSER_ACCEPTANCE.json` — 26 static-browser geometry/interaction gates.
- `ui_static_acceptance/evidence/*.png` — desktop and short-height static render evidence.
- `historical external: BUILD_ACCEPTANCE_v0_7_5_R6.json` — cumulative deterministic/backend acceptance.

## Remaining hard gate

`STREAMLIT_1_63_RUNTIME_RENDER_ACCEPTANCE` is **NOT RUN / ENVIRONMENT BLOCKED** in this build container because Streamlit is absent and the environment cannot fetch the package. Static browser evidence does not close this gate. No final accepted release package should be claimed until the real Streamlit app is rendered and the UI scenarios in the continuity handoff are exercised.
