from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import acceptance.runners.run_acceptance as run_acceptance
import scientist.knowledge.scientist_knowledge as scientist_knowledge_module
from models.model_registry import registry_for_scientist
from scientist.knowledge.scientist_knowledge import (
    KB_JSON, KB_MD, AUDIT_JSON, load_knowledge, sync_status,
    local_acceptance_expectations, workflow_audit, workflow_audit_sync_status,
)

ROOT=Path(__file__).resolve().parents[1]
PACKAGE_ROOT=ROOT.parent

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

kb=load_knowledge()
req(KB_JSON.exists() and KB_MD.exists() and AUDIT_JSON.exists(),"Scientist knowledge/audit artifacts must exist")
req(kb.get("schema")=="MAX_SCIENTIST_KNOWLEDGE_V1","knowledge schema mismatch")
req(kb.get("knowledge_revision")=="SCIENTIST_KNOWLEDGE_MAX_MTF_V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR","knowledge revision mismatch")
req(kb.get("scientific_authority")=="Max MTF v2.0.1 — canonical MTF-1 data foundation plus shared MODEL_TRAINING_METHOD_CONTRACT_V1 for Manual, AUTO, LLM Scientist and Scientist Chat","scientific authority mismatch")
req(((kb.get("research_controls") or {}).get("learning_system") or {}).get("schema")=="MAX_AGENTIC_RESEARCH_LEARNING_V1","v1.4.5 learning-system knowledge missing")
req(kb.get("control_revision")=="Research Control R1","control revision mismatch")
req(((kb.get("research_controls") or {}).get("kpi_ui_visibility_contract") or {}).get("schema")=="MAX_KPI_UI_FULL_AUTHORITY_V1","v1.4.5 KPI UI visibility contract missing")
req(((kb.get("research_controls") or {}).get("model_inspector_live_runtime") or {}).get("schema")=="MAX_MODEL_INSPECTOR_LIVE_RUNTIME_V1","v1.4.5 model inspector/live runtime contract missing")

sync=sync_status(kb)
req(sync.get("in_sync"),f"Scientist knowledge source/doc manifest is stale: {sync.get('changed')}")

workflow=[x.get("id") for x in kb.get("workflow") or []]
req(workflow==["STRATEGY_OPTIMIZER","DATA_QUALITY","RESEARCH_PLAN_FREEZE","DISCOVERY_FULL_WFA","POOL","CPCV","TOURNAMENT","MONTE_CARLO","FRESH_FORWARD","CHAMPION"],f"workflow order mismatch: {workflow}")

caps={x.get("id") for x in kb.get("existing_capabilities") or []}
for cap in {
    "TOPOLOGY_ALLOCATION","FAMILY_SIZE_PRIORITY","MODEL_SIZE_ADVISOR","STRATEGY_NAVIGATION_LIFECYCLE","KPI_UI_FULL_AUTHORITY","MODEL_DETAIL_INSPECTOR_LIVE_RUNTIME","DYNAMIC_HYBRIDS","FIDELITY_LADDER",
    "POLICY_DISCOVERY","TRAINING_MEMORY_WINDOW_DISCOVERY","SCIENTIFIC_CREATIVITY",
    "EXPERIMENT_BLOCKS_HYPOTHESES","RESEARCH_MEMORY","CPCV_PROGRESSIVE_FINALISTS",
    "MONTE_CARLO","FRESH_FORWARD","ONNX_RUNTIME_PARITY","AUTO_AND_MANUAL_RESEARCH",
    "SCIENTIST_CHAT_STATE_RECONCILIATION","AUTONOMOUS_LLM_SCIENTIST_ROUTING","LANGGRAPH_AGENTIC_SCIENTIST","SCIENTIST_DIRECTED_SEARCH","SCIENTIST_PYTHON_ANALYSIS_RUNTIME","GATE_KPI_PROFILES","STRATEGY_OPTIMIZER_KPI","ONNX_RUNTIME_TRADE_AUDIT","CHALLENGER_LIFECYCLE","STRATEGY_CHALLENGER_LIFECYCLE","GOLDEN_RESEARCH_E2E",
}:
    req(cap in caps,f"missing Max capability in Scientist knowledge: {cap}")

nov=(kb.get("novelty_policy") or {}).get("classes") or {}
req(set(nov)=={"EXISTING","EXTENSION","EXPERIMENT","NEW","CONFLICT","OUTSIDE_CURRENT_CONTRACT"},"novelty classification contract incomplete")


