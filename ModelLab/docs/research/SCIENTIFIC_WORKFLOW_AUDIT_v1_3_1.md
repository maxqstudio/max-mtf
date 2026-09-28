# Scientific Workflow Audit — v1.3.1

Status: **OPEN DEFECT REGISTER — DOCUMENTED, NOT REPAIRED IN v1.3.1**  
Audit scope: `Data → feature/label → Cheap Screen → chronological WFA → CPCV → Tournament → Monte Carlo → Fresh Forward → Model Challenger`  
Release purpose: preserve the findings as project authority before the next scientific-workflow repair release.

## 1. Executive verdict

v1.3.1 source/contract acceptance does **not** mean the current Model Research simulator is production-parity with the promoted Strategy Champion. The audit found several scientific-parity and objective-alignment defects that can make a model learn or be ranked against a proxy different from the live EA execution process.

The next real scientific research cycle must not be treated as production-parity evidence until the CRITICAL/HIGH items below are repaired and regression-tested.

## 2. Critical execution-parity defects

### SCI-01 — Research execution gates differ from current Strategy Champion — CRITICAL

Current promoted Strategy authority:

- `InpEntryThreshold = 0.18`
- `InpMinConsensus = 0.70`
- `InpShockHaltATR = 3.5`
- `InpExitReverseThreshold = 0.25`
- `InpSL_ATR = 3.2`
- `InpTP_ATR = 4.8`
- `InpMaxHoldBars = 54`

Current Model Research deployment defaults:

- `entry_threshold = 0.34`
- `min_consensus = 0.30`
- `shock_halt_range_atr = 4.0`

SL/TP/MaxHold are bound to Strategy geometry, but Entry Threshold / Consensus / Shock Halt are not currently synchronized to the promoted Strategy Champion. Therefore Model Research may evaluate entries that the live EA would reject, or reject entries the EA would permit.

**Required repair:** make the complete execution-policy subset required for Model Research an immutable Strategy Champion authority input and fail closed on mismatch.

### SCI-02 — Research evaluator is stateless per row while EA is single-position — CRITICAL

`evaluation.trade_outcomes()` maps every selected row directly to `long_r` / `short_r`. It does not maintain the EA state machine `FLAT → LONG/SHORT → EXIT`.

The production EA contract is one active position per symbol. Consecutive signals while a position is already open cannot be counted as independent new trades.

**Impact:** trade count, expectancy, PF, DD, Recovery Factor, Sharpe/Sortino, CVaR and downstream Monte Carlo input can diverge from the live EA distribution.

**Required repair:** one canonical event-driven research simulator must own WFA/CPCV/Tournament/Fresh realized R and enforce single-position semantics.

### SCI-03 — REVERSE_EXIT is absent from label/evaluation outcome path — CRITICAL

The promoted Strategy Champion has `InpExitReverseThreshold = 0.25`, but current `ModelLab/data/labels.py` and `ModelLab/research/evaluation.py` outcome logic only represents SL, TP and MaxHold/timeout. Reverse exit is not applied to the realized research trade path.

**Required repair:** canonical event-driven simulator must implement the current EA reverse-exit contract from the exact promoted Strategy authority.

## 3. Label / training objective defects

### SCI-04 — Label objective is not trading-utility objective — HIGH

Current labels compare counterfactual `long_r` and `short_r` over the horizon and assign SELL/SKIP/BUY from `min_edge_r` and `min_margin_r`. Model fitting then optimizes classification loss, while qualification optimizes realized trading utility such as expectancy, PF, DD, Recovery, stability and tail risk.

This is not future-feature leakage, but it is an objective mismatch: the model can improve classification of the ex-post best direction without improving the sparse execution decisions that determine trading KPI.

**Required repair:** retain the `[P(SELL), P(SKIP), P(BUY)]` runtime contract, but redesign target/loss/evaluation so training has an explicit utility-aware relationship to realized R/selectivity.

### SCI-05 — Structurally non-executable rows can still become actionable supervised targets — HIGH

