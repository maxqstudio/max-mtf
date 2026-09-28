# Max Research Agent — E2E Workflow Contract Audit

## v0.11.1 Data Quality staged authority

Data Quality is now explicitly staged before Research. The audit stage performs only local CP32 validation plus an exact-SHA cached broker proof and must never initialize/open MT5. A ready dataset proceeds directly into Research. A repairable failure alone enters REPAIR / VERIFY, where MT5 may open, the exact broker/feed is verified, `Max_GapRepair.set` drives the first-write-wins EA writer, and a post-repair broker audit must prove zero source-backed missing bars before Research resumes. Structural corruption remains fail-closed without MT5. Broker proof is immutable-by-hash: any CSV byte change invalidates the cached proof.



## v0.11.0 Strategy Challenger lifecycle

Strategy Optimizer now mirrors the Model Challenger authority split. An eligible optimizer winner terminates the run as `STRATEGY_CHALLENGER_FOUND` and is materialized as a human-readable EA + fixed Tester setup + metadata bundle. The current canonical `Max.mq5` Strategy Champion is unchanged until explicit Owner promotion.

Promotion is transactional across canonical `Max.mq5`, canonical Tester `Max.set`, MetaEditor compile/deploy, Python strategy execution authority, and the Strategy registry. On successful promotion, the former Champion is preserved as a new uniquely coded Challenger. On any failure, the pre-promotion Champion authority is restored.

Only the promoted current Strategy Champion owns CP32 execution geometry. Unpromoted Strategy Challengers are evaluation artifacts and cannot alter Research labels, purge/embargo, or model authority.

## v0.10.0 Model Challenger lifecycle

The current workflow separates Strategy Champion, Model Challenger, Shadow audit, and Production Model Champion authority:

```text
Strategy Optimizer Champion
        ↓
CP32 generated with exact upstream geometry
        ↓
Model Research / locked deterministic validation
        ↓
ELIGIBLE_CHALLENGER
        ↓
human-readable immutable Challenger artifact(s)
        ├─ optional Shadow publish (copy only; no EA input mutation)
        └─ Challenger Registry + KPI evidence
        ↓
existing deterministic promotion gates
        ↓
explicit Owner promotion on Champion page
        ↓
Production Model Champion
```

Research cannot self-promote. Human Challenger names use family/topology + UTC run timestamp, e.g. `Challenger_LSTM_20260916_223501.onnx` or hybrid `Challenger_GRU-LightGBM_20260916_224002_Temporal.onnx` and `_Policy.onnx`; SHA-256 remains provenance/integrity metadata only. Python may publish a Challenger to MT5 Shadow by copying its artifact(s), but it must not edit `InpChallenger*` EA settings. The Owner controls the active Shadow filename manually.

The imported Strategy Champion is kept separate from this model lifecycle. v0.10.0 imports the Owner-uploaded optimizer-owned defaults into the latest EA instead of replacing newer runtime logic. Execution geometry authority is SL ATR `3.2`, TP ATR `4.8`, MaxHold `54`; complete imported parameter provenance is stored in `EA_v1_06/CHAMPION_IMPORTED_PARAMETERS.json`.


**Scientific authority:** v0.7.5 R6 — Per-Family Model Size Priority  
**Control revision:** Research Control R1  
**Knowledge revision:** Scientist Knowledge R1

## Canonical end-to-end route

### AUTO FACTORY

`Data Quality → Freeze Research Plan → Discovery Proposal → Cheap Screen → Full WFA → Pool → CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion → ONNX Runtime Gate`

### MANUAL RESEARCH

`Data Quality → Freeze Owner Exact Candidates → Full WFA → Pool → CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion → ONNX Runtime Gate`

MANUAL replaces only proposal/discovery authority. It does **not** replace deterministic validation.

---

## 1. Data contract and Data Quality

### Dataset contract

