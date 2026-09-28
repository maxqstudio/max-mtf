from pathlib import Path
import hashlib, json, os, re, subprocess, sys, tempfile
from acceptance.runners.acceptance_process_env import acceptance_utf8_env
import acceptance.runners.run_acceptance as run_acceptance
from acceptance.runners.max_python_bootstrap import _canonical_env
from acceptance.runners.owner_scientist_python_runtime_acceptance import _run_logged_stage
from acceptance.verification.modellab_layout_verify import (
    EXTERNAL_RUNTIME_IMPORTS,
    _fresh_import_rows,
    _import_sweep,
    _validate_external_runtime_contracts,
    verify_layout,
)
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)

for rel in ('Releases/active/release.json','ModelLab/runtime/active_release.json'):
    p=PKG/rel; obj=json.loads(p.read_text(encoding='utf-8')); path=str((obj.get('ea') or {}).get('path') or '')
    req(path and not Path(path).is_absolute(),rel+' must use project-relative EA path')
    req('/mnt/data/' not in path.replace('\\','/'),rel+' must not embed build-container path')
    req(not re.match(r'^[A-Za-z]:[\\/]',path),rel+' must not embed Windows absolute project path')

manifest_path=PKG/'governance/MTF1_INHERITED_V145_SCIENTIFIC_CORE.json'
EXPECTED_MANIFEST_SHA='e69a55292decbab280e6ad2f02321b188a5107d6819e5edc569e33b981c405c7'
req(hashlib.sha256(manifest_path.read_bytes()).hexdigest()==EXPECTED_MANIFEST_SHA,'frozen v1.4.5 scientific-core manifest identity')
m=json.loads(manifest_path.read_text(encoding='utf-8'))
req(m['schema']=='MAX_MTF_INHERITED_V145_SCIENTIFIC_CORE_V4','v1.4.5 core manifest uses explicit selective repair scopes including Scientist E2E sync')
req(m['source_package_sha256']=='371a4575ed87a845fb7bdfee4f8ded45fe811a77dcf33c8ed93e9f48ee92c190','exact v1.4.5 source package authority')
science=m.get('selective_scientific_repair') or {}
req(science.get('authority')=='CURRENT_MAX_MTF_V2_0_1_TRAINING_SCIENCE_REPAIR_ONLY','training-science repair authority is narrow/current-only')
science_expected={'V201_DL_INTERNAL_EARLYSTOP_PURGE','V201_MOE_TOP1_ROUTER_GRADIENT','V201_MOE_ROUTING_DIAGNOSTICS'}
req(set(science.get('required_gates') or [])==science_expected,'training-science repair bound to exact three new gates')
science_allowed={'ModelLab/core/temporal_index.py','ModelLab/research/gru_research.py','ModelLab/research/temporal_research.py','ModelLab/research/hybrid_research.py','ModelLab/models/models.py','ModelLab/models/model_lab.py','ModelLab/factory/supervisor_agent.py','ModelLab/research/cpcv.py','ModelLab/factory/champion_factory.py','ModelLab/config/models/model_registry.json'}
req(set((science.get('files') or {}).keys())==science_allowed,'training-science repair file allowlist is exact')
for rel,row in (science.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' training-science repair source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' training-science repair source matches authorized current hash')
sync=m.get('selective_scientist_sync_repair') or {}
req(sync.get('authority')=='CURRENT_MAX_MTF_V2_0_1_SCIENTIST_E2E_SYNC_ONLY','Scientist E2E repair authority is narrow/current-only')
sync_gates={'V201_SCIENTIST_KNOWLEDGE_SYNC','V201_SCIENTIST_STRICT_CANDIDATE_ADMISSION','V201_TRAINING_METHOD_CONTRACT_E2E_SYNC','V201_MANUAL_EXACT_PARAMETER_IDENTITY','V201_MEMORY_EXACT_RECHECK_LINEAGE','V201_SCIENTIST_HYPOTHESIS_ADMISSION'}
req(set(sync.get('required_gates') or [])==sync_gates,'research-intent E2E repair bound to exact current gates')
sync_allowed={'ModelLab/models/models.py','ModelLab/scientist/core/scientist.py','ModelLab/factory/supervisor_agent.py','ModelLab/models/model_registry.py','ModelLab/research/research_architect.py','ModelLab/research/research_control.py','ModelLab/scientist/knowledge/scientist_knowledge.py','ModelLab/scientist/chat/scientist_chat.py','ModelLab/ui/app.py','ModelLab/max_graph/scientist_director_graph.py','ModelLab/core/training_method_contract.py','ModelLab/governance/MODEL_TRAINING_METHOD_CONTRACT_V1.json','ModelLab/research/research_memory.py','ModelLab/research/scientific_hypotheses.py'}
req(set((sync.get('files') or {}).keys())==sync_allowed,'Scientist E2E repair file allowlist is exact')
for rel,row in (sync.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Scientist E2E repair source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Scientist E2E repair source matches authorized current hash')

capacity=m.get('selective_dynamic_capacity_repair') or {}
req(capacity.get('authority')=='CURRENT_MAX_MTF_V2_0_1_DYNAMIC_MODEL_CAPACITY_ONLY','dynamic capacity repair authority is narrow/current-only')
req(set(capacity.get('required_gates') or [])=={'V201_DYNAMIC_MODEL_CAPACITY_AUTHORITY','V201_DYNAMIC_CAPACITY_SEARCH_DIVERSITY_FAMILY_EVIDENCE','V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM'},'dynamic capacity repair bound to exact current gates')
capacity_allowed={
    'ModelLab/models/capacity_governor.py','ModelLab/host/resource_preflight.py','ModelLab/models/model_registry.py',
    'ModelLab/research/research_architect.py','ModelLab/research/research_control.py','ModelLab/scientist/core/scientist.py',
    'ModelLab/models/models.py','ModelLab/factory/champion_factory.py','ModelLab/ui/app.py',
    'ModelLab/scientist/knowledge/scientist_knowledge.py','ModelLab/config/config.json','ModelLab/config/models/model_registry.json',
}
req(set((capacity.get('files') or {}).keys())==capacity_allowed,'dynamic capacity repair file allowlist is exact')
for rel,row in (capacity.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' dynamic-capacity repair source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' dynamic-capacity repair source matches authorized current hash')

runtime=m.get('selective_scientist_python_analysis_runtime') or {}
req(runtime.get('authority')=='CURRENT_MAX_MTF_V2_0_1_INTEGRATED_ONE_CLICK_SCIENTIST_PYTHON_OWNER_ACCEPTANCE_ONLY','Scientist Python V1 repair authority is narrow/current-only')
req(set(runtime.get('required_gates') or [])=={'V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME','V201_SCIENTIST_KNOWLEDGE_SYNC'},'Scientist Python V1 repair bound to runtime + Knowledge sync gates')
runtime_allowed={
    'ModelLab/scientist/python/scientist_python_runtime.py','ModelLab/scientist/python/scientist_python_child.py','ModelLab/scientist/python/scientist_python_capabilities.py','ModelLab/scientist/python/scientist_python_setup.py',
    'ModelLab/requirements/requirements-scientist-python.txt','ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd','ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd',
    'ModelLab/scientist/core/scientist.py','ModelLab/scientist/chat/scientist_chat.py','ModelLab/scientist/knowledge/scientist_knowledge.py',
    'ModelLab/docs/contracts/SCIENTIST_PYTHON_ANALYSIS_RUNTIME_V1.md',
    'ModelLab/acceptance/runners/owner_scientist_python_runtime_acceptance.py','ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd','ModelLab/acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
}
req(set((runtime.get('files') or {}).keys())==runtime_allowed,'Scientist Python V1 file allowlist is exact')
for rel,row in (runtime.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Scientist Python V1 source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Scientist Python V1 source matches authorized current hash')

authorized_core=science_allowed | {rel for rel in sync_allowed if rel in set(m['files'])} | {rel for rel in capacity_allowed if rel in set(m['files'])} | {rel for rel in runtime_allowed if rel in set(m['files'])}
layout_auth=m.get('selective_modellab_layout_migration') or {}
req(layout_auth.get('authority')=='CURRENT_MAX_MTF_V2_0_1_MODELLAB_CANONICAL_LAYOUT_MIGRATION_ONLY','ModelLab layout migration authority is explicit and narrow')
req(layout_auth.get('layout_manifest')=='ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json','layout migration binds canonical relocation manifest')
req(layout_auth.get('required_gate')=='V201_RELEASE_PORTABILITY','layout migration is covered by mandatory release-portability gate')
layout_result=verify_layout(write_evidence=True)
req(layout_result.get('overall_status')=='PASS','canonical ModelLab layout verification passes')
binding=m.get('selective_owner_acceptance_canonical_max_python_binding') or {}
req(binding.get('authority')=='CURRENT_MAX_MTF_V2_0_1_OWNER_ACCEPTANCE_CANONICAL_MAX_PYTHON_BINDING_REPAIR_ONLY','canonical MAX Python binding repair authority is explicit and narrow')
req(binding.get('canonical_authority')=='ui.ui_bootstrap.ensure_python312 + ui.ui_launcher.ensure_env/venv_python','canonical MAX Python binding must reuse existing UI bootstrap/venv authority')
req(set(binding.get('required_gates') or [])=={'V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME','V201_RELEASE_PORTABILITY','V201_FINAL_CLOSURE_PYTHON_ENV_AUTHORITY'},'canonical MAX Python binding repair gate set')
binding_allowed={
    'ModelLab/acceptance/runners/max_python_bootstrap.py',
    'ModelLab/acceptance/runners/run_acceptance.py',
    'ModelLab/acceptance/runners/owner_scientist_python_runtime_acceptance.py',
    'ModelLab/acceptance/verification/modellab_layout_verify.py',
    'ModelLab/RUN_ACCEPTANCE.cmd',
    'ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
    'ModelLab/acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
    'ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd',
    'ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd',
}
req(set((binding.get('files') or {}).keys())==binding_allowed,'canonical MAX Python binding file allowlist is exact')
for rel,row in (binding.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' canonical MAX Python binding source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' canonical MAX Python binding source matches authorized current hash')
ui_import=m.get('selective_ui_acceptance_runtime_import_classification') or {}
req(ui_import.get('authority')=='CURRENT_MAX_MTF_V2_0_1_UI_ACCEPTANCE_RUNTIME_IMPORT_CLASSIFICATION_REPAIR_ONLY','UI acceptance runtime import classification authority is explicit and narrow')
req(ui_import.get('required_gate')=='V201_RELEASE_PORTABILITY','UI acceptance runtime import classification stays inside release portability gate')
req(ui_import.get('external_runtime_gate')=='STREAMLIT_1_63_RUNTIME_RENDER_ACCEPTANCE','UI browser acceptance uses canonical external runtime gate')
ui_import_allowed={
    'ModelLab/acceptance/verification/modellab_layout_verify.py',
    'ModelLab/acceptance/runners/ui_runtime_acceptance_bootstrap.py',
    'ModelLab/acceptance/runners/ui_runtime_browser_acceptance.py',
    'ModelLab/requirements/requirements-ui-acceptance.txt',
    'governance/EXTERNAL_RUNTIME_GATES.json',
    'governance/PACKAGE_MANIFEST.json',
}
req(set((ui_import.get('files') or {}).keys())==ui_import_allowed,'UI acceptance runtime import classification file allowlist is exact')
for rel,row in (ui_import.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' UI acceptance runtime import classification source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' UI acceptance runtime import classification source matches authorized current hash')
utf8_repair=m.get('selective_windows_acceptance_utf8_process_contract_repair') or {}
req(utf8_repair.get('authority')=='CURRENT_MAX_MTF_V2_0_1_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR_ONLY','Windows acceptance UTF-8 repair authority is explicit and narrow')
req(utf8_repair.get('build_scope')=='MAX_MTF_V2_0_1_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR','Windows acceptance UTF-8 repair build scope')
req(utf8_repair.get('required_gate')=='V201_RELEASE_PORTABILITY','Windows acceptance UTF-8 repair stays inside release portability gate')
req((utf8_repair.get('required_python_environment') or {})=={'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'},'Windows acceptance UTF-8 standard Python environment contract')
req(utf8_repair.get('cumulative_gate_count')==75,'Windows acceptance UTF-8 repair must not add a gate')
utf8_allowed={
    'ModelLab/acceptance/runners/acceptance_process_env.py',
    'ModelLab/acceptance/runners/run_acceptance.py',
    'ModelLab/acceptance/runners/max_python_bootstrap.py',
    'ModelLab/acceptance/runners/owner_scientist_python_runtime_acceptance.py',
    'ModelLab/acceptance/verification/modellab_layout_verify.py',
    'ModelLab/acceptance/runners/cuda_runtime_acceptance.py',
    'ModelLab/acceptance/runners/langgraph_runtime_acceptance.py',
    'ModelLab/acceptance/runners/ui_runtime_acceptance_bootstrap.py',
    'ModelLab/acceptance/runners/ui_runtime_browser_acceptance.py',
    'ModelLab/scientist/knowledge/scientist_knowledge.py',
    'ModelLab/docs/repairs/V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR.md',
    'governance/PACKAGE_MANIFEST.json',
    'ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json',
    'governance/CURRENT_AUTHORITY.json',
}
req(set((utf8_repair.get('files') or {}).keys())==utf8_allowed,'Windows acceptance UTF-8 repair file allowlist is exact')
for rel,row in (utf8_repair.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Windows acceptance UTF-8 repair source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Windows acceptance UTF-8 repair source matches authorized current hash')
req(utf8_repair.get('scientific_semantics_change') is False and utf8_repair.get('mtf2_status')=='BLOCKED','Windows acceptance UTF-8 repair preserves scientific semantics and MTF-2 block')
newline_repair=m.get('selective_windows_utf8_newline_portability_selftest_repair') or {}
req(newline_repair.get('authority')=='CURRENT_MAX_MTF_V2_0_1_WINDOWS_UTF8_NEWLINE_PORTABILITY_SELFTEST_REPAIR_ONLY','Windows UTF-8 newline selftest repair authority is explicit and narrow')
req(newline_repair.get('build_scope')=='MAX_MTF_V2_0_1_WINDOWS_UTF8_NEWLINE_PORTABILITY_SELFTEST_REPAIR','Windows UTF-8 newline selftest repair build scope')
req(newline_repair.get('required_gate')=='V201_RELEASE_PORTABILITY' and newline_repair.get('cumulative_gate_count')==75,'Windows UTF-8 newline selftest repair stays inside existing portability gate')
req(newline_repair.get('strict_decode')=='utf-8 errors=strict' and newline_repair.get('newline_normalization')=='CRLF_CR_LF_ONLY','Windows UTF-8 newline selftest strict decode/newline contract')
req(newline_repair.get('preserve_negative_cp1252_fixture') is True and newline_repair.get('preserve_real_cpcv_redirected_regression') is True,'Windows UTF-8 newline selftest preserves negative/real regressions')
req(newline_repair.get('previous_process_contract_preserved') is True and newline_repair.get('global_lf_forcing') is False,'Windows UTF-8 newline selftest must not replace process contract or force LF')
req(newline_repair.get('scientific_semantics_change') is False and newline_repair.get('mtf2_status')=='BLOCKED','Windows UTF-8 newline selftest preserves scientific semantics and MTF-2 block')
newline_allowed={'ModelLab/docs/repairs/V201_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR.md','governance/PACKAGE_MANIFEST.json','governance/CURRENT_AUTHORITY.json'}
req(set((newline_repair.get('files') or {}).keys())==newline_allowed,'Windows UTF-8 newline selftest governance file allowlist is exact')
for rel,row in (newline_repair.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Windows UTF-8 newline selftest governance source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Windows UTF-8 newline selftest governance hash')

reconcile=m.get('selective_scientist_python_owner_runtime_authority_reconciliation') or {}
req(reconcile.get('authority')=='CURRENT_MAX_MTF_V2_0_1_SCIENTIST_PYTHON_OWNER_RUNTIME_AUTHORITY_RECONCILIATION_ONLY','Scientist Python Owner runtime reconciliation authority is explicit and narrow')
req(reconcile.get('build_scope')=='MAX_MTF_V2_0_1_SCIENTIST_PYTHON_OWNER_RUNTIME_AUTHORITY_RECONCILIATION','Scientist Python Owner runtime reconciliation build scope')
req(set(reconcile.get('required_gates') or [])=={'V201_RELEASE_PORTABILITY','V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME','V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY'},'Scientist Python Owner runtime reconciliation uses existing exact gates only')
req(reconcile.get('owner_runtime_status')=='READY_PASS','Scientist Python Owner runtime reconciliation records READY_PASS')
req(reconcile.get('evidence_policy')=='CANONICAL_ONE_CLICK_OWNER_WINDOWS_RUNTIME_PLUS_READ_ONLY_VERIFIER_CANDIDATE_BOUND','Scientist Python Owner runtime reconciliation evidence policy')
reconcile_allowed={'governance/CURRENT_AUTHORITY.json'}
req(set((reconcile.get('files') or {}).keys())==reconcile_allowed,'Scientist Python Owner runtime reconciliation file allowlist is exact')
for rel,row in (reconcile.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Scientist Python Owner runtime reconciliation source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Scientist Python Owner runtime reconciliation source matches authorized current hash')
req(reconcile.get('scientific_semantics_change') is False and reconcile.get('factory_decision_authority_change') is False and reconcile.get('mtf2_status')=='BLOCKED','Scientist Python Owner runtime reconciliation preserves science/factory authority and MTF-2 block')

postseal=m.get('selective_owner_acceptance_postseal_evidence_exitcode_repair') or {}
req(postseal.get('authority')=='CURRENT_MAX_MTF_V2_0_1_OWNER_ACCEPTANCE_POSTSEAL_EVIDENCE_AND_EXITCODE_REPAIR_ONLY','Owner post-seal evidence/exitcode repair authority is explicit and narrow')
req(postseal.get('build_scope')=='MAX_MTF_V2_0_1_OWNER_ACCEPTANCE_POSTSEAL_EVIDENCE_AND_EXITCODE_REPAIR','Owner post-seal repair build scope')
req(set(postseal.get('required_gates') or [])=={'V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY','V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME'},'Owner post-seal repair reuses exact existing gates')
req(postseal.get('cumulative_gate_count')==75 and postseal.get('bootstrap_unavailable_exit_code')==103,'Owner post-seal repair preserves gate count and unavailable exit 103')
req(postseal.get('current_acceptance_claim_policy')=='ONE_MUTABLE_CANDIDATE_BUILD_CLAIM_PLUS_CANONICAL_REPORT_AND_SYNC_RECORD','Owner post-seal repair current-evidence authority policy')
req(postseal.get('historical_repair_evidence_policy')=='IMMUTABLE_NOT_REBOUND_TO_LATER_OWNER_REPORT_SHA','Owner post-seal repair historical evidence policy')
req(postseal.get('owner_cmd_returncode_policy')=='EXACT_CHILD_RETURNCODE_LABEL_FLOW_NO_DELAYED_EXPANSION','Owner post-seal repair truthful CMD return-code policy')
req(postseal.get('scientific_semantics_change') is False and postseal.get('mtf2_status')=='BLOCKED','Owner post-seal repair preserves science and MTF-2 block')
postseal_allowed={
    'ModelLab/acceptance/runners/run_acceptance.py',
    'ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
    'ModelLab/acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd',
    'ModelLab/docs/repairs/V201_OWNER_ACCEPTANCE_POSTSEAL_EVIDENCE_AND_EXITCODE_REPAIR.md',
    'governance/PACKAGE_MANIFEST.json','governance/CURRENT_AUTHORITY.json',
    'ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json',
}
req(set((postseal.get('files') or {}).keys())==postseal_allowed,'Owner post-seal repair file allowlist is exact')
for rel,row in (postseal.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' Owner post-seal repair source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' Owner post-seal repair source matches authorized current hash')

for rel,expected in m['files'].items():
    p=PKG/rel
    req(p.is_file(),rel+' inherited scientific core exists at canonical relocated path')
    req(isinstance(expected,str) and len(expected)==64,rel+' retains frozen v1.4.5 baseline hash for lineage')
port=m.get('selective_bugfix_port') or {}
req(port.get('authority')=='CURRENT_MAX_MTF_V2_0_1_SELECTIVE_PORT_ONLY','selective bugfix port is explicitly scoped to current v2.0.1')
expected_gates={'V201_INHERITED_V147_STRATEGY_GEOMETRY_HANDOFF','V201_INHERITED_V147_FAILED_CPCV_RESUME','V201_CPCV_LIVE_KPI_TELEMETRY'}
req(set(port.get('required_gates') or [])==expected_gates,'selective v1.4.7 port is bound to the three inherited regression gates')
allowed=set((port.get('files') or {}).keys())
req(allowed=={'ModelLab/factory/champion_factory.py','ModelLab/factory/factory_jobs.py','ModelLab/factory/factory_worker.py','ModelLab/strategy/strategy_geometry.py','ModelLab/core/inherited_v147.py','ModelLab/ui/app.py'},'selective bugfix file allowlist is exact; no wholesale v1.4.7 replacement')
for rel,row in (port.get('files') or {}).items():
    p=PKG/rel
    req(p.is_file(),rel+' selective bugfix source exists')
    req(hashlib.sha256(p.read_bytes()).hexdigest()==row.get('current_sha256'),rel+' selective bugfix source matches authorized current hash')

# UI acceptance-only runtime import classification (UI-A through UI-H).
# Playwright is intentionally NOT a canonical MAX production dependency.
ui_contract = EXTERNAL_RUNTIME_IMPORTS.get('acceptance.runners.ui_runtime_browser_acceptance') or {}
req(ui_contract.get('dependency') == 'playwright', 'UI-A browser acceptance runner must be explicitly classified as Playwright external runtime')
req(ui_contract.get('requirements') == 'requirements/requirements-ui-acceptance.txt', 'UI-C browser runner must bind acceptance-only requirements')
req(ui_contract.get('required_pin') == 'playwright==1.57.0', 'UI-C browser runner exact Playwright pin')
req(ui_contract.get('bootstrap_module') == 'acceptance.runners.ui_runtime_acceptance_bootstrap', 'UI-D browser runner must bind dedicated UI acceptance bootstrap')
req(ui_contract.get('external_gate') == 'STREAMLIT_1_63_RUNTIME_RENDER_ACCEPTANCE', 'UI-E browser runner must bind canonical real UI runtime gate')

# UI-A: emulate a canonical MAX environment in which Playwright is unavailable.
# The production sweep must still pass because only the explicit governed module is excluded.
blocked_playwright = _import_sweep(blocked_dependencies={'playwright'})
external_rows = {row['module']: row for row in blocked_playwright['external_runtime_gated']}
req('acceptance.runners.ui_runtime_browser_acceptance' in external_rows, 'UI-A browser runner must be external-runtime gated')
req(all(row['module'] != 'acceptance.runners.ui_runtime_browser_acceptance' for row in blocked_playwright['fresh_process_imported']), 'UI-A browser runner must not import in canonical MAX sweep')

# UI-B/C/D/E are also enforced by production contract validation.
validated_external = _validate_external_runtime_contracts()
validated_modules = {row['module'] for row in validated_external}
req('acceptance.runners.ui_runtime_browser_acceptance' in validated_modules, 'UI-B browser runner source must parse and validate')

# UI-F/UI-G: synthetic fixture proves missing pin or gate binding fails closed.
with tempfile.TemporaryDirectory(prefix='max_mtf_ui_external_contract_') as td:
    troot = Path(td) / 'ModelLab'
    tpkg = troot.parent
    (troot / 'acceptance/runners').mkdir(parents=True)
    (troot / 'requirements').mkdir(parents=True)
    browser = troot / 'acceptance/runners/ui_runtime_browser_acceptance.py'
    bootstrap = troot / 'acceptance/runners/ui_runtime_acceptance_bootstrap.py'
    browser.write_text('from playwright.sync_api import sync_playwright\n', encoding='utf-8')
    bootstrap.write_text('TARGET="acceptance.runners.ui_runtime_browser_acceptance"\nREQ="requirements-ui-acceptance.txt"\n', encoding='utf-8')
    contracts = {
        'acceptance.runners.ui_runtime_browser_acceptance': {
            'dependency': 'playwright',
            'requirements': 'requirements/requirements-ui-acceptance.txt',
            'required_pin': 'playwright==1.57.0',
            'external_gate': 'UI_BROWSER_GATE',
            'bootstrap_module': 'acceptance.runners.ui_runtime_acceptance_bootstrap',
        }
    }
    good_registry = {'gates': [{'gate': 'UI_BROWSER_GATE'}]}
    reqfile = troot / 'requirements/requirements-ui-acceptance.txt'
    reqfile.write_text('playwright==1.57.0\n', encoding='utf-8')
    _validate_external_runtime_contracts(root=troot, pkg=tpkg, contracts=contracts, registry=good_registry)
    reqfile.write_text('playwright==1.56.0\n', encoding='utf-8')
    try:
        _validate_external_runtime_contracts(root=troot, pkg=tpkg, contracts=contracts, registry=good_registry)
    except AssertionError:
        pass
    else:
        raise AssertionError('UI-F mutated Playwright pin must fail layout verification')
    reqfile.write_text('playwright==1.57.0\n', encoding='utf-8')
    try:
        _validate_external_runtime_contracts(root=troot, pkg=tpkg, contracts=contracts, registry={'gates': []})
    except AssertionError:
        pass
    else:
        raise AssertionError('UI-G missing external runtime gate binding must fail layout verification')

# UI-H: a random production module with an undeclared missing dependency is NOT exempted.
with tempfile.TemporaryDirectory(prefix='max_mtf_ui_import_negative_') as td:
    troot = Path(td)
    (troot / 'research').mkdir(parents=True)
    (troot / 'research/__init__.py').write_text('', encoding='utf-8')
    (troot / 'research/some_module.py').write_text('import nonexistent_optional_package\n', encoding='utf-8')
    try:
        _fresh_import_rows(['research.some_module'], root=troot, timeout=20)
    except AssertionError:
        pass
    else:
        raise AssertionError('UI-H undeclared production dependency must fail fresh import sweep')


# Windows acceptance UTF-8 process contract regression (UTF-A through UTF-G).
UTF_SAMPLE="DL→ML\nA↔B\nPASS — deterministic\nPF ≥ 1.5\n→ ↔ — · … × ≥\n"
UTF_CODE=f"import sys;sys.stdout.write({UTF_SAMPLE!r});sys.stdout.flush()"

def normalize_standard_newlines(value:str)->str:
    return value.replace('\r\n','\n').replace('\r','\n')

def strict_utf8_semantic_equal(raw:bytes,expected:str)->bool:
    return normalize_standard_newlines(raw.decode('utf-8',errors='strict'))==normalize_standard_newlines(expected)

legacy_env=dict(os.environ)
legacy_env['PYTHONUTF8']='0'
legacy_env['PYTHONIOENCODING']='cp1252'
legacy=subprocess.run([sys.executable,'-c',UTF_CODE],cwd=ROOT,env=legacy_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
req(legacy.returncode!=0 and b'UnicodeEncodeError' in (legacy.stdout or b''),'UTF-NEG/UTF-F CP1252-like child must reproduce UnicodeEncodeError without canonical UTF-8 env')
print('UTF-F PASS — CP1252-like negative fixture is locale-independent')

utf_env=acceptance_utf8_env(legacy_env)
utf=subprocess.run([sys.executable,'-c',UTF_CODE],cwd=ROOT,env=utf_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
req(utf.returncode==0,f'UTF-A/C child failed rc={utf.returncode}: {(utf.stdout or b"")[-1000:]!r}')
utf_bytes=utf.stdout or b''
utf_text=utf_bytes.decode('utf-8',errors='strict')
req('DL→ML' in utf_text,'UTF-A arrow missing')
print('UTF-A PASS — DL→ML')
for token in ('→','↔','—','·','…','×','≥'):
    req(token in utf_text,f'UTF-B symbol missing: {token}')
print('UTF-B PASS — → ↔ — · … × ≥')
for token in ('→','↔','—','≥'):
    req(token.encode('utf-8') in utf_bytes,f'UTF-C UTF-8 bytes missing for {token}')
req(strict_utf8_semantic_equal(utf_bytes,UTF_SAMPLE),'UTF-C redirected stdout semantic text must round-trip as strict UTF-8 across native newline conventions')
print('UTF-C PASS — redirected stdout strict UTF-8 semantic round-trip')

lf=UTF_SAMPLE.encode('utf-8')
crlf=UTF_SAMPLE.replace('\n','\r\n').encode('utf-8')
req(strict_utf8_semantic_equal(lf,UTF_SAMPLE),'UTF-C1 LF must PASS')
print('UTF-C1 PASS — LF semantic UTF-8 text accepted')
req(strict_utf8_semantic_equal(crlf,UTF_SAMPLE),'UTF-C2 CRLF must PASS')
print('UTF-C2 PASS — CRLF semantic UTF-8 text accepted')

bad=lf.replace('→'.encode('utf-8'),b'\xe2\x28\xa1',1)
try:
    strict_utf8_semantic_equal(bad,UTF_SAMPLE)
except UnicodeDecodeError:
    pass
else:
    raise AssertionError('UTF-C3 malformed UTF-8 must FAIL strict decoding')
print('UTF-C3 PASS — malformed UTF-8 rejected')

changed=UTF_SAMPLE.replace('DL→ML','DL→XX',1).replace('\n','\r\n').encode('utf-8')
req(not strict_utf8_semantic_equal(changed,UTF_SAMPLE),'UTF-C4 content change must FAIL')
print('UTF-C4 PASS — actual content corruption rejected')

real_env=acceptance_utf8_env(os.environ)
real_env['PYTHONPATH']=str(ROOT)+(os.pathsep+real_env['PYTHONPATH'] if real_env.get('PYTHONPATH') else '')
real=subprocess.run([sys.executable,str(ROOT/'tests/cpcv_seed_confirmation_selftest.py')],cwd=ROOT,env=real_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
req(real.returncode==0,f'UTF-C real CPCV failed: {(real.stdout or b"")[-2000:]!r}')
req('DL→ML hybrid requires CPCV seed confirmation' in (real.stdout or b'').decode('utf-8',errors='strict'),'UTF-C real CPCV Unicode PASS text missing')
print('UTF-C REAL CPCV PASS — redirected DL→ML output preserved')

run_env=run_acceptance._acceptance_child_env()
req(run_env.get('PYTHONUTF8')=='1' and run_env.get('PYTHONIOENCODING')=='utf-8','UTF-E run_acceptance env')
bootstrap_env=_canonical_env({},canonical_python=Path(sys.executable),canonical_venv=Path(sys.prefix),bootstrap_python=sys.executable)
req(bootstrap_env.get('PYTHONUTF8')=='1' and bootstrap_env.get('PYTHONIOENCODING')=='utf-8','UTF-E bootstrap env')
nested_code=("import os,subprocess,sys\n" "assert os.environ.get('PYTHONUTF8')=='1'\n" "assert os.environ.get('PYTHONIOENCODING')=='utf-8'\n" f"code={UTF_CODE!r}\n" "cp=subprocess.run([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)\n" "sys.stdout.buffer.write(cp.stdout or b'')\n" "raise SystemExit(cp.returncode)\n")
with tempfile.TemporaryDirectory(prefix='max_mtf_utf8_nested_') as td:
    log_path=Path(td)/'nested_utf8.log'
    rc=_run_logged_stage([sys.executable,'-c',nested_code],log_path,timeout=20)
    req(rc==0 and strict_utf8_semantic_equal(log_path.read_bytes(),UTF_SAMPLE),'UTF-E nested semantic UTF-8 failed')
print('UTF-E PASS — Owner logged stage → canonical Python → test child propagation')

ascii_cp=subprocess.run([sys.executable,'-c',"print('ASCII PASS')"],cwd=ROOT,env=acceptance_utf8_env(os.environ),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
ab=ascii_cp.stdout or b''
at=ab.decode('ascii',errors='strict')
req(ascii_cp.returncode==0 and normalize_standard_newlines(at)=='ASCII PASS\n','UTF-G ASCII semantic output changed')
req(ab in (b'ASCII PASS\n',b'ASCII PASS\r\n'),'UTF-G unexpected newline bytes')
print('UTF-G PASS — ASCII output unchanged across native newline convention')

print('V201_RELEASE_PORTABILITY PASS')