chat_state=kb.get("scientist_chat_contract") or {}
req(chat_state.get("chat_state_revision")=="Chat State R1","Scientist chat state contract revision missing")
req("thread_id" in str(chat_state.get("clear_semantics") or "") and "stale" in str(chat_state.get("stale_isolation") or "").lower(),"Scientist chat clear/thread isolation knowledge missing")

models=kb.get("models") or {}
req(set(models.get("temporal_families") or []) >= {"gru","lstm","tcn","transformer","transformer_moe","patchtst","itransformer","tft"},"temporal model universe incomplete")
req(set(models.get("policy_families") or []) >= {"lightgbm","xgboost","random_forest"},"policy model universe incomplete")
req((models.get("final_decision_contract") or {}).get("shape")=="[N,3]","decision contract missing")

chat=(ROOT/"scientist/chat/scientist_chat.py").read_text(encoding="utf-8")
req("from scientist.knowledge.scientist_knowledge import" in chat,"Scientist Chat must import Max knowledge authority")
req('ctx["max_knowledge"]' in chat,"Scientist context must expose max_knowledge")
req("perform a Max novelty check" in chat,"Scientist system prompt must require novelty check")
req("OUTSIDE_CURRENT_CONTRACT" in chat and "EXISTING" in chat and "EXTENSION" in chat,"Scientist prompt novelty classes missing")
req("KPI authority for ONNX Factory Research is PER GATE" in chat and "Strategy Optimizer is a separate upstream MT5" in chat and "research_settings.strategy_optimizer_kpi" in chat,"Scientist prompt must understand v0.8.9 Optimizer/Research KPI boundary")


pol=((kb.get("kpi") or {}).get("scientist_policy") or {})
req(pol.get("authority")=="ADVISORY_INTERPRETATION_ONLY_LIVE_GATE_KPIS_REMAIN_RUNTIME_AUTHORITY","Scientist KPI interpretation authority missing")
roles=pol.get("gate_roles") or {}
req(set(roles)>={"discovery","cpcv","tournament","monte_carlo","fresh_forward","champion"},"Scientist KPI gate-role semantics incomplete")
req("not a new untouched" in str((roles.get("tournament") or {}).get("dataset_semantics") or "").lower(),"Scientist must not call Tournament Fresh/OOS")
pbo_policy=str((roles.get("cpcv") or {}).get("pbo_policy") or "")
req("OFF by default" in pbo_policy and "cross-strategy" in pbo_policy and "insufficient matrix evidence fails closed" in pbo_policy and "pseudo-PBO" in pbo_policy,"Scientist PBO computability semantics missing")

req("Result=Mean R" in chat or "Result column is Mean R" in str(kb),"Scientist must know MT5 Result is Mean R under Custom max")
req("Weighted R" in chat and "sum(net P/L)/sum(initial risk)" in str(kb),"Scientist must know independent Weighted R authority")
req("execution geometry" in str(kb).lower() and "adaptive lot/risk" in str(kb).lower(),"Scientist must know strategy-geometry lock and sizing/model boundary")
req("overall oof mean r" in str(kb).lower() and "median fold mean r" in str(kb).lower() and "worst fold mean r" in str(kb).lower(),"Scientist must know v0.8.9 retained Overall/Median/Worst Mean-R gate trio")
req("frameinputs" in str(kb).lower() and "opaque" in str(kb).lower() and "uint64" in str(kb).lower(),"Scientist must know v0.8.9 MT5 frame/cache authority")
req("optimization-cache" in str(kb).lower() or "tester_no_cache" in str(kb).lower(),"Scientist must know v0.8.9 cache/frame completeness contract")
req("min edge r" in str(kb).lower() and "min margin r" in str(kb).lower(),"Scientist must know Model Research label-policy boundary")
req("history" in str(kb).lower() and "ontradetransaction" in str(kb).lower(),"Scientist must know v0.8.6 history-rebuild accounting authority retained in v0.8.9")
req("DETERMINISTIC_ONLY" in str(kb) and "SCIENTIST_PROPOSAL" in str(kb) and "DETERMINISTIC_FALLBACK" in str(kb) and "NO_CHAMPION_MAX_ROUNDS" in str(kb) and "automatically" in str(kb).lower(),"Scientist knowledge must encode automatic no-winner refinement and max-round stop")
req("fingerprint" in str(kb).lower() and "created" in str(kb).lower() and "eligible_passes > 0" in str(kb),"Scientist knowledge must encode fresh-report provenance and eligibility invariant")
req("Max_MTF.xml" in str(kb) and "Max_MTF.set" in str(kb) and "hidden-page widget cleanup" in str(kb).lower() and "rehydrated" in str(kb).lower(),"Scientist knowledge must encode canonical optimizer filenames and durable hidden-page settings")
req("Max_MTF_GapRepair.set" in str(kb) and "missing=0" in str(kb) and "training-enabled" in str(kb).lower(),"Scientist knowledge must encode v0.9.1 dedicated MT5 gap-repair authority")
req("e2e_workflow_test_v1" in str(kb).lower() and "sandbox" in str(kb).lower(),"Scientist knowledge must encode v1.2.5 Challenger/E2E authority")
req("local/exact-sha" in str(kb).lower() and "repairable fail" in str(kb).lower() and "utf-16" in str(kb).lower(),"Scientist knowledge must encode v0.11.1 local-first staged repair and MT5 encoding authority")
req("Max_MTF_Champion_Trades.csv" in str(kb) and "Max_MTF_Shadow_Trades.csv" in str(kb) and "executed=0" in str(kb),"Scientist knowledge must encode v0.9.1 Champion/Shadow audit separation")
req("human-readable" in str(kb).lower() and "explicit owner promotion" in str(kb).lower() and "strategy challenger" in str(kb).lower() and "model challenger" in str(kb).lower(),"Scientist knowledge must encode Strategy + Model Challenger lifecycles")
req("STRATEGY_CHALLENGER_FOUND" in chat and "PROMOTE TO STRATEGY CHAMPION" in chat,"Scientist must know Optimizer stops at Strategy Challenger and Owner promotion is explicit")
req("verified current strategy champion kpi evidence" in str(kb).lower() or "uniquely matched owner max.xml" in str(kb).lower(),"Scientist must know v1.2.5 verified current Strategy Champion KPI evidence")