- Feature contract: `CP32_V1`.
- Required model features: **32**.
- Final decision classes: `[SELL, SKIP, BUY]` → `[N,3]` probabilities.
- One symbol/timeframe per dataset.
- Duplicate identity rows are a hard failure.
- Unexpected feature contract is a hard failure.
- Invalid signal timestamps, OHLC, ATR, non-finite features, non-positive/inverted decision quotes are hard failures.
- `decision_ask == decision_bid` is legal but recorded as a zero-spread warning.
- Canonical Max runtime CSV names are `Max_Training.csv`, `Max_Telemetry.csv`, actual Champion deal audit `Max_Champion_Trades.csv`, non-executing Shadow candidate audit `Max_Shadow_Trades.csv`, and optimizer evidence `Max_metrics.csv`; active Python auto-detection/repair authority consumes `Max_Training.csv` only and does not silently fall back to legacy ComplexPolicy training names.

### Broker continuity authority

`research_readiness()` requires broker reconciliation to be verified. Source-backed missing bars and dataset-only timestamps block research readiness.

Repair authority is verified MT5 source data only. Interpolation/forward-fill is not research authority.

v0.9.1 gap-repair launch is fail-closed and uses a dedicated `Max_GapRepair.set` cloned from canonical Champion `Max.set`. It explicitly forces `InpWriteTrainingData=true` and `InpTrainingFile=Max_Training.csv` while preserving Champion strategy parameters. The exact verified terminal must be closed before startup `/config` launch; a process start is only pending evidence, and repair is accepted only after a fresh broker reconciliation proves zero source-backed missing bars.

### START RESEARCH lifecycle authority

`START AUTO/MANUAL RESEARCH` may spawn the owned worker immediately for UI responsiveness, but the worker status is **`DATA_QUALITY_PREFLIGHT`**, not research `RUNNING`, until broker-backed Data Quality and `research_readiness()` PASS. Only after that PASS may the worker transition to `RUNNING` and enter Factory/Discovery logic. A blocked Data Quality result terminates the start fail-closed; no LLM proposal, Discovery candidate, or downstream stage may execute first.

### Label contract

Labels use configured horizon + ATR-scaled SL/TP first-barrier logic. Ambiguous same-bar TP+SL events are dropped by default. A row becomes SKIP when neither side achieves configured edge/margin separation.

---

## 2. Research-plan freeze

Before candidate search/validation, Max freezes:

- exact chronological Discovery/Tournament/Fresh windows;
- immutable Discovery snapshot and source-master identity/hash;
- hardware profile;
- dataset capacity profile;
- legal/effective model parameter envelopes;
- Owner topology priority;
- per-family model-size priorities;
- research mode and proposal authority.

Current mutable UI config is not the same authority as the frozen active `research_plan`.

Capacity Governor is always above Owner size preference or Scientist proposal.

---

## 3. Discovery and Full WFA

### Existing search capabilities

Max already supports:

- Single ↔ Hybrid allocation (`0.00` single-only, `1.00` hybrid-only, intermediate mixed allocation);
- AUTO/allowed-family model universe;
- per-family Small ↔ Large priority;
- hardware/data-capacity compilation;
- dynamic temporal→policy hybrids;
- integrated training-memory/window discovery;
- bounded OOF Policy Discovery;
- Fidelity Ladder Cheap Screen;
- Scientific Creativity / bounded hypothesis blocks;
- Research Memory and Failure Topology;
- hybrid ablation and seed-stability hypotheses.

Scientist must not suggest adding these as if absent.

### Qualification authority

Cheap Screen is disposable compute allocation only. It cannot qualify a candidate.

Only **Full chronological WFA** may admit a candidate to Pool. Ranking, LLM recommendations, creativity, Failure Margin, or Cheap Screen cannot override a WFA hard-gate failure.

Worst WFA/CV expectancy hard floor is `>= 0.00R`.

### Hybrid leakage contract

Hybrid temporal outputs used by the policy are OOF/index-preserving. In-sample stacking is forbidden.

---

## 4. Pool

The default target/minimum is 12 qualified candidates in AUTO mode. MANUAL uses the Owner exact candidate count and its explicit minimum-survivor setting.

Pool is frozen from Full-WFA PASS candidates before CPCV. CPCV/downstream evidence cannot retroactively tune the already-active Discovery cycle.

