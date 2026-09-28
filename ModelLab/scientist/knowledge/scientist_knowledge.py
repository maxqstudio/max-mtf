from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.training_method_contract import CONTRACT_PATH as TRAINING_METHOD_CONTRACT_PATH, training_method_context

ROOT = MODELLAB_ROOT
PACKAGE_ROOT = ROOT.parent
KB_JSON = ROOT / "scientist" / "knowledge" / "SCIENTIST_KNOWLEDGE_BASE.json"
KB_MD = ROOT / "docs/contracts/SCIENTIST_KNOWLEDGE_BASE.md"
AUDIT_JSON = ROOT / "evidence/current/WORKFLOW_CONTRACT_AUDIT_R1.json"

SCHEMA = "MAX_SCIENTIST_KNOWLEDGE_V1"
AUDIT_SCHEMA = "MAX_WORKFLOW_CONTRACT_AUDIT_R1"

# Any change to production code or canonical release-authority code participates in
# the knowledge provenance manifest. run_acceptance.py is intentionally included:
# its ordered TESTS list is the single local-acceptance count authority consumed by
# Scientist Knowledge release-integrity checks.
EXCLUDED_CODE_NAMES = {
    "tests/scientist_knowledge_sync_selftest.py",
}
EXCLUDED_CODE_SUFFIXES = ("_selftest.py", "_smoke.py")

CANONICAL_DOCS = [
    ROOT / "docs/mtf/MAX_MTF_V2_FOUNDATION.md",
    ROOT / "docs/mtf/MTF_DATA_FOUNDATION_V1.md",
    ROOT / "docs/mtf/MTF_RESEARCH_ARCHITECTURE_V1_ROADMAP.md",
    PACKAGE_ROOT / "governance/PACKAGE_MANIFEST.json",
    PACKAGE_ROOT / "README_FIRST.md",
    PACKAGE_ROOT / "governance/PROJECT_HANDOFF_CURRENT.md",
    PACKAGE_ROOT / "governance/CONTRACT_AUDIT_INDEX.md",
    PACKAGE_ROOT / "governance/CURRENT_AUTHORITY.json",
    PACKAGE_ROOT / "governance/PACKAGE_LAYOUT.json",
    PACKAGE_ROOT / "governance/PACKAGE_LAYOUT.md",
    ROOT / "governance/MODELLAB_LAYOUT_MANIFEST.json",
    ROOT / "docs/contracts/MAX_WORKFLOW_CONTRACT_E2E.md",
    ROOT / "docs/reference/README.md",
    ROOT / "docs/contracts/AGENT_ARCHITECTURE.md",
    ROOT / "docs/research/RESEARCH_WORKFLOW_V3.md",
    ROOT / "docs/research/RESEARCH_CONTROL_R1.md",
    ROOT / "docs/contracts/MANUAL_RESEARCH_V1.md",
    ROOT / "docs/research/CHAMPION_FACTORY_V3.md",
    ROOT / "docs/contracts/KPI_ACCEPTANCE_V6.md",
    ROOT / "docs/contracts/KPI_BY_GATE_V079.md",
    ROOT / "docs/repairs/REPAIR_v0_7_9.md",
    ROOT / "docs/repairs/REPAIR_v0_8_0.md",
    ROOT / "docs/repairs/REPAIR_v0_8_1.md",
    ROOT / "docs/repairs/REPAIR_v0_8_2.md",
    ROOT / "docs/repairs/REPAIR_v0_8_3.md",
    ROOT / "docs/repairs/REPAIR_v0_8_4.md",
    ROOT / "docs/repairs/REPAIR_v0_8_5.md",
    ROOT / "docs/repairs/REPAIR_v0_8_6.md",
    ROOT / "docs/repairs/REPAIR_v0_8_7.md",
    ROOT / "docs/repairs/REPAIR_v0_8_8.md",
    ROOT / "docs/repairs/REPAIR_v0_8_9.md",
    ROOT / "docs/repairs/REPAIR_v0_9_0.md",
    ROOT / "docs/repairs/REPAIR_v0_9_1.md",
    ROOT / "docs/repairs/REPAIR_v0_10_0.md",
    ROOT / "docs/repairs/REPAIR_v0_11_0.md",
    ROOT / "docs/repairs/REPAIR_v1_3_0.md",
    ROOT / "docs/repairs/REPAIR_v1_3_1.md",
    ROOT / "docs/repairs/REPAIR_v1_3_2.md",
    ROOT / "docs/repairs/REPAIR_v1_3_3.md",
    ROOT / "docs/repairs/REPAIR_v1_3_4.md",
    ROOT / "docs/repairs/REPAIR_v1_4_0.md",
    ROOT / "docs/repairs/REPAIR_v1_4_1.md",
    ROOT / "docs/repairs/REPAIR_v1_4_2.md",
    ROOT / "docs/repairs/REPAIR_v1_4_3.md",
    ROOT / "docs/repairs/REPAIR_v1_4_4.md",
    ROOT / "docs/repairs/REPAIR_v1_4_5.md",
    ROOT / "docs/repairs/V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR.md",
    ROOT / "docs/research/SCIENTIFIC_WORKFLOW_AUDIT_v1_3_1.md",
    ROOT / "docs/research/MODEL_SIZE_PRIORITY_V1.md",
    ROOT / "docs/research/POLICY_DISCOVERY_V1.md",
    ROOT / "docs/ui/SCIENTIST_CHAT_R2_STREAMING_CONTRACT.md",
    ROOT / "docs/contracts/SCIENTIST_KNOWLEDGE_UPDATE_POLICY.md",
    ROOT / "docs/contracts/SCIENTIST_PYTHON_ANALYSIS_RUNTIME_V1.md",
    ROOT / "docs/reference/LLM_SCIENTIST_R1.md",
    ROOT / "docs/ui/UI_GROUPING_R1.md",
    ROOT / "docs/research/STRATEGY_OPTIMIZER_V2.md",
    PACKAGE_ROOT / "owner_acceptance/runtime/OWNER_MT5_STRATEGY_OPTIMIZER_V2_ACCEPTANCE.md",
    PACKAGE_ROOT / "governance/handoffs/STAGE12_STRATEGY_OPTIMIZER_V2_REBASE_AUDIT.md",
]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def watched_code_files() -> list[Path]:
    out: list[Path] = []
    excluded_top = {"tests", "evidence", "runtime", "docs", "skills", "requirements", "config"}
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in excluded_top:
            continue
        if "__pycache__" in rel.parts or p.name in EXCLUDED_CODE_NAMES or p.name.endswith(EXCLUDED_CODE_SUFFIXES):
            continue
        out.append(p)
    for rel in ("config/config.json", "config/models/model_registry.json"):
        p = ROOT / rel
        if p.exists():
            out.append(p)
    ea = PACKAGE_ROOT / "EA_v2_00" / "baseline" / "Max_MTF.mq5"
    if ea.exists():
        out.append(ea)
    imported_champion = PACKAGE_ROOT / "EA_v2_00" / "baseline" / "CHAMPION_IMPORTED_PARAMETERS.json"
    if imported_champion.exists():
        out.append(imported_champion)
    return sorted(set(out), key=lambda x: str(x))


def watched_doc_files() -> list[Path]:
    return [p for p in CANONICAL_DOCS if p.exists()]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PACKAGE_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def source_manifest() -> dict[str, str]:
    files = watched_code_files() + watched_doc_files() + ([TRAINING_METHOD_CONTRACT_PATH] if TRAINING_METHOD_CONTRACT_PATH.exists() else [])
    return {_rel(p): _sha(p) for p in files}


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def _model_capabilities(registry: dict) -> dict:
    fams = registry.get("families") if isinstance(registry, dict) else {}
    fams = fams if isinstance(fams, dict) else {}
    standalone = []
    temporal = []
    policy = []
    legacy_hybrids = []
    size_dims = {}
    for family, spec in fams.items():
        if not isinstance(spec, dict) or not spec.get("deployable", False):
            continue
        item = {
            "family": family,
            "category": spec.get("category"),
            "role": spec.get("role"),
            "input_contract": spec.get("input_contract"),
            "hybrid_compatible": bool(spec.get("hybrid_compatible", False)),
            "architecture_note": spec.get("architecture_note"),
            "strategy_expert_prior": list(spec.get("strategy_expert_prior") or []),
            "strategy_expert_prior_semantics": spec.get("strategy_expert_prior_semantics"),
            "expert_identity": spec.get("expert_identity"),
        }
        if spec.get("legacy_alias"):
            legacy_hybrids.append(item)
        else:
            standalone.append(item)
        if spec.get("role") == "temporal":
            temporal.append(family)
        if spec.get("role") == "policy":
            policy.append(family)
        size_dims[family] = list(spec.get("size_parameters") or [])
    return {
        "standalone_deployable": standalone,
        "temporal_families": temporal,
        "policy_families": policy,
        "legacy_hybrid_aliases": legacy_hybrids,
        "dynamic_hybrid_rule": "Any registered hybrid-compatible temporal family may be composed with any registered hybrid-compatible policy family when legal/capacity-feasible.",
        "family_size_dimensions": size_dims,
        "final_decision_contract": {"classes": ["SELL", "SKIP", "BUY"], "shape": "[N,3]"},
        "hybrid_runtime_contract": "Temporal predicts DOWN/UP out-of-fold; policy consumes CP32 plus temporal probabilities/signals and emits SELL/SKIP/BUY. In-sample stacking is forbidden.",
    }


def _risk_kpis(cfg: dict) -> list[dict]:
    rows=[]
    registry=((cfg.get("acceptance") or {}).get("risk_kpis") or {})
    if isinstance(registry, dict):
        for key, spec in registry.items():
            if not isinstance(spec, dict):
                continue
            rows.append({
                "id": key,
                "label": spec.get("label"),
                "enabled": bool(spec.get("enabled", False)),
                "threshold": spec.get("threshold"),
                "direction": spec.get("direction"),
                "unit": spec.get("unit"),
                "basis": spec.get("basis"),
            })
    return rows


