from __future__ import annotations
import copy, hashlib, json, tempfile
from pathlib import Path
import acceptance.runners.run_acceptance as run_acceptance
import acceptance.runners.owner_mtf1_runtime_acceptance as owner
from mtf1_closure_test_utils import valid_local_acceptance_payload

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def rejected(payload, *, fresh=True):
    try:
        run_acceptance.validate_local_acceptance_report(payload, require_fresh_full=fresh)
    except Exception:
        return True
    return False

archived_real=ROOT/'evidence/history/build_repairs/V201_WINDOWS_UTF8_NEWLINE_PORTABILITY_SELFTEST.json'
current_real=ROOT/'evidence/current/V201_WINDOWS_UTF8_NEWLINE_PORTABILITY_SELFTEST.json'
req(not current_real.exists(),'sealed newline selftest evidence is absent from evidence/current')
req(archived_real.is_file() and hashlib.sha256(archived_real.read_bytes()).hexdigest()=='873a94216d0b505aae228ace0db4daf176b5849035e83265c15406130a778ddc','sealed newline selftest evidence preserved byte-identical in history/build_repairs')

valid=valid_local_acceptance_payload()
run_acceptance.validate_local_acceptance_report(valid,require_fresh_full=True)
req(True,f'complete exact ordered {len(run_acceptance.TESTS)}-gate PASS report accepted')

bad=copy.deepcopy(valid);bad['results']=[]
req(rejected(bad),'forged PASS header with empty results rejected')
bad=copy.deepcopy(valid);bad['results']=[{'gate':'FAKE','script':'fake.py','status':'FAIL','exit_code':1}]
req(rejected(bad),'forged PASS header with fake failed result rejected')
bad=copy.deepcopy(valid);bad['results'][0]['exit_code']=1
req(rejected(bad),'nonzero gate exit code rejected')
bad=copy.deepcopy(valid);bad['results'][0]['status']='FAIL'
req(rejected(bad),'non-PASS gate status rejected')
bad=copy.deepcopy(valid);bad['results'][0],bad['results'][1]=bad['results'][1],bad['results'][0]
req(rejected(bad),'gate order mismatch rejected')
bad=copy.deepcopy(valid);bad['results'][1]=copy.deepcopy(bad['results'][0])
req(rejected(bad),'duplicate gate result rejected')
bad=copy.deepcopy(valid);bad['execution_mode']='RESUMED_CHECKPOINT'
req(rejected(bad,fresh=True),'Owner closure rejects non-fresh local acceptance report')