---

## 5. CPCV

Default authority:

- 6 chronological groups;
- 2 test groups per split;
- up to 15 purged combinatorial splits;
- purge = 24 bars;
- embargo = 24 bars;
- progressive finalists ranked from frozen WFA OOF evidence;
- target 3 survivors, minimum 1 to open Tournament.

R6 also reconstructs 5 canonical chronological paths for path-dependent Advanced KPI while retaining legacy stress-split economic/DD/recovery authority.

For DL/hybrid candidates, training-seed confirmation is fixed:

`42 → 11 → 77`

All required seeds must PASS. Progressive stop after a failed seed is allowed. Seed mining is forbidden.

CPCV PASS/FAIL is hard authority and cannot be offset by ranking.

---

## 6. Tournament

Every CPCV survivor is evaluated on the frozen Tournament window. Tournament does not choose one winner; **all hard-gate survivors** continue.

Evidence includes trade metrics, yearly metrics, temporal stability, regime diagnostics, stress diagnostics and hierarchical KPI acceptance.

---

## 7. Monte Carlo

Every Tournament survivor enters configurable bootstrap robustness (default 10,000 simulations; source minimum 100).

Monte Carlo evaluates robust/tail distributions after Tournament chronological Advanced KPI. It does not create a ranking bypass around hard gates.

All Monte Carlo survivors continue to Forward.

---

## 8. Fresh / Forward Championship

Fresh/Forward is untouched selection evidence for the same snapshot.

- Same-snapshot Forward results are report-only, not tuning input.
- Insufficient sample waits for new Forward data.
- Every Monte Carlo survivor is evaluated.
- Only Forward KPI PASS candidates may be ranked for Champion.
- Forward failure does not trigger same-snapshot learning/research restart.

---

## 9. Champion and ONNX runtime gate

Top-ranked Forward PASS candidate becomes the research Champion candidate.

Runtime export/parity is separate authority:

- standalone final output: `[N,3]` SELL/SKIP/BUY;
- hybrid temporal ONNX: DOWN/UP internal output; policy ONNX emits final `[N,3]`;
- configured ONNX parity tolerance is mandatory.

`CHAMPION_RUNTIME_BLOCKED` means scientific selection succeeded but runtime export/parity failed. Research must not be rerun merely to hide a runtime defect.

### v0.7.6 final statistical/promotion contract

Fresh Forward owns the final untouched statistical thresholds through `gate_kpis.fresh_forward`; they are configurable **before START** and frozen in the scientific contract. Research trade-sample sufficiency uses H1 baseline **8 trades/month**, automatically scaled by timeframe and exact evaluation exposure with integer round-up.

Champion does not run another market/statistical filter. `gate_kpis.champion_promotion` verifies upstream PASS, artifact integrity, no post-Fresh scientific-contract mutation, ONNX export, and ONNX parity. Earlier hard-coded Champion KPI numbers are historical policy references, not a hidden second authority.

---

## 10. Failure learning and research memory

Discovery/Pool, CPCV, Tournament and Monte Carlo failures may produce bounded next-cycle learning only after deterministic evidence is committed and exposure-budget authority permits it.

Forward failure is not fed back into the same snapshot.

Research Memory is Discovery-side scientific memory; it must not import locked/fresh evidence as tuning authority.

---

## 11. Scientist authorities

### Autonomous Research Scientist

May propose hypotheses/experiments within the selected AUTO route and ordered fallback contract. It never owns PASS/FAIL.

### Scientist Chat

Read-only advisor. It may inspect current settings, frozen plan, research evidence and **Max-native static knowledge**. It may recommend ideas outside Max, but must first check existing capability and classify novelty.

Scientist Chat cannot mutate settings/research, execute tools, call MT5, admit candidates, lower hard gates, promote a Champion, or expose raw hidden chain-of-thought.

---

## 12. Release-sync requirement

`ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json` embeds SHA-256 provenance for production Python code, `ModelLab/config/config.json`, `ModelLab/config/models/model_registry.json` and canonical contract docs. Any watched change makes the Scientist knowledge state stale until regenerated.