def _workflow(cfg: dict) -> list[dict]:
    split=cfg.get("split") or {}; acc=cfg.get("acceptance") or {}; fc=cfg.get("champion_factory") or {}
    cstage=fc.get("cpcv_stage") or {}
    return [
        {
            "id":"STRATEGY_OPTIMIZER",
            "order":0,
            "purpose":"Upstream MT5 EA parameter search that produces Strategy Challengers; only explicit Owner promotion changes the current Max_MTF.mq5 Strategy Champion.",
            "authority":"MT5_NATIVE_PARAMETER_SEARCH_SEPARATE_FROM_RESEARCH",
            "contracts":[
                "This is not Discovery and does not run WFA/CPCV/Tournament/Monte Carlo/Fresh Forward",
                "PF >= 1, RF >= 0, Mean R >= frozen threshold, Weighted R >= frozen threshold",
                "AUTO minimum trades uses H1 baseline 20 trades/month, timeframe sqrt scaling, integer round-up monthly rate and integer round-up exact-range requirement",
                "MT5 genetic fitness is Custom max from Max OnTester arithmetic Mean R, so the MT5 Result column is Mean R; Weighted R = sum(net P/L)/sum(initial risk) is transported per pass through MT5 optimization frames and is an independent Python hard gate; Recovery Factor remains an independent hard gate sourced from the dedicated MT5 statistic",
                "when an eligible winner is found the Optimizer creates a human-readable Strategy Challenger EA + fixed .set + metadata bundle, leaves current Max_MTF.mq5/Max_MTF.set/strategy authority unchanged, enters STRATEGY_CHALLENGER_FOUND, then STOPS",
                "Owner manually runs the MT5 backtest to write training data, then explicitly STARTs ModelLab Research; Optimizer never auto-backtests, auto-generates the dataset, or auto-starts Research",
                "one Max round launches one native MT5 optimization; MT5 owns genetic population/job/task scheduling across tester agents, so Tasks/Passed counts are native passes inside the round rather than extra Max rounds",
                "each Optimizer round has durable PREPARED/MT5_RUNNING/MT5_COMPLETE/REPORT_READY/PARSED checkpoints; START/RESUME process compatible existing evidence first and Resume never reruns the checkpointed MT5 round",
                "after any parsed round with no eligible winner and remaining frozen round budget, Optimizer automatically performs bounded refinement and launches the next native MT5 round; no manual Continue authority exists",
                "Scientist is only next-range advisory on that automatic no-winner refinement: OFF=DETERMINISTIC_ONLY; actual successful LLM proposal=SCIENTIST_PROPOSAL with persisted deterministic acceptance/rejection; requested provider/model/call failure=DETERMINISTIC_FALLBACK with explicit reason",
                "if existing evidence already yields an eligible winner, Scientist is never called and no next round is launched; Strategy Challenger registration is an immediate hard stop and promotion remains explicit Owner authority",
                "if the frozen maximum round count is exhausted without a winner, terminal state is NO_CHAMPION_MAX_ROUNDS",
                "Windows atomic writes use unique same-directory temp files plus bounded WinError 5/32 retry, and launcher PID metadata is separated from worker-owned status.json",
                "MT5 SpreadsheetML Created is provenance only, not round-freshness authority; every launched round snapshots compatible report fingerprints before MT5 starts, prefers its unique requested report name, and accepts only a new/changed compatible XML while still enforcing internal EA+Symbol+Timeframe+From+To identity",
                "canonical runtime naming is Max_MTF.mq5/Max_MTF.ex5 with Max_MTF.xml and Max_MTF.set; round identity lives in checkpoint/evidence rather than R1/R2/R3 filename suffixes; new runtime flows never emit legacy ComplexPolicy_ONNXReady_EA or MAX_StrategyOptimizer_* names",
                "a brand-new Optimizer job may bootstrap only from compatible external/manual MT5 XML that has an explicitly paired <stem>.metrics.csv Weighted-R sidecar; XML-only legacy evidence is not v0.8.6 Champion-compatible; prior Max-generated reports remain usable only through the owning job checkpoint/recovery path",
                "Strategy Optimizer operator settings use durable shadow-state so Streamlit hidden-page widget cleanup cannot erase saved strategy_opt_* values; missing keys are rehydrated before page render while active jobs remain frozen",
                "round evidence persists report SHA, selection provenance, parsed-pass count, eligible-pass count, frozen KPI thresholds and per-gate counts; eligible_passes > 0 without a deterministic Strategy Challenger selection is a hard invariant failure rather than a no-winner continuation",
                "active Optimizer request freezes KPI, search-space/selected parameters, maximum rounds, native optimizer mode, date/symbol/timeframe and non-secret Scientist routing; later UI edits apply only to a new run",
            ],
            "evidence":["runtime/strategy_optimizer_runs/*/strategy_challenger.json", "EA_v2_00/challengers/Max_Challenger_*.mq5", "EA_v2_00/challengers/Max_Challenger_*.set", "runtime/strategy_challenger_registry.json"],
            "next":"OWNER_MT5_BACKTEST_AND_DATASET",
        },
        {
            "id":"DATA_QUALITY",
            "order":1,
            "purpose":"Prove the CP32 dataset is structurally valid and same-broker source continuity is verified before research.",
            "authority":"DETERMINISTIC_FAIL_CLOSED",
            "inputs":["master dataset CSV", "same-broker MT5 history for reconciliation"],
            "contracts":[
                "Required CP32_V1 columns and 32 features",
                "one symbol/timeframe only",
                "no duplicate identity rows",
                "finite features; valid OHLC/ATR/decision quotes",
                "ask >= bid; zero spread is warning, not hard failure",
                "broker reconciliation must be verified",
                "source-backed missing bars or dataset-only timestamps block readiness",
                "repair may use verified MT5 writer data only; no interpolation/forward-fill authority",
            ],
            "evidence":["data-quality report", "dataset_quality_context.json"],
            "next":"RESEARCH_PLAN_FREEZE",
        },
        {
            "id":"RESEARCH_PLAN_FREEZE",
            "order":2,
            "purpose":"Freeze chronology, hardware/data capacity, topology/family search authority and immutable research contract.",
            "authority":"DETERMINISTIC",
            "contracts":[
                "Discovery < Tournament < Fresh/Forward windows must be chronological and non-overlapping",
                "Dynamic Capacity Governor admits temporal candidates by min(LEGAL, RESOURCE, SCIENTIFIC) actual-parameter-count authority; model-size priority is search preference only",
                "current Owner config is distinct from frozen active research_plan",
                "AUTO and MANUAL proposal authorities are explicit and provenance-recorded",
            ],
            "evidence":["research_plan.json", "hardware_profile.json", "dataset_capacity_profile.json", "factory_manifest.json"],
            "next":"DISCOVERY_FULL_WFA",
        },
        {
            "id":"DISCOVERY_FULL_WFA",
            "order":3,
            "purpose":"Generate/evaluate candidate hypotheses without opening downstream holdouts.",
            "authority":"AUTO: Factory + deterministic Discovery with optional LLM proposals; MANUAL: Owner exact candidates. PASS/FAIL always deterministic.",
            "contracts":[
                "Topology allocation already supports Single/Hybrid priority including 0=single-only, 1=hybrid-only and intermediate percentages/AUTO allocation",
                "Per-family Small/Balanced/Large priority biases search location inside dynamic capacity and never hard-slices or widens executable ceilings",
                "Fidelity cheap screen may allocate compute but can never qualify a candidate",
                "Only Full chronological WFA can qualify a candidate for Pool",
                "Policy Discovery/window discovery/experiment blocks/research memory are existing Discovery capabilities when enabled",
                "LLM proposals never own admission or PASS/FAIL",
                "Discovery qualification uses gate_kpis.discovery; thresholds are frozen with the Factory scientific contract",
                "Research AUTO minimum trades uses H1 baseline 8 trades/month with timeframe scaling and integer round-up",
            ],
            "evidence":["research_runs/*/cv_leaderboard.json", "all_trials.jsonl", "failure_topology.json", "research_memory.json"],
            "next":"POOL",
        },
        {
            "id":"POOL",
            "order":4,
            "purpose":"Freeze WFA-qualified candidates before downstream validation.",
            "authority":"DETERMINISTIC",
            "defaults":{"target_pool":int(fc.get("target_pool",12) or 12), "minimum_pool":int(fc.get("minimum_pool",12) or 12), "pool_diversity_weight":fc.get("pool_diversity_weight")},
            "contracts":["Only independently revalidated Full-WFA PASS candidates enter", "AUTO Pool authority is exactly 12 candidates", "pool evidence plus Discovery/Tournament/refit-history snapshots are hash-sealed before CPCV", "CPCV results cannot retroactively tune active Discovery"],
            "evidence":["candidate_pool.json", "factory_manifest.json"],
            "next":"CPCV",
        },
        {
            "id":"CPCV",
            "order":5,
            "purpose":"Robustness qualification on purged combinatorial partitions after Pool freeze.",
            "authority":"DETERMINISTIC_HARD_GATE",
            "defaults":{
                "groups":int(split.get("cpcv_groups",6) or 6),
                "test_groups":int(split.get("cpcv_test_groups",2) or 2),
                "max_combinations":int(split.get("cpcv_max_combinations",15) or 15),
                "purge_bars":int(split.get("purge_bars",24) or 24),
                "embargo_bars":int(split.get("embargo_bars",split.get("purge_bars",24)) or 24),
                "target_survivors":int(cstage.get("target_survivors",3) or 3),
                "minimum_survivors_to_tournament":int(cstage.get("minimum_survivors_to_tournament",1) or 1),
            },
            "contracts":[
                "Finalist ranking is frozen from WFA OOF evidence before CPCV opens",
                "exactly 15 purged+embargoed splits for N=6,k=2; CPCV cannot be disabled",
                "purge_bars and embargo_bars must each be >= label horizon",
                "5 canonical reconstructed chronological paths feed path-dependent Advanced KPI",
                "DL/hybrid fixed seed confirmation = 42 -> 11 -> 77; all required seeds PASS; progressive stop on failure; no seed mining",
                "CPCV hard gates come from gate_kpis.cpcv and cannot be offset by ranking score",
                "PBO is CPCV-only and optional by default. v1.3.2 can compute cross-strategy CSCV-style PBO from the six-group CPCV OOS expectancy matrix when enough finalists exist; candidate-local pseudo-PBO remains forbidden. If Owner enables the hard gate and matrix evidence is insufficient, CPCV fails closed.",
            ],
            "evidence":["cpcv_finalist_plan.json", "cpcv_qualification_evidence.json", "cpcv_survivors.json"],
            "next":"TOURNAMENT",
        },
        {
            "id":"TOURNAMENT",
            "order":6,
            "purpose":"Apply frozen Tournament hard eligibility to every CPCV survivor, then rank PASS survivors; Tournament is not the untouched Fresh/OOS validation stage.",
            "authority":"DETERMINISTIC_HARD_GATE",
            "contracts":[
                "Tournament does not select a single winner; every KPI survivor proceeds",
                "stage verifies CPCV terminal seal and exact survivor identity",
                "stage uses the Tournament snapshot frozen before downstream validation",
                "base threshold or frozen CP_POLICY_V1 is replayed exactly",
                "Tournament eligibility uses gate_kpis.tournament; temporal/regime/stress evidence cannot be rescued by ranking",
                "all hard-gate survivors proceed; Tournament ranking does not impose Top-K elimination",
            ],
            "evidence":["tournament_immutable.csv", "tournament_leaderboard.json", "tournament_survivors.json"],
            "next":"MONTE_CARLO",
        },
        {
            "id":"MONTE_CARLO",
            "order":7,
            "purpose":"Bootstrap Tournament trade outcomes and reject candidates whose robust tail distribution violates survival gates.",
            "authority":"DETERMINISTIC_HARD_GATE",
            "defaults":{"simulations":int(fc.get("monte_carlo_simulations",10000) or 10000)},
            "contracts":[
                "Tournament terminal seal and exact survivor↔trade-return set are verified before simulation",
                "minimum 100 simulations",
                "Monte Carlo uses gate_kpis.monte_carlo independently: tail PF/expectancy/recovery, P95 DD, and configured probability loss/ruin/survival",
                "all Monte-Carlo survivors preserve model/seed/threshold/policy identity and proceed to Forward",
                "terminal Monte Carlo evidence is hash-sealed",
            ],
            "evidence":["monte_carlo_evidence.json", "monte_carlo_survivors.json"],
            "next":"FRESH_FORWARD",
        },
        {
            "id":"FRESH_FORWARD",
            "order":8,
            "purpose":"Evaluate frozen survivors on new/locked Fresh Forward data that was not used for selection.",
            "authority":"DETERMINISTIC_HARD_GATE_NO_TUNING",
            "contracts":[
                "Fresh/Forward evidence is not a tuning input for the same snapshot",
                "Fresh start boundary and pre-Forward refit history are frozen before OOS",
                "each Fresh extension must pass canonical Data Quality and same-symbol/timeframe authority",
                "committed Forward checks are append-only and individually sealed",
                "insufficient sample waits for new data rather than fabricating PASS",
                "every Monte-Carlo survivor is evaluated; Fresh Forward uses gate_kpis.fresh_forward independently and only PASS candidates may be ranked for Champion",
                "sufficient sample with zero PASS survivors is terminal for that Factory, not a fake wait state",
                "no runner-up substitution after a failed Forward candidate unless an explicit future contract says otherwise",
            ],
            "evidence":["forward_immutable_*.csv", "forward_evidence_*.json", "forward_leaderboard_*.json", "forward_check_*_terminal_seal.json"],
            "next":"CHAMPION",
        },
        {
            "id":"CHAMPION",
            "order":9,
            "purpose":"Select top-ranked Forward PASS candidate, export executable ONNX runtime and verify parity.",
            "authority":"DETERMINISTIC_SELECTION_AND_RUNTIME_GATE",
            "promotion_contract_source":"gate_kpis.champion_promotion",
            "contracts":[
                "Champion adds no new market/backtest dataset test; it verifies gate_kpis.champion_promotion",
                "Forward PASS precedes ranking",
                "Champion is the exact top-ranked Forward PASS identity and final fit uses only frozen pre-Forward history",
                "runtime manifest locks CP32 feature order and SELL/SKIP/BUY class order",
                "policy-qualified Champion exports a separately hashed CP_POLICY_V1 artifact",
                "ONNX parity tolerance comes from acceptance.max_onnx_abs_error",
                "FACTORY_WINNER_RUNTIME_BLOCKED means research selection passed but runtime export/parity failed; do not rerun research to hide a runtime defect",
                "Model Research outputs Challenger artifacts first; it never self-promotes a research winner into Production Champion",
                "v0.10.0 Challenger filenames are human-readable family+UTC identities; hash remains integrity evidence only, never operator-facing filename identity",
                "Owner promotion is explicit from the Champion registry after existing deterministic parity/test/shadow/promotion gates pass",
                "Model Challenger promotion is independent from Strategy Challenger promotion; model promotion cannot change SL/TP/MaxHold or Strategy execution geometry",
            ],
            "evidence":["champion.json", "champion_runtime/runtime_manifest.json", "champion_terminal_seal.json", "factory_manifest.json"],
            "next":"RUNTIME_EXTERNAL_VALIDATION",
        },
    ]


