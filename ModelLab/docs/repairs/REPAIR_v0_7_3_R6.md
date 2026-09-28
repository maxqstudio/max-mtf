# CPMF v0.7.3 R6 — KPI + CPCV Governance + Research UI/Scientist Hardening

## Baseline

R6 is repaired from the exact accepted **v0.7.3 R5 Hotfix1** code baseline. R5/Hotfix1 history remains immutable provenance; R6 does not rewrite prior evidence.

## Owner KPI authority

Full-WFA/CV and CPCV now share the same business floor:

`Worst aggregate / worst-fold expectancy >= 0.00R`

A tiny epsilon (`1e-9` default) is used only for floating-point noise around zero.

The seven Advanced KPI are default-active hard gates and are configured through the data-driven `acceptance.risk_kpis` registry:

- Sharpe >= 0.30.
- Sortino >= 0.40.
- Calmar/MAR >= 1.00, annualized across the full evaluation window.
- PSR >= 0.95 against benchmark Sharpe 0.20.
- DSR >= 0.95 using predeclared current-cycle research budget by default.
- Ulcer Index <= 5.00R.
- Daily CVaR / Expected Shortfall 95% >= -2.00R/day.

Legacy per-trade CVaR remains diagnostic only.

## Repairs

1. **CPCV dual-view methodology and KPI authority**
   - Preserve all 15 purged `C(6,2)` stress splits for existing CPCV economic/stress gates.
   - Emit deterministic 5 reconstructed chronological paths for `N=6,k=2`.
   - Use reconstructed paths as CPCV gate evidence for the seven Advanced KPI.
   - Emit per-group attribution so repeated weak chronological regions can be separated from non-contiguous split effects.
   - Canonical DD/recovery do not silently replace legacy stress-split DD/recovery.

2. **Seven active Advanced KPI gates**
   - Sharpe, Sortino, Calmar/MAR, PSR, DSR, Ulcer Index, and daily CVaR/Expected Shortfall 95%.
   - KPI label, enabled state, threshold, direction, basis and UI editor metadata come from registry/config rather than UI hardcoding.
   - Calmar uses full evaluation-window duration, not first-trade to last-trade duration.
   - Daily CVaR aggregates trade R by calendar day before computing the worst 5% tail.

3. **Scientist scientific-method discipline**
   - `OBSERVATION → HYPOTHESIS → EXPERIMENT → FALSIFICATION → CONCLUSION` is persisted/rendered.
   - Observation is constructed from deterministic evidence; causal language remains hypothesis/advisory.
   - LLM cannot override deterministic stage PASS/FAIL or KPI gates.
   - All seven KPI are exposed in compact candidate evidence supplied to Scientist.

4. **Decisive hypothesis lifecycle**
   - Full-WFA is a proxy/safety screen for hypotheses born from CPCV/Tournament/Monte-Carlo failures.
   - Full-WFA PASS cannot by itself mark such a hypothesis `SUPPORTED`.
   - Matching evidence at the originating stage closes the hypothesis as `SUPPORTED`, `PARTIALLY_SUPPORTED`, `FALSIFIED`, or `INCONCLUSIVE`.

5. **Research UI state separation**
   - Dedicated ACTIVE RESEARCH CYCLE card.
   - Dedicated PREVIOUS CYCLE card.
   - No fallback from an active runtime cycle to a selected historical factory summary.
   - Per-cycle active-family provenance distinguishes DEFAULT from MANUAL_ENABLED.
   - Visible generic `Score` wording is clarified as `Ranking Score`; hard gates remain authority.

6. **Ordered LLM model stack**
   - More than one LLM model may be enabled in priority order.
   - Fallback is allowed for quota/rate-limit exhaustion, timeout, model/capacity unavailable, or provider 5xx.
   - Authentication/authorization errors, malformed configuration/request, and deterministic response validation errors fail closed and do not silently switch models.
   - Every attempt/selected model/fallback reason is persisted as Scientist call provenance.

## Preserved authorities

- R5 Hotfix1 runtime fix.
- Default active model families: GRU→LightGBM and GRU→XGBoost.
- Random Forest support remains retained/dormant unless manually enabled.
- No TCN/Transformer/HMM/MiniROCKET family expansion in R6.
- Forward/fresh evidence remains protected from repeated tuning on the same window.

## Acceptance

R6 acceptance covers zero-floor WFA+CPCV expectancy, seven KPI formulas/default gates, daily CVaR basis, 5 reconstructed path invariants, Scientist evidence discipline, decisive downstream hypothesis lifecycle, LLM quota fallback/fail-closed behavior, active/previous UI separation, family provenance and Ranking Score wording.

Full cumulative acceptance is required before packaging. External ONNX runtime parity, MetaEditor compile, and Owner MT5 runtime acceptance remain external machine gates.


## Cockpit + LLM usage hardening
- Scientist report now displays the exact selected provider/model and PRIMARY/FALLBACK route per committed report.
- Token telemetry records input/output/total/cached/reasoning tokens when provider usage is available; otherwise a tokenizer-agnostic fallback is explicitly labelled `ESTIMATED`.
- Advanced exposes operator-owned per-model USD/1M input/output/cached-input pricing. No API price is hardcoded. Cost is shown only when pricing is enabled.
- Current Scientist journal aggregates calls, input/output/total tokens, fallback count and known priced cost.
- Scientist information is not reduced: OBSERVATION/HYPOTHESIS/EXPERIMENT/FALSIFICATION/CONCLUSION, condition, interpretation, next action, strategy, next-discovery plan, proposals and feedback state are preserved but grouped into cockpit cards.
- Wide data tables/proposals remain full-width. General content width is capped for higher information density.
