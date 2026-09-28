from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import argparse, hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from mtf.mtf1_closure_run import read_run as read_closure_run
from acceptance.runners.acceptance_process_env import acceptance_utf8_env

ROOT=MODELLAB_ROOT
PKG=ROOT.parent
GOV=PKG/'governance'
OUT=ROOT/'evidence/current/BUILD_ACCEPTANCE_v2_0_1.json'
CURRENT_EVIDENCE_DIR=ROOT/'evidence/current'
CURRENT_ACCEPTANCE_REPORT_NAME='BUILD_ACCEPTANCE_v2_0_1.json'
CURRENT_CANDIDATE_CLAIM_NAME='CANDIDATE_BUILD_v2_0_1.json'
CURRENT_EVIDENCE_SYNC_NAME='CURRENT_EVIDENCE_SYNC_v2_0_1.json'
CURRENT_MUTABLE_ACCEPTANCE_CLAIMS=(CURRENT_CANDIDATE_CLAIM_NAME,)
CANDIDATE_BUILD_EVIDENCE=CURRENT_EVIDENCE_DIR/CURRENT_CANDIDATE_CLAIM_NAME
CURRENT_EVIDENCE_SYNC_EVIDENCE=CURRENT_EVIDENCE_DIR/CURRENT_EVIDENCE_SYNC_NAME
ACCEPTANCE_SCHEMA='MAX_MTF_BUILD_ACCEPTANCE_V8_MTF1_EXTERNAL_EXECUTION_PROOF'
ACCEPTANCE_PHASE='MTF_1_EXTERNAL_EXECUTION_PROOF'
TESTS=[
 ('V201_MTF_DATA_CONFIG','tests/v201_mtf_data_config_selftest.py'),
 ('V201_MTF_CLOSED_BAR','tests/v201_mtf_closed_bar_selftest.py'),
 ('V201_MTF_RESAMPLING_PARITY','tests/v201_mtf_resampling_parity_selftest.py'),
 ('V201_MTF_ALIGNMENT','tests/v201_mtf_alignment_selftest.py'),
 ('V201_MTF_FUTURE_LEAKAGE','tests/v201_mtf_future_leakage_selftest.py'),
 ('V201_MTF_MISSING_M5','tests/v201_mtf_missing_m5_selftest.py'),
 ('V201_MTF_SESSION_GAP','tests/v201_mtf_session_gap_selftest.py'),
 ('V201_MTF_TIMEZONE','tests/v201_mtf_timezone_selftest.py'),
 ('V201_MTF_VALUE_AUTHORITY','tests/v201_mtf_value_authority_selftest.py'),
 ('V201_MTF_LINEAGE_BUNDLE','tests/v201_mtf_lineage_bundle_selftest.py'),
 ('V201_ACTIVE_RELEASE_IDENTITY','tests/v201_active_release_identity_selftest.py'),
 ('V201_RELEASE_PORTABILITY','tests/v201_release_portability_selftest.py'),
 ('V201_REAL_VOLUME_PARITY','tests/v201_real_volume_parity_selftest.py'),
 ('V201_MANIFEST_DATA_BINDING','tests/v201_manifest_data_binding_selftest.py'),
 ('V201_SEALED_BUNDLE_IMMUTABILITY','tests/v201_sealed_bundle_immutability_selftest.py'),
 ('V201_ATOMIC_BUNDLE_COMMIT','tests/v201_atomic_bundle_commit_selftest.py'),
 ('V201_IMPORTED_M5_CONTINUITY_REQUIRED','tests/v201_imported_m5_continuity_required_selftest.py'),
 ('V201_IMPORTED_M5_NEUTRAL_BAR_MISSING','tests/v201_imported_m5_neutral_bar_missing_selftest.py'),
 ('V201_RUNTIME_REGISTRY_PORTABILITY','tests/v201_runtime_registry_portability_selftest.py'),
 ('V201_ACCEPTANCE_RUNTIME_IMMUTABILITY','tests/v201_acceptance_runtime_immutability_selftest.py'),
 ('V201_ACTIVE_RELEASE_VERSION_PARITY','tests/v201_active_release_version_parity_selftest.py'),
 ('V201_EXTERNAL_GATE_AUTHORITY_SYNC','tests/v201_external_gate_authority_sync_selftest.py'),
 ('V201_EXTERNAL_GATE_SIGNATURE_BINDING','tests/v201_external_gate_signature_binding_selftest.py'),
 ('V201_SOURCE_KIND_FAIL_CLOSED','tests/v201_source_kind_fail_closed_selftest.py'),
 ('V201_EXTERNAL_GATE_REQUIREMENT_LOCK','tests/v201_external_gate_requirement_lock_selftest.py'),
 ('V201_OWNER_EVIDENCE_TREE_BINDING','tests/v201_owner_evidence_tree_binding_selftest.py'),
 ('V201_README_AUTHORITY_SYNC','tests/v201_readme_authority_sync_selftest.py'),
 ('V201_INHERITED_V146_SCIENTIST_JSON_RECOVERY','tests/v146_scientist_json_recovery_selftest.py'),
 ('V201_SCIENTIST_KNOWLEDGE_SYNC','tests/scientist_knowledge_sync_selftest.py'),
 ('V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME','tests/v201_scientist_python_analysis_runtime_selftest.py'),
 ('V201_SCIENTIST_STRICT_CANDIDATE_ADMISSION','tests/v201_scientist_strict_candidate_admission_selftest.py'),
 ('V201_TRAINING_METHOD_CONTRACT_E2E_SYNC','tests/v201_training_method_contract_e2e_sync_selftest.py'),
 ('V201_MANUAL_EXACT_PARAMETER_IDENTITY','tests/v201_manual_exact_parameter_identity_selftest.py'),
 ('V201_MEMORY_EXACT_RECHECK_LINEAGE','tests/v201_memory_exact_recheck_lineage_selftest.py'),
 ('V201_SCIENTIST_HYPOTHESIS_ADMISSION','tests/v201_scientist_hypothesis_admission_selftest.py'),
 ('V201_DYNAMIC_MODEL_CAPACITY_AUTHORITY','tests/v201_dynamic_model_capacity_authority_selftest.py'),
 ('V201_DYNAMIC_CAPACITY_SEARCH_DIVERSITY_FAMILY_EVIDENCE','tests/v201_dynamic_capacity_search_diversity_family_evidence_selftest.py'),
 ('V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM','tests/v201_transformer_tft_legal_capacity_headroom_selftest.py'),
 ('V201_INHERITED_V147_STRATEGY_GEOMETRY_HANDOFF','tests/v201_inherited_v147_strategy_geometry_handoff_selftest.py'),
 ('V201_INHERITED_V147_FAILED_CPCV_RESUME','tests/v201_inherited_v147_failed_cpcv_resume_selftest.py'),
 ('V201_CPCV_LIVE_KPI_TELEMETRY','tests/v201_cpcv_live_kpi_telemetry_selftest.py'),
 ('V201_DL_INTERNAL_EARLYSTOP_PURGE','tests/v201_dl_internal_earlystop_purge_selftest.py'),
 ('V201_MOE_TOP1_ROUTER_GRADIENT','tests/v201_moe_top1_router_gradient_selftest.py'),
 ('V201_MOE_ROUTING_DIAGNOSTICS','tests/v201_moe_routing_diagnostics_selftest.py'),
 ('V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY','tests/v201_local_acceptance_result_integrity_selftest.py'),
 ('V201_OWNER_EVIDENCE_PROOF_COMPLETENESS','tests/v201_owner_evidence_proof_completeness_selftest.py'),
 ('V201_OWNER_MT5_BROKER_SYMBOL_RESOLUTION','tests/v201_owner_mt5_broker_symbol_resolution_selftest.py'),
 ('V201_METAEDITOR_FINAL_CLOSURE_WIRING','tests/v201_metaeditor_final_closure_wiring_selftest.py'),
 ('V201_OWNER_RAW_REPLAY_AUTHENTICITY','tests/v201_owner_raw_replay_authenticity_selftest.py'),
 ('V201_METAEDITOR_EXECUTION_ARTIFACT_AUTHENTICITY','tests/v201_metaeditor_execution_artifact_authenticity_selftest.py'),
 ('V201_METAEDITOR_LOG_REPARSE_AUTHORITY','tests/v201_metaeditor_log_reparse_authority_selftest.py'),
 ('V201_METAEDITOR_PROCESS_EXITCODE_AUTHORITY','tests/v201_metaeditor_process_exitcode_authority_selftest.py'),
 ('V201_FINAL_CLOSURE_PYTHON_ENV_AUTHORITY','tests/v201_final_closure_python_env_authority_selftest.py'),
 ('V201_FINAL_VERIFY_READ_ONLY','tests/v201_final_verify_read_only_selftest.py'),
 ('V201_CLOSURE_RUN_ID_BINDING','tests/v201_closure_run_id_binding_selftest.py'),
 ('V200_FOUNDATION_IDENTITY','tests/v200_mtf_foundation_identity_selftest.py'),
 ('V200_ZERO_CHAMPION_LIFECYCLE','tests/v200_zero_champion_lifecycle_selftest.py'),
 ('V200_MT5_TERMINAL_ROOT','tests/v200_mt5_terminal_root_selftest.py'),
 ('V200_NAMESPACE_ISOLATION','tests/v200_namespace_isolation_selftest.py'),
 ('V200_RELEASE_LAYOUT','tests/v200_release_layout_selftest.py'),
 ('V200_MTF_CONTRACT','tests/v200_mtf_contract_selftest.py'),
 ('V200_SCIENTIST_CONTEXT','tests/v200_scientist_context_selftest.py'),
 ('V200_FIRST_STRATEGY_PROMOTION','tests/v200_first_strategy_promotion_selftest.py'),
 ('V200_OPTIMIZER_NAMESPACE','tests/v200_optimizer_namespace_selftest.py'),
 ('V200_UI_BOOTSTRAP','tests/v200_ui_bootstrap_selftest.py'),
 ('INHERITED_CPCV_PURGE_EMBARGO','tests/cpcv_selftest.py'),
 ('INHERITED_MONTE_CARLO','tests/monte_carlo_selftest.py'),
 ('INHERITED_LEAKAGE_ADVERSARIAL','tests/leakage_adversarial_selftest.py'),
 ('INHERITED_TRAINING_MEMORY_CV','tests/training_memory_cv_selftest.py'),
 ('INHERITED_FAMILY_SIZE_PRIORITY','tests/family_size_priority_selftest.py'),
 ('INHERITED_DECISION_CONTRACT','tests/standalone_hybrid_decision_contract_selftest.py'),
 ('INHERITED_TRANSFORMER_FAMILY','tests/transformer_family_expansion_selftest.py'),
 ('INHERITED_RESEARCH_KERNEL','tests/research_kernel_selftest.py'),
 ('INHERITED_RESOURCE_PREFLIGHT','tests/resource_preflight_selftest.py'),
 ('INHERITED_CPCV_SEED_CONFIRMATION','tests/cpcv_seed_confirmation_selftest.py'),
]