def _existing_capabilities(cfg: dict, registry: dict) -> list[dict]:
    arch=cfg.get("research_architecture") or {}; agent=cfg.get("agent") or {}; fc=cfg.get("champion_factory") or {}
    llm=agent.get("llm") or {}
    return [
        {"id":"DATA_QUALITY_CP32","status":"EXISTING","summary":"CP32 schema, physical integrity, feature health, market sanity and broker reconciliation gate research. v0.11.1 stages Data Quality as local/exact-SHA cached audit first: AUDIT and initial Auto Research preflight never open MT5; PASS proceeds directly to Research, while a repairable FAIL alone enters MT5 verify/repair. The repair stage uses the same verified broker/feed, dedicated training-enabled Max_MTF_GapRepair.set, preserves MT5 UTF-16/UTF-8 preset encoding, verifies missing=0 afterward, and caches that broker proof only for the exact repaired CSV SHA. v0.9.1 first-write-wins EA repair remains the writer authority; interpolation/synthetic rows remain forbidden."},
        {"id":"ONNX_RUNTIME_TRADE_AUDIT","status":"EXISTING","summary":"v0.9.1 EA runtime exposes the complete deployable tree/temporal model-family identity for Champion and Shadow, validates hybrid temporal→tree topology without changing tensor/decision authority, writes actual Max-owned MT5 Champion deals to Max_MTF_Champion_Trades.csv, and writes non-executing Shadow entry candidates with executed=0 to Max_MTF_Shadow_Trades.csv. Optimizer and gap-repair presets disable both audit writers; OnTester history rebuild remains the only optimizer R-fitness authority."},
        {"id":"CHALLENGER_LIFECYCLE","status":"EXISTING","summary":"Model lifecycle: v1.3.3 enforces Factory-winner retention end-to-end. Every sealed LangGraph AUTO FACTORY_WINNER must be registered as a persistent ELIGIBLE_CHALLENGER before terminal success. Registration is append/retain and idempotent; later winners never delete/replace older Challengers and PROMOTED status survives replay. Model Champion still requires explicit Owner promotion after deterministic promotion gates PASS. Factory/LangGraph has no promotion authority."},
        {"id":"GOLDEN_RESEARCH_E2E","status":"EXISTING","summary":"v1.2.5 keeps E2E_WORKFLOW_TEST_V1 sandbox-only, preserves separated Model/Strategy authority pages and 1:1 Forward-to-Challenger KPI evidence, and adds verified current Strategy Champion KPI evidence from Owner XML + Weighted-R sidecar. Synthetic sandbox-only promotion proofs remain explicitly labelled SYNTHETIC_E2E; production broker reconciliation and promotion KPI authority are unchanged. E2E artifacts are never production scientific evidence."},
        {"id":"STRATEGY_CHALLENGER_LIFECYCLE","status":"EXISTING","summary":"v0.11.0 separates Strategy Optimizer winner from current Strategy Champion. Eligible winners become human-readable Max_Challenger_STRAT-<UTC>-R<round>-P<pass>.mq5 + fixed .set + metadata with PF/RF/Mean R/Weighted R/Profit/Trades and exact setup. Current Max_MTF.mq5 remains unchanged until explicit Owner promotion. Promotion atomically commits Max_MTF.mq5, canonical Max_MTF.set, compile/deploy and Python strategy authority while demoting the prior Champion to a new Challenger. Only non-Champion Challengers may be deleted; audit tombstones remain."},
        {"id":"AUTO_AND_MANUAL_RESEARCH","status":"EXISTING","summary":"AUTO Factory and Owner-exact MANUAL Research are explicit proposal authorities; deterministic validation remains mandatory."},
        {"id":"TOPOLOGY_ALLOCATION","status":"EXISTING","summary":"Single/Hybrid candidate allocation already exists as a 0.00..1.00 Owner priority with single-only, hybrid-only and mixed allocations.","current_default":arch.get("hybrid_priority")},
        {"id":"FAMILY_SIZE_PRIORITY","status":"EXISTING","summary":"Per-family Small<->Large priority biases deterministic search inside dynamic capacity; it is not an executable hard-bound slice.","current_default":arch.get("family_size_priorities")},
        {"id":"MODEL_SIZE_ADVISOR","status":"EXISTING","summary":"v1.4.2 adds advisory-only dataset-aware Suggested 0.xx guidance for AUTO size sliders plus canonical current-slider parameter-range tooltips and MANUAL per-parameter suggested/legal ranges. Suggestions never mutate Owner controls; temporal parameter-count estimates use executable model constructors and tree parameter count remains N/A/data-dependent."},
        {"id":"STRATEGY_NAVIGATION_LIFECYCLE","status":"EXISTING","summary":"v1.4.3 binds Strategy Optimizer, Strategy Challengers and Strategy Champion navigation pages to one contextual Optimizer lifecycle/status authority while all non-Strategy pages remain on the Research lifecycle."},
        {"id":"KPI_UI_FULL_AUTHORITY","status":"EXISTING","summary":"v1.4.4 requires every active configurable Research hard PASS/FAIL threshold and enabled advanced-risk evidence-sufficiency requirement to be visible/editable in Advanced -> KPI by Gate. The UI edits the same frozen gate_kpis stage profiles consumed by deterministic evaluators; evaluation formulas are unchanged."},
        {"id":"MODEL_DETAIL_INSPECTOR_LIVE_RUNTIME","status":"EXISTING","summary":"v1.4.5 adds a read-only Model Detail Inspector across Research model/candidate lists and 2-second flat live status polling for Research and Strategy Optimizer; it does not change scientific evaluation, search, worker state or promotion authority. Tree models expose structural complexity instead of fabricated neural parameter counts."},
        {"id":"DYNAMIC_HYBRIDS","status":"EXISTING","summary":"Temporal and policy families can be composed into executable dynamic hybrids when registry/capacity-compatible."},
        {"id":"HARDWARE_DATA_CAPACITY","status":"EXISTING","summary":"Evidence-aware dynamic Capacity Governor separates LEGAL architecture, RESOURCE execution, and candidate-aware SCIENTIFIC information ceilings; historical recommended envelopes are starting guidance only."},
        {"id":"FIDELITY_LADDER","status":"EXISTING","summary":"Cheap screen exists for compute allocation; qualification authority remains Full WFA.","enabled":bool((agent.get("fidelity_ladder") or {}).get("enabled",False))},
        {"id":"POLICY_DISCOVERY","status":"EXISTING","summary":"Bounded OOF policy/selectivity search exists and cannot open locked/fresh holdout.","enabled":bool((agent.get("policy_discovery") or {}).get("enabled",False))},
        {"id":"TRAINING_MEMORY_WINDOW_DISCOVERY","status":"EXISTING","summary":"training_memory_months is an integrated candidate-search dimension within declared bounds.","enabled":bool((agent.get("window_discovery") or {}).get("enabled",False))},
        {"id":"SCIENTIFIC_CREATIVITY","status":"EXISTING","summary":"Scientific creativity controls proposal/search breadth only; it cannot alter KPI, chronology, CPCV seeds, Forward or PASS/FAIL.","current":((agent.get("search") or {}).get("scientific_creativity"))},
        {"id":"EXPERIMENT_BLOCKS_HYPOTHESES","status":"EXISTING","summary":"Bounded hypothesis experiment blocks, including hybrid ablation and seed stability, already exist.","enabled":bool((agent.get("experiment_blocks") or {}).get("enabled",False)),"hypothesis_kinds":list(llm.get("hypothesis_kinds") or [])},
        {"id":"RESEARCH_MEMORY","status":"EXISTING","summary":"Discovery-side research memory stores elites/failure topology/hypothesis lifecycle while excluding locked/fresh evidence.","enabled":bool((agent.get("research_memory") or {}).get("enabled",False))},
        {"id":"DOWNSTREAM_FAILURE_FEEDBACK","status":"EXISTING","summary":"Pool/CPCV/Tournament/Monte-Carlo failures may produce bounded learning for a new Discovery cycle; Forward is report-only for the same snapshot.","enabled":bool((fc.get("research_feedback") or {}).get("enabled",False))},
        {"id":"CPCV_PROGRESSIVE_FINALISTS","status":"EXISTING","summary":"Pool freezes before a separate progressive CPCV finalist stage with hard PASS/FAIL and fixed seed confirmation for DL/hybrid."},
        {"id":"GATE_KPI_PROFILES","status":"EXISTING","summary":"v0.7.9 stores independent Discovery, CPCV, Tournament, Monte Carlo and Fresh Forward statistical profiles plus a non-statistical Champion Promotion contract; the complete profile snapshot is frozen with the Factory."},
        {"id":"STRATEGY_OPTIMIZER_KPI","status":"EXISTING","summary":"Upstream MT5 Strategy Optimizer has separate editable PF/RF/Mean-R/Weighted-R/AUTO minimum-trade authority, defaults to H1 baseline 20/month, uses Custom max / OnTester Mean R as native genetic fitness, transports Weighted R through MT5 optimization frames as an independent hard gate, and keeps Recovery Factor separate. v0.8.6 history-rebuild R accounting from complete tester history instead of OnTradeTransaction event ordering remains in force. In v0.8.7, Strategy Optimizer/CP32 is the sole SL/TP/MaxHold authority: Model Research no longer exposes or stores duplicate execution-geometry label knobs, and purge/embargo automatically respect upstream MaxHold. Model Research label research owns only Min edge R / Min margin R / ambiguous policy. Discovery/WFA expectancy acceptance requires editable Overall OOF Mean R plus Median Fold Mean R plus Worst Fold Mean R, all as mandatory AND gates. Mixed/stale geometry fails closed, and adaptive lot/risk remains outside model features/targets. v0.8.8 binds every MT5 Weighted-R optimization frame to its exact FrameInputs parameter vector; the opaque unsigned 64-bit (uint64) frame pass ID is provenance only and must never be converted through float or joined directly to the SpreadsheetML display Pass column. v0.8.9 disables MT5 optimization-cache reuse because cached XML results can bypass frame replay; rows without Weighted-R frame evidence remain ineligible, unresolved native-gate contenders block Champion promotion, and are retained for next-round refinement. v0.9.0 established transactional EA↔Max_MTF.set parity for direct Champion commit. v0.11.0 supersedes the automatic commit step: an eligible Optimizer winner is first registered as a Strategy Challenger and cannot mutate canonical Max_MTF.mq5/Max_MTF.set/Python strategy authority. Explicit Owner promotion is transactional across canonical EA defaults, canonical Strategy Tester Max_MTF.set, compiled/deployed EX5, Python execution-geometry authority and the Strategy registry; the prior Champion is demoted into a uniquely coded Challenger, and any failure restores the pre-promotion authority. v0.9.1 keeps canonical Max_MTF.set immutable during Data Quality repair and uses a separate training-enabled Max_MTF_GapRepair.set so CP32 gaps can be filled without weakening current Champion tester parity. The same v0.9.1 authority also makes ONNX runtime family identity generic across current deployable tree/temporal families and isolates actual Champion deal audit from non-executing Shadow candidate audit; neither audit ledger can mutate optimizer fitness, strategy geometry, or live execution authority. v1.2.5 records the existing Strategy Champion KPI from uniquely matched Owner Max_MTF.xml + Max_MTF_metrics.csv evidence, including independent Weighted R arithmetic and R-trade parity, without changing strategy parameters or execution logic."},
        {"id":"ADVANCED_RISK_KPI","status":"EXISTING","summary":"Sharpe, Sortino, Calmar/MAR, PSR, DSR, Ulcer Index and daily CVaR are data-driven hard-gate metrics where enabled."},
        {"id":"MONTE_CARLO","status":"EXISTING","summary":"Configurable bootstrap robustness stage exists after Tournament."},
        {"id":"FRESH_FORWARD","status":"EXISTING","summary":"Fresh/Forward holdout is separated from tuning and can wait for new data when sample is insufficient."},
        {"id":"ONNX_RUNTIME_PARITY","status":"EXISTING","summary":"Champion export/parity gate exists; runtime-only failures produce FACTORY_WINNER_RUNTIME_BLOCKED rather than rewriting research results."},
        {"id":"SCIENTIST_PYTHON_ANALYSIS_RUNTIME","status":"EXISTING","summary":"v2.0.1 optional Scientist Python Analysis Runtime V1 provides one shared guarded analytical executor for autonomous LLM Scientist/Director and Scientist Chat. Generated scientific import spellings resolve to a deterministic capability allowlist/proxy surface rather than raw third-party module objects, closing transitive ctypes/native file/process/network authority while preserving approved in-memory NumPy/pandas/SciPy/sklearn analysis. It uses a dedicated user-local interpreter/environment separate from canonical MAX Python, accepts only host-authorized in-memory evidence IDs, records exact code/input/runtime provenance, and falls back to REASONING_ONLY on unavailable/rejected/error/timeout. Python output is ANALYTICAL_EVIDENCE_ONLY and can never own deterministic PASS/FAIL, candidate admission, promotion, training, acceptance, MT5, governance, or Factory state.","live_authority":"scientist_python_health() plus deterministic run_scientist_python_analysis(); static Knowledge never proves interpreter availability"},
        {"id":"SCIENTIST_CHAT_READ_ONLY","status":"EXISTING","summary":"Scientist Chat is read-only, model-selectable, per-model profiled and separate from autonomous Research Scientist routing."},
        {"id":"SCIENTIST_CHAT_STATE_RECONCILIATION","status":"EXISTING","summary":"Scientist Chat uses persistent thread identity, stale-event/result rejection, immutable terminal job state and explicit client reconciliation so completed replies settle without an operator Stop click."},
        {"id":"SCIENTIST_CHAT_BACKEND_INTEGRITY","status":"EXISTING","summary":"Scientist Chat enforces cross-process thread/request idempotency, monotonic terminal CAS, duplicate-call-safe provider compatibility/fallback, sealed deterministic evidence, route provenance and visible-history parity."},
        {"id":"LANGGRAPH_AGENTIC_SCIENTIST","status":"EXISTING","summary":"v1.3.3 AUTO Factory orchestration uses LangGraph and requires persistent Model Challenger registration before terminal Factory-winner success. The Research Director persists hypothesis memory and proposal lineage, requests bounded read-only evidence, attributes actual prior outcomes, designs the next experiments and can escape family/topology local optima inside the Owner allow-list. Deterministic code still owns legality and PASS/FAIL; Owner still owns promotion."},
        {"id":"SCIENTIST_DIRECTED_SEARCH","status":"EXISTING","summary":"SCIENTIST_DIRECTED family/topology authority keeps every Owner-allowed feasible path available across the Factory so the Scientist can choose local refinement, structural escape, family escape or topology escape without mutating hard KPI, Strategy geometry, Locked/Fresh evidence, CPCV seeds, live risk or promotion."},
        {"id":"AUTONOMOUS_LLM_SCIENTIST_ROUTING","status":"EXISTING","summary":"AUTO Factory Research Scientist/Director is ordered-fallback routed and exact-contract-memory scoped. In v1.3.3 it is agentic for bounded research direction, while deterministic validation remains the sole scientific PASS/FAIL authority and retryable stack exhaustion may fall back deterministically."},
    ]


