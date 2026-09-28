# Agent Architecture — Current Control Addendum

## v0.11.1 Data Quality / MT5 boundary

The Data Quality component owns a local-first preflight boundary. UI AUDIT and initial Factory preflight are read-only with respect to MT5. MT5 belongs only to the REPAIR / VERIFY stage after a repairable Data Quality failure. The repair stage may verify broker history, run the dedicated tester writer, and re-verify the repaired bytes. Exact-SHA broker proof is stored outside the package and cannot authorize a different CSV revision.



## v0.11.0 Strategy Challenger / Champion authority

The upstream Strategy Optimizer and downstream Model Research now use parallel but separate Challenger registries.

- **Strategy**: `Max.mq5` is the current Strategy Champion. Eligible optimizer winners become `Max_Challenger_<human-code>.mq5` + `.set` + metadata. Promotion is explicit Owner authority and demotes the previous Champion into another Strategy Challenger.
- **Model**: eligible Research outputs remain Model Challengers with human-readable ONNX filenames. Shadow is non-executing and model promotion remains explicit from the Champion page.

A Strategy promotion changes execution geometry authority and therefore can invalidate existing CP32 data. A Model promotion does not own SL/TP/MaxHold. These authorities must never be conflated.

## v0.10.0 Challenger / Champion authority split

```text
Research Supervisor
    └─ produces ELIGIBLE_CHALLENGER + locked KPI evidence
          ↓
    Challenger Registry
          ├─ human-readable immutable artifact identity
          ├─ optional Shadow publish (copy only)
          └─ no EA input mutation / no automatic promotion
          ↓
    Champion Page
          └─ deterministic promotion gates + explicit Owner confirmation
                ↓
          Production Model Champion
```

User-facing model artifact identity is human-readable family/topology + UTC timestamp. SHA-256 is retained only for integrity evidence. Standalone and hybrid deployments preserve their topology: hybrids promote the temporal and tree-policy ONNX pair atomically.

The Strategy Optimizer Champion remains upstream execution authority and is not the same entity as a Model Champion. v0.10.0 imports its optimizer-owned defaults into the current EA while retaining later runtime repairs.


## Scientist Knowledge R1

```text
Canonical code + contracts
        ↓ hash/sync gate
SCIENTIST_KNOWLEDGE_BASE.json
        ↓ compact read-only context
Scientist Chat
        ↓
Capability/novelty check before recommendation
```

The Scientist knowledge layer is advisory context only. It cannot mutate Factory state or replace deterministic evidence. `EXISTING` capability knowledge prevents duplicate recommendations; `NEW`/`OUTSIDE_CURRENT_CONTRACT` ideas remain allowed when explicitly labeled.


## Research Control R1 authority split

```text
Owner
 ├─ Scientist Chat (read-only advisor)
 │   └─ manual model profile / safe streaming / no mutation
 └─ Research Control
     ├─ AUTO FACTORY
     │   ├─ optional LLM Research Scientist/Director
     │   ├─ deterministic Discovery
     │   └─ deterministic validation chain
     └─ MANUAL RESEARCH
         ├─ Owner exact candidate list
         ├─ NO autonomous Research LLM
         ├─ NO deterministic candidate generation
         └─ deterministic Full WFA → CPCV → Tournament → MC → Forward → Champion
```

Chat Scientist and autonomous Research Scientist are separate authorities and must never share implicit fallback/mutation behavior.

---

# ComplexPolicy Agent Architecture · current through v0.7.0

## Authority model

### LLM Scientist

Advisory only. It may:

- inspect dataset summary and walk-forward CV results;
- propose bounded XGBoost / LightGBM / Random Forest / GRU / hybrid GRU→classical hyperparameters, including training-memory/selectivity dimensions;
- suggest stopping when additional research looks unproductive.

It may **not**:

- change labels, chronological split, purge, or locked-test fraction;
- see locked-test metrics before the Supervisor freezes a winner;
- change acceptance or risk gates;
- install an ONNX model;
- promote a Challenger;
- write `champion.onnx`.

