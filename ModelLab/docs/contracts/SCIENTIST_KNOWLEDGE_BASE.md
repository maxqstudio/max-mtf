# Scientist Knowledge Base — Max Research Agent

**Schema:** `MAX_SCIENTIST_KNOWLEDGE_V1`  
**Knowledge revision:** **SCIENTIST_KNOWLEDGE_MAX_MTF_V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR**  
**Scientific authority:** **Max MTF v2.0.1 — canonical MTF-1 data foundation plus shared MODEL_TRAINING_METHOD_CONTRACT_V1 for Manual, AUTO, LLM Scientist and Scientist Chat**  
**Control revision:** **Research Control R1**

This file is generated from the machine-readable knowledge database and canonical source/doc manifests. Do not hand-edit generated facts; update source/contracts then regenerate.

## E2E workflow

### 0. STRATEGY_OPTIMIZER

Upstream MT5 EA parameter search that produces Strategy Challengers; only explicit Owner promotion changes the current Max_MTF.mq5 Strategy Champion.

**Authority:** `MT5_NATIVE_PARAMETER_SEARCH_SEPARATE_FROM_RESEARCH`

**Core contracts:**
- This is not Discovery and does not run WFA/CPCV/Tournament/Monte Carlo/Fresh Forward
- PF >= 1, RF >= 0, Mean R >= frozen threshold, Weighted R >= frozen threshold
- AUTO minimum trades uses H1 baseline 20 trades/month, timeframe sqrt scaling, integer round-up monthly rate and integer round-up exact-range requirement
- MT5 genetic fitness is Custom max from Max OnTester arithmetic Mean R, so the MT5 Result column is Mean R; Weighted R = sum(net P/L)/sum(initial risk) is transported per pass through MT5 optimization frames and is an independent Python hard gate; Recovery Factor remains an independent hard gate sourced from the dedicated MT5 statistic
- when an eligible winner is found the Optimizer creates a human-readable Strategy Challenger EA + fixed .set + metadata bundle, leaves current Max_MTF.mq5/Max_MTF.set/strategy authority unchanged, enters STRATEGY_CHALLENGER_FOUND, then STOPS
- Owner manually runs the MT5 backtest to write training data, then explicitly STARTs ModelLab Research; Optimizer never auto-backtests, auto-generates the dataset, or auto-starts Research
- one Max round launches one native MT5 optimization; MT5 owns genetic population/job/task scheduling across tester agents, so Tasks/Passed counts are native passes inside the round rather than extra Max rounds
- each Optimizer round has durable PREPARED/MT5_RUNNING/MT5_COMPLETE/REPORT_READY/PARSED checkpoints; START/RESUME process compatible existing evidence first and Resume never reruns the checkpointed MT5 round
- after any parsed round with no eligible winner and remaining frozen round budget, Optimizer automatically performs bounded refinement and launches the next native MT5 round; no manual Continue authority exists
- Scientist is only next-range advisory on that automatic no-winner refinement: OFF=DETERMINISTIC_ONLY; actual successful LLM proposal=SCIENTIST_PROPOSAL with persisted deterministic acceptance/rejection; requested provider/model/call failure=DETERMINISTIC_FALLBACK with explicit reason
- if existing evidence already yields an eligible winner, Scientist is never called and no next round is launched; Strategy Challenger registration is an immediate hard stop and promotion remains explicit Owner authority
- if the frozen maximum round count is exhausted without a winner, terminal state is NO_CHAMPION_MAX_ROUNDS
- Windows atomic writes use unique same-directory temp files plus bounded WinError 5/32 retry, and launcher PID metadata is separated from worker-owned status.json
- MT5 SpreadsheetML Created is provenance only, not round-freshness authority; every launched round snapshots compatible report fingerprints before MT5 starts, prefers its unique requested report name, and accepts only a new/changed compatible XML while still enforcing internal EA+Symbol+Timeframe+From+To identity
- canonical runtime naming is Max_MTF.mq5/Max_MTF.ex5 with Max_MTF.xml and Max_MTF.set; round identity lives in checkpoint/evidence rather than R1/R2/R3 filename suffixes; new runtime flows never emit legacy ComplexPolicy_ONNXReady_EA or MAX_StrategyOptimizer_* names
- a brand-new Optimizer job may bootstrap only from compatible external/manual MT5 XML that has an explicitly paired <stem>.metrics.csv Weighted-R sidecar; XML-only legacy evidence is not v0.8.6 Champion-compatible; prior Max-generated reports remain usable only through the owning job checkpoint/recovery path
- Strategy Optimizer operator settings use durable shadow-state so Streamlit hidden-page widget cleanup cannot erase saved strategy_opt_* values; missing keys are rehydrated before page render while active jobs remain frozen
- round evidence persists report SHA, selection provenance, parsed-pass count, eligible-pass count, frozen KPI thresholds and per-gate counts; eligible_passes > 0 without a deterministic Strategy Challenger selection is a hard invariant failure rather than a no-winner continuation
- active Optimizer request freezes KPI, search-space/selected parameters, maximum rounds, native optimizer mode, date/symbol/timeframe and non-secret Scientist routing; later UI edits apply only to a new run