def _kpi_scientist_policy(cfg: dict) -> dict:
    """Scientific interpretation layer for KPI advice; never runtime PASS/FAIL authority."""
    return {
        "authority":"ADVISORY_INTERPRETATION_ONLY_LIVE_GATE_KPIS_REMAIN_RUNTIME_AUTHORITY",
        "principles":[
            "Current gate_kpis are runtime authority; enabled=true describes current Owner config, not proof that the metric is scientifically well placed.",
            "Do not copy one KPI set across gates. Each gate answers a different scientific question.",
            "Do not enable many correlated risk metrics merely because they exist. Distinguish hard gates from diagnostics and preserve Discovery diversity.",
            "Never recommend lowering a frozen active-generation threshold after seeing its result. Changes apply only to a new configuration revision/generation.",
            "Use exact metric units. Do not silently convert percentage drawdown policy into R drawdown or vice versa.",
        ],
        "owner_policy_references":{
            "strategy_optimizer":{"h1_min_trades_per_month":20,"scope":"UPSTREAM_MT5_ONLY"},
            "research_trade_sample":{"h1_min_trades_per_month":8,"scope":"MODELLAB_RESEARCH_AUTO_SCALED"},
            "fresh_production_reference":{
                "expectancy_r_min":0.50,
                "profit_factor_min":1.50,
                "recovery_factor_min":3.00,
                "max_drawdown_percent_lt":10.0,
                "note":"Policy reference from Owner contract. Live Fresh gate_kpis remain execution authority; percent-DD must not be equated to max_drawdown_r without an explicit mapping."
            },
        },
        "gate_roles":{
            "discovery":{
                "question":"Can a candidate survive inexpensive screening and full chronological 3-fold WFA with enough trades and acceptable fold consistency?",
                "preferred_hard_gate_families":["expectancy/PF/RF/DD","AUTO trade sufficiency","worst-fold/non-negative evidence","fold consistency"],
                "risk_metric_policy":"Sharpe/Sortino/Calmar/Ulcer/CVaR are supplementary diagnostics by default; PSR/DSR should not be mandatory early-Discovery defaults.",
                "anti_pattern":"Do not turn every available risk metric ON and create a correlated zero-survivor filter."
            },
            "cpcv":{
                "question":"Does the frozen candidate remain robust across purged combinatorial partitions and reconstructed paths?",
                "preferred_hard_gate_families":["median/aggregate PF and expectancy","worst-path expectancy/PF/DD","positive-path ratio","path sample sufficiency"],
                "pbo_policy":"PBO is CPCV-only and OFF by default. When enabled, compute it from the six-group cross-strategy CPCV OOS expectancy matrix with the configured minimum finalist count; insufficient matrix evidence fails closed. Never fabricate candidate-level pseudo-PBO.",
                "anti_pattern":"Do not simply clone every Discovery risk gate into CPCV."
            },
            "tournament":{
                "question":"Which CPCV survivors remain eligible under the frozen Tournament evaluation and how should PASS survivors be ranked?",
                "dataset_semantics":"Tournament is not a new untouched OOS/Fresh dataset. It is a deterministic hard-eligibility plus ranking stage after CPCV.",
                "ranking_policy":"Ranking can order PASS survivors but cannot rescue a hard-gate failure; no Top-K elimination unless a future explicit contract changes this.",
                "psr_dsr_policy":"PSR may be considered only with predeclared benchmark and adequate sample. DSR requires defensible trial-universe/effective-trials accounting; otherwise leave it OFF/not authoritative."
            },
            "monte_carlo":{
                "question":"Does the candidate survive adverse resampling/path realizations?",
                "preferred_hard_gate_families":["P05 expectancy/PF/recovery","P95 drawdown","probability of loss","probability of ruin","survival rate"],
                "anti_pattern":"Do not treat PSR/DSR as Monte Carlo-native metrics; they answer statistical-confidence/multiple-testing questions, not path robustness."
            },
            "fresh_forward":{
                "question":"Does the frozen survivor generalize on untouched Fresh data without same-snapshot tuning?",
                "policy":"Use strict predeclared absolute production floors plus any predeclared degradation checks. Never relax Fresh after observing failure.",
                "owner_reference":"Expectancy >=0.50R, PF >=1.50, RF >=3.00, Max DD <10%, H1 trade-sample baseline 8/month (AUTO scaled). Flag unit/schema mismatches instead of silently translating them."
            },
            "champion":{
                "question":"May an upstream PASS candidate be promoted as an executable artifact?",
                "policy":"No sixth statistical market test. Verify all upstream PASS, artifact integrity, no post-Fresh tuning/config drift, ONNX export and parity/runtime contract."
            },
        },
        "metric_roles":{
            "sharpe_sortino_calmar_ulcer_cvar":"Useful diagnostics and optionally predeclared hard gates when sample/role justify them; existence in config is not a recommendation to enable them everywhere.",
            "psr":"Statistical confidence metric; avoid mandatory early-Discovery use by default. If promoted to hard gate, benchmark/sample policy must be explicit.",
            "dsr":"Multiple-testing/selection-bias metric; requires canonical trial accounting/effective trial universe. Do not compute from only the small survivor pool or pretend migrated enabled=true proves validity.",
            "pbo":"CPCV/CSCV selection-overfit metric requiring canonical cross-strategy matrix; NOT_COMPUTABLE is distinct from Owner intentionally disabling the concept.",
        },
    }


