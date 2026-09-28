# Max Research Agent — ONNX Factory UI Shell Recovery Contract

Status: **UI ADAPTIVE R1 CANDIDATE — NOT YET OWNER/RUNTIME ACCEPTED**  
Scientific authority: **v0.7.5 R6**  
Recovery source: **full Repair7 Scientist Chat package**, verified against Repair6 core hashes.  
Failed comparison: **Repair9**, retained only as failure evidence; it is not a baseline.

## Single shell authority

```text
AppShell
├── ShellState            # only left/right transform + center margin authority
├── LeftNav               # persistent fixed viewport panel (not st.sidebar, not a named fragment)
│   ├── Brand + hide
│   ├── Navigation
│   └── LifecycleHeartbeat # 2 s read-only/status fragment
├── MainWorkspace         # named fragment; normal center page scroll
└── ScientistDrawer       # named fixed viewport drawer
    ├── Header
    ├── Model / Context / Options
    ├── MessageHistory    # only scrollable drawer child
    └── Composer
```

Rules:
- No executable `st.sidebar` shell authority.
- `ShellState` alone controls `LeftNav` / `ScientistDrawer` transforms and center margins.
- LeftNav remains mounted; it is not rebuilt for hide/show.
- Main page navigation reruns only `workspace`.
- Scientist hide/show reruns only `shell_state`; the Scientist fragment stays mounted.
- Left hide/show reruns only `shell_state`; the left widget tree stays mounted.
- Lifecycle heartbeat remains the only periodic fragment in the left panel.

## Scientist state isolation

- History persists per Factory through `ScientistChatStore`.
- Model, context, fallback and draft use session-persistent widget state.
- Manual fallback default is OFF.
- Hide/show does not rerun Scientist, specifically to avoid destroying browser-only unsent form text before submit.
- Scientist remains read-only and has zero execution tools.

## Visual contract

- Wide desktop: left width `clamp(196px, 14vw, 224px)` and Scientist width `clamp(336px, 25vw, 410px)` with true 3-panel reflow.
- Compact desktop (901–1240 px): both fixed regions compress while the center still reflows.
- Tablet (<=900 px): center owns the full viewport and left/Scientist become slide-over drawers.
- Phone (<=640 px): Scientist uses the full viewport width.
- Short height (<=700 px): header/toolbar/composer shrink deterministically to protect history height.
- Scientist header, toolbar, history and composer are independently viewport-anchored; they no longer depend on a fragile parent Streamlit grid wrapper.
- Only chat history has vertical scrolling.
- User bubble is compact/right; Scientist bubble is bounded/left and long content wraps.
- Composer stays single-line and compact.
- Main workspace owns normal document/page scrolling and expands when drawers hide.

## Scientific authority preserved

This repair does not relax or modify KPI authority, R3 topology allocation, R4 deterministic Discovery, R5 creativity, R6 family-size priority, capacity governance, CPCV fixed seeds `42 → 11 → 77`, Data Quality, locked/fresh Forward separation, Champion authority, MT5 authority, or ONNX decision contracts.

## Acceptance truth

- Static browser shell evidence is useful for geometry and interaction isolation only.
- It is **not** equivalent to Streamlit runtime/render acceptance.
- Real Streamlit 1.63 render acceptance remains mandatory before this candidate may be called visually accepted.