**Evidence:** `historical external: runtime/strategy_optimizer_runs/*/strategy_challenger.json`, `EA_v2_00/challengers/Max_Challenger_*.mq5`, `EA_v2_00/challengers/Max_Challenger_*.set`, `ModelLab/runtime/strategy_challenger_registry.json`

### 1. DATA_QUALITY

Prove the CP32 dataset is structurally valid and same-broker source continuity is verified before research.

**Authority:** `DETERMINISTIC_FAIL_CLOSED`

**Core contracts:**
- Required CP32_V1 columns and 32 features
- one symbol/timeframe only
- no duplicate identity rows
- finite features; valid OHLC/ATR/decision quotes
- ask >= bid; zero spread is warning, not hard failure
- broker reconciliation must be verified
- source-backed missing bars or dataset-only timestamps block readiness
- repair may use verified MT5 writer data only; no interpolation/forward-fill authority

**Evidence:** `data-quality report`, `historical external: dataset_quality_context.json`

### 2. RESEARCH_PLAN_FREEZE

Freeze chronology, hardware/data capacity, topology/family search authority and immutable research contract.

**Authority:** `DETERMINISTIC`

**Core contracts:**
- Discovery < Tournament < Fresh/Forward windows must be chronological and non-overlapping
- Dynamic Capacity Governor admits temporal candidates by min(LEGAL, RESOURCE, SCIENTIFIC) actual-parameter-count authority; model-size priority is search preference only
- current Owner config is distinct from frozen active research_plan
- AUTO and MANUAL proposal authorities are explicit and provenance-recorded

**Evidence:** `historical external: research_plan.json`, `historical external: hardware_profile.json`, `historical external: dataset_capacity_profile.json`, `historical external: factory_manifest.json`

### 3. DISCOVERY_FULL_WFA

Generate/evaluate candidate hypotheses without opening downstream holdouts.

**Authority:** `AUTO: Factory + deterministic Discovery with optional LLM proposals; MANUAL: Owner exact candidates. PASS/FAIL always deterministic.`

**Core contracts:**
- Topology allocation already supports Single/Hybrid priority including 0=single-only, 1=hybrid-only and intermediate percentages/AUTO allocation
- Per-family Small/Balanced/Large priority biases search location inside dynamic capacity and never hard-slices or widens executable ceilings
- Fidelity cheap screen may allocate compute but can never qualify a candidate
- Only Full chronological WFA can qualify a candidate for Pool
- Policy Discovery/window discovery/experiment blocks/research memory are existing Discovery capabilities when enabled
- LLM proposals never own admission or PASS/FAIL
- Discovery qualification uses gate_kpis.discovery; thresholds are frozen with the Factory scientific contract
- Research AUTO minimum trades uses H1 baseline 8 trades/month with timeframe scaling and integer round-up

**Evidence:** `historical external: research_runs/*/cv_leaderboard.json`, `all_trials.jsonl`, `historical external: failure_topology.json`, `historical external: research_memory.json`

### 4. POOL

Freeze WFA-qualified candidates before downstream validation.

**Authority:** `DETERMINISTIC`

**Core contracts:**
- Only independently revalidated Full-WFA PASS candidates enter
- AUTO Pool authority is exactly 12 candidates
- pool evidence plus Discovery/Tournament/refit-history snapshots are hash-sealed before CPCV
- CPCV results cannot retroactively tune active Discovery