def _novelty_policy() -> dict:
    return {
        "required_before_recommendation": True,
        "classes": {
            "EXISTING":"Max already has the requested capability. Do not propose building it again; explain/configure/use the existing authority.",
            "EXTENSION":"An existing capability covers the core idea but a scientifically distinct extension may be useful. State the existing capability first, then the exact gap.",
            "EXPERIMENT":"No new feature is required; the idea can be tested with existing Factory controls/evidence. Propose an experiment, not a duplicate feature.",
            "NEW":"Capability is not present. It may be proposed as a new architecture/contract with expected integration points and validation burden.",
            "CONFLICT":"Suggestion would violate a hard scientific/governance invariant. Explain the conflict and offer a compliant alternative.",
            "OUTSIDE_CURRENT_CONTRACT":"Scientifically plausible but needs an explicit contract/revision before implementation.",
        },
        "rule":"Scientist may recommend beyond Max, but must first name overlapping EXISTING capability and avoid duplicate implementation suggestions.",
    }


def build_payload() -> dict:
    cfg=_load_json(ROOT/"config"/"config.json",{})
    registry=_load_json(ROOT/"config"/"models"/"model_registry.json",{})
    return {
        "schema":SCHEMA,
        "knowledge_revision":"SCIENTIST_KNOWLEDGE_MAX_MTF_V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR",
        "scientific_authority":"Max MTF v2.0.1 — canonical MTF-1 data foundation plus shared MODEL_TRAINING_METHOD_CONTRACT_V1 for Manual, AUTO, LLM Scientist and Scientist Chat",
        "control_revision":"Research Control R1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "purpose":"Machine-readable Max-native knowledge for read-only Scientist Chat and room-transfer contract audit.",
        "authority":{
            "scientist_may_recommend_outside_current_contract":True,
            "scientist_must_know_existing_capabilities_before_recommending":True,
            "scientist_must_not_duplicate_existing_capability":True,
            "scientist_must_label_evidence_vs_inference":True,
            "scientist_can_modify_research":False,
            "deterministic_code_owns_pass_fail":True,
            "locked_fresh_evidence_may_not_be_used_for_same_snapshot_tuning":True,
        },
        "workflow":_workflow(cfg),
        "data_contract":{
            "feature_contract":"CP32_V1",
            "feature_count":32,
            "classes":["SELL","SKIP","BUY"],
            "label_method":"ATR-scaled first-barrier/timeout outcome using Strategy Optimizer/Max EA execution geometry inherited from uniform CP32 sl_atr/tp_atr/max_hold_bars; ambiguous dual-hit bars are dropped by default; SKIP when edge/margin requirements are not met. Execution geometry is not a Model Research knob.",
            "current_label_defaults":deepcopy(cfg.get("label") or {}),
            "data_quality_fail_closed":True,
        },
        "models":_model_capabilities(registry),
        "model_training_method_contract":training_method_context(),
        "research_controls":{
            "research_mode":["AUTO","MANUAL"],
            "research_architecture":deepcopy(cfg.get("research_architecture") or {}),
            "model_size_advisor":{
                "schema":"MAX_MODEL_SIZE_ADVISOR_V1",
                "authority":"ADVISORY_ONLY_NEVER_AUTO_APPLY",
                "auto_slider_semantics":"0_TO_1_STEP_0_05_SEARCH_PREFERENCE; executable bounds are not hard-sliced by the slider; dynamic candidate capacity remains authoritative",
                "manual_semantics":"Exact Owner numeric values; tooltip shows suggested/legal range only",
                "data_scope":"Discovery window only; no Fresh/Locked/Shadow/Promotion feedback",
                "wfa_min_train_authority":"split.min_train_rows",
            },
            "trade_sample_policy":deepcopy(cfg.get("trade_sample_policy") or {}),
            "strategy_optimizer_kpi":deepcopy(((cfg.get("strategy_optimizer") or {}).get("kpi") or {})),
            "gate_kpis":deepcopy(cfg.get("gate_kpis") or {}),
            "kpi_ui_visibility_contract":{
                "schema":"MAX_KPI_UI_FULL_AUTHORITY_V1",
                "rule":"Every active configurable hard PASS/FAIL threshold and enabled risk-KPI evidence-sufficiency requirement must be visible/editable in Advanced -> KPI by Gate; methodology invariants remain non-editable.",
                "evaluation_formula_change":False,
                "inactive_fields_are_not_presented_as_active_kpi":True,
            },
            "model_inspector_live_runtime":{
                "schema":"MAX_MODEL_INSPECTOR_LIVE_RUNTIME_V1",
                "authority":"READ_ONLY_OBSERVABILITY_ONLY",
                "model_detail":"Stored candidate setup plus executable temporal trainable-parameter count when computable; tree models expose structural complexity and never fabricate neural parameter counts.",
                "research_polling":"2-second read-only lifecycle polling while active.",
                "optimizer_polling":"2-second read-only lifecycle polling while active.",
                "ui_rule":"Research and Strategy Optimizer live status are flat/outside card.",
                "forbidden":["MUTATE_CANDIDATE_FROM_INSPECTOR","MUTATE_RESEARCH_STATE_FROM_POLL","INVENT_TREE_PARAMETER_COUNT"],
            },
            "fidelity_ladder":deepcopy(((cfg.get("agent") or {}).get("fidelity_ladder") or {})),
            "policy_discovery":deepcopy(((cfg.get("agent") or {}).get("policy_discovery") or {})),
            "window_discovery":deepcopy(((cfg.get("agent") or {}).get("window_discovery") or {})),
            "experiment_blocks":deepcopy(((cfg.get("agent") or {}).get("experiment_blocks") or {})),
            "research_memory":deepcopy(((cfg.get("agent") or {}).get("research_memory") or {})),
            "learning_system":deepcopy(((cfg.get("agent") or {}).get("learning_system") or {})),
            "research_feedback":deepcopy(((cfg.get("champion_factory") or {}).get("research_feedback") or {})),
        },
        "kpi":{
            "authority":"PER_GATE_NOT_GLOBAL",
            "scientist_policy":_kpi_scientist_policy(cfg),
            "gate_profiles":deepcopy(cfg.get("gate_kpis") or {}),
            "research_trade_sample":deepcopy(cfg.get("trade_sample_policy") or {}),
            "strategy_optimizer_kpi":deepcopy(((cfg.get("strategy_optimizer") or {}).get("kpi") or {})),
            "champion_rule":"Champion is promotion/integrity/runtime authority; it performs no sixth statistical market test.",
            "ranking_rule":"Ranking/utility may order survivors but can never compensate for a failed hard gate.",
            "pbo_rule":"PBO belongs only to CPCV. v1.3.2 provides optional cross-strategy six-group computation; it is authoritative only when Owner enables it and minimum matrix evidence exists, otherwise it remains disabled/not-computable rather than approximated.",
        },
        "existing_capabilities":_existing_capabilities(cfg,registry),
        "novelty_policy":_novelty_policy(),
        "scientist_chat_contract":{
            "chat_state_revision":"Chat State R1",
            "terminal_reconciliation":"Pending V2 component updates a hidden reconcile state on a bounded cadence; the registered state callback reruns the Scientist fragment so partial/terminal worker state settles automatically without operator Stop.",
            "clear_semantics":"Clear Chat cancels active work, atomically empties history and rotates persistent thread_id.",
            "stale_isolation":"UI events and background jobs carry thread_id; stale pre-clear sends/results are rejected and cannot repopulate the new thread.",
            "terminal_immutability":"Late Stop cannot overwrite COMPLETED/FAILED/CANCELLED job state.",
        },
        "scientist_response_contract":{
            "before_recommending":[
                "Identify relevant existing Max capability from this knowledge base.",
                "Compare current Owner config vs frozen active research plan when available.",
                "Classify suggestion as EXISTING / EXTENSION / EXPERIMENT / NEW / CONFLICT / OUTSIDE_CURRENT_CONTRACT.",
                "State evidence that supports the recommendation and what remains hypothesis/speculation.",
                "Do not invent warning causes, numeric ratings, thresholds or stage results absent from evidence.",
            ],
            "preferred_format":["Current Max capability","Observed evidence/gap","Classification","Recommendation","Why","Trade-off","How to validate"],
        },
        "project_mtf":{
            "schema":"MAX_MTF_PROJECT_CONTEXT_V2",
            "project":"Max MTF",
            "version":"2.0.1",
            "ea_version":"2.00",
            "fork_source":"Max single-TF v1.4.5",
            "single_tf_status":"CLOSED_EXCEPT_BUGFIX",
            "strategy_champion":None,
            "model_champion":None,
            "baseline":"BASELINE-MTF-V2",
            "baseline_is_champion":False,
            "active_ea":"EA_v2_00/baseline/Max_MTF.mq5",
            "mtf_roles":{"TF+2":"Trend / Regime / Volatility","TF+1":"Setup / Pullback / Breakout / Structure","TF":"Primary Decision","TF-1":"Entry Timing / Execution"},
            "reference_ladder":["H4","H1","M15","M5"],
            "mt5_target":"VERIFIED_TERMINAL_DATA_ROOT_ONLY_NOT_RAW_C_DRIVE",
            "mtf_logic_status":"MTF1_DATA_FOUNDATION_IMPLEMENTED_NOT_RESEARCH_ACTIVE",
            "mtf_data":deepcopy(cfg.get("mtf_data") or {}),
        },
        "source_manifest":source_manifest(),
    }