# Default Owner preflight must consume the same canonical validator.
with tempfile.TemporaryDirectory() as td:
    td=Path(td); acc=td/'acceptance.json'; cfg=td/'config/config.json'; cfg.parent.mkdir(parents=True,exist_ok=True)
    cfg.write_bytes((PKG/'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
    forged=copy.deepcopy(valid);forged['results']=[]
    acc.write_text(json.dumps(forged,indent=2)+'\n',encoding='utf-8')
    try:
        owner._current_candidate_binding(acceptance_path=acc,config_path=cfg,registry_path=PKG/'governance/EXTERNAL_RUNTIME_GATES.json', require_closure_run_id=False)
        accepted=True
    except owner.OwnerMTF1AcceptanceError:
        accepted=False
    req(not accepted,'default Owner preflight rejects forged local PASS report')


# Current-evidence lifecycle contract: current report identity is mutable per fresh run,
# while source tree/suite/gate identity is fail-closed and historical repair evidence is immutable.
with tempfile.TemporaryDirectory() as td:
    td=Path(td); evidence_dir=td/'current'; history_dir=td/'history/build_repairs'
    evidence_dir.mkdir(parents=True); history_dir.mkdir(parents=True)
    report_path=evidence_dir/run_acceptance.CURRENT_ACCEPTANCE_REPORT_NAME
    candidate_path=evidence_dir/run_acceptance.CURRENT_CANDIDATE_CLAIM_NAME

    run_a=copy.deepcopy(valid)
    run_a['generated_utc']='2026-09-21T00:00:00+00:00'
    run_a['results'][0]['elapsed_seconds']=0.111
    report_path.write_text(json.dumps(run_a,indent=2)+'\n',encoding='utf-8')
    report_sha_a=hashlib.sha256(report_path.read_bytes()).hexdigest()
    local_a={
        'status':'PASS','gate_count':len(run_acceptance.TESTS),'result_count':len(run_acceptance.TESTS),
        'first_failed_gate':None,'execution_mode':'FRESH_FULL',
        'source_tree_signature':run_a['source_tree_signature'],'suite_signature':run_a['suite_signature'],
        'report':f'ModelLab/evidence/current/{run_acceptance.CURRENT_ACCEPTANCE_REPORT_NAME}',
        'report_sha256':report_sha_a,
    }
    candidate={
        'schema':'TEST','project':'Max MTF','version':'2.0.1','build_id':'TEST',
        'implementation_authority':{
            'current_version':'MAX MTF v2.0.1',
            'source_tree_signature':run_a['source_tree_signature'],
            'suite_signature':run_a['suite_signature'],
        },
        'local_acceptance':copy.deepcopy(local_a),
    }
    candidate_path.write_text(json.dumps(candidate,indent=2)+'\n',encoding='utf-8')

    historical_path=history_dir/'V201_BUILD_REPAIR_EXAMPLE.json'
    historical_payload={
        'schema':'HISTORICAL_BUILD_REPAIR','project':'Max MTF','version':'2.0.1',
        'local_acceptance':{'report_sha256':report_sha_a},
    }
    historical_path.write_text(json.dumps(historical_payload,indent=2)+'\n',encoding='utf-8')
    historical_bytes_a=historical_path.read_bytes()

    sync_a=run_acceptance.sync_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir)
    req(sync_a['status']=='PASS' and sync_a['report_sha256']==report_sha_a,'EVID-A fresh run A becomes current authority')

    run_b=copy.deepcopy(run_a)
    run_b['generated_utc']='2026-09-21T00:01:00+00:00'
    run_b['results'][0]['elapsed_seconds']=0.222
    report_path.write_text(json.dumps(run_b,indent=2)+'\n',encoding='utf-8')
    report_sha_b=hashlib.sha256(report_path.read_bytes()).hexdigest()
    req(report_sha_a!=report_sha_b,'EVID-A repeated fresh reports have distinct SHA identities')
    sync_b=run_acceptance.sync_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir)
    req(sync_b['status']=='PASS' and sync_b['report_sha256']==report_sha_b,'EVID-A fresh run B becomes current authority sequentially')
    req(historical_path.read_bytes()==historical_bytes_a,'EVID-B/G historical repair evidence remains byte-identical across current sync')
    current_candidate=json.loads(candidate_path.read_text(encoding='utf-8'))
    req((current_candidate.get('local_acceptance') or {}).get('report_sha256')==report_sha_b,'EVID-C stale candidate report SHA regenerated to current run B')

    stray=evidence_dir/'V201_STRAY_BUILD_REPAIR.json'
    stray.write_text(json.dumps({
        'schema':'BUILD_REPAIR','project':'Max MTF','version':'2.0.1',
        'local_acceptance':{'report_sha256':report_sha_a},
    },indent=2)+'\n',encoding='utf-8')
    try:
        run_acceptance.sync_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir)
        stray_rejected=False
    except Exception:
        stray_rejected=True
    req(stray_rejected,'EVID-D stray repair acceptance claim in evidence/current fails policy')
    stray.unlink()

    good_candidate=json.loads(candidate_path.read_text(encoding='utf-8'))
    bad_tree=copy.deepcopy(good_candidate)
    bad_tree['implementation_authority']['source_tree_signature']='4'*64
    candidate_path.write_text(json.dumps(bad_tree,indent=2)+'\n',encoding='utf-8')
    try:
        run_acceptance.sync_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir)
        tree_rejected=False
    except Exception:
        tree_rejected=True
    req(tree_rejected,'EVID-E candidate source tree mismatch remains fail-closed')

    bad_suite=copy.deepcopy(good_candidate)
    bad_suite['implementation_authority']['suite_signature']='5'*64
    candidate_path.write_text(json.dumps(bad_suite,indent=2)+'\n',encoding='utf-8')
    try:
        run_acceptance.sync_current_build_evidence(report_path=report_path,evidence_dir=evidence_dir)
        suite_rejected=False
    except Exception:
        suite_rejected=True
    req(suite_rejected,'EVID-F candidate suite mismatch remains fail-closed')

    candidate_path.write_text(json.dumps(good_candidate,indent=2)+'\n',encoding='utf-8')
    final=run_acceptance.validate_current_build_evidence(
        report_path=report_path,evidence_dir=evidence_dir,
        expected_tree=run_b['source_tree_signature'],expected_suite=run_b['suite_signature'],
        expected_gate_count=len(run_acceptance.TESTS),require_fresh_full=True)
    req(final['status']=='PASS' and final['claim_count']==1,'single canonical mutable current acceptance claim validates')

print('V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY PASS')