**Evidence:** `historical external: candidate_pool.json`, `historical external: factory_manifest.json`

### 5. CPCV

Robustness qualification on purged combinatorial partitions after Pool freeze.

**Authority:** `DETERMINISTIC_HARD_GATE`

**Core contracts:**
- Finalist ranking is frozen from WFA OOF evidence before CPCV opens
- exactly 15 purged+embargoed splits for N=6,k=2; CPCV cannot be disabled
- purge_bars and embargo_bars must each be >= label horizon
- 5 canonical reconstructed chronological paths feed path-dependent Advanced KPI
- DL/hybrid fixed seed confirmation = 42 -> 11 -> 77; all required seeds PASS; progressive stop on failure; no seed mining
- CPCV hard gates come from gate_kpis.cpcv and cannot be offset by ranking score
- PBO is CPCV-only and optional by default. v1.3.2 can compute cross-strategy CSCV-style PBO from the six-group CPCV OOS expectancy matrix when enough finalists exist; candidate-local pseudo-PBO remains forbidden. If Owner enables the hard gate and matrix evidence is insufficient, CPCV fails closed.

**Evidence:** `historical external: cpcv_finalist_plan.json`, `historical external: cpcv_qualification_evidence.json`, `historical external: cpcv_survivors.json`

### 6. TOURNAMENT

Apply frozen Tournament hard eligibility to every CPCV survivor, then rank PASS survivors; Tournament is not the untouched Fresh/OOS validation stage.

**Authority:** `DETERMINISTIC_HARD_GATE`

**Core contracts:**
- Tournament does not select a single winner; every KPI survivor proceeds
- stage verifies CPCV terminal seal and exact survivor identity
- stage uses the Tournament snapshot frozen before downstream validation
- base threshold or frozen CP_POLICY_V1 is replayed exactly
- Tournament eligibility uses gate_kpis.tournament; temporal/regime/stress evidence cannot be rescued by ranking
- all hard-gate survivors proceed; Tournament ranking does not impose Top-K elimination

**Evidence:** `tournament_immutable.csv`, `historical external: tournament_leaderboard.json`, `historical external: tournament_survivors.json`

### 7. MONTE_CARLO

Bootstrap Tournament trade outcomes and reject candidates whose robust tail distribution violates survival gates.

**Authority:** `DETERMINISTIC_HARD_GATE`

**Core contracts:**
- Tournament terminal seal and exact survivor↔trade-return set are verified before simulation
- minimum 100 simulations
- Monte Carlo uses gate_kpis.monte_carlo independently: tail PF/expectancy/recovery, P95 DD, and configured probability loss/ruin/survival
- all Monte-Carlo survivors preserve model/seed/threshold/policy identity and proceed to Forward
- terminal Monte Carlo evidence is hash-sealed

**Evidence:** `historical external: monte_carlo_evidence.json`, `historical external: monte_carlo_survivors.json`

### 8. FRESH_FORWARD

Evaluate frozen survivors on new/locked Fresh Forward data that was not used for selection.

**Authority:** `DETERMINISTIC_HARD_GATE_NO_TUNING`

**Core contracts:**
- Fresh/Forward evidence is not a tuning input for the same snapshot
- Fresh start boundary and pre-Forward refit history are frozen before OOS
- each Fresh extension must pass canonical Data Quality and same-symbol/timeframe authority
- committed Forward checks are append-only and individually sealed
- insufficient sample waits for new data rather than fabricating PASS
- every Monte-Carlo survivor is evaluated; Fresh Forward uses gate_kpis.fresh_forward independently and only PASS candidates may be ranked for Champion
- sufficient sample with zero PASS survivors is terminal for that Factory, not a fake wait state
- no runner-up substitution after a failed Forward candidate unless an explicit future contract says otherwise

**Evidence:** `forward_immutable_*.csv`, `historical external: forward_evidence_*.json`, `historical external: forward_leaderboard_*.json`, `historical external: forward_check_*_terminal_seal.json`

### 9. CHAMPION

Select top-ranked Forward PASS candidate, export executable ONNX runtime and verify parity.

**Authority:** `DETERMINISTIC_SELECTION_AND_RUNTIME_GATE`