def _hash_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def _suite_sig()->str:return _hash_bytes(json.dumps(TESTS,separators=(',',':')).encode())

def _tree_sig()->str:
    files=[]
    for ext in ('*.py','*.md'):
        for p in ROOT.rglob(ext):
            if '__pycache__' not in p.parts and 'evidence' not in p.parts and 'runtime' not in p.parts:
                files.append(p)
    for p in [
        PKG/'EA_v2_00/baseline/Max_MTF.mq5', PKG/'README_FIRST.md',
        PKG/'governance/PROJECT_IDENTITY.json', PKG/'governance/CURRENT_AUTHORITY.json',
        PKG/'governance/PACKAGE_MANIFEST.json', PKG/'governance/PACKAGE_LAYOUT.json', PKG/'governance/PACKAGE_LAYOUT.md',
        PKG/'governance/PROJECT_HANDOFF_CURRENT.md', PKG/'governance/CONTRACT_AUDIT_INDEX.md',
        PKG/'governance/handoffs/MAX_MTF_V2_HANDOFF.md', ROOT/'config/config.json', ROOT/'config/models/model_registry.json',
        ROOT/'scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json', ROOT/'governance/MODEL_TRAINING_METHOD_CONTRACT_V1.json', PKG/'Data/MTF/native/README.txt', PKG/'Data/MTF/bundles/README.txt',
        PKG/'Releases/active/release.json', ROOT/'runtime/active_release.json',
        ROOT/'runtime/strategy_challenger_registry.json', ROOT/'runtime/strategy_authority.json',
        PKG/'governance/MTF1_INHERITED_V145_SCIENTIFIC_CORE.json',
        PKG/'governance/EXTERNAL_RUNTIME_GATES.json',
        ROOT/'RUN_MTF1_OWNER_ACCEPTANCE.cmd',
        ROOT/'acceptance/verification/VERIFY_MTF1_OWNER_ACCEPTANCE.cmd',
        ROOT/'RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd',
        ROOT/'acceptance/verification/VERIFY_MTF1_METAEDITOR_ACCEPTANCE.cmd',
        ROOT/'acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd',
        ROOT/'RUN_MTF1_FINAL_CLOSURE.cmd',
        ROOT/'RUN_ACCEPTANCE.cmd',
        ROOT/'RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
        ROOT/'acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
        ROOT/'tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd',
        ROOT/'tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd',
    ]:
        if p.exists(): files.append(p)
    h=hashlib.sha256()
    for p in sorted(set(files),key=lambda x:str(x)):
        rel=str(p.relative_to(PKG)).replace('\\','/')
        h.update(rel.encode());h.update(b'\0');h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