for rel in [
    "governance/PROJECT_HANDOFF_CURRENT.md","governance/CONTRACT_AUDIT_INDEX.md","ModelLab/docs/contracts/MAX_WORKFLOW_CONTRACT_E2E.md",
    "ModelLab/docs/contracts/SCIENTIST_KNOWLEDGE_UPDATE_POLICY.md","ModelLab/docs/ui/SCIENTIST_CHAT_R2_STREAMING_CONTRACT.md",
]:
    req((PACKAGE_ROOT/rel).exists(),f"canonical knowledge/continuity doc missing: {rel}")

audit=json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
req(audit.get("schema")=="MAX_WORKFLOW_CONTRACT_AUDIT_R1","workflow audit schema mismatch")
req(audit.get("overall_status")=="PASS",f"workflow audit failed: {audit.get('first_failed_gate')}")
req(audit.get("first_failed_gate") is None,"workflow audit has first failed gate")
req(all(x.get("status")=="PASS" for x in audit.get("checks") or []),"workflow audit contains non-PASS checks")
audit_sync=workflow_audit_sync_status(kb,audit)
req(audit_sync.get("in_sync"),f"persisted workflow audit is stale versus current canonical authority: {audit_sync}")

# CASE A — a watched production-source hash change after generation must be detected.
current_manifest=scientist_knowledge_module.source_manifest()
watched_source=next((k for k in current_manifest if k.endswith("ModelLab/models/capacity_governor.py")),None)
req(bool(watched_source),"CASE A watched production source is present in the knowledge manifest")
changed_manifest=dict(current_manifest); changed_manifest[watched_source]="0"*64
with patch.object(scientist_knowledge_module,"source_manifest",return_value=changed_manifest):
    changed_status=sync_status(kb)
req((not changed_status.get("in_sync")) and watched_source in (changed_status.get("changed") or []),"CASE A changed watched production source fails Scientist Knowledge sync")

# CASE B — the shipped artifacts were regenerated from this exact final tree.
req(sync_status(kb).get("in_sync"),"CASE B regenerated knowledge from exact final tree is synchronized")