All LLM proposals are schema-checked and clipped to Supervisor-owned parameter bounds.

### Supervisor Agent

Deterministic authority for:

1. dataset and CP32 preflight;
2. forward labels;
3. purged expanding walk-forward research;
4. bounded experiment budget and early stop;
5. candidate deduplication;
6. winner freeze;
7. one-time locked-test opening;
8. native-vs-ONNX parity;
9. `ELIGIBLE_CHALLENGER` status;
10. MT5 parity / Strategy Tester / fresh-shadow evidence gates;
11. current-Champion comparison;
12. Champion registry and promotion.

## v0.6.6 temporal + hybrid authority

Research is staged to control compute and leakage risk:

```text
Stage A/B: classical + standalone GRU
    -> temporal evidence exists
Stage C: bounded GRU→classical stacks (default max 2/round)
    -> same walk-forward survival gates
    -> locked/fresh validation only after upstream authority passes
```

Hybrid direction GRU has **DOWN/UP only** authority. The downstream classical meta-policy has `SELL/SKIP/BUY` opportunity authority. It is trained only on OOF GRU direction probabilities. Deterministic EA code retains capital-risk authority.

Deployment contract for hybrid candidates is atomic: `*_temporal.onnx + *_policy_model.onnx + decision policy/manifest`. A hybrid artifact is incomplete if either ONNX component or its exact sequence length/runtime contract is missing.


## State machine

```text
RESEARCHING
  -> NEEDS_FRESH_HOLDOUT | RESEARCH_REJECTED | WAITING_MT5_PARITY
  -> WAITING_STRATEGY_TESTER
  -> WAITING_SHADOW_FORWARD
  -> PROMOTION_READY
  -> CHAMPION
```

`NEEDS_FRESH_HOLDOUT` is deliberate. If the same locked-test generation was already opened, the Supervisor refuses to silently reuse it. Repeatedly optimizing after seeing the same holdout turns a test set into another training aid with better branding.

## Research loop

```text
baseline candidate pool
  -> walk-forward CV
  -> rank robust score
  -> LLM Scientist proposals (optional)
  -> deterministic refinement fallback
  -> repeat until budget / patience / rounds
  -> freeze winner
  -> open locked test once
  -> export challenger.onnx
  -> ONNX parity
```

If the LLM endpoint is unavailable, the Supervisor continues deterministic refinement. LLM failure is not a research-system failure.

## Promotion evidence

A Challenger needs:

- historical `ELIGIBLE_CHALLENGER` status;
- MT5 inference parity PASS;
- Strategy Tester integration PASS;
- fresh shadow-forward PASS;
- same-window comparison against the current Champion when one exists.

Only then does the state become `PROMOTION_READY`.

The Streamlit UI additionally requires explicit user authority before the Supervisor writes `MQL5\Files\models\champion.onnx`.

## v0.5.9 operator/reporting and ranking contract

- LLM Scientist remains advisory and backend-JSON evidence remains canonical, but operator UI renders a human-readable research report rather than raw JSON.
- Live report is emitted after each Scientist round through the existing Supervisor progress callback.
- Research ranking uses `CV_SCORE_V4_SURVIVAL_RISK_AWARE`, built only from walk-forward-observable evidence. Ranking is subordinate to `KPI_V5_HIERARCHICAL`; failed DD/RF/PF/robustness/stress gates cannot be compensated by total score.
- Locked-test evidence is excluded from ranking until the CV acceptance gate authorizes the one-time holdout opening.
- Acceptance and promotion remain deterministic, fail-closed authorities separate from the ranking score.

## v0.6.0 authority extension

`MODEL_SEARCH -> OOF_POLICY_DISCOVERY -> LOCKED_TEST` is now the only route when the model frontier itself fails CV but predictive signal remains measurable. Policy Discovery is deterministic, bounded, uses only upstream walk-forward evidence, and is scored by the same 28 KPI surface. Locked test remains unavailable until the selected model+policy pair passes current CV gates. If Policy Discovery fails, the state transitions to `FEATURE_LABEL_AUDIT`.