RUNTIME_AUTHORITY_FILES=(
    ROOT/'runtime/active_release.json',
    ROOT/'runtime/strategy_authority.json',
    ROOT/'runtime/strategy_challenger_registry.json',
)

def _runtime_authority_signature()->str:
    h=hashlib.sha256()
    for p in RUNTIME_AUTHORITY_FILES:
        rel=str(p.relative_to(PKG)).replace('\\','/')
        h.update(rel.encode());h.update(b'\0')
        if p.exists():
            h.update(hashlib.sha256(p.read_bytes()).digest())
        else:
            h.update(b'MISSING')
    return h.hexdigest()


MTF1_EXTERNAL_REQUIREMENT_LOCK={
    'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY':'REQUIRED_ON_OWNER_MACHINE',
    'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION':'REQUIRED_ON_OWNER_MACHINE',
    'METAEDITOR_MAX_MTF_V2_COMPILE':'REQUIRED_ON_OWNER_MACHINE',
    'MTF_STRATEGY_RUNTIME':'NOT_APPLICABLE_MTF1',
}

def _external_gates()->list[dict]:
    path=GOV/'EXTERNAL_RUNTIME_GATES.json'
    try:
        payload=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_REGISTRY_UNREADABLE: {exc}') from exc
    if payload.get('schema')!='MAX_EXTERNAL_RUNTIME_GATES_V1' or payload.get('authority')!='SINGLE_CANONICAL_EXTERNAL_RUNTIME_GATE_REGISTRY' or not isinstance(payload.get('gates'),list):
        raise RuntimeError('EXTERNAL_RUNTIME_GATE_REGISTRY_SCHEMA')
    gates=[]; seen=set()
    for raw in payload.get('gates') or []:
        if not isinstance(raw,dict) or not raw.get('gate'):
            raise RuntimeError('EXTERNAL_RUNTIME_GATE_REGISTRY_ROW')
        gate=str(raw['gate'])
        if gate in seen:
            raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_REGISTRY_DUPLICATE: {gate}')
        if str(raw.get('status') or '').upper()=='PASS':
            raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_REGISTRY_ILLEGAL_PREPASS: {gate}')
        seen.add(gate); gates.append(dict(raw))
    required=set(MTF1_EXTERNAL_REQUIREMENT_LOCK)
    missing=sorted(required-seen)
    if missing:
        raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_REGISTRY_MISSING_MTF1: {missing}')
    by_gate={str(row.get('gate')):row for row in gates}
    for gate,expected in MTF1_EXTERNAL_REQUIREMENT_LOCK.items():
        row=by_gate[gate]
        actual_requirement=str(row.get('requirement') or '').upper()
        compatibility_status=str(row.get('status') or '').upper()
        if actual_requirement!=expected:
            raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_REQUIREMENT_LOCK: {gate}: expected={expected} actual={actual_requirement or "EMPTY"}')
        # The source registry never stores runtime PASS/FAIL. For MTF-1 these rows retain
        # an exact compatibility mirror so legacy consumers cannot downgrade obligation by
        # editing `status` while leaving the new `requirement` field intact.
        if compatibility_status!=expected:
            raise RuntimeError(f'EXTERNAL_RUNTIME_GATE_STATUS_REQUIREMENT_DIVERGENCE: {gate}: expected={expected} actual={compatibility_status or "EMPTY"}')
    return gates