def compact_context(payload: dict | None = None) -> dict:
    p=payload if isinstance(payload,dict) else load_knowledge()
    return {
        "schema":p.get("schema"),
        "knowledge_revision":p.get("knowledge_revision"),
        "scientific_authority":p.get("scientific_authority"),
        "control_revision":p.get("control_revision"),
        "authority":deepcopy(p.get("authority") or {}),
        "workflow":[{
            "id":x.get("id"),"purpose":x.get("purpose"),"authority":x.get("authority"),
            "contracts":deepcopy(x.get("contracts") or []),"next":x.get("next")
        } for x in (p.get("workflow") or [])],
        "existing_capabilities":deepcopy(p.get("existing_capabilities") or []),
        "novelty_policy":deepcopy(p.get("novelty_policy") or {}),
        "models":deepcopy(p.get("models") or {}),
        "model_training_method_contract":deepcopy(p.get("model_training_method_contract") or {}),
        "kpi_scientist_policy":deepcopy(((p.get("kpi") or {}).get("scientist_policy") or {})),
        "scientist_chat_contract":deepcopy(p.get("scientist_chat_contract") or {}),
        "scientist_response_contract":deepcopy(p.get("scientist_response_contract") or {}),
        "project_mtf":deepcopy(p.get("project_mtf") or {}),
    }


def load_knowledge() -> dict:
    return _load_json(KB_JSON,{})


def sync_status(payload: dict | None = None) -> dict:
    p=payload if isinstance(payload,dict) else load_knowledge()
    expected=p.get("source_manifest") if isinstance(p.get("source_manifest"),dict) else {}
    current=source_manifest()
    changed=sorted(k for k in set(expected)|set(current) if expected.get(k)!=current.get(k))
    return {"in_sync":not changed,"changed":changed,"expected_count":len(expected),"current_count":len(current)}


def _workflow_audit_semantics(audit: dict | None) -> dict[str, Any]:
    """Return deterministic audit semantics, excluding generation timestamp only."""
    src = audit if isinstance(audit, dict) else {}
    return {k: deepcopy(v) for k, v in src.items() if k != "generated_utc"}


def workflow_audit_sync_status(payload: dict | None = None, persisted_audit: dict | None = None) -> dict[str, Any]:
    """Compare persisted workflow audit with a recomputation from current authority.

    This closes the stale-artifact hole where the canonical acceptance suite changes
    after Knowledge generation but the persisted WORKFLOW_CONTRACT_AUDIT_R1.json still
    says PASS.  generated_utc is intentionally excluded; every semantic field must match.
    """
    p = payload if isinstance(payload, dict) else load_knowledge()
    stored = persisted_audit if isinstance(persisted_audit, dict) else _load_json(AUDIT_JSON, {})
    current = workflow_audit(p)
    stored_sem = _workflow_audit_semantics(stored)
    current_sem = _workflow_audit_semantics(current)
    keys = sorted(set(stored_sem) | set(current_sem))
    changed = [k for k in keys if stored_sem.get(k) != current_sem.get(k)]
    return {
        "in_sync": not changed,
        "changed": changed,
        "persisted_overall_status": stored.get("overall_status"),
        "current_overall_status": current.get("overall_status"),
        "persisted_first_failed_gate": stored.get("first_failed_gate"),
        "current_first_failed_gate": current.get("first_failed_gate"),
    }


def local_acceptance_expectations() -> dict[str, Any]:
    """Derive release-integrity expectations from the canonical ordered acceptance suite.

    Scientist Knowledge must never own an independent gate-count integer.  The ordered
    ``run_acceptance.TESTS`` list is the single local-acceptance count authority.
    """
    from acceptance.runners.run_acceptance import TESTS as canonical_local_acceptance_tests

    gate_count = len(canonical_local_acceptance_tests)
    return {
        "gate_count": gate_count,
        "target": f"{gate_count}/{gate_count} PASS",
        "status_prefix": f"MTF1_EXTERNAL_EXECUTION_PROOF_{gate_count}_OF_{gate_count}",
        "exact_results_token": f"EXACT_ORDERED_{gate_count}_RESULTS",
        "exact_gate_script_token": f"EXACT_ORDERED_{gate_count}_GATE_SCRIPT",
    }