Label construction currently operates on valid rows using SL/TP/MaxHold geometry, but it does not mask the complete live execution eligibility policy before assigning an actionable BUY/SELL target.

Rows blocked by live consensus/shock/spread/other immutable execution gates may therefore consume supervised model capacity even though the EA cannot enter there.

**Required repair:** preserve all valid rows as temporal context, but add canonical `execution_eligible` authority. Non-executable rows must not become actionable supervised targets/loss observations.

### SCI-06 — Temporal chronology gaps are destroyed after dropped labels — HIGH

`labels.build_labels()` drops invalid/ambiguous targets and then calls `reset_index(drop=True)`. This discards original source-row identity. Temporal sequence builders can then see rows separated by a dropped source observation as contiguous.

Tree families are not affected by sequence continuity, but GRU/LSTM/TCN/Transformer/PatchTST/iTransformer/TFT/MoE and temporal→tree hybrids can construct sequences across hidden gaps.

**Required repair:** preserve immutable `source_row_id`/source timestamp continuity before labeling; temporal sequence construction must reject sequences crossing dropped-row discontinuities.

## 4. KPI / ranking defects

### KPI-01 — Positive CVaR thresholds can invert intended tail-loss policy — CRITICAL CONFIG RISK

Canonical CVaR definition is daily aggregated R over the worst 5% trading days, and the gate direction is `higher`.

Therefore `CVaR >= +0.80R` literally requires the average of the worst 5% days to still be at least +0.80R. If the intended policy is "tail loss no worse than 0.80R", the correct signed threshold is approximately `>= -0.80R`, not `+0.80R`.

The uploaded last research run used positive CVaR thresholds and this materially contributed to Full-WFA failures.

**Required repair:** clarify UI wording/sign semantics and add configuration validation/examples. Do not silently reinterpret Owner-entered values.

### KPI-02 — Selection-score weights do not preserve longitudinal comparability — HIGH

`walk_forward_composite_score()` comments describe a 100-point base allocation, but actual non-risk component weights sum to 108 before Advanced Risk KPI are added. Every enabled risk KPI then adds weight 2 and the full vector is renormalized to 100.

Consequently enabling new KPI changes the effective weight of all existing metrics, so the same candidate can receive a lower `selection_score` without any change in its raw performance.

This is a ranking-contract defect, not a PASS/FAIL bypass: hard gates remain independent.

**Required repair:** define an explicitly versioned fixed-100 scoring schema. Adding/removing optional risk metrics must not silently rescale historical core components unless the score schema version deliberately changes.

### KPI-03 — Advanced statistical KPI are not sufficiently sample-aware — HIGH

PSR/DSR/CVaR/Sharpe/Sortino can become unstable or non-informative when a fold contains very few trades or very few active trading days. Current hard-gate handling does not consistently distinguish `INSUFFICIENT_EVIDENCE` from genuine bad model quality.

**Required repair:** define minimum evidence requirements per metric and expose `NOT_ENOUGH_EVIDENCE` separately from economic failure. Sample insufficiency may still fail promotion, but Scientist attribution must not call it model-quality failure.

### KPI-04 — Cheap Screen receives too much pressure from advanced risk KPI — MEDIUM/HIGH

Cheap Screen is intentionally reduced-fidelity. Metrics such as PSR/DSR/CVaR are least stable at small sample size, but they can influence candidate ranking before Full-WFA.

**Required repair:** Cheap Screen should prioritize integrity, gross economic/survival sanity, sample/coverage and relative ranking. Full risk-adjusted authority belongs to Full-WFA and downstream gates after sufficient evidence exists.

### KPI-05 — Fresh Forward default KPI is not a distinct production-grade final economic bar — HIGH

Current default Fresh Forward core gates are approximately PF 1.35 / Expectancy 0.15R / Recovery 2 / DD 12R. Champion Promotion primarily verifies upstream PASS plus artifact/integrity/parity; it does not independently impose a stricter production economic contract.

**Required repair:** explicitly define final production KPI authority at Fresh/Promotion. Do not rely on historical or hidden numbers.

