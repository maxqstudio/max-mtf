# Strategy Optimizer V2

## Purpose

Strategy Optimizer is a **pre-model parameter search tool** for Max's existing EA `EA_v1_06/Max.mq5`. Strategy logic is fixed. During search Max deploys a byte-identical copy into the selected terminal data directory. When a champion is found, Max may change only the whitelisted optimized input default literals in that same EA, verifies the normalized strategy-logic hash did not change, deploys/compiles the updated EA, then stops. Max never synthesizes a replacement EA and never substitutes an unrelated terminal EA.

**Runtime naming authority:** canonical EA source/executable name is `Max.mq5` / `Max.ex5`. Optimizer runtime artifacts use the exact EA stem: `historical external: Max.xml` and `Max.set`. Round identity is stored in the job checkpoint/evidence directory, not encoded into the external MT5 filename. New runtime output must not emit the legacy `ComplexPolicy_ONNXReady_EA` or `MAX_StrategyOptimizer_*` names. Legacy historical evidence remains readable only for audit/recovery compatibility and is never bootstrap evidence for a new job.
It does not replace ModelLab validation and it does not choose one strategy family from seven.
The EA remains one system with all seven strategy families active:

1. Trend
2. Range
3. Breakout
4. Pullback
5. Session
6. Shock
7. Relative Value

The output is exactly one **strategy-parameter champion candidate** for a later Owner MT5 backtest that produces the training dataset consumed by ModelLab.

## Authority split

- **MT5 Strategy Tester** owns every market simulation, trade execution, optimization pass and native PF/RF statistic.
- **MT5 genetic fitness** is **Custom max**, driven by Max `OnTester()` arithmetic Mean R/trade, so the visible `Result` column represents Mean R. Weighted R is exported separately per pass through MT5 optimization frames and is a Python hard gate.
- **EA `OnTester()` / Custom** returns arithmetic Mean R/trade rebuilt from complete tester history after the pass is finished. Entry ownership is seeded by this EA's entry deals, exits are reconciled by position ID, and each denominator is the actual initial stop risk in account currency calculated from executed entry fill + initial historical entry-order SL + executed volume via `OrderCalcProfit()` (`DEAL_SL` fallback). Missing/invalid risk, non-finite values, accounting errors, or `R-accounted trades != STAT_TRADES` fail the pass closed. This Mean R is MT5 genetic fitness and one independent Python hard gate.
- **Python** owns orchestration, range compilation, report parsing and deterministic champion selection.
- **LLM Scientist V2** is advisory only. It may propose the next `start/step/stop` ranges after an unsuccessful MT5 round. It cannot change parameters, KPI gates, strategy count, EA logic, dates, symbols or validation policy.
- **ModelLab** remains the authority for later WFA/CPCV/Tournament/Monte Carlo/Fresh/Champion validation. None of those stages run inside Strategy Optimizer.

## Hard target

A pass is eligible only when all are true:

- Profit Factor >= 1.00
- Recovery Factor >= 0.00
- Mean R >= 0.00 R/trade
- Weighted R >= 0.00, where `Weighted R = sum(net P/L) / sum(actual initial stop risk)`
- AUTO minimum closed trades from exact optimization range; H1 baseline = 20 trades/month, timeframe-scaled monthly rate rounded up to integer, then final exact-range requirement rounded up

The thresholds are inclusive exactly as locked by Owner. NaN/non-finite metrics, missing metrics, malformed reports, and passes below the frozen AUTO minimum-trade requirement are ineligible. Threshold relaxation, score compensation, and fallback candidates are forbidden.

Among eligible passes, deterministic ranking is:

1. Weighted R descending
2. Mean R descending
3. Profit Factor descending
4. Recovery Factor descending
5. MT5 pass number ascending

## V2 adaptive rounds

Default maximum: **3 MT5 rounds**.

- Round 1 uses deterministic broad ranges compiled from `ABSOLUTE_BOUNDS`.
- If no champion exists, Scientist may propose a new range set from aggregate MT5 result evidence.
- Every Scientist proposal is passed through `validate_search_space()` before use.
- If Scientist is disabled, unavailable, malformed or outside bounds, deterministic refinement around the best near-miss is used instead.
- A round is never skipped into Python backtesting; every candidate search is executed by MT5.
- V2 stops as soon as a completed MT5 round contains at least one eligible pass, applies the champion parameter defaults to the existing EA, deploys/compiles it, writes audit evidence, and stops. Owner manually runs the training-data backtest afterward.

