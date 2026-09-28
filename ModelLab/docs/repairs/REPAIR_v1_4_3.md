# Repair v1.4.3 — Strategy Navigation Lifecycle Routing

## Defect

The left-footer contextual lifecycle treated only the `Strategy Optimizer` page as Strategy-domain state. `Strategy Challengers` and `Strategy Champion` therefore fell through to the Research lifecycle and displayed `START RESEARCH`, even though all three pages belong to the same upstream Strategy Optimizer/Strategy Registry domain.

The workspace status bar had the same page-only condition, so Challenger/Champion pages could report Research status instead of Optimizer status.

## Repair

- Add one canonical `STRATEGY_NAV_PAGES` domain containing:
  - `Strategy Optimizer`
  - `Strategy Challengers`
  - `Strategy Champion`
- Route the contextual footer through `_is_strategy_nav_page()`.
- All three Strategy pages now render the same Optimizer lifecycle authority: START / RESUME / STOP.
- All three Strategy pages now render Optimizer status chips in the workspace header.
- Persisted `strategy_opt_*` operator settings are rehydrated inside the contextual footer before START/RESUME logic runs. This is required because the footer may render or rerun before the workspace and independently of the Optimizer settings page.
- Non-Strategy pages continue to use the Research lifecycle.

## Authority preserved

- Strategy Optimizer still creates Strategy Challengers only; it does not auto-promote a Strategy Champion.
- Strategy Challenger/Champion registry and explicit Owner promotion semantics are unchanged.
- Model Research lifecycle is unchanged.
- Strategy and Research concurrent-start interlock is unchanged.
- v1.4.2 model-size advisor, Exp R visibility and H1 minimum-trades repairs remain preserved.
- RL, RAG and Embedder remain disabled/fail-closed.

## Regression

`R57_V143_STRATEGY_NAVIGATION_LIFECYCLE` verifies that all three Strategy pages share the Optimizer footer/status authority, durable Optimizer settings are available to the footer, and non-Strategy pages retain Research lifecycle authority.

Cumulative local source/contract target: **134/134 exact-tree PASS**.