`ModelLab/tests/scientist_knowledge_sync_selftest.py` is a cumulative acceptance gate. A package with stale Scientist knowledge must fail acceptance.


## Backend E2E Audit R1 — Stage 1–7 physical authority

Active physical chain:

`Data Flow → Discovery → CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion`

Hard invariants:
- exact Data Quality source hash before Discovery; no non-finite CP32 features; purge >= label horizon;
- AUTO Discovery Pool exactly 12; Full-WFA independently revalidated; scientific/windows and downstream history frozen;
- CPCV mandatory exact 6C2=15; purge and embargo >= label horizon; temporal/hybrid 42→11→77, all PASS;
- every downstream stage verifies the previous terminal seal and exact candidate identity; CP_POLICY_V1 is replayed rather than silently falling back to base threshold;
- Monte Carlo remains IID bootstrap with replacement and preserves strategy identity;
- Forward is predeclared, DQ-gated and append-only; insufficient sample waits, sufficient all-fail is terminal;
- Champion final fit uses frozen pre-Forward history only, locks CP32 feature order and SELL/SKIP/BUY class order, requires ONNX parity, and seals runtime artifacts.

Dedicated Stage 1–7 gates are part of the 93-gate cumulative suite. Historical 86-gate UI acceptance does not substitute for backend closure.

**Stage 1–7 closure status:** exact-tree cumulative **93/93 PASS**, `first_failed_gate=null` on the pre-Stage-8 checkpoint. Stage 8 changes invalidate that exact-tree signature and require the 94-gate closure below.

## Backend E2E Audit R1 — Stage 8 orchestration authority

Cross-stage orchestration must preserve the already-validated scientific stages rather than create a second authority around them. The workflow layer therefore enforces:

- job START and RESUME share one cross-process registry mutex and reject a second active worker;
- `WAITING_FOR_NEW_FORWARD_DATA` / immature Forward states are persisted as resumable `PAUSED`, so the same Factory continues when fresh data arrives;
- Scientist failure-learning retry consumes only already-committed terminal failure evidence, verifies the relevant stage seal first, and rejects scientific-contract drift;
- Discovery terminal publication occurs only after its terminal seal exists;
- completed Factory history is idempotent across WAIT/RESUME;
- terminal `CHAMPION` consumption verifies the Champion terminal seal and exact runtime artifact authority rather than trusting manifest status alone;
- any upstream terminal artifact tamper blocks the downstream/resume path fail-closed.

Dedicated gate: `ModelLab/tests/stage8_e2e_workflow_backend_contract_selftest.py`.

**Stage 8 closure status:** **CLOSED — exact-tree cumulative 94/94 PASS, `first_failed_gate=null`**. Stage 9 LLM Scientist is the next audit authority. Any watched source/canonical-contract change invalidates this closure until a fresh matching-signature cumulative run passes again.

## Backend E2E Audit R1 — Stage 9 autonomous LLM Scientist authority

The autonomous Research Scientist/Director is advisory only. Deterministic code owns PASS/FAIL, chronology, KPI and promotion. `stop_research` is stored only as advisory evidence and cannot stop Supervisor execution or suppress committed actionable failure learning.

Ordered routing is fail-safe: retryable quota/rate-limit, timeout, provider 5xx, model-unavailable and provider-connection failures may advance to the next configured route. Authentication, malformed requests/config, generic endpoint 404, JSON/programming/deterministic errors fail closed. Route cooldown identity includes provider, model, endpoint and API-key environment identity and is cross-process locked.

START RESEARCH stack exhaustion latches deterministic-only mode for the current Factory Discovery invocation. Mid-Supervisor all-route exhaustion likewise disables further LLM calls for remaining rounds while deterministic research continues. Legacy Scientist `_call(messages)` compatibility is chosen by signature inspection before invocation, never by catching an internal `TypeError`, preventing duplicate provider requests.

Research Memory is exact-contract keyed and corrupt global memory fails closed. LLM dataset context remains header/schema plus committed aggregate evidence; current-cycle sealed holdouts/raw rows are excluded. Every LLM candidate is revalidated by effective bounds and Capacity Governor.