## Search-space contract

V2 optimizes only existing EA inputs:

- seven family weights
- entry threshold
- reverse-exit threshold
- minimum consensus
- SL ATR
- TP ATR
- max hold bars
- shock halt ATR
- Relative Value lookback
- minimum Relative correlation

All seven family weights have strictly positive minimum bounds. Session hours, risk percentage, ONNX settings and strategy formulas remain fixed in V2.

## Seven-family fail-closed rules

During MT5 optimization, EA initialization fails if:

- `InpAllowLiveTrading=false` in tester mode,
- `InpConfirmSymbol` is blank,
- Confirm Symbol equals the main symbol,
- Confirm Symbol cannot be selected by MT5,
- any of the seven family weights is `<= 0`.

This prevents an optimization run from silently becoming a six-family system.

## MT5 native configuration

Default V2 mode:

- `Optimization=2` (Fast Genetic)
- `OptimizationCriterion=6` (Custom max)
- `Result` in MT5 therefore displays Max `OnTester()` Mean R
- Recovery Factor remains a separate independent hard gate from the dedicated MT5 Recovery Factor statistic
- `ForwardMode=0`
- `UseCloud=0`
- tick model default: 1 Minute OHLC

Slow complete optimization is available in UI but is not the default.

## Artifacts per run

`ModelLab/runtime/strategy_optimizer_runs/<job_id>/`

- `historical external: request.json`
- `historical external: status.json`
- `metaeditor_compile.log`
- `historical external: round_N.ini`
- `historical external: reports/round_N.xml`
- `historical external: champion.json` when found
- `historical external: ea_champion_apply.json` when found
- `owner_acceptance/evidence/strategy_optimizer/<job_id>/champion/ea_before_champion.mq5`
- `owner_acceptance/evidence/strategy_optimizer/<job_id>/champion/ea_after_champion.mq5`

No automatic backtest or dataset generation follows. The Owner manually runs the updated EA in MT5 to generate training data, then explicitly starts Research.


## v0.8.6 history-rebuild R accounting

The v0.8.5 event-driven R accumulator is superseded. MQL5 does not guarantee trade-transaction arrival priority, therefore `OnTradeTransaction()` cannot be used as scientific fitness state. v0.8.6 reconstructs the full position ledger in `OnTester()` from `HistorySelect()` after the pass completes.

Contract:

- seed owned positions only from entry deals matching main symbol + `InpMagic`;
- use `DEAL_POSITION_ID` as the ownership key after entry;
- include all entry/exit deals for the owned position when summing net P/L;
- initial risk uses actual entry fill, initial historical order SL, executed entry volume and `OrderCalcProfit`;
- partial entry fills accumulate risk;
- net P/L includes profit, commission, swap and fee;
- exit deal magic is not required after ownership was established by the entry;
- `OnTradeTransaction()` does not mutate Mean-R/Weighted-R state;
- zero accounting errors and exact `STAT_TRADES` parity remain mandatory.

This specifically repairs the all-pass `-1e9` sentinel failure observed in real MT5 optimization while preserving the fail-closed contract.

## v0.8.5 strategy geometry + Weighted R authority

- Frozen Optimizer KPI V2 contains independent PF, RF, Mean R, Weighted R, and AUTO minimum-trade gates.
- Every MT5 pass emits `Mean R`, `Weighted R`, `sum_net`, `sum_initial_risk`, MT5 trade count, R-accounted trade count, accounting-error count, and run nonce through optimization frames. Terminal-side `Max_metrics.csv` is hash-sealed with the XML evidence.
- Python recomputes Weighted R and rejects missing/extra pass rows, nonce mismatch, hash mismatch, non-finite values, non-positive summed risk, accounting errors, or trade-count mismatch. XML-only legacy evidence cannot produce a v0.8.6 Champion.
- Champion `SL_ATR`, `TP_ATR`, and `MaxHoldBars` become the single execution-geometry authority inherited by Max EA, uniform CP32 metadata, Python labels and Model Research. Mixed/stale geometry fails closed.
- Adaptive lot/risk/equity remains EA/system-layer authority and is excluded from model features and training targets.