def workflow_audit(payload: dict | None = None) -> dict:
    p=payload if isinstance(payload,dict) else build_payload()
    code={x.name:x.read_text(encoding="utf-8",errors="replace") for x in watched_code_files() if x.suffix==".py"}
    checks=[]
    def ck(name: str, passed: bool, evidence: str):
        checks.append({"gate":name,"status":"PASS" if passed else "FAIL","evidence":evidence})
    fw=code.get("factory_worker.py",""); rc=code.get("research_control.py",""); cf=code.get("champion_factory.py","")
    fo=code.get("factory_orchestrator.py",""); sc=code.get("scientist_chat.py",""); dq=code.get("data_quality.py","")
    rp=code.get("research_planner.py",""); cpcv=code.get("cpcv.py","")
    labels=code.get("labels.py",""); models=code.get("models.py",""); onnx=code.get("onnx_export.py","")
    hybrid=code.get("hybrid_research.py",""); scientist=code.get("scientist.py","")
    so=code.get("strategy_optimizer.py",""); sow=code.get("strategy_optimizer_worker.py",""); gap=code.get("mt5_gap_repair.py","")
    ea=(PACKAGE_ROOT/"EA_v2_00"/"baseline"/"Max_MTF.mq5").read_text(encoding="utf-8",errors="replace") if (PACKAGE_ROOT/"EA_v2_00"/"baseline"/"Max_MTF.mq5").exists() else ""
    scr=code.get("strategy_challenger_registry.py","")
    ck("CHAMPION_TESTER_PRESET_PARITY", 'write_champion_tester_preset' in so and 'assert_champion_ea_set_parity' in so and 'write_champion_tester_preset(req,params,path=tester_set)' in scr and 'tester_set.write_bytes(before_set)' in scr and 'DEMOTED_CHAMPION' in scr, "v0.11.0 explicit Strategy promotion synchronizes/validates canonical Max_MTF.set, demotes the former Champion, and rolls EA/set/authority/registry back on failure")
    ck("DATA_QUALITY_AUTO_AND_MANUAL_PREFLIGHT", 'action=="AUTO"' in fw and 'action=="MANUAL"' in fw and fw.count('_prepare_auto_data_quality(')>=3, "factory_worker routes both AUTO and MANUAL through owned-worker Data Quality preflight")
    ck("DATA_QUALITY_BROKER_FAIL_CLOSED", 'BROKER_RECONCILIATION_REQUIRED' in dq and 'SOURCE_BACKED_MISSING_BARS' in dq and 'DATASET_ONLY_TIMESTAMPS' in dq, "research_readiness requires verified broker reconciliation and zero source/dataset mismatches")
    ck("V091_MT5_GAP_REPAIR_DEDICATED_PRESET", 'from mtf.mtf_names import TRAINING_CSV, TESTER_SET, GAP_REPAIR_SET' in gap and 'dest=src.with_name(GAP_REPAIR_SET)' in gap and 'InpWriteTrainingData' in gap and 'InpTrainingFile' in gap and 'TESTER_STARTED_PENDING_AUDIT' in gap and '_running_target_terminal_pids' in gap and 'Strategy geometry mismatch' in gap, "v0.9.1 dedicated training-enabled Tester preset and exact geometry authority remain active through canonical GAP_REPAIR_SET naming authority")
    ck("V0111_STAGED_DATA_QUALITY_REPAIR", 'broker_reconcile=False,use_cached_broker_proof=True' in fw and 'run_gap_repair_cycle' in fw and 'REPAIR / VERIFY WITH MT5' in code.get("app.py","") and '_read_mt5_text' in gap and 'utf-16' in gap and 'REPAIRED_AND_VERIFIED' in gap, "v0.11.1 AUDIT/Auto preflight is local first; only repairable FAIL may open MT5, repair preserves MT5 preset encoding, and post-repair broker verification is mandatory")
    ck("V091_ONNX_FAMILY_AND_TRADE_AUDIT", all(x in ea for x in ['MODEL_FAMILY_LIGHTGBM','MODEL_FAMILY_XGBOOST','MODEL_FAMILY_RANDOM_FOREST','MODEL_FAMILY_GRU','MODEL_FAMILY_LSTM','MODEL_FAMILY_TCN','MODEL_FAMILY_TRANSFORMER_ENCODER','MODEL_FAMILY_PATCHTST','MODEL_FAMILY_ITRANSFORMER','MODEL_FAMILY_TFT','MODEL_FAMILY_TRANSFORMER_MOE','Max_MTF_Champion_Trades.csv','Max_MTF_Shadow_Trades.csv','TRADE_TRANSACTION_DEAL_ADD','SHADOW_ENTRY_CANDIDATE']) and 'InpWriteChampionTrades": False' in so and 'InpWriteShadowTrades": False' in so, "v0.9.1 ONNX family identity covers the deployable registry universe; Champion actual deals and Shadow non-executing candidates are isolated audit ledgers disabled during optimizer/gap repair")
    ck("MANUAL_ZERO_LLM", 'llm["enabled"] = False' in rc and '"llm_used": False' in rc, "compiled MANUAL runtime disables autonomous LLM")
    ck("MANUAL_ZERO_DISCOVERY_GENERATION", '"deterministic_discovery_used": False' in rc and 'OWNER_MANUAL_EXACT' in rc, "MANUAL proposal authority is Owner exact candidates")
    ck("MANUAL_VALIDATION_CHAIN", all(s in fo for s in ['run_cpcv_qualification','run_tournament','run_monte_carlo','run_forward_championship']), "manual orchestrator retains downstream deterministic validators")
    ck("POOL_BEFORE_CPCV", 'DISCOVERY_POOL_READY' in cf and 'CPCV fail-closed: frozen WFA-qualified Discovery pool belum READY' in cf, "CPCV cannot open before frozen WFA pool")
    ck("CPCV_FIXED_SEEDS", '42' in cf and '11' in cf and '77' in cf and 'seed_confirmation' in cf, "DL/hybrid CPCV uses fixed seed confirmation authority")
    ck("CPCV_PURGE_EMBARGO", 'purge_bars' in cpcv and 'embargo_bars' in cpcv and 'cpcv_splits' in cpcv, "CPCV source uses purged/embargo splits")
    ck("TOURNAMENT_AFTER_CPCV", 'CPCV_SURVIVORS_READY' in cf and 'TOURNAMENT_SURVIVORS_READY' in cf, "Tournament consumes CPCV survivors and emits survivor set")
    ck("MONTE_CARLO_AFTER_TOURNAMENT", 'TOURNAMENT_SURVIVORS_READY' in cf and 'MONTE_CARLO_SURVIVORS_READY' in cf, "Monte Carlo consumes Tournament survivors")
    ck("FORWARD_AFTER_MONTE_CARLO", 'MONTE_CARLO_SURVIVORS_READY' in cf and 'NO_CHAMPION_FORWARD_FAIL' in cf, "Forward consumes Monte Carlo survivors and fails closed")
    ck("CHAMPION_ONNX_PARITY", 'FACTORY_WINNER_RUNTIME_BLOCKED' in cf and 'max_onnx_abs_error' in cf, "Champion selection is separated from runtime export/parity failure")
    ck("STAGE1_DATA_FLOW_ATOMIC_AUTHORITY", '_assert_data_quality_authority(master,cfg)' in cf and 'DATA_FLOW_TEMPORAL_LEAKAGE_GUARD' in cf and 'read_csv_auto(path)' in code.get("model_lab.py","") and 'np.isfinite(vals).all()' in code.get("model_lab.py",""), "Data Flow binds Discovery to exact DQ source hash, fail-closes temporal leakage and rejects non-finite CP32 features")
    ck("STAGE2_DISCOVERY_FROZEN_AUTHORITY", 'configured_target != 12' in cf and 'discovery_stage_contract_hash' in cf and 'FULL_WFA_POLICY' in cf and 'tournament_immutable.csv' in cf and 'forward_refit_history.csv' in cf, "Discovery freezes exact scientific/window authority, exact AUTO Pool 12, policy-qualified Full-WFA identity and downstream historical snapshots")
    ck("STAGE3_CPCV_MANDATORY_EXACT", 'CPCV_MANDATORY_EXACT' in cf and '(6,2,15)' in cf and '_verify_stage_seal(fd,"DISCOVERY"' in cf and '_assert_temporal_leakage_guard(cfg,require_embargo=True)' in cf and '[42,11,77]' in cf, "CPCV is mandatory exact 6C2=15 with purge/embargo guards, sealed Pool input and fixed temporal seed confirmation")
    ck("STAGE4_TOURNAMENT_SEALED_POLICY_REPLAY", '_verify_stage_seal(fd,"CPCV"' in cf and '_stage_seal(fd,"TOURNAMENT"' in cf and '_strategy_outcomes' in cf and 'tournament_immutable.csv' in cf, "Tournament verifies CPCV terminal seal, uses pre-frozen holdout and replays exact strategy/policy identity")
    ck("STAGE5_MONTE_CARLO_SEALED_IDENTITY", '_verify_stage_seal(fd,"TOURNAMENT"' in cf and '_stage_seal(fd,"MONTE_CARLO"' in cf and 'survivor/trade-return set mismatch' in cf and 'trade count mismatch' in cf, "Monte Carlo verifies Tournament seal, exact return-set/count authority and seals identity-preserving survivors")
    ck("STAGE6_FORWARD_APPEND_ONLY_AUTHORITY", '_verify_stage_seal(fd,"MONTE_CARLO"' in cf and 'FORWARD_APPEND_ONLY_VIOLATION' in cf and 'forward_leaderboard_{n:03d}.json' in cf and 'predeclared Fresh boundary drift' in cf and "'status':'NO_CHAMPION_FORWARD_FAIL','stage':'TERMINAL'" in fo, "Forward is predeclared, Data-Quality gated, append-only and distinguishes immature wait from terminal sufficient-sample failure")
    ck("STAGE7_CHAMPION_RUNTIME_SEAL", 'CP_CHAMPION_RUNTIME_V2' in cf and 'feature_order' in cf and '["SELL","SKIP","BUY"]' in cf and 'decision_policy.csv' in cf and '_stage_seal(fd,"CHAMPION"' in cf, "Champion binds exact winner/refit/OOS lineage, explicit CP32/class order, optional policy artifact, ONNX parity and terminal runtime seal")
    fj=code.get("factory_jobs.py",""); fworker=code.get("factory_worker.py","")
    ck("STAGE8_E2E_ATOMIC_RESUME_AND_TERMINAL_AUTHORITY",
       'with _job_registry_lock(factory_root)' in fj
       and 'status not in RESUMABLE_STATUSES' in fj
       and 'WAITING_FOR_NEW_FORWARD_DATA' in fworker and 'job["status"]="PAUSED"' in fworker
       and '_record_completed_factory' in fo and 'verify_champion_terminal_authority' in fo
       and 'retry_failure_scientist_learning' in cf and cf.count('_verify_stage_seal(fd,') >= 8,
       "E2E orchestration is single-active and resumable at Forward wait; failure-learning and terminal Champion consumption require sealed evidence")
    pc=code.get("provider_catalog.py",""); lh=code.get("llm_health.py",""); sup=code.get("supervisor_agent.py","")
    ck("STAGE9_LLM_SCIENTIST_ORDERED_FAILSAFE_AUTHORITY",
       'stop_research_advisory' in scientist
       and 'inspect.signature' in scientist
       and 'factory_session_deterministic_only' in cf
       and 'DETERMINISTIC_ONLY_AFTER_LLM_EXHAUSTION' in sup
       and 'PROVIDER_UNREACHABLE' in pc
       and 'status in {400,401,403,422}' in pc
       and '_cross_process_lock' in lh
       and 'Global Research Memory corrupt' in cf,
       "Autonomous LLM Scientist is advisory-only; ordered fallback is retryable-only, endpoint-scoped, duplicate-call safe, deterministic on exhaustion and exact-memory fail-closed")
    ck("TOPOLOGY_ALLOCATION_EXISTING", 'configured_hybrid_priority' in rp and 'allocation_counts' in rp, "Single/Hybrid allocation already exists in planner")
    import ast
    chat_tree=ast.parse(sc)
    imported_modules=set()
    for node in ast.walk(chat_tree):
        if isinstance(node,ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    forbidden_chat_imports={"factory_control","champion_factory","factory_jobs"}
    ck("SCIENTIST_READ_ONLY", not (imported_modules & forbidden_chat_imports) and 'can_modify_research' in sc, "Scientist Chat has no execution imports and context declares no mutation authority")
    ck("LABEL_FIRST_BARRIER_CONTRACT", all(x in labels for x in ["_first_barrier", "min_edge_r", "min_margin_r", "ambiguous_policy"]), "labels.py implements ATR first-barrier labeling, edge/margin separation and explicit ambiguous-bar handling")
    ck("FINAL_DECISION_SELL_SKIP_BUY", "FINAL_DECISION_CLASSES = (0, 1, 2)" in models and "SELL/SKIP/BUY" in models and "[0,1,2]=[SELL,SKIP,BUY]" in onnx, "model and ONNX authorities preserve canonical SELL/SKIP/BUY class order")
    ck("HYBRID_OOF_STACKING", "Leakage-safe" in hybrid and "out-of-fold" in hybrid and "OOF_DIRECTION_STACK_V2_PURGED_INDEXED" in hybrid, "hybrid policy sees purged/index-preserving OOF temporal meta-features rather than in-sample stacking")
    ck("FULL_WFA_ONLY_POOL_ADMISSION", 'qualification_authority":"FULL_WFA_ONLY' in cf and "only WFA PASS rows" in cf, "Pool admission authority is Full-WFA PASS only; cheap/ranking evidence cannot qualify")
    gk=code.get("gate_kpi.py",""); sp=code.get("sample_policy.py",""); so=code.get("strategy_optimizer.py","")
    ck("V076_KPI_BY_GATE_AUTHORITY", "MAX_GATE_KPI_PROFILES_V1" in gk and all(x in gk for x in ["discovery","cpcv","tournament","monte_carlo","fresh_forward","champion_promotion"]) and '"gate_kpis": gate_profiles_snapshot(cfg)' in cf, "Research statistical thresholds are per-gate and participate in the frozen scientific contract")
    ck("V076_TRADE_SAMPLE_AUTHORITY", "CEIL_MONTHLY_RATE_AND_FINAL_REQUIREMENT" in sp and "base_h1_trades_per_month" in sp and "OPTIMIZER_H1_TRADES_PER_MONTH = 20" in so, "Optimizer and Research share deterministic timeframe scaling while retaining separate H1 baselines and integer round-up")
    sow=code.get("strategy_optimizer_worker.py",""); soj=code.get("strategy_optimizer_jobs.py",""); app_src=code.get("app.py",""); settings=code.get("settings_store.py","")
    ck("V083_OPTIMIZER_AUTO_CONTINUE_CHAMPION_STOP_WINDOWS_IO",
       "ROUND_COMPLETE_NO_CHAMPION" in sow and "NO_CHAMPION_MAX_ROUNDS" in sow and "while True:" in sow
       and "Hard stop contract: once an eligible winner exists" in sow
       and "continue_next_round_job" not in soj and "CONTINUE NEXT ROUND" not in app_src
       and "RECOVER LATEST MT5 RESULT" not in app_src and "RESUME FROM MT5 REPORT" not in app_src
       and "MAX_STRATEGY_OPTIMIZER_PROCESS_OWNER_V1" in soj and "worker_process.json" in soj
       and "atomic_write_json" in sow and "atomic_write_json" in soj and "mkstemp" in fj
       and "strategy_opt_symbol" in settings and "strategy_opt_scientist" in settings
       and "SCIENTIST_PROPOSAL" in sow and "DETERMINISTIC_ONLY" in sow and "DETERMINISTIC_FALLBACK" in sow
       and "prelaunch_report_snapshot" in sow and "EXPECTED_CANONICAL_REPORT" in sow and "FRESH_FINGERPRINT" in sow
       and "eligibility_audit" in sow and "report_sha256" in sow and "report_selection_mode" in sow
       and 'from core.project_paths import EA_SOURCE' in so
       and 'from mtf.mtf_names import OPTIMIZER_METRICS_CSV, OPTIMIZER_REPORT_XML, TESTER_SET' in so
       and 'set_name=TESTER_SET' in sow and 'report_name=OPTIMIZER_REPORT_XML' in sow
       and "discover_bootstrap_optimization_reports" in so and 'max_r\\d+\\.xml' in so.lower()
       and "Report provenance:" in app_src and "Evidence report" in app_src,
       "Winner is a hard stop; no-winner auto-refines/continues within frozen max_rounds; report freshness is fingerprint-proven rather than MT5-Created-clock based; exact report/KPI eligibility evidence is visible; no manual Continue/Recovery authority remains; Optimizer form state is durable; Scientist path and Windows-safe atomic/process ownership are machine-readable")
    sg=code.get("strategy_geometry.py",""); sor=code.get("strategy_optimizer_runtime_acceptance.py","")
    ck("V085_STRATEGY_GEOMETRY_WEIGHTED_R_AUTHORITY",
       "synchronize_cfg_with_dataset_geometry" in sg and "STRATEGY_GEOMETRY_MIXED_DATASET" in sg
       and "persist_optimizer_champion_authority" in sg and "OrderCalcProfit" in (PACKAGE_ROOT/"EA_v2_00"/"baseline"/"Max_MTF.mq5").read_text(encoding="utf-8",errors="replace")
       and "StrategyOptimizerInitialRiskFromDeal" in (PACKAGE_ROOT/"EA_v2_00"/"baseline"/"Max_MTF.mq5").read_text(encoding="utf-8",errors="replace")
       and "min_weighted_r" in so and "parse_optimizer_metrics_csv" in so and "weighted_r" in sow
       and "optimizer_metrics_sha256" in sow and "WEIGHTED_R_SIDECAR_HASH_MISMATCH" in sor
       and 'number_input("Min Weighted R"' in app_src and "strategy_opt_kpi_weighted_r" in settings,
       "v0.8.9 preserves the v0.8.8 FrameInputs identity, disables MT5 optimization-cache reuse for frame-dependent Weighted-R evidence, and blocks Champion promotion while any native-gate contender lacks Weighted-R evidence; v0.9.0 additionally requires atomic Champion parity between EA defaults and canonical Tester Max_MTF.set before CHAMPION_FOUND")
    ea_src=(PACKAGE_ROOT/"EA_v2_00"/"baseline"/"Max_MTF.mq5").read_text(encoding="utf-8",errors="replace")
    ck("V086_OPTIMIZER_HISTORY_REBUILD_AUTHORITY",
       "StrategyOptimizerRebuildHistoryMetrics()" in ea_src
       and "HistorySelect(0,to_time)" in ea_src
       and "HistoryOrderGetDouble(order_ticket,ORDER_SL)" in ea_src
       and "bool rebuilt=StrategyOptimizerRebuildHistoryMetrics();" in ea_src
       and "OnTradeTransaction" in ea_src,
       "v0.8.6 rebuilds Mean/Weighted R from complete tester history instead of event-order-dependent trade callbacks")
    kpi_src=code.get("kpi.py",""); labels_src=code.get("labels.py",""); ti_src=code.get("temporal_index.py","")
    ck("V087_RESEARCH_STRATEGY_BOUNDARY_OVERALL_MEAN_R",
       "cv_min_overall_expectancy_r" in gk and "CV_OVERALL_EXPECTANCY" in kpi_src
       and "resolved_strategy_horizon_bars" in ti_src
       and "assert_strategy_geometry_matches_dataset" in labels_src
       and "Horizon · Strategy locked" not in app_src
       and "SL × ATR · Strategy locked" not in app_src
       and "TP × ATR · Strategy locked" not in app_src,
       "v0.9.1 retains v0.9.0 Champion EA↔Tester Max_MTF.set parity/rollback, v0.8.9 cache/frame completeness, v0.8.8 exact FrameInputs identity, and v0.8.7 Research geometry/Overall-Median-Worst Mean-R authority")
    ck("FORWARD_NO_SAME_SNAPSHOT_TUNING", "Forward remains report-only for the same snapshot" in cf and 'research_restart_required":False' in cf, "Forward evidence is report-only for same snapshot and cannot trigger same-snapshot research restart")
    ck("AUTONOMOUS_SCIENTIST_LOCKED_EXCLUSION", "context deliberately excludes locked-test results" in scientist and "no authority to inspect or optimize against locked/fresh holdouts" in scientist.lower(), "autonomous Research Scientist context excludes locked/fresh tuning authority")
    ck("SCIENTIST_KNOWLEDGE_SYNC_INTEGRATION", 'scientist_knowledge' in sc and 'max_knowledge' in sc, "Scientist Chat loads Max-native capability/workflow knowledge")
    spr=code.get("scientist_python_runtime.py",""); spc=code.get("scientist_python_child.py","")
    ck("SCIENTIST_PYTHON_ANALYTICAL_ONLY",
       'ANALYTICAL_EVIDENCE_ONLY' in spr and 'run_scientist_python_analysis' in spr
       and 'factory_control' not in spr and 'champion_factory' not in spr and 'factory_jobs' not in spr
       and 'analysis_capability_instruction' in scientist and 'run_scientist_python_analysis' in scientist
       and 'analysis_capability_instruction' in sc and 'run_scientist_python_analysis' in sc
       and 'SCIENTIST_PYTHON_CHILD' in spr and '_SAFE_BUILTINS' in spc,
       "Scientist Python is one shared capability-allowlisted analytical-support runtime with no Factory/control authority; autonomous Scientist and Chat reuse the same host executor and generated code never receives raw scientific module objects")
    app=code.get("app.py",""); comp=code.get("scientist_chat_component.py",""); jobs=code.get("scientist_chat_jobs.py","")
    ck("SCIENTIST_CHAT_TERMINAL_RECONCILIATION", 'setStateValue("reconcile"' in comp and '_scientistReconcileInterval' in comp and 'setInterval(' in comp and 'on_reconcile_change=lambda: None' in comp and 'setTriggerValue("poll"' not in comp and '_settle_scientist_chat_job(factory_id,thread_id)' in app, "pending custom component uses a recurring hidden state heartbeat so a lost/coalesced pulse cannot strand partial/terminal replies behind Stop while legacy poll trigger remains absent")
    ck("SCIENTIST_CHAT_CLEAR_THREAD_ISOLATION", 'current_thread_id' in sc and 'STALE_SCIENTIST_CHAT_THREAD' in sc and 'job_thread != current_thread' in app and 'event_thread != thread_id' in app and 'TERMINAL_STATUSES' in jobs, "Clear rotates persistent thread identity; stale events/results are rejected and terminal job state is immutable")
    ck("SCIENTIST_CHAT_LIVE_HARDWARE_CONTEXT", 'MAX_SCIENTIST_LIVE_HARDWARE_V1' in sc and 'MAX_SCIENTIST_LIVE_COMPUTE_V1' in sc and 'LIVE_HW' in sc and 'LIVE_COMPUTE' in sc and 'live_hardware=_chat_live_hw' in app and 'live_compute_plan=_chat_live_compute' in app and 'do not ask the Owner to repeat hardware specs' in sc, "Scientist Chat receives detected current-host hardware and resolved compute truth even before a Factory exists, separate from configured allowances and frozen Factory plans")
    ck("STAGE10_SCIENTIST_CHAT_CONCURRENCY_AND_PROVENANCE",
       '_verify_read_only_stage_seal' in sc
       and '_compatible_kwargs' in sc
       and '_is_preanswer_stream_capability_failure' in sc
       and '_chat_fallback_route_entries' in sc
       and 'SCIENTIST_CHAT_STORE_CORRUPT' in sc
       and '_registry_lock' in jobs
       and 'commit_terminal_job' in jobs
       and 'update_active_job' in jobs
       and 'answering_route' in app
       and '"visibility":"internal"' in app,
       "Scientist Chat is cross-process/idempotent, terminal-CAS monotonic, duplicate-call safe, sealed-evidence verified, route-provenanced and excludes hidden failures from future visible history")
    pm=_load_json(PACKAGE_ROOT / "governance/PACKAGE_MANIFEST.json",{})
    ca=_load_json(PACKAGE_ROOT / "governance/CURRENT_AUTHORITY.json",{})
    runacc=(ROOT / "acceptance" / "runners" / "run_acceptance.py").read_text(encoding="utf-8",errors="replace")
    cpi=code.get("checkpoint_integrity.py","")
    acceptance=local_acceptance_expectations()
    expected_gate_count=int(acceptance["gate_count"])
    expected_target=str(acceptance["target"])
    expected_status_prefix=str(acceptance["status_prefix"])
    ck("V201_RELEASE_AUTHORITY_INTEGRITY",
       str(pm.get("status") or "").startswith(expected_status_prefix)
       and int((pm.get("local_acceptance") or {}).get("gates",-1))==expected_gate_count
       and (ca.get("local_acceptance") or {}).get("target")==expected_target
       and "governance/PACKAGE_MANIFEST.json" in runacc
       and "V201_RELEASE_PORTABILITY" in runacc
       and "V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY" in runacc
       and "V201_SCIENTIST_KNOWLEDGE_SYNC" in runacc
       and "UNMANIFESTED_FILE" in cpi and "HASH_MISMATCH" in cpi,
       f"Current v2.0.1 release metadata is synchronized to the canonical {expected_gate_count}-gate exact-tree authority derived from run_acceptance.TESTS; Scientist Knowledge sync is mandatory, package manifest participates in acceptance signatures, and checkpoint sealing retains tamper/addition detection")
    first=next((x["gate"] for x in checks if x["status"]!="PASS"),None)
    return {
        "schema":AUDIT_SCHEMA,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "overall_status":"PASS" if first is None else "FAIL",
        "first_failed_gate":first,
        "workflow_order":[x.get("id") for x in p.get("workflow") or []],
        "checks":checks,
        "known_external_gates":[
            "Owner Windows Streamlit visual/runtime",
            "real ONNX Runtime parity for every family",
            "CUDA runtime where applicable",
            "MetaEditor/MQL5 compile/runtime",
            "same-broker live MT5 reconciliation/repair on Owner machine",
        ],
    }


def render_markdown(payload: dict) -> str:
    lines=[
        "# Scientist Knowledge Base — Max Research Agent",
        "",
        f"**Schema:** `{payload.get('schema')}`  ",
        f"**Knowledge revision:** **{payload.get('knowledge_revision')}**  ",
        f"**Scientific authority:** **{payload.get('scientific_authority')}**  ",
        f"**Control revision:** **{payload.get('control_revision')}**",
        "",
        "This file is generated from the machine-readable knowledge database and canonical source/doc manifests. Do not hand-edit generated facts; update source/contracts then regenerate.",
        "",
        "## E2E workflow",
        "",
    ]
    for stage in payload.get("workflow") or []:
        lines += [f"### {stage.get('order')}. {stage.get('id')}", "", str(stage.get("purpose") or ""), "", f"**Authority:** `{stage.get('authority')}`", "", "**Core contracts:**"]
        for c in stage.get("contracts") or []:
            lines.append(f"- {c}")
        lines += ["", "**Evidence:** " + ", ".join(f"`{x}`" for x in stage.get("evidence") or []), ""]
    method=payload.get("model_training_method_contract") or {}
    lines += ["## Canonical model training method", "", f"**Schema:** `{method.get('schema')}`  ", f"**Authority:** `{method.get('authority')}`", "", "This single contract is shared by Manual, AUTO deterministic planning, Factory Director, round Scientist, Scientist Chat and acceptance tests.", ""]
    pol=((payload.get("kpi") or {}).get("scientist_policy") or {})
    lines += ["## KPI Scientist interpretation policy", "", f"**Authority:** `{pol.get('authority')}`", "", "### Principles"]
    for item in pol.get("principles") or []:
        lines.append(f"- {item}")
    lines += ["", "### Gate roles", ""]
    for gate,spec in (pol.get("gate_roles") or {}).items():
        lines.append(f"- **{gate.upper()}** — {spec.get('question') or spec.get('policy') or ''}")
    lines += ["", "## Existing Max capabilities — novelty guard", ""]
    for cap in payload.get("existing_capabilities") or []:
        lines.append(f"- **{cap.get('id')}** — {cap.get('summary')}")
    lines += ["", "## Recommendation classification", ""]
    for k,v in ((payload.get("novelty_policy") or {}).get("classes") or {}).items():
        lines.append(f"- **{k}** — {v}")
    lines += ["", "## Mandatory sync rule", "", "Every production-code or canonical-contract change updates the source manifest. `scientist_knowledge_sync_selftest.py` fails acceptance until this database is regenerated and the canonical handoff/docs are synchronized.", ""]
    return "\n".join(lines)


def write_all() -> tuple[dict, dict]:
    payload=build_payload()
    KB_JSON.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    KB_MD.write_text(render_markdown(payload),encoding="utf-8")
    audit=workflow_audit(payload)
    AUDIT_JSON.write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    return payload,audit


if __name__ == "__main__":
    payload,audit=write_all()
    print(f"{KB_JSON.name}: {len(payload.get('source_manifest') or {})} watched source/doc files")
    print(f"{AUDIT_JSON.name}: {audit.get('overall_status')} first_failed_gate={audit.get('first_failed_gate')}")
    raise SystemExit(0 if audit.get("overall_status")=="PASS" else 1)