def validate_local_acceptance_report(payload_or_path, *, require_current_tree: bool=True, require_current_suite: bool=True, require_fresh_full: bool=False, require_closure_run_id: bool=False):
    """Validate the complete machine proof produced by this acceptance suite.

    Header-only PASS is never sufficient. The exact ordered gate/script sequence must be
    present once, every row must be PASS with exit_code 0, and the report must bind the
    current tree/suite plus the canonical external-gate registry snapshot.
    """
    if isinstance(payload_or_path,(str,Path)):
        try:
            payload=json.loads(Path(payload_or_path).read_text(encoding='utf-8'))
        except Exception as exc:
            raise RuntimeError(f'LOCAL_ACCEPTANCE_REPORT_UNREADABLE: {exc}') from exc
    else:
        payload=payload_or_path
    if not isinstance(payload,dict):
        raise RuntimeError('LOCAL_ACCEPTANCE_REPORT_NOT_OBJECT')
    if payload.get('schema')!=ACCEPTANCE_SCHEMA:
        raise RuntimeError(f'LOCAL_ACCEPTANCE_SCHEMA_MISMATCH: {payload.get("schema")!r}')
    if payload.get('project')!='Max MTF' or payload.get('version')!='2.0.1' or payload.get('phase')!=ACCEPTANCE_PHASE:
        raise RuntimeError('LOCAL_ACCEPTANCE_IDENTITY_MISMATCH')
    if str(payload.get('overall_status') or '').upper()!='PASS':
        raise RuntimeError('LOCAL_ACCEPTANCE_NOT_PASS')
    if payload.get('first_failed_gate') is not None:
        raise RuntimeError(f'LOCAL_ACCEPTANCE_HAS_FAILED_GATE: {payload.get("first_failed_gate")}')
    if int(payload.get('gate_count',-1))!=len(TESTS):
        raise RuntimeError(f'LOCAL_ACCEPTANCE_GATE_COUNT_MISMATCH: stored={payload.get("gate_count")} expected={len(TESTS)}')
    if require_fresh_full and str(payload.get('execution_mode') or '')!='FRESH_FULL':
        raise RuntimeError(f'LOCAL_ACCEPTANCE_NOT_FRESH_FULL: {payload.get("execution_mode")!r}')
    rows=payload.get('results')
    if not isinstance(rows,list) or len(rows)!=len(TESTS):
        raise RuntimeError(f'LOCAL_ACCEPTANCE_RESULTS_COUNT_MISMATCH: stored={len(rows) if isinstance(rows,list) else "NOT_LIST"} expected={len(TESTS)}')
    seen=set()
    for idx,(expected_gate,expected_script) in enumerate(TESTS):
        row=rows[idx]
        if not isinstance(row,dict):
            raise RuntimeError(f'LOCAL_ACCEPTANCE_RESULT_ROW_INVALID: index={idx}')
        pair=(row.get('gate'),row.get('script'))
        if pair in seen:
            raise RuntimeError(f'LOCAL_ACCEPTANCE_DUPLICATE_RESULT: {pair}')
        seen.add(pair)
        if pair!=(expected_gate,expected_script):
            raise RuntimeError(f'LOCAL_ACCEPTANCE_ORDER_OR_IDENTITY_MISMATCH: index={idx} stored={pair} expected={(expected_gate,expected_script)}')
        if str(row.get('status') or '').upper()!='PASS':
            raise RuntimeError(f'LOCAL_ACCEPTANCE_RESULT_NOT_PASS: {expected_gate}')
        try:
            exit_code=int(row.get('exit_code'))
        except Exception as exc:
            raise RuntimeError(f'LOCAL_ACCEPTANCE_EXIT_CODE_INVALID: {expected_gate}') from exc
        if exit_code!=0:
            raise RuntimeError(f'LOCAL_ACCEPTANCE_EXIT_CODE_NONZERO: {expected_gate}: {exit_code}')
    tree=_tree_sig(); suite=_suite_sig()
    if require_current_tree and str(payload.get('source_tree_signature') or '')!=tree:
        raise RuntimeError('LOCAL_ACCEPTANCE_SOURCE_TREE_STALE')
    if require_current_suite and str(payload.get('suite_signature') or '')!=suite:
        raise RuntimeError('LOCAL_ACCEPTANCE_SUITE_STALE')
    current_external=_external_gates()
    if payload.get('external_gates')!=current_external:
        raise RuntimeError('LOCAL_ACCEPTANCE_EXTERNAL_GATE_SNAPSHOT_MISMATCH')
    closure_run_id=payload.get('closure_run_id')
    if closure_run_id is not None:
        closure_run_id=str(closure_run_id)
        if len(closure_run_id)!=32 or any(c not in '0123456789abcdef' for c in closure_run_id.lower()):
            raise RuntimeError('LOCAL_ACCEPTANCE_CLOSURE_RUN_ID_INVALID')
    if require_closure_run_id:
        run=read_closure_run(required=True)
        expected=str(run.get('closure_run_id') or '')
        if not closure_run_id or closure_run_id!=expected:
            raise RuntimeError(f'LOCAL_ACCEPTANCE_CLOSURE_RUN_ID_MISMATCH: stored={closure_run_id!r} active={expected!r}')
    return payload