## Explicit non-goals

V2 does **not** run:

- walk-forward validation,
- CPCV,
- Tournament,
- Monte Carlo,
- locked/fresh Forward,
- model training,
- ONNX promotion.

A Strategy Optimizer champion is a **candidate strategy configuration**, not a validated trading strategy.


## Owner-runtime diagnostics contract

- Source authority is the existing package `EA_v1_06/Max.mq5`; arbitrary terminal EA selection is forbidden.
- START freezes its pre-optimization SHA-256 and deploys a byte-identical tester copy. Champion application may mutate only the whitelisted optimizer input defaults; pre/post EA copies and hashes are retained in evidence.
- MetaEditor process exit code is diagnostic only. Compile PASS requires an explicit MetaEditor `Result: 0 errors, ...` summary plus the expected EX5 artifact. A non-zero process code cannot by itself convert a zero-error compile into FAIL.
- `Confirm Symbol` is shown as **Relative reference symbol**. It exists only for the seventh strategy family, Relative Value.
- Every run publishes diagnostics under `owner_acceptance/evidence/strategy_optimizer/<job_id>/`, including request/status, compile command/context/log, worker stdout/stderr, MT5 round evidence and champion artifacts.
- A failed run writes `historical external: diagnostic.json` + `diagnostic.txt`; the UI surfaces the diagnostic and evidence location directly.

## R4 navigation and lifecycle separation

Strategy Optimizer is intentionally outside the ModelLab Research lifecycle. It is the final sidebar item after `Advanced`, separated visually from Research/Data/validation pages. Selecting it changes the fixed footer authority from `START AUTO RESEARCH` to `START AUTO OPTIMIZER`.

The label change is not cosmetic routing: Research and Optimizer use different handlers, workers, state and evidence. The optimizer page no longer contains a duplicate START/STOP row. While either lifecycle is active, the other start authority is disabled. On the Strategy Optimizer page the app bar reports Optimizer status/round rather than Research status.

Canonical repair note: `ModelLab/docs/repairs/STAGE12_STRATEGY_OPTIMIZER_V2_R4_NAV_LIFECYCLE.md`.

## v0.7.7 UI/runtime authority repair

- Research and Strategy Optimizer footer lifecycle controls are separate mounted authorities. Navigation changes only which control is visible, preventing stale `START AUTO RESEARCH` / `START AUTO OPTIMIZER` cross-wiring while keeping Scientist chat/draft mounted.
- Optimizer KPI is editable on the Strategy Optimizer page and frozen into each request: PF, RF, Expectancy R, and H1 minimum trades/month. Timeframe scaling and integer round-up remain deterministic.
- Strategy Optimizer contains a live **Scientist Optimizer Report** showing the latest bounded range proposal/fallback and its model provenance. Scientist receives the frozen Optimizer KPI and minimum-trade requirement; it cannot alter them.


## v0.7.8 canonical-EA + single-click lifecycle repair

- v0.7.7 Owner-EA selector interpretation is superseded. Strategy Optimizer is coupled to the existing package `EA_v1_06` input/search-space contract.
- Request freeze stores canonical EA path identity + SHA-256. Worker deployment must remain byte-identical.
- MetaEditor process return code is diagnostic-only; explicit compile summary with zero errors plus fresh EX5 owns compile PASS.
- Navigation refreshes `workspace` and `contextual_lifecycle` keyed fragments atomically. Scientist is excluded from that rerun so chat/draft state stays mounted.
- `START AUTO OPTIMIZER` creates the optimizer job in the same click callback and immediately reruns the lifecycle/workspace fragments. No second click is part of the contract.

## v0.7.9 native MT5 task transparency

One Max Strategy Optimizer **round** launches one native MT5 optimization session. When `Fast genetic` is selected, MetaTrader owns population generation, job batching, and distribution of native optimization passes to local tester agents. Therefore the `Tasks / Passed` counters shown in MT5 Agents are **not** additional Max rounds and are not generated one-by-one by the Max Python orchestrator.

