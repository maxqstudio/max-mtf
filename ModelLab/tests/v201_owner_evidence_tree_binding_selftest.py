from __future__ import annotations
import copy, json, tempfile
from pathlib import Path
import acceptance.runners.owner_mtf1_runtime_acceptance as owner
from mtf1_closure_test_utils import write_valid_local_acceptance, valid_owner_runtime_payload

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def rejected(payload,acc,cfg):
    try:
        owner.verify_owner_evidence_payload(payload,acceptance_path=acc,config_path=cfg,registry_path=PKG/'governance/EXTERNAL_RUNTIME_GATES.json', require_live_mt5=False, require_closure_run_id=False)
    except owner.OwnerMTF1AcceptanceError:
        return True
    return False

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    acc=td/'acceptance.json';cfg=td/'owner_config.json'
    cfg.write_bytes((PKG/'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
    write_valid_local_acceptance(acc)
    binding=owner._current_candidate_binding(acceptance_path=acc,config_path=cfg,registry_path=PKG/'governance/EXTERNAL_RUNTIME_GATES.json', require_closure_run_id=False)
    for key in ('source_tree_signature','suite_signature','local_acceptance_sha256','external_registry_sha256','active_ea_relative_path','active_ea_sha256','active_ea_version','owner_config_sha256'):
        req(bool(binding.get(key)),'candidate binding contains '+key)

    payload=valid_owner_runtime_payload(owner,acceptance_path=acc,config_path=cfg,registry_path=PKG/'governance/EXTERNAL_RUNTIME_GATES.json')
    owner.verify_owner_evidence_payload(payload,acceptance_path=acc,config_path=cfg,registry_path=PKG/'governance/EXTERNAL_RUNTIME_GATES.json', require_live_mt5=False, require_closure_run_id=False)
    req(True,'exact candidate-bound Owner evidence accepted')

    stale=copy.deepcopy(payload);stale['candidate_binding']['source_tree_signature']='0'*64
    req(rejected(stale,acc,cfg),'PASS evidence from another source tree rejected')
    stale=copy.deepcopy(payload);stale['candidate_binding']['suite_signature']='1'*64
    req(rejected(stale,acc,cfg),'PASS evidence from another suite rejected')
    stale=copy.deepcopy(payload);stale['candidate_binding']['active_ea_sha256']='2'*64
    req(rejected(stale,acc,cfg),'PASS evidence with stale EA identity rejected')
    stale=copy.deepcopy(payload);stale['candidate_binding']['external_registry_sha256']='3'*64
    req(rejected(stale,acc,cfg),'PASS evidence with stale external registry rejected')

    cfg_obj=json.loads(cfg.read_text());cfg_obj['symbol']='XAUUSDm'
    cfg.write_text(json.dumps(cfg_obj,indent=2)+'\n',encoding='utf-8')
    req(rejected(payload,acc,cfg),'Owner config mutation invalidates old PASS evidence via config SHA')

print('V201_OWNER_EVIDENCE_TREE_BINDING PASS')
