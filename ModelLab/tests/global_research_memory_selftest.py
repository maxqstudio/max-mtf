from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from factory.champion_factory import _load_global_contract,_save_global_contract,_merge_learning_memory,_record_downstream_failure
import json

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    with TemporaryDirectory() as td:
        root=Path(td); h='abc123'
        gm,rec=_load_global_contract(root,h)
        rec['tested_experiment_fingerprints']=['fp_old']; rec['learning_memory']={'schema':'CP_RESEARCH_MEMORY_V1','elites':[],'failure_gate_counts':{'DD':2},'experiment_count':2,'qualified_pool_count':0}
        rec['factories']=['FACTORY_OLD']; _save_global_contract(root,gm,h,rec)
        gm2,rec2=_load_global_contract(root,h)
        req('fp_old' in rec2['tested_experiment_fingerprints'],'tested experiment fingerprints persist across Factory runs')
        req(rec2['factories']==['FACTORY_OLD'],'Factory lineage persists')
        merged=_merge_learning_memory(rec2['learning_memory'],{'schema':'CP_RESEARCH_MEMORY_V1','elites':[],'failure_gate_counts':{'PF':1},'experiment_count':1,'qualified_pool_count':0})
        req(merged['failure_gate_counts']['DD']==2 and merged['failure_gate_counts']['PF']==1,'scientific failure memory merges across Factories')
        fd=root/'FACTORY_X'; fd.mkdir(); (fd/'factory_manifest.json').write_text(json.dumps({'research_contract_hash':h}),encoding='utf-8')
        _record_downstream_failure(fd,'FORWARD_CHAMPIONSHIP',{'survivors':3,'passed':0})
        _,rec3=_load_global_contract(root,h)
        req(not (rec3.get('learning_memory') or {}).get('downstream_failures'),'downstream failure does not feed active Discovery memory')
        req((rec3.get('evaluation_vault') or {}).get('last_failure_stage')=='FORWARD_CHAMPIONSHIP','downstream failure is preserved in sealed evaluation vault')
    print('GLOBAL_RESEARCH_MEMORY_SELFTEST PASS')
if __name__=='__main__': main()