Max records the raw Cartesian search-space cardinality only as operator/scientist context. It must never be presented as the expected MT5 genetic task count. For the canonical broad Round-1 space, the complete grid is intentionally enormous; this is why Fast Genetic is the practical native method. Later Max rounds only occur after the previous native MT5 round completes without an eligible Strategy-Optimizer champion.

## v0.8.0 Result / RF + champion-to-EA stop repair

- Native MT5 genetic fitness is **Custom max** (`OptimizationCriterion=6`). The MT5 `Result` column is Max arithmetic Mean R returned by `OnTester()`. Weighted R comes only from verified frame sidecar evidence; Recovery Factor is never inferred from `Result`.
- Max `OnTester()` remains the independent **Expectancy R** metric in the MT5 `Custom` statistic. All-sentinel custom results fail closed and cannot trigger Scientist refinement or champion promotion.
- Tester deal accounting explicitly selects deal history before reading deal properties and anchors entry position identity to the actual entry deal with fallback.
- On champion selection, Max changes only the 16 whitelisted optimized input defaults in the existing `EA_v1_06`. A normalized strategy-logic hash must remain unchanged.
- Max deploys/compiles that updated EA and then **stops**. It does not auto-run final backtest, does not auto-generate the dataset, and does not auto-start Research. The Owner performs the training-data backtest manually and starts Research explicitly.


## v0.8.1 Atomic round/resume authority

Each MT5 round owns a durable `historical external: round_N_state.json` with PREPARED -> MT5_RUNNING -> MT5_COMPLETE -> REPORT_READY -> PARSED phases. Once MT5 has been launched for a round, worker restart/resume must never blindly relaunch that round. Missing report output is recoverable `WAITING_FOR_REPORT`; Max scans the selected terminal `MQL5/Profiles/Tester` for XML whose internal SpreadsheetML Title matches the frozen EA, symbol, timeframe and date range. The Owner may resume after manual/exported XML appears. Legacy v0.8.0 recovery is restricted to the original default all-parameter Round-1 space.

Owner parameter-selection is also frozen per request. Only selected inputs get MT5 `Y` optimization flags. Unselected inputs use the current EA default with `N`, and Scientist may only narrow the selected universe.

## v0.8.2 recovery UI and Scientist provenance

Recovery/resume actions may be initiated from Streamlit script or fragment bodies, so they use a legal app-scope rerun after job creation. Keyed fragment reruns are reserved for widget callbacks. Scientist Optimizer Report is bound to the frozen Optimizer request: Scientist OFF is reported as `DETERMINISTIC_ONLY`; a requested-but-unavailable/failed Scientist is `DETERMINISTIC_FALLBACK` with an explicit reason/error provenance. `NO_CHAMPION` evidence always states the frozen KPI thresholds used. Legacy report recovery is not offered after already-consumed evidence reaches a terminal `NO_CHAMPION` or `CHAMPION_FOUND` state.


## v0.8.4 durable settings and canonical runtime filenames

Strategy Optimizer operator settings are durable across page navigation, fragment reruns, browser reload and app restart. Missing widget keys caused by Streamlit page cleanup are not deletion requests: a durable shadow-state retains them, while explicit live values overwrite normally. Before Strategy Optimizer renders, missing `strategy_opt_*` keys are rehydrated from that durable state. Active jobs remain isolated from later edits through the frozen request snapshot.

Canonical external MT5 names are `Max.set` and `historical external: Max.xml`, matching `Max.mq5` / `Max.ex5`. Each round still has its own internal `historical external: round_N_state.json` and `evidence/round_NN/` copy. Freshness is proved by the pre-launch fingerprint changing, so round suffixes are unnecessary. A brand-new job excludes `historical external: Max.xml`, legacy `historical external: Max_R<N>.xml`, and `MAX_StrategyOptimizer_*` from bootstrap evidence.

## v0.8.3 champion-stop automatic round lifecycle

`START`/`RESUME` consume compatible existing XML first. Resume never reruns the checkpointed native MT5 round. If the parsed evidence already contains an eligible winner, Max applies only whitelisted optimized defaults to `EA_v1_06`, compiles/deploys that same EA, and **stops immediately**. Scientist and all later optimization rounds are forbidden after a winner exists.