**Core contracts:**
- Champion adds no new market/backtest dataset test; it verifies gate_kpis.champion_promotion
- Forward PASS precedes ranking
- Champion is the exact top-ranked Forward PASS identity and final fit uses only frozen pre-Forward history
- runtime manifest locks CP32 feature order and SELL/SKIP/BUY class order
- policy-qualified Champion exports a separately hashed CP_POLICY_V1 artifact
- ONNX parity tolerance comes from acceptance.max_onnx_abs_error
- FACTORY_WINNER_RUNTIME_BLOCKED means research selection passed but runtime export/parity failed; do not rerun research to hide a runtime defect
- Model Research outputs Challenger artifacts first; it never self-promotes a research winner into Production Champion
- v0.10.0 Challenger filenames are human-readable family+UTC identities; hash remains integrity evidence only, never operator-facing filename identity
- Owner promotion is explicit from the Champion registry after existing deterministic parity/test/shadow/promotion gates pass
- Model Challenger promotion is independent from Strategy Challenger promotion; model promotion cannot change SL/TP/MaxHold or Strategy execution geometry

**Evidence:** `historical external: champion.json`, `historical external: champion_runtime/runtime_manifest.json`, `historical external: champion_terminal_seal.json`, `historical external: factory_manifest.json`

## Canonical model training method

**Schema:** `MODEL_TRAINING_METHOD_CONTRACT_V1`  
**Authority:** `SINGLE_CANONICAL_TRAINING_METHOD_AUTHORITY`

This single contract is shared by Manual, AUTO deterministic planning, Factory Director, round Scientist, Scientist Chat and acceptance tests.

## KPI Scientist interpretation policy

**Authority:** `ADVISORY_INTERPRETATION_ONLY_LIVE_GATE_KPIS_REMAIN_RUNTIME_AUTHORITY`

### Principles
- Current gate_kpis are runtime authority; enabled=true describes current Owner config, not proof that the metric is scientifically well placed.
- Do not copy one KPI set across gates. Each gate answers a different scientific question.
- Do not enable many correlated risk metrics merely because they exist. Distinguish hard gates from diagnostics and preserve Discovery diversity.
- Never recommend lowering a frozen active-generation threshold after seeing its result. Changes apply only to a new configuration revision/generation.
- Use exact metric units. Do not silently convert percentage drawdown policy into R drawdown or vice versa.

### Gate roles

- **DISCOVERY** — Can a candidate survive inexpensive screening and full chronological 3-fold WFA with enough trades and acceptable fold consistency?
- **CPCV** — Does the frozen candidate remain robust across purged combinatorial partitions and reconstructed paths?
- **TOURNAMENT** — Which CPCV survivors remain eligible under the frozen Tournament evaluation and how should PASS survivors be ranked?
- **MONTE_CARLO** — Does the candidate survive adverse resampling/path realizations?
- **FRESH_FORWARD** — Does the frozen survivor generalize on untouched Fresh data without same-snapshot tuning?
- **CHAMPION** — May an upstream PASS candidate be promoted as an executable artifact?

## Existing Max capabilities — novelty guard