## 5. CPCV / WFA / feature findings

### CPCV-01 — PBO is configured but disabled — MEDIUM

The CPCV profile contains `pbo_max = 0.2`, but `pbo_enabled = false` and status indicates no canonical strategy matrix yet. PBO therefore is not current hard authority.

**Required repair:** implement/validate the canonical strategy matrix before enabling PBO; do not expose PBO as active protection until the evidence is actually computed.

### WFA-01 — configured minimum train rows and wrapper authority require consolidation — LOW

The audit found a legacy path where WFA wrapper behavior may use a hard-coded minimum rather than the configured training minimum. It did not materially affect the inspected large dataset, but duplicate authority is unsafe.

**Required repair:** one canonical resolved minimum-training-row authority with a regression test.

### FEAT-01 — strategy rule signal has double exposure — DESIGN RISK

The model receives strategy-family/rule-derived features including `rule_meta_score`, and deployment later blends model direction with `rule_meta_score` again.

This is not look-ahead leakage, but it can make the model mostly reproduce the rule engine rather than contribute independent edge.

**Required experiment after parity repair:** ablate (A) rule features, (B) post-model rule blend, (C) both/current combinations and compare incremental OOF utility.

## 6. Parts currently considered structurally sound

The audit did not find an obvious closed-bar feature look-ahead in the reviewed feature path. Future data is used for target/outcome construction, not current-row feature construction.

The inspected WFA run used purge/embargo aligned to the 54-bar horizon, and chronological WFA / frozen-threshold principles remain directionally correct. CPCV 6C2=15 structure and downstream stage ordering are not the main defect; the problem is that the realized trade distribution entering those stages is not yet guaranteed to match the live EA execution state machine.

## 7. Mandatory repair order for the next scientific-workflow release

1. Build one canonical event-driven research execution simulator from exact promoted Strategy Champion authority.
2. Route WFA/CPCV/Tournament/Fresh realized trade outcomes through that simulator.
3. Preserve `source_row_id` and temporal continuity across label filtering.
4. Add `execution_eligible` target/loss masking without deleting context rows.
5. Redesign label/loss toward utility-aware training while preserving `[P(SELL),P(SKIP),P(BUY)]` inference contract.
6. Version and repair selection-score weighting.
7. Make Advanced KPI sample-aware and correct CVaR sign/UI semantics.
8. Re-tier KPI authority by fidelity: Cheap Screen → Full-WFA → CPCV → Tournament → MC → Fresh/Promotion.
9. Only after these repairs should more-agentic LangGraph Scientist optimization be trusted for real scientific search.

## 8. Release boundary

v1.3.1 closes CUDA/backend authority work only. These scientific findings are intentionally **not repaired inside v1.3.1** to avoid mixing a compute/runtime release with a large scientific-semantics rewrite.

Until the next repair release closes the blockers above, Real Model Research output may be used for debugging/research exploration but must not be presented as production-parity Model Challenger evidence solely because software acceptance passes.


---

## v1.3.2 closure status

The findings above remain immutable audit history. They are repaired by `ModelLab/docs/repairs/REPAIR_v1_3_2.md` and regression gate `R51_V132_SCIENTIFIC_WORKFLOW_REPAIR`.

- SCI-01: **CLOSED v1.3.2**
- SCI-02: **CLOSED v1.3.2**
- SCI-03: **CLOSED v1.3.2**
- SCI-04: **CLOSED/MITIGATED v1.3.2** by bounded utility-aware supervised weighting; endogenous reverse exit remains replay authority.
- SCI-05: **CLOSED v1.3.2**
- SCI-06: **CLOSED v1.3.2**
- KPI-01..KPI-05: **CLOSED v1.3.2**
- CPCV-01: **CLOSED v1.3.2** as optional cross-strategy PBO authority; OFF by default.
- WFA-01: **CLOSED v1.3.2**
- FEAT-01: **CLOSED v1.3.2** as explicit bounded ablation authority.

This closure does not convert external LangGraph/CUDA/MT5/ONNX runtime gates into PASS.
