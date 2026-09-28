from __future__ import annotations
import json, tempfile
from pathlib import Path
import factory.factory_orchestrator as fo
def write_manifest(fd: Path, status: str):
    fd.mkdir(parents=True,exist_ok=True)
    (fd/'factory_manifest.json').write_text(json.dumps({'status':status,'research_mode':'MANUAL'}),encoding='utf-8')


def main():
    calls=[]
    old={k:getattr(fo,k) for k in ('run_discovery_pool','run_cpcv_qualification','run_tournament','run_monte_carlo','run_forward_championship')}
    try:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); oid='JOB_TEST'; fd=root/f'MANUAL_{oid}'
            def disc(*a,**kw):
                calls.append(('DISCOVERY',kw.get('llm_api_key'))); write_manifest(fd,'DISCOVERY_POOL_READY'); return {'status':'DISCOVERY_POOL_READY','manifest':{'status':'DISCOVERY_POOL_READY'}}
            def cpcv(*a,**kw): calls.append(('CPCV',kw.get('llm_api_key'))); write_manifest(fd,'CPCV_SURVIVORS_READY'); return {'status':'CPCV_SURVIVORS_READY'}
            def tourn(*a,**kw): calls.append(('TOURNAMENT',kw.get('llm_api_key'))); write_manifest(fd,'TOURNAMENT_SURVIVORS_READY'); return {'status':'TOURNAMENT_SURVIVORS_READY'}
            def mc(*a,**kw): calls.append(('MONTE_CARLO',kw.get('llm_api_key'))); write_manifest(fd,'MONTE_CARLO_SURVIVORS_READY'); return {'status':'MONTE_CARLO_SURVIVORS_READY'}
            def fwd(*a,**kw): calls.append(('FORWARD',kw.get('llm_api_key'))); write_manifest(fd,'FACTORY_WINNER'); return {'status':'FACTORY_WINNER','champion':{'pool_id':'C1'}}
            fo.run_discovery_pool=disc; fo.run_cpcv_qualification=cpcv; fo.run_tournament=tourn; fo.run_monte_carlo=mc; fo.run_forward_championship=fwd
            out=fo.run_manual_factory(root,'d.csv','c.json','2020','2021','2022','2023','2024','2025',orchestrator_id=oid)
            assert out['status']=='FACTORY_WINNER'
            assert [x[0] for x in calls]==['DISCOVERY','CPCV','TOURNAMENT','MONTE_CARLO','FORWARD']
            assert all(x[1] is None for x in calls),calls

        calls.clear()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); oid='JOB_FAIL'; fd=root/f'MANUAL_{oid}'
            def disc_fail(*a,**kw):
                calls.append(('DISCOVERY',kw.get('llm_api_key'))); write_manifest(fd,'MANUAL_WFA_NO_SURVIVOR'); return {'status':'MANUAL_WFA_NO_SURVIVOR','manifest':{'status':'MANUAL_WFA_NO_SURVIVOR','qualified_candidates':0}}
            fo.run_discovery_pool=disc_fail
            out=fo.run_manual_factory(root,'d.csv','c.json','2020','2021','2022','2023','2024','2025',orchestrator_id=oid)
            assert out['status']=='MANUAL_WFA_NO_SURVIVOR'
            assert calls==[('DISCOVERY',None)]
    finally:
        for k,v in old.items(): setattr(fo,k,v)
    print('MANUAL ORCHESTRATOR SELFTEST PASS')

if __name__=='__main__': main()