If the parsed round has no eligible winner and `round < frozen max_rounds`, Max automatically refines the bounded search space and launches the next native MT5 round. Scientist is a next-range adviser only on this no-winner path: OFF uses `DETERMINISTIC_ONLY`; ON with a successful real provider call persists `SCIENTIST_PROPOSAL` and deterministic accept/reject evidence; provider/model/call failure uses `DETERMINISTIC_FALLBACK` with an explicit reason. If no Champion exists after the last allowed round, Max stops at `NO_CHAMPION_MAX_ROUNDS`. There is no manual `CONTINUE NEXT ROUND` authority.

Optimizer operator settings are durable, while every active run reads only its frozen request snapshot. The frozen snapshot contains market/date/tick model, KPI and exact-range trade requirement, selected optimization parameters, maximum rounds, native optimizer mode, canonical EA identity and non-secret Scientist route config. Credential material remains outside request/evidence storage.
## v0.8.3 report freshness and eligibility evidence repair

SpreadsheetML `<Created>` is retained only as provenance. It is **not** a reliable UTC freshness clock across MT5 terminals/timezones and must not decide whether an XML belongs to a newly launched Max round.

For every newly launched MT5 round Max now:

1. snapshots all currently compatible report file fingerprints before launch,
2. requests a unique round report filename,
3. after MT5 returns, requires internal `EA + Symbol + Timeframe + From + To` identity **and** a new/changed file fingerprint, preferring the unique requested filename when present,
4. waits in the existing recoverable report state rather than reusing stale compatible XML.

Each parsed round persists `report_sha256`, `report_selection_mode`, parsed-pass count, eligible-pass count, frozen KPI thresholds and per-gate counts. The UI surfaces the exact report name, parsed passes, eligible count and SHA prefix. `eligible_passes > 0` without a deterministic Champion is an invariant failure; it can never be treated as a normal no-winner round.

`Expected Payoff` remains an MT5 informational statistic. Strategy Optimizer **Expectancy R** is the XML `Custom` value returned by Max `OnTester()`. Therefore a frozen gate such as `Expectancy R >= -0.01` correctly accepts `Custom=-0.000986...`; the sign comparison is not relaxed or rewritten.


### v0.8.8 frame identity rule

`FrameNext.pass` is an opaque unsigned 64-bit optimization-frame identifier. It is preserved as text for provenance only. `Max_metrics.csv` carries `FrameInputs` and Python joins Mean-R/Weighted-R evidence to `historical external: Max.xml` by the canonical Strategy Optimizer parameter vector, with Mean-R/trade-count/net-profit parity checks. The SpreadsheetML display `Pass` column is never assumed to share the frame-pass namespace.


### v0.9.0 historical Champion Tester preset parity; v0.11.0 supersession

v0.9.0 introduced transactional parity for the then-direct Champion commit. **v0.11.0 supersedes automatic Strategy promotion.** A deterministic eligible Optimizer winner now terminates as `STRATEGY_CHALLENGER_FOUND` and creates a human-readable `Max_Challenger_<code>.mq5` + fixed `.set` + KPI/setup metadata while canonical `EA_v1_06/Max.mq5`, canonical Tester `Max.set`, and Python strategy authority remain unchanged.

Only explicit Owner **PROMOTE TO STRATEGY CHAMPION** may perform the transactional commit: the selected Challenger parameters are applied to canonical `Max.mq5`; canonical Tester `Max.set` is rewritten with every Optimizer-owned parameter fixed (`N`); EA↔set parity is verified; the EA compiles/deploys; Python strategy authority is updated to the promoted SL/TP/MaxHold geometry; and the previous Champion is preserved as a newly coded Strategy Challenger with available KPI/setup lineage. Any failure restores the pre-promotion EA source, prior `Max.set` (or absence), prior strategy authority, and registry state.

### v0.8.9 frame completeness / MT5 cache rule

Because Weighted R is transported through `FrameAdd` and bound with `FrameInputs`, cached optimization results are not sufficient scientific evidence: MT5 can reuse cached pass results without replaying the frame handlers. The canonical EA therefore declares `#property tester_no_cache`. Missing frame evidence is row-local incompleteness: the row is never Champion-eligible, and any incomplete row that already clears Trades/PF/RF/Mean-R blocks promotion until revalidated. Such contenders remain valid refinement evidence only. Extra sidecar vectors that do not exist in the XML remain fail-closed provenance errors.