Dedicated gate: `ModelLab/tests/stage9_llm_scientist_backend_contract_selftest.py`.

**Stage 9 closure status:** **CLOSED — exact-tree cumulative 95/95 PASS, `first_failed_gate=null`**. Stage 10 Scientist Chat is the next audit authority. Any watched source/canonical-contract change invalidates this closure until a fresh matching-signature cumulative run passes again.


## Backend E2E Audit R1 — Stage 10 Scientist Chat backend authority

Scientist Chat remains a discussion-only surface. It cannot execute, mutate settings/research, stop/resume Factory work, or promote a Champion. Stage 10 hardens only its persistence, job lifecycle, provider-call safety, evidence integrity, and provenance boundaries.

Hard invariants:
- chat history clear/save is cross-process atomic and thread-generation monotonic; corruption fails closed;
- backend `request_id` idempotency prevents duplicate workers across tabs/processes;
- the first job terminal commit wins and is immutable; hard timeout is one terminal transition;
- provider compatibility is inspected before call, never inferred from an exception after a provider request;
- stream→buffered retry is limited to explicit pre-answer stream-capability incompatibility; auth/programming/post-init timeout cannot trigger duplicate calls;
- explicit fallback preserves full route identity and uses the actual answering model's request budget; fallback remains OFF by default;
- CPCV/Tournament/Monte-Carlo deterministic evidence requires terminal-seal/hash verification before Chat may present it as fact;
- persisted assistant success includes actual provider/answering-route provenance and supported cost metadata; hidden failed rows never become invisible future prompts;
- STOP that races with an already terminal worker reconciles the committed terminal result instead of overwriting/discarding it.

Dedicated gate: `ModelLab/tests/stage10_scientist_chat_backend_contract_selftest.py`.

**Stage 10 closure status:** **CLOSED — final canonical tree requires exact-tree cumulative 96/96 PASS with `first_failed_gate=null`**. The first full 96-gate pre-closure run passed before this closure-doc transition; the closure tree must and does not inherit that prior tree signature. R4 Stage 1–9 remains immutable rollback evidence only.

## Stage 11 — Release & Authority Integrity — CLOSED

Stage 11 is governance-only. R5 Stage 1–10 scientific/runtime authority remains unchanged. Canonical package metadata must agree with `governance/CURRENT_AUTHORITY.json` and the exact acceptance report; stale lower-stage PASS/next-stage claims fail acceptance. `governance/PACKAGE_MANIFEST.json` participates in exact-tree hashing and Scientist Knowledge provenance. Final checkpoint per-file hashes are generated only after the matching final 97/97 cumulative acceptance and must verify with zero missing, extra, or mismatched files before R6 ZIP sealing. External NOT_RUN gates remain NOT_RUN and cannot be promoted by package metadata.


### v0.9.1 ONNX runtime family identity and audit

ONNX Champion/Shadow settings represent every deployable tree/temporal family in the Model Registry. Family selection is identity/topology validation only; it cannot alter the canonical `[P(SELL), P(SKIP), P(BUY)]` decision contract or deterministic EA risk authority. Champion actual MT5 deals are auditable in `Max_Champion_Trades.csv`. Shadow remains non-executing and writes candidate plans with `executed=0` to `Max_Shadow_Trades.csv`. Optimizer/gap-repair runs disable both trade-audit writers.


## Known scientific-parity blockers after v1.3.1 audit

The current workflow ordering remains canonical, but production-parity of realized Model Research trade outcomes is **not yet claimed**. Open findings `SCI-01..06`, `KPI-01..05`, `CPCV-01`, `WFA-01`, and `FEAT-01` are authoritative in `ModelLab/docs/research/SCIENTIFIC_WORKFLOW_AUDIT_v1_3_1.md`. v1.3.1 documents these findings but does not repair them. Until the next scientific-workflow repair closes the CRITICAL/HIGH items, software acceptance must not be interpreted as proof that WFA/CPCV/Tournament/Fresh trade distributions exactly match the promoted EA execution state machine.