def write(results,status,first=None,tree=None,suite=None,execution_mode=None,closure_run_id=None):
    payload={
      'schema':ACCEPTANCE_SCHEMA,'project':'Max MTF','version':'2.0.1','phase':ACCEPTANCE_PHASE,
      'overall_status':status,'first_failed_gate':first,'gate_count':len(TESTS),'results':results,
      'source_tree_signature':tree or _tree_sig(),'suite_signature':suite or _suite_sig(),
      'execution_mode':execution_mode or 'UNKNOWN','closure_run_id':closure_run_id,
      'generated_utc':datetime.now(timezone.utc).isoformat(),'checkpointed_after_each_gate':True,
      'external_gates':_external_gates(),
      'note':'MAX MTF v2.0.1 preserves MTF-1 external proof-of-execution and process-returncode authority while selectively porting inherited v1.4.7 bugfix contracts for Strategy-geometry handoff, fail-closed FAILED-to-CPCV resume, and provisional CPCV live KPI telemetry. Temporal DL/hybrid checkpoint selection uses purged internal early-validation, and Transformer MoE top-1 routing retains differentiable gate magnitude with post-best-checkpoint per-block routing diagnostics. Concrete LLM Scientist proposals use strict effective-bound admission with requested/executable provenance, and MODEL_TRAINING_METHOD_CONTRACT_V1 is shared across Manual, AUTO, Factory Director, round Scientist and Scientist Chat. v1.4.6 Scientist JSON recovery remains preserved. MTF-1 external execution proof remains preserved; MTF-2 feature/label implementation has independent phase-specific evidence and does not inherit future-phase model, ONNX, shadow, promotion, or runtime PASS.'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    return payload


def _acceptance_report_sha256(path: Path=OUT)->str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json_object(path: Path)->dict:
    try:
        payload=json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception as exc:
        raise RuntimeError(f'CURRENT_EVIDENCE_UNREADABLE: {Path(path).name}: {exc}') from exc
    if not isinstance(payload,dict):
        raise RuntimeError(f'CURRENT_EVIDENCE_NOT_OBJECT: {Path(path).name}')
    return payload


def _assert_current_evidence_policy(evidence_dir: Path=CURRENT_EVIDENCE_DIR)->dict:
    """Enforce one mutable current acceptance claim; repair/selftest claims are historical.

    `evidence/current` answers what is authoritative now. A v2.0.1 JSON document outside
    the canonical mutable claim may not carry a `local_acceptance` claim at all; otherwise
    a one-time repair artifact could accidentally become a volatile report-SHA authority.
    """
    evidence_dir=Path(evidence_dir)
    allowed=set(CURRENT_MUTABLE_ACCEPTANCE_CLAIMS)
    canonical={CURRENT_ACCEPTANCE_REPORT_NAME,CURRENT_EVIDENCE_SYNC_NAME,*allowed}
    forbidden=[]
    for path in sorted(evidence_dir.glob('*.json')):
        if path.name in canonical:
            continue
        payload=_load_json_object(path)
        if str(payload.get('version') or '')!='2.0.1':
            continue
        if isinstance(payload.get('local_acceptance'),dict):
            forbidden.append(path.name)
    if forbidden:
        raise RuntimeError(f'CURRENT_EVIDENCE_FORBIDDEN_STRAY_ACCEPTANCE_CLAIM: {forbidden}')
    return {
        'status':'PASS',
        'mutable_acceptance_claims':list(CURRENT_MUTABLE_ACCEPTANCE_CLAIMS),
        'acceptance_report':CURRENT_ACCEPTANCE_REPORT_NAME,
        'sync_record':CURRENT_EVIDENCE_SYNC_NAME,
    }


def _iter_current_v201_build_evidence(evidence_dir: Path=CURRENT_EVIDENCE_DIR):
    """Yield only canonical mutable current-build acceptance claims.

    Historical/intermediate repair evidence belongs under evidence/history and is never
    compared to a later Owner acceptance report SHA.
    """
    evidence_dir=Path(evidence_dir)
    _assert_current_evidence_policy(evidence_dir)
    for name in CURRENT_MUTABLE_ACCEPTANCE_CLAIMS:
        path=evidence_dir/name
        if not path.is_file():
            raise RuntimeError(f'CURRENT_EVIDENCE_CANDIDATE_BUILD_MISSING: {name}')
        payload=_load_json_object(path)
        if str(payload.get('version') or '')!='2.0.1':
            raise RuntimeError(f'CURRENT_EVIDENCE_CLAIM_VERSION: {name}')
        local=payload.get('local_acceptance')
        if not isinstance(local,dict):
            raise RuntimeError(f'CURRENT_EVIDENCE_LOCAL_ACCEPTANCE_MISSING: {name}')
        yield path,payload,local


def validate_current_build_evidence(*, report_path: Path=OUT, evidence_dir: Path=CURRENT_EVIDENCE_DIR,
                                    expected_tree: str|None=None, expected_suite: str|None=None,
                                    expected_gate_count: int|None=None, require_fresh_full: bool=True):
    """Fail closed on current identity while allowing report SHA to rotate per fresh run."""
    report_path=Path(report_path); evidence_dir=Path(evidence_dir)
    report=validate_local_acceptance_report(report_path,require_current_tree=False,require_current_suite=False,
                                            require_fresh_full=require_fresh_full)
    tree=str(expected_tree or report.get('source_tree_signature') or '')
    suite=str(expected_suite or report.get('suite_signature') or '')
    gates=int(expected_gate_count if expected_gate_count is not None else report.get('gate_count',-1))
    if str(report.get('source_tree_signature') or '')!=tree:
        raise RuntimeError('CURRENT_EVIDENCE_REPORT_TREE_MISMATCH')
    if str(report.get('suite_signature') or '')!=suite:
        raise RuntimeError('CURRENT_EVIDENCE_REPORT_SUITE_MISMATCH')
    if int(report.get('gate_count',-1))!=gates:
        raise RuntimeError('CURRENT_EVIDENCE_REPORT_GATE_COUNT_MISMATCH')
    if require_fresh_full and str(report.get('execution_mode') or '')!='FRESH_FULL':
        raise RuntimeError('CURRENT_EVIDENCE_REPORT_NOT_FRESH_FULL')
    report_sha=hashlib.sha256(report_path.read_bytes()).hexdigest()
    claims=list(_iter_current_v201_build_evidence(evidence_dir))
    if len(claims)!=1 or claims[0][0].name!=CURRENT_CANDIDATE_CLAIM_NAME:
        raise RuntimeError('CURRENT_EVIDENCE_CANONICAL_CLAIM_SET_MISMATCH')
    names={p.name for p,_,_ in claims}
    for path,payload,local in claims:
        if str(local.get('status') or '').upper()!='PASS':
            raise RuntimeError(f'CURRENT_EVIDENCE_NOT_PASS: {path.name}')
        implementation=payload.get('implementation_authority')
        if not isinstance(implementation,dict) or str(implementation.get('current_version') or '')!='MAX MTF v2.0.1':
            raise RuntimeError(f'CURRENT_EVIDENCE_IMPLEMENTATION_AUTHORITY_INVALID: {path.name}')
        if str(implementation.get('source_tree_signature') or '')!=tree:
            raise RuntimeError(f'CURRENT_EVIDENCE_IMPLEMENTATION_TREE_MISMATCH: {path.name}')
        if str(implementation.get('suite_signature') or '')!=suite:
            raise RuntimeError(f'CURRENT_EVIDENCE_IMPLEMENTATION_SUITE_MISMATCH: {path.name}')
        local_gates=local.get('gate_count',local.get('gates'))
        try: local_gates=int(local_gates)
        except Exception as exc: raise RuntimeError(f'CURRENT_EVIDENCE_GATE_COUNT_INVALID: {path.name}') from exc
        checks={
            'source_tree_signature':(str(local.get('source_tree_signature') or ''),tree),
            'suite_signature':(str(local.get('suite_signature') or ''),suite),
            'report_sha256':(str(local.get('report_sha256') or ''),report_sha),
            'gate_count':(local_gates,gates),
        }
        for field,(actual,expected) in checks.items():
            if actual!=expected:
                raise RuntimeError(f'CURRENT_EVIDENCE_{field.upper()}_MISMATCH: {path.name}: stored={actual!r} expected={expected!r}')
        if require_fresh_full and str(local.get('execution_mode') or '')!='FRESH_FULL':
            raise RuntimeError(f'CURRENT_EVIDENCE_NOT_FRESH_FULL: {path.name}')
    return {'status':'PASS','claim_count':len(claims),'files':sorted(names),'report_sha256':report_sha,
            'source_tree_signature':tree,'suite_signature':suite,'gate_count':gates,'execution_mode':report.get('execution_mode')}


def sync_current_build_evidence(*, report_path: Path=OUT, evidence_dir: Path=CURRENT_EVIDENCE_DIR):
    """Rotate only volatile current report identity; historical repair evidence is immutable."""
    report_path=Path(report_path); evidence_dir=Path(evidence_dir)
    _assert_current_evidence_policy(evidence_dir)
    report=validate_local_acceptance_report(report_path,require_current_tree=True,require_current_suite=True,require_fresh_full=True)
    report_sha=hashlib.sha256(report_path.read_bytes()).hexdigest()
    candidate_path=evidence_dir/CURRENT_CANDIDATE_CLAIM_NAME
    sync_path=evidence_dir/CURRENT_EVIDENCE_SYNC_NAME
    if not candidate_path.is_file():
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_BUILD_MISSING')
    candidate=_load_json_object(candidate_path)
    if str(candidate.get('version') or '')!='2.0.1':
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_BUILD_VERSION')
    tree=str(report['source_tree_signature']); suite=str(report['suite_signature']); gates=int(report['gate_count'])
    implementation=candidate.get('implementation_authority')
    if not isinstance(implementation,dict) or str(implementation.get('current_version') or '')!='MAX MTF v2.0.1':
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_IMPLEMENTATION_AUTHORITY')
    if str(implementation.get('source_tree_signature') or '')!=tree:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_TREE_MISMATCH')
    if str(implementation.get('suite_signature') or '')!=suite:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_SUITE_MISMATCH')
    previous_local=candidate.get('local_acceptance')
    if not isinstance(previous_local,dict):
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_LOCAL_ACCEPTANCE_MISSING')
    if str(previous_local.get('source_tree_signature') or '')!=tree:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_LOCAL_TREE_MISMATCH')
    if str(previous_local.get('suite_signature') or '')!=suite:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_LOCAL_SUITE_MISMATCH')
    try:
        previous_gates=int(previous_local.get('gate_count',previous_local.get('gates')))
    except Exception as exc:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_GATE_COUNT_INVALID') from exc
    if previous_gates!=gates:
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_GATE_COUNT_MISMATCH')
    if str(previous_local.get('execution_mode') or '')!='FRESH_FULL':
        raise RuntimeError('CURRENT_EVIDENCE_CANDIDATE_NOT_FRESH_FULL')
    candidate['build_id']=f'V201_{tree[:12].upper()}_{suite[:8].upper()}'
    candidate['generated_utc']=str(report.get('generated_utc') or datetime.now(timezone.utc).isoformat())
    candidate['local_acceptance']={
        'status':'PASS','gate_count':gates,'result_count':len(report.get('results') or []),'first_failed_gate':None,
        'execution_mode':'FRESH_FULL','source_tree_signature':tree,'suite_signature':suite,
        'report':f'ModelLab/evidence/current/{CURRENT_ACCEPTANCE_REPORT_NAME}','report_sha256':report_sha,
    }
    candidate['current_evidence_policy']={
        'authority':CURRENT_ACCEPTANCE_REPORT_NAME,
        'mutable_current_acceptance_claims':list(CURRENT_MUTABLE_ACCEPTANCE_CLAIMS),
        'historical_repair_evidence_location':'ModelLab/evidence/history/build_repairs/',
        'binding':'EXACT_SOURCE_TREE_SUITE_REPORT_SHA_GATE_COUNT_FRESH_FULL',
        'report_sha_lifecycle':'VOLATILE_PER_FRESH_ACCEPTANCE_RUN',
    }
    candidate_path.write_text(json.dumps(candidate,indent=2)+'\n',encoding='utf-8')
    sync_payload={
        'schema':'MAX_MTF_V201_CURRENT_EVIDENCE_SYNC_V2','project':'Max MTF','version':'2.0.1',
        'generated_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS',
        'acceptance_report':f'ModelLab/evidence/current/{CURRENT_ACCEPTANCE_REPORT_NAME}',
        'acceptance_report_sha256':report_sha,'source_tree_signature':tree,'suite_signature':suite,
        'gate_count':gates,'execution_mode':'FRESH_FULL',
        'mutable_current_acceptance_claims':list(CURRENT_MUTABLE_ACCEPTANCE_CLAIMS),
        'historical_repair_evidence_policy':'IMMUTABLE_NOT_REBOUND_TO_FUTURE_ACCEPTANCE_REPORT_SHA',
        'owner_mt5_metaeditor_execution':'NOT_RUN_BY_BUILDER'
    }
    sync_path.write_text(json.dumps(sync_payload,indent=2)+'\n',encoding='utf-8')
    return validate_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir,
                                           expected_tree=tree,expected_suite=suite,expected_gate_count=gates,
                                           require_fresh_full=True)