# CASE C — mutate the REAL canonical run_acceptance.py TESTS list, not a mock.
# The persisted Knowledge/audit must immediately become stale and fail closed.
base_expect=local_acceptance_expectations(); base_count=len(run_acceptance.TESTS)
req(base_expect.get("gate_count")==base_count and base_expect.get("target")==f"{base_count}/{base_count} PASS","CASE C canonical acceptance count/target are derived from run_acceptance.TESTS")
run_acceptance_path=ROOT/"acceptance/runners/run_acceptance.py"
original_run_acceptance=run_acceptance_path.read_bytes()
try:
    source=original_run_acceptance.decode("utf-8")
    marker="]\n\ndef _hash_bytes"
    req(marker in source,"CASE C canonical TESTS terminator located for real-source mutation")
    mutated=source.replace(marker," ('V201_SYNTHETIC_REAL_COUNT_PROBE','tests/_synthetic_count_probe.py'),\n]\n\ndef _hash_bytes",1)
    run_acceptance_path.write_text(mutated,encoding="utf-8")
    importlib.invalidate_caches()
    run_acceptance=importlib.reload(run_acceptance)
    shifted=local_acceptance_expectations()
    shifted_audit=workflow_audit(kb)
    shifted_sync=sync_status(kb)
    shifted_persisted_audit_sync=workflow_audit_sync_status(kb,audit)
    req(shifted.get("gate_count")==base_count+1 and shifted.get("target")==f"{base_count+1}/{base_count+1} PASS","CASE C real canonical suite mutation changes Scientist Knowledge expectation without source edit")
    req(not shifted_sync.get("in_sync") and "ModelLab/acceptance/runners/run_acceptance.py" in (shifted_sync.get("changed") or []),"CASE C real canonical suite mutation invalidates Knowledge source provenance")
    req(not shifted_persisted_audit_sync.get("in_sync") and "checks" in (shifted_persisted_audit_sync.get("changed") or []),"CASE C persisted workflow audit cannot remain false-PASS after real canonical suite mutation")
    shifted_release=next(x for x in shifted_audit.get("checks") or [] if x.get("gate")=="V201_RELEASE_AUTHORITY_INTEGRITY")
    req(shifted_release.get("status")=="FAIL" and str(base_count+1) in str(shifted_release.get("evidence")),"CASE C release-integrity audit consumes the dynamically derived changed count")
finally:
    run_acceptance_path.write_bytes(original_run_acceptance)
    importlib.invalidate_caches()
    run_acceptance=importlib.reload(run_acceptance)
req(len(run_acceptance.TESTS)==base_count,"CASE C canonical run_acceptance.py restored byte-for-byte after adversarial mutation")
req(sync_status(kb).get("in_sync"),"CASE C clean-tree Knowledge sync restored after adversarial mutation")
req(workflow_audit_sync_status(kb,audit).get("in_sync"),"CASE C clean-tree persisted workflow audit sync restored after adversarial mutation")

# CASE D — a tampered stored KB source_manifest hash must fail synchronization.
tampered=deepcopy(kb); manifest=dict(tampered.get("source_manifest") or {})
tamper_key=next(iter(sorted(manifest))); manifest[tamper_key]="f"*64; tampered["source_manifest"]=manifest
req(not sync_status(tampered).get("in_sync"),"CASE D tampered KB source_manifest hash fails closed")

# CASE E — live deterministic model registry exposes the already-approved headroom.
live_registry=registry_for_scientist(); bases=live_registry.get("base_families") or {}
transformer_max=((((bases.get("transformer") or {}).get("search") or {}).get("d_model") or {}).get("max"))
tft_max=((((bases.get("tft") or {}).get("search") or {}).get("d_model") or {}).get("max"))
req(transformer_max==816 and tft_max==480,"CASE E Scientist live registry exposes Transformer d_model<=816 and TFT d_model<=480")

# CASE F — static knowledge is descriptive only and has no path into executable capacity authority.
stale_static=deepcopy(kb); stale_static.setdefault("models",{})["fake_legal_override"]={"transformer_d_model_max":999999,"tft_d_model_max":999999}
live_after=registry_for_scientist(); live_bases=live_after.get("base_families") or {}
authority_sources="\n".join((ROOT/name).read_text(encoding="utf-8",errors="replace") for name in ["models/model_registry.py","models/capacity_governor.py","models/models.py"] )
req(((((live_bases.get("transformer") or {}).get("search") or {}).get("d_model") or {}).get("max"))==816 and ((((live_bases.get("tft") or {}).get("search") or {}).get("d_model") or {}).get("max"))==480,"CASE F stale static knowledge cannot mutate live registry bounds")
req("SCIENTIST_KNOWLEDGE_BASE" not in authority_sources and "load_knowledge(" not in authority_sources,"CASE F executable legal/resource/scientific capacity authority does not consume static Scientist Knowledge")

print("SCIENTIST KNOWLEDGE SYNC PASS")
print("WATCHED",sync.get("current_count"),"files")
print("WORKFLOW", " -> ".join(workflow))
