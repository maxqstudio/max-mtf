from __future__ import annotations
import copy, tempfile
from pathlib import Path
import acceptance.runners.owner_mtf1_runtime_acceptance as owner
from mtf1_closure_test_utils import write_valid_local_acceptance, valid_owner_runtime_payload

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent
REG=PKG/'governance/EXTERNAL_RUNTIME_GATES.json'


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def rejected(payload,acc,cfg):
    try:
        owner.verify_owner_evidence_payload(payload,acceptance_path=acc,config_path=cfg,registry_path=REG, require_live_mt5=False, require_closure_run_id=False)
    except owner.OwnerMTF1AcceptanceError:
        return True
    return False

with tempfile.TemporaryDirectory() as td:
    td=Path(td);acc=td/'acceptance.json';cfg=td/'config/config.json';cfg.parent.mkdir(parents=True,exist_ok=True)
    cfg.write_bytes((PKG/'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
    write_valid_local_acceptance(acc)
    full=valid_owner_runtime_payload(owner,acceptance_path=acc,config_path=cfg,registry_path=REG)
    owner.verify_owner_evidence_payload(full,acceptance_path=acc,config_path=cfg,registry_path=REG, require_live_mt5=False, require_closure_run_id=False)
    req(True,'complete substantive Owner MT5/parity proof accepted')

    minimal={
        'schema':owner.SCHEMA,'project':'Max MTF','version':'2.0.1','phase':owner.PHASE,
        'generated_utc':full['generated_utc'],'overall_status':'PASS','candidate_binding':copy.deepcopy(full['candidate_binding']),
        'gates':[
            {'gate':'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION','status':'PASS'},
            {'gate':'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY','status':'PASS'},
        ],
    }
    req(rejected(minimal,acc,cfg),'PASS labels plus valid binding without runtime proof rejected')

    for field in ('broker_provenance','native_rows','parity','alignment','data_quality','lineage_manifest_preview','bundle_identity_preview_sha256'):
        bad=copy.deepcopy(full);bad.pop(field,None)
        req(rejected(bad,acc,cfg),f'missing {field} proof rejected')

    bad=copy.deepcopy(full);bad['native_rows']['M5']=0
    req(rejected(bad,acc,cfg),'zero native M5 rows rejected')
    bad=copy.deepcopy(full);bad['parity']['status']='FAIL'
    req(rejected(bad,acc,cfg),'parity FAIL rejected')
    bad=copy.deepcopy(full);bad['alignment']['audit']['future_close_violations']['m5']=1
    bad['data_quality']['alignment']['future_close_violations']['m5']=1
    req(rejected(bad,acc,cfg),'causal alignment violation rejected')
    bad=copy.deepcopy(full);bad['data_quality']['status']='FAIL'
    req(rejected(bad,acc,cfg),'Data Quality FAIL rejected')
    bad=copy.deepcopy(full);bad['bundle_identity_preview_sha256']='0'*64
    req(rejected(bad,acc,cfg),'forged bundle identity rejected')
    bad=copy.deepcopy(full);bad['parity']['parity']['H1']['real_volume_failed_bars']=1
    req(rejected(bad,acc,cfg),'real-volume parity failure rejected')

print('V201_OWNER_EVIDENCE_PROOF_COMPLETENESS PASS')