def _acceptance_child_env()->dict[str,str]:
    env=acceptance_utf8_env(os.environ)
    env['PYTHONPATH']=str(ROOT)+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    env['MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE']='1'
    return env

def main():
    from mtf.mtf1_python_env_authority import assert_current_process_if_required
    assert_current_process_if_required('local_acceptance')
    ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    tree=_tree_sig();suite=_suite_sig();runtime_sig=_runtime_authority_signature();results=[];execution_mode='RESUMED_CHECKPOINT' if args.resume else 'FRESH_FULL'
    active_run=read_closure_run(required=False); closure_run_id=(str(active_run.get('closure_run_id')) if active_run else None)
    if args.resume and OUT.exists():
        try:
            old=json.loads(OUT.read_text(encoding='utf-8'))
            compatible=(old.get('version')=='2.0.1' and old.get('first_failed_gate') is None and old.get('source_tree_signature')==tree and old.get('suite_signature')==suite and int(old.get('gate_count',-1))==len(TESTS) and old.get('closure_run_id')==closure_run_id)
            if compatible:
                rows={(r.get('gate'),r.get('script')):r for r in old.get('results',[]) if r.get('status')=='PASS'}
                for pair in TESTS:
                    if pair not in rows: break
                    results.append(rows[pair])
        except Exception:
            results=[]
    done={(r['gate'],r['script']) for r in results}
    write(results,'RUNNING',tree=tree,suite=suite,execution_mode=execution_mode,closure_run_id=closure_run_id)
    env=_acceptance_child_env()
    for gate,script in TESTS:
        if (gate,script) in done:
            print(f'=== {gate} :: {script} === [CHECKPOINT PASS; SKIP]',flush=True);continue
        print(f'=== {gate} :: {script} ===',flush=True);t=time.monotonic()
        cp=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,env=env)
        elapsed=round(time.monotonic()-t,3)
        if _runtime_authority_signature()!=runtime_sig:
            results.append({'gate':'ACCEPTANCE_RUNTIME_AUTHORITY_MUTATED','script':script,'status':'FAIL','exit_code':98,'elapsed_seconds':elapsed})
            write(results,'FAIL','ACCEPTANCE_RUNTIME_AUTHORITY_MUTATED',tree,suite,execution_mode,closure_run_id);return 1
        if _tree_sig()!=tree:
            results.append({'gate':'ACCEPTANCE_TREE_MUTATED_DURING_RUN','script':script,'status':'FAIL','exit_code':97,'elapsed_seconds':elapsed})
            write(results,'FAIL','ACCEPTANCE_TREE_MUTATED_DURING_RUN',tree,suite,execution_mode,closure_run_id);return 1
        row={'gate':gate,'script':script,'status':'PASS' if cp.returncode==0 else 'FAIL','exit_code':cp.returncode,'elapsed_seconds':elapsed};results.append(row)
        if cp.returncode:
            write(results,'FAIL',gate,tree,suite,execution_mode,closure_run_id);return 1
        write(results,'RUNNING',tree=tree,suite=suite,execution_mode=execution_mode,closure_run_id=closure_run_id)
    p=write(results,'PASS',tree=tree,suite=suite,execution_mode=execution_mode,closure_run_id=closure_run_id)
    validate_local_acceptance_report(p,require_fresh_full=(execution_mode=='FRESH_FULL'))
    if execution_mode=='FRESH_FULL':
        try:
            synced=sync_current_build_evidence(report_path=OUT,evidence_dir=CURRENT_EVIDENCE_DIR)
        except Exception as exc:
            write(results,'FAIL','V201_CURRENT_EVIDENCE_SYNC_POSTSEAL',tree,suite,execution_mode,closure_run_id)
            print(f'CURRENT EVIDENCE SYNC FAIL: {exc}',flush=True)
            return 1
        print(f"CURRENT EVIDENCE SYNC PASS {synced['claim_count']} current build claim(s)",flush=True)
    print(f"BUILD ACCEPTANCE PASS {len(results)}/{len(TESTS)}",flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
