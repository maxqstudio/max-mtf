# HISTORICAL VISUAL FAIL / NOT ACCEPTED

Owner runtime review rejected this presentation because related groups were split into selector/radio navigation and the UI resembled a multiple-choice form. Current authority is `ModelLab/docs/ui/UI_GROUPING_R1.md`.

# UI Hierarchy R1 — Data → Advanced

**Status:** HISTORICAL LOCAL TEST PASS · **OWNER VISUAL FAIL / NOT ACCEPTED**  
**Scientific authority:** v0.7.5 R6  
**Control:** Research Control R1  
**Scientist knowledge:** Scientist Knowledge R1  
**Chat state:** Chat State R1  
**UI revision:** **UI Hierarchy R1**

## Goal

Reduce visual noise without removing scientific evidence or changing backend authority. The UI follows functional minimalism: one visible hierarchy, deliberate whitespace, and no decorative card-in-card composition.

## Global presentation contract

1. Primary page information is rendered as **flat sections** (`page header → section → subsection`).
2. Metrics use compact stat/fact strips; individual metrics are not promoted into separate decorative cards.
3. A disclosure/expander is permitted only for **optional dense evidence** such as forensics, stage Scientist analysis, or Data Quality repair detail.
4. **Nested expanders/card-in-card are forbidden** from Data through Advanced.
5. Main workspace remains the single vertical scroll owner; section grouping must not create inner page scroll surfaces.
6. UI cleanup cannot alter research settings, lifecycle authority, deterministic validation, evidence semantics, or scientific contracts.

## Page audit

### Data
- Dataset identity is flat primary information.
- Data Quality remains a first-level disclosure because broker reconciliation, missing-bar forensics and repair can be large.
- Research windows are flat; Discovery/Tournament/Forward are whitespace-separated subsections.
- Compute backend is a small opt-in toggle instead of another card.

### Discovery
- Discovery limits/target and direct Discovery-only control are flat.
- Live job monitor remains lifecycle evidence.
- Latest Factory evidence is flat.
- Near-miss details are optional via a lightweight toggle.

### Pool
- Pool authority, summary and candidate table are flat.
- Stage Scientist analysis remains optional evidence disclosure.

### CPCV
- Qualification progress and finalist result table are flat.
- Only CPCV forensic detail is collapsible; its internal views use tabs, not nested cards.

### Tournament
- Summary + results are flat.
- Tournament forensics are optional first-level evidence.

### Monte Carlo
- Summary + results are flat.
- Monte Carlo forensics are optional first-level evidence.

### Forward Championship
- Fresh-forward summary + results are flat.
- Locked evidence forensics are optional first-level evidence.

### Champion
- Champion authority and terminal state are flat. No outer status card.

### Advanced
Advanced uses one first-level selector:

`Research Control | Scientist | Model Research | Validation | Compute | Factory | Authority | Diagnostics`

Only the selected concern is rendered. This prevents one extremely tall configuration page and protects whitespace/scroll behavior.

#### Scientist
Scientist configuration has its own compact concern selector:

`Connection | Routing | Chat profile | Cost`

- Connection = provider, endpoint, credential handshake.
- Routing = primary autonomous Research model, ordered Research fallback, explicit/manual Chat fallback.
- Chat profile = per-model discussion depth/temperature/streaming/timeout/output/context/history budgets.
- Cost = optional estimator only.

No Scientist configuration concern is nested inside an expander/card.

## Acceptance

Static/source contract: `ModelLab/tests/ui_information_hierarchy_selftest.py`.

Local exact-tree cumulative acceptance: **86/86 PASS**, `first_failed_gate = null` (`historical external: BUILD_ACCEPTANCE_v0_7_5_R6.json`).

The Guided/Lineage synthetic smoke harness is acceptance-only thread-bounded/shell-owned on constrained CI so native ML-library teardown cannot masquerade as a product regression. Production CPU resource calibration and research execution are unchanged.

Owner visual acceptance must verify:
- hierarchy is visually calm at the Owner desktop size;
- Data→Advanced remains scrollable after left/right drawer hide/show;
- no information is clipped;
- no evidence disclosure creates a second vertical scroll owner;
- Scientist configuration is materially less crowded;
- no backend/research behavior changes.

Generated: 2026-09-13T10:45:58.412305+00:00
