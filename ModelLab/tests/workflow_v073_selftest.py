from __future__ import annotations
import json, tempfile
from pathlib import Path
from copy import deepcopy
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(c,m):
    if not c: raise AssertionError(m)
    print('PASS ',m)

def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    discovery_src=src[src.index('def run_discovery_pool'):src.index('def _fit_candidate')]
    req('candidate_cpcv(' not in discovery_src,'Discovery generation no longer executes CPCV')
    req('\"cpcv_status\":\"WAITING\"' in discovery_src and 'POOL_COMMITTED' in discovery_src,'WFA-qualified pool is the Discovery terminal authority with explicit CPCV WAITING state')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    cblock=app[app.index('def _render_cpcv_stage'):app.index('def _render_tournament_stage')]
    tblock=app[app.index('def _render_tournament_stage'):app.index('def _render_monte_carlo_stage')]
    req('_start_factory_stage_job' not in cblock and 'RUN CPCV FINALISTS' not in cblock,'CPCV page is evidence-only; no duplicate workflow authority')
    req('_start_factory_stage_job' not in tblock,'Tournament page is evidence-only; no duplicate workflow authority')
    cpcv_backend=src[src.index('def run_cpcv_qualification'):src.index('def run_tournament')]
    tournament_backend=src[src.index('def run_tournament'):src.index('def run_monte_carlo')]
    req('DISCOVERY_POOL_READY' in cpcv_backend and 'frozen WFA-qualified Discovery pool' in cpcv_backend,'CPCV backend opens only from frozen WFA pool')
    req('CPCV_SURVIVORS_READY' in tournament_backend,'Tournament backend opens only after CPCV survivors')
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/'F'; fd.mkdir()
        cfg=deepcopy(CFG); cfg['champion_factory']['cpcv_stage'].update({'target_survivors':2,'minimum_survivors_to_tournament':1,'finalist_batch_size':2,'max_finalists':4})
        cp=Path(td)/'cfg.json'; cp.write_text(json.dumps(cfg),encoding='utf-8')
        pool=[]
        for i,score in enumerate([9,8,7,6],1):
            pool.append({'pool_id':f'CAND_{i:02d}','family':'xgboost','name':f'm{i}','params':{},'fingerprint':f'f{i}','spec_fingerprint':f's{i}','trained_candidate_id':f't{i}','training_seed':42,'take_threshold':0.65,'research_overrides':{},'discovery_metrics':{'selection_score':score},'discovery_acceptance':{'passed':True},'wfa_evidence':{'cv_gate_pass':True}})
        (fd/'candidate_pool.json').write_text(json.dumps(pool),encoding='utf-8')
        (fd/'discovery_immutable.csv').write_text('dummy\n1\n',encoding='utf-8')
        dcontract={'schema':'TEST_DISCOVERY','scientific_contract':cf._critical_scientific_contract(cfg)}
        manifest={'status':'DISCOVERY_POOL_READY','cpcv_opened':False,'discovery_stage_contract':dcontract}
        (fd/'factory_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        seal=cf._stage_seal(fd,'DISCOVERY',contract=dcontract,files=['candidate_pool.json','discovery_immutable.csv'])
        manifest['discovery_terminal_seal']='discovery_terminal_seal.json'; manifest['discovery_terminal_seal_hash']=seal['seal_hash']
        (fd/'factory_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        old_read,old_build,old_cpcv,old_wfa=cf.read_csv_auto,cf.build_labels,cf.candidate_cpcv,cf.walk_forward_acceptance
        calls=[]
        try:
            cf.read_csv_auto=lambda *a,**k: __import__('pandas').DataFrame({'dummy':[1]})
            cf.build_labels=lambda df,cfg: df
            cf.walk_forward_acceptance=lambda *a,**k: {'passed':True}
            def fake(spec,df,cfg,threshold,progress=None,decision_policy=None):
                calls.append(spec.name); return {'schema':'X','passed':True,'first_failed_gate':None,'reasons':[],'summary':{'median_profit_factor':1.5,'worst_expectancy_r':0.2,'worst_max_drawdown_r':2.0,'worst_recovery_factor':2.0},'combinations':15,'groups':6,'test_groups':2,'purge_bars':24,'embargo_bars':24,'gates':{},'methodology_audit':{}}
            cf.candidate_cpcv=fake
            r=cf.run_cpcv_qualification(fd,cp)
        finally:
            cf.read_csv_auto,cf.build_labels,cf.candidate_cpcv,cf.walk_forward_acceptance=old_read,old_build,old_cpcv,old_wfa
        req(r['status']=='CPCV_SURVIVORS_READY' and r['survivors']==2,'CPCV produces separate survivor authority')
        req(calls==['m1','m2'],'Progressive CPCV stops when survivor target is reached')
        ev=json.loads((fd/'cpcv_qualification_evidence.json').read_text())
        req(ev['candidates_evaluated']==2,'Only finalists consumed CPCV compute')
        req(json.loads((fd/'factory_manifest.json').read_text())['next_required']=='RUN_TOURNAMENT','Tournament opens only after CPCV survivor stage')
    print('WORKFLOW V0.7.3 SELFTEST PASS')
if __name__=='__main__': main()