- **DATA_QUALITY_CP32** — CP32 schema, physical integrity, feature health, market sanity and broker reconciliation gate research. v0.11.1 stages Data Quality as local/exact-SHA cached audit first: AUDIT and initial Auto Research preflight never open MT5; PASS proceeds directly to Research, while a repairable FAIL alone enters MT5 verify/repair. The repair stage uses the same verified broker/feed, dedicated training-enabled Max_MTF_GapRepair.set, preserves MT5 UTF-16/UTF-8 preset encoding, verifies missing=0 afterward, and caches that broker proof only for the exact repaired CSV SHA. v0.9.1 first-write-wins EA repair remains the writer authority; interpolation/synthetic rows remain forbidden.
- **ONNX_RUNTIME_TRADE_AUDIT** — v0.9.1 EA runtime exposes the complete deployable tree/temporal model-family identity for Champion and Shadow, validates hybrid temporal→tree topology without changing tensor/decision authority, writes actual Max-owned MT5 Champion deals to Max_MTF_Champion_Trades.csv, and writes non-executing Shadow entry candidates with executed=0 to Max_MTF_Shadow_Trades.csv. Optimizer and gap-repair presets disable both audit writers; OnTester history rebuild remains the only optimizer R-fitness authority.
- **CHALLENGER_LIFECYCLE** — Model lifecycle: v1.3.3 enforces Factory-winner retention end-to-end. Every sealed LangGraph AUTO FACTORY_WINNER must be registered as a persistent ELIGIBLE_CHALLENGER before terminal success. Registration is append/retain and idempotent; later winners never delete/replace older Challengers and PROMOTED status survives replay. Model Champion still requires explicit Owner promotion after deterministic promotion gates PASS. Factory/LangGraph has no promotion authority.
- **GOLDEN_RESEARCH_E2E** — v1.2.5 keeps E2E_WORKFLOW_TEST_V1 sandbox-only, preserves separated Model/Strategy authority pages and 1:1 Forward-to-Challenger KPI evidence, and adds verified current Strategy Champion KPI evidence from Owner XML + Weighted-R sidecar. Synthetic sandbox-only promotion proofs remain explicitly labelled SYNTHETIC_E2E; production broker reconciliation and promotion KPI authority are unchanged. E2E artifacts are never production scientific evidence.
- **STRATEGY_CHALLENGER_LIFECYCLE** — v0.11.0 separates Strategy Optimizer winner from current Strategy Champion. Eligible winners become human-readable Max_Challenger_STRAT-<UTC>-R<round>-P<pass>.mq5 + fixed .set + metadata with PF/RF/Mean R/Weighted R/Profit/Trades and exact setup. Current Max_MTF.mq5 remains unchanged until explicit Owner promotion. Promotion atomically commits Max_MTF.mq5, canonical Max_MTF.set, compile/deploy and Python strategy authority while demoting the prior Champion to a new Challenger. Only non-Champion Challengers may be deleted; audit tombstones remain.
- **AUTO_AND_MANUAL_RESEARCH** — AUTO Factory and Owner-exact MANUAL Research are explicit proposal authorities; deterministic validation remains mandatory.
- **TOPOLOGY_ALLOCATION** — Single/Hybrid candidate allocation already exists as a 0.00..1.00 Owner priority with single-only, hybrid-only and mixed allocations.
- **FAMILY_SIZE_PRIORITY** — Per-family Small<->Large priority biases deterministic search inside dynamic capacity; it is not an executable hard-bound slice.
- **MODEL_SIZE_ADVISOR** — v1.4.2 adds advisory-only dataset-aware Suggested 0.xx guidance for AUTO size sliders plus canonical current-slider parameter-range tooltips and MANUAL per-parameter suggested/legal ranges. Suggestions never mutate Owner controls; temporal parameter-count estimates use executable model constructors and tree parameter count remains N/A/data-dependent.
- **STRATEGY_NAVIGATION_LIFECYCLE** — v1.4.3 binds Strategy Optimizer, Strategy Challengers and Strategy Champion navigation pages to one contextual Optimizer lifecycle/status authority while all non-Strategy pages remain on the Research lifecycle.
- **KPI_UI_FULL_AUTHORITY** — v1.4.4 requires every active configurable Research hard PASS/FAIL threshold and enabled advanced-risk evidence-sufficiency requirement to be visible/editable in Advanced -> KPI by Gate. The UI edits the same frozen gate_kpis stage profiles consumed by deterministic evaluators; evaluation formulas are unchanged.
- **MODEL_DETAIL_INSPECTOR_LIVE_RUNTIME** — v1.4.5 adds a read-only Model Detail Inspector across Research model/candidate lists and 2-second flat live status polling for Research and Strategy Optimizer; it does not change scientific evaluation, search, worker state or promotion authority. Tree models expose structural complexity instead of fabricated neural parameter counts.
- **DYNAMIC_HYBRIDS** — Temporal and policy families can be composed into executable dynamic hybrids when registry/capacity-compatible.
- **HARDWARE_DATA_CAPACITY** — Evidence-aware dynamic Capacity Governor separates LEGAL architecture, RESOURCE execution, and candidate-aware SCIENTIFIC information ceilings; historical recommended envelopes are starting guidance only.
- **FIDELITY_LADDER** — Cheap screen exists for compute allocation; qualification authority remains Full WFA.
- **POLICY_DISCOVERY** — Bounded OOF policy/selectivity search exists and cannot open locked/fresh holdout.
- **TRAINING_MEMORY_WINDOW_DISCOVERY** — training_memory_months is an integrated candidate-search dimension within declared bounds.
- **SCIENTIFIC_CREATIVITY** — Scientific creativity controls proposal/search breadth only; it cannot alter KPI, chronology, CPCV seeds, Forward or PASS/FAIL.
- **EXPERIMENT_BLOCKS_HYPOTHESES** — Bounded hypothesis experiment blocks, including hybrid ablation and seed stability, already exist.
- **RESEARCH_MEMORY** — Discovery-side research memory stores elites/failure topology/hypothesis lifecycle while excluding locked/fresh evidence.
- **DOWNSTREAM_FAILURE_FEEDBACK** — Pool/CPCV/Tournament/Monte-Carlo failures may produce bounded learning for a new Discovery cycle; Forward is report-only for the same snapshot.
- **CPCV_PROGRESSIVE_FINALISTS** — Pool freezes before a separate progressive CPCV finalist stage with hard PASS/FAIL and fixed seed confirmation for DL/hybrid.
- **GATE_KPI_PROFILES** — v0.7.9 stores independent Discovery, CPCV, Tournament, Monte Carlo and Fresh Forward statistical profiles plus a non-statistical Champion Promotion contract; the complete profile snapshot is frozen with the Factory.
- **STRATEGY_OPTIMIZER_KPI** — Upstream MT5 Strategy Optimizer has separate editable PF/RF/Mean-R/Weighted-R/AUTO minimum-trade authority, defaults to H1 baseline 20/month, uses Custom max / OnTester Mean R as native genetic fitness, transports Weighted R through MT5 optimization frames as an independent hard gate, and keeps Recovery Factor separate. v0.8.6 history-rebuild R accounting from complete tester history instead of OnTradeTransaction event ordering remains in force. In v0.8.7, Strategy Optimizer/CP32 is the sole SL/TP/MaxHold authority: Model Research no longer exposes or stores duplicate execution-geometry label knobs, and purge/embargo automatically respect upstream MaxHold. Model Research label research owns only Min edge R / Min margin R / ambiguous policy. Discovery/WFA expectancy acceptance requires editable Overall OOF Mean R plus Median Fold Mean R plus Worst Fold Mean R, all as mandatory AND gates. Mixed/stale geometry fails closed, and adaptive lot/risk remains outside model features/targets. v0.8.8 binds every MT5 Weighted-R optimization frame to its exact FrameInputs parameter vector; the opaque unsigned 64-bit (uint64) frame pass ID is provenance only and must never be converted through float or joined directly to the SpreadsheetML display Pass column. v0.8.9 disables MT5 optimization-cache reuse because cached XML results can bypass frame replay; rows without Weighted-R frame evidence remain ineligible, unresolved native-gate contenders block Champion promotion, and are retained for next-round refinement. v0.9.0 established transactional EA↔Max_MTF.set parity for direct Champion commit. v0.11.0 supersedes the automatic commit step: an eligible Optimizer winner is first registered as a Strategy Challenger and cannot mutate canonical Max_MTF.mq5/Max_MTF.set/Python strategy authority. Explicit Owner promotion is transactional across canonical EA defaults, canonical Strategy Tester Max_MTF.set, compiled/deployed EX5, Python execution-geometry authority and the Strategy registry; the prior Champion is demoted into a uniquely coded Challenger, and any failure restores the pre-promotion authority. v0.9.1 keeps canonical Max_MTF.set immutable during Data Quality repair and uses a separate training-enabled Max_MTF_GapRepair.set so CP32 gaps can be filled without weakening current Champion tester parity. The same v0.9.1 authority also makes ONNX runtime family identity generic across current deployable tree/temporal families and isolates actual Champion deal audit from non-executing Shadow candidate audit; neither audit ledger can mutate optimizer fitness, strategy geometry, or live execution authority. v1.2.5 records the existing Strategy Champion KPI from uniquely matched Owner Max_MTF.xml + Max_MTF_metrics.csv evidence, including independent Weighted R arithmetic and R-trade parity, without changing strategy parameters or execution logic.
- **ADVANCED_RISK_KPI** — Sharpe, Sortino, Calmar/MAR, PSR, DSR, Ulcer Index and daily CVaR are data-driven hard-gate metrics where enabled.
- **MONTE_CARLO** — Configurable bootstrap robustness stage exists after Tournament.
- **FRESH_FORWARD** — Fresh/Forward holdout is separated from tuning and can wait for new data when sample is insufficient.
- **ONNX_RUNTIME_PARITY** — Champion export/parity gate exists; runtime-only failures produce FACTORY_WINNER_RUNTIME_BLOCKED rather than rewriting research results.
- **SCIENTIST_PYTHON_ANALYSIS_RUNTIME** — v2.0.1 optional Scientist Python Analysis Runtime V1 provides one shared guarded analytical executor for autonomous LLM Scientist/Director and Scientist Chat. Generated scientific import spellings resolve to a deterministic capability allowlist/proxy surface rather than raw third-party module objects, closing transitive ctypes/native file/process/network authority while preserving approved in-memory NumPy/pandas/SciPy/sklearn analysis. It uses a dedicated user-local interpreter/environment separate from canonical MAX Python, accepts only host-authorized in-memory evidence IDs, records exact code/input/runtime provenance, and falls back to REASONING_ONLY on unavailable/rejected/error/timeout. Python output is ANALYTICAL_EVIDENCE_ONLY and can never own deterministic PASS/FAIL, candidate admission, promotion, training, acceptance, MT5, governance, or Factory state.
- **SCIENTIST_CHAT_READ_ONLY** — Scientist Chat is read-only, model-selectable, per-model profiled and separate from autonomous Research Scientist routing.
- **SCIENTIST_CHAT_STATE_RECONCILIATION** — Scientist Chat uses persistent thread identity, stale-event/result rejection, immutable terminal job state and explicit client reconciliation so completed replies settle without an operator Stop click.
- **SCIENTIST_CHAT_BACKEND_INTEGRITY** — Scientist Chat enforces cross-process thread/request idempotency, monotonic terminal CAS, duplicate-call-safe provider compatibility/fallback, sealed deterministic evidence, route provenance and visible-history parity.
- **LANGGRAPH_AGENTIC_SCIENTIST** — v1.3.3 AUTO Factory orchestration uses LangGraph and requires persistent Model Challenger registration before terminal Factory-winner success. The Research Director persists hypothesis memory and proposal lineage, requests bounded read-only evidence, attributes actual prior outcomes, designs the next experiments and can escape family/topology local optima inside the Owner allow-list. Deterministic code still owns legality and PASS/FAIL; Owner still owns promotion.
- **SCIENTIST_DIRECTED_SEARCH** — SCIENTIST_DIRECTED family/topology authority keeps every Owner-allowed feasible path available across the Factory so the Scientist can choose local refinement, structural escape, family escape or topology escape without mutating hard KPI, Strategy geometry, Locked/Fresh evidence, CPCV seeds, live risk or promotion.
- **AUTONOMOUS_LLM_SCIENTIST_ROUTING** — AUTO Factory Research Scientist/Director is ordered-fallback routed and exact-contract-memory scoped. In v1.3.3 it is agentic for bounded research direction, while deterministic validation remains the sole scientific PASS/FAIL authority and retryable stack exhaustion may fall back deterministically.

## Recommendation classification

- **EXISTING** — Max already has the requested capability. Do not propose building it again; explain/configure/use the existing authority.
- **EXTENSION** — An existing capability covers the core idea but a scientifically distinct extension may be useful. State the existing capability first, then the exact gap.
- **EXPERIMENT** — No new feature is required; the idea can be tested with existing Factory controls/evidence. Propose an experiment, not a duplicate feature.
- **NEW** — Capability is not present. It may be proposed as a new architecture/contract with expected integration points and validation burden.
- **CONFLICT** — Suggestion would violate a hard scientific/governance invariant. Explain the conflict and offer a compliant alternative.
- **OUTSIDE_CURRENT_CONTRACT** — Scientifically plausible but needs an explicit contract/revision before implementation.

## Mandatory sync rule

Every production-code or canonical-contract change updates the source manifest. `ModelLab/tests/scientist_knowledge_sync_selftest.py` fails acceptance until this database is regenerated and the canonical handoff/docs are synchronized.
