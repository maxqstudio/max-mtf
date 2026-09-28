# UI Grouping R1 — Owner grouping restoration

**Status:** CANDIDATE · local exact-tree acceptance **86/86 PASS** · Owner visual review pending  
**Scientific authority:** v0.7.5 R6  
**Control:** Research Control R1  
**Scientist knowledge:** Scientist Knowledge R1  
**Chat state:** Chat State R1  
**UI revision:** **UI Grouping R1**

## Why this revision exists

UI Hierarchy R1 was rejected visually by the Owner. It over-flattened the interface and introduced radio-like navigation that made Advanced look like a multiple-choice form. The Owner contract is to preserve the earlier coherent grouping and make only small presentation repairs.

## Owner visual contract

1. Related controls stay together; do not split one logical group across tabs/pages/selectors.
2. Advanced remains one page with the proven top-level groups/disclosures.
3. No radio/bullet navigation for switching Advanced or Scientist configuration sections.
4. `Scientist · connection & routing` keeps provider, endpoint, credentials, primary Research model, autonomous fallback, manual Chat fallback, and route health in one coherent flow.
5. Scientist Chat per-model profile and optional token pricing remain secondary detail disclosures inside the Scientist group, but are visually flattened (borderless/detail-row treatment) so they do not look like cards inside cards.
6. `Supervisor & Scientist creativity`, KPI gates, Adaptive model research, Compute, Factory, Research authority, and Diagnostics remain their own coherent groups on the same Advanced page.
7. Data→Champion returns to the accepted pre-UI-Hierarchy grouping rather than introducing new flat-section semantics.
8. Whitespace, divider, padding, and typography may be refined; scientific/backend authority may not change.

## Explicit rejection of UI Hierarchy R1

The following UI Hierarchy R1 ideas are **not current authority**:
- Advanced single-concern radio navigation;
- Scientist `Connection | Routing | Chat profile | Cost` radio navigation;
- splitting related configuration into separate selector-driven pages;
- flattening already-good groups merely to remove cards.

UI Hierarchy R1 remains historical evidence only and is **VISUAL FAIL / NOT ACCEPTED**.

## Acceptance

- Active static/source gate: `ModelLab/tests/ui_grouping_r1_selftest.py`.
- Exact-tree cumulative authority: `historical external: BUILD_ACCEPTANCE_v0_7_5_R6.json` = **86/86 PASS**, `first_failed_gate = null`.
- Local PASS does not substitute for Owner Windows/Streamlit visual acceptance.


Owner runtime visual checks remain required on Windows/Streamlit:
- Advanced reads as coherent grouped configuration, not a multiple-choice form;
- related Scientist controls are visible together;
- no redundant card-in-card appearance;
- whitespace is calm without splitting related controls;
- Data→Advanced scroll/reflow remains healthy with left/right panels hidden or shown.
## Operator state feedback amendment

Runtime testing requires UI state to distinguish work-in-progress from idle/completed state:

- navigation sets an explicit workspace render-pending state, displays a loading indicator while the selected page is being rendered, and emits a `Page ready` acknowledgement only after that render returns;
- automatic Data/Advanced persistence emits `Data saved` / `Settings saved` only after the settings store write succeeds; a failed write is surfaced as an error rather than silently swallowed;
- these notifications are presentation feedback only and do not alter scientific PASS/FAIL authority.