Deployment lineage for policy-aware candidates is atomic: `challenger.onnx + challenger_policy.csv -> parity/test/shadow -> champion.onnx + champion_policy.csv`.

## v0.6.1 recovery state machine

```text
MODEL RESEARCH
  -> CV PASS -> LOCKED TEST
      -> PASS -> ELIGIBLE_CHALLENGER
      -> FAIL -> RETIRE HOLDOUT -> OOF POLICY DISCOVERY
          -> POLICY CV FAIL -> FEATURE/LABEL AUDIT
          -> POLICY CV PASS -> NEWER H1 FRESH HOLDOUT
              -> PASS -> ELIGIBLE_CHALLENGER
              -> FAIL -> FEATURE/LABEL AUDIT / NEW HYPOTHESIS
```

The retired locked test may inform postmortem diagnosis but is never re-scored during policy search. Source model hyperparameters are frozen. Fresh validation is restricted to rows strictly newer than the source raw-data cutoff.


## v0.6.2 authority and routing

- Dataset identity authority: `DATASET_ID_V2` (`symbol + period/timeframe + start/end + SHA-256`).
- Holdout authority: `HOLDOUT_ID_V2`; cross-timeframe identity is part of the key.
- Operator route is lineage-specific. Policy Discovery is a branch, not a mandatory fake step.
- PASS authority is hierarchical: integrity → survival (DD/RF) → economic (PF/Exp) → robustness → stress.
- Composite Score is ranking-only.
- Only `ELIGIBLE_CHALLENGER` can enter MT5/shadow/promotion controls.


## v0.6.3 workflow authority

The workflow router is now a first-class authority: `workflow_router.route_for_manifest()` determines page and legal next action from manifest state. UI pages do not independently invent transitions.

Post-policy/research failure route:

`... → FEATURE_LABEL_AUDIT_READY → GUIDED_RESEARCH_READY → new-generation CV → NEEDS_FRESH_HOLDOUT → fresh validation`.

The retired historical holdout remains unavailable to guided new-generation research. `agent.skip_locked_test=true` forces CV-only closure and requires future data.


## v0.6.8 Research Memory + Scientist V2

New generations are lineage-aware. `historical external: research_memory.json` contains OOF-only elites, failure gates, coverage/training-memory evidence, Guided winner, and Scientist scientific agenda. Locked/fresh holdout metrics are forbidden inputs. Round 1 becomes `MEMORY_ANCHORED_DISCOVERY`: bounded elite rechecks plus exploration reserve.

Scientist V2 produces concrete model proposals and higher-level hypotheses. Deterministic translation routes executable hypotheses to the legal OOF stage; unsupported objective ideas are retained as backlog. Scientist cannot change gates, read sealed data, promote, or control live risk.

Settings are externalized from the version folder to `%LOCALAPPDATA%\ComplexPolicy\ModelLab`, with DPAPI-protected API secret and backup recovery.


## v0.7.0 Champion Factory authority

Champion selection is now a separate chronological state machine:

`DISCOVERY_POOL → TOURNAMENT → ONE_WINNER → FRESH_FORWARD`.

Discovery is OOF-only and may learn across bounded generations until exactly 12 unique qualified candidates are frozen. Tournament is a separate untouched chronological window and may be opened once. It does not feed same-epoch tuning. Exactly one winner is frozen. Fresh is evaluated only on that winner; runner-up fallback is forbidden.

Trade-count sample sufficiency is no longer a fixed H1 constant. `CP_TRADE_SAMPLE_AUTO_V1` resolves the minimum from exact time exposure and timeframe before performance is observed.

## Scientist Chat state authority — Chat State R1

Scientist Chat history is server-authoritative. Each persistent thread has a `thread_id`; Clear Chat rotates it. Component SEND/STOP/poll events and background jobs carry that id. Stale-thread sends/results are rejected, terminal job states are immutable, and a bounded client reconciliation pulse ensures a completed LLM result is settled without requiring Owner interaction. Client optimistic/thinking/streaming rows are presentation-only.
