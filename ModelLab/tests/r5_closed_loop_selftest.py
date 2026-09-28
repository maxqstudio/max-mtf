from __future__ import annotations
import json, tempfile
from pathlib import Path

import factory.champion_factory as cf
from models.model_lab import load_cfg
from models.model_registry import enabled_families, family_registry, get_bounds
from models.models import CandidateSpec, random_candidate, trained_candidate_id
from research.scientific_hypotheses import validate_hypothesis, apply_policy_agenda
from research.experiment_blocks import compile_experiment_block, apply_block_to_spec, normalize_hypothesis

ROOT=Path(__file__).resolve().parents[1]

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)

def _hybrid_anchor(fam='hybrid_gru_lightgbm'):
    b=get_bounds()[fam]
    p={}
    for k,(lo,hi,typ) in b.items():
        if k in {'policy_reg_alpha','reg_alpha'}: v=0.0
        elif k in {'policy_reg_lambda','reg_lambda'}: v=1.0
        else: v=(lo+hi)/2
        p[k]=int(round(v)) if typ is int else float(v)
    return CandidateSpec(fam,'anchor',p)

def main():
    cfg=load_cfg(ROOT/'config/config.json')
    fams=enabled_families(cfg)
    req(set(fams)=={'hybrid_gru_lightgbm','hybrid_gru_xgboost'},'default research active only GRU→LightGBM / GRU→XGBoost')
    reg=family_registry()
    req('random_forest' in reg and 'hybrid_gru_random_forest' in reg,'Random Forest families retained as reserve')
    req(not cfg['models']['random_forest'] and not cfg['models']['hybrid_random_forest'],'Random Forest reserve dormant by default')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('params.get("gru_sequence_length","—")' in app and 'params.get("policy_n_estimators","—")' in app,'Scientist hybrid proposal renderer uses family-aware GRU/policy keys')
    req('params.get("policy_reg_alpha","—")' in app and 'params.get("policy_reg_lambda","—")' in app,'Scientist renderer exposes policy regularization')
    req('@st.fragment(run_every="2s", key="contextual_lifecycle")\ndef _render_contextual_lifecycle_controls' in app and '@st.fragment(run_every="2s")\ndef _render_research_live_summary' in app,'Research/contextual lifecycle UI heartbeat is 2s')
    req('cpcv_live_split_results.json' in app,'CPCV UI consumes live completed-split evidence')
    req('COMMITTED POOL' in app and 'UNIQUE PENDING ELIGIBLE' in app and 'PROJECTED POOL' in app,'Research/Discovery UI explains committed vs pending vs projected Pool')
    ssrc=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8'); wsrc=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')
    req('projection_authority="EXACT_UNIQUE_FULL_WFA_PASS_AT_SAFE_ROUND_BOUNDARY"' in ssrc and 'pending_eligible=pending_eligible' in ssrc,'Supervisor emits exact deduplicated Pool projection at safe round boundaries')
    req('feature_contract=CONTRACT_ID' in ssrc and 'feature_count=len(FEATURES)' in ssrc and 'research_contract_hash=str(ac.get("research_contract_hash") or "")' in ssrc,'Supervisor calls keyword-only LLM dataset-header contract correctly')
    req('job["pending_pool_eligible"]' in wsrc and 'job["projected_pool"]' in wsrc and 'job["pool_projection_authority"]' in wsrc,'worker persists Pool projection telemetry across UI reruns')

    # Exact dataset revision is part of the research contract, not a global blacklist.
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); snap=td/'snap.csv'; snap.write_text('signal_time,symbol,period\n2026-01-01,X,60\n',encoding='utf-8')
        ident={'symbol':'X','period':60}
        h1,p1=cf._research_contract(snap,cfg,ident,'MASTER_A')
        h2,p2=cf._research_contract(snap,cfg,ident,'MASTER_B')
        req(h1!=h2 and p1['source_master_sha256']=='MASTER_A','research contract changes with source master dataset revision')

        fd=td/'FACTORY'; fd.mkdir(); (fd/'discovery_immutable.csv').write_text('signal_time,symbol,period,f1,f2\n',encoding='utf-8')
        (fd/'factory_manifest.json').write_text(json.dumps({'research_contract_hash':h1,'status':'CPCV_NO_SURVIVOR','stage':'CPCV'}),encoding='utf-8')
        hdr=cf._llm_header_context(fd,h1)
        req('columns' in hdr and 'rows' not in hdr and 'sample_rows' not in hdr,'LLM dataset context is header/schema only')

    # Model-architecture failure learning must compile to actual constrained knobs.
    h=validate_hypothesis({'kind':'MODEL_ARCHITECTURE','title':'bounded survival regularization','payload':{
        'family_priorities':{'hybrid_gru_lightgbm':1.5},
        'parameter_ranges_by_family':{'hybrid_gru_lightgbm':{'policy_reg_alpha':[2.0,6.0],'policy_reg_lambda':[4.0,12.0],'policy_max_depth':[3,5]}}
    }},cfg)
    req(h is not None and h['executable'] and h['payload'].get('parameter_ranges_by_family'),'Scientist architecture hypothesis validates bounded parameter ranges')
    anchor=_hybrid_anchor(); block=compile_experiment_block(h,anchor,cfg,generation=2,block_no=1,budget=6)
    import random
    spec=random_candidate(cfg,'hybrid_gru_lightgbm',random.Random(123),'random')
    out=apply_block_to_spec(spec,block,cfg,1)
    req(2.0<=out.params['policy_reg_alpha']<=6.0 and 4.0<=out.params['policy_reg_lambda']<=12.0 and 3<=out.params['policy_max_depth']<=5,'Experiment Block remaps variables inside Scientist-declared ranges')
    req(out.params['gru_sequence_length']==anchor.params['gru_sequence_length'],'Experiment Block freezes unrelated knobs to anchor')

    hm=validate_hypothesis({'kind':'TRAINING_MEMORY','title':'recent windows','payload':{'months':[12,18,24]}},cfg)
    bm=compile_experiment_block(hm,anchor,cfg,generation=2,block_no=2,budget=6)
    vals=[apply_block_to_spec(spec,bm,cfg,i).params['training_memory_months'] for i in range(1,4)]
    req(vals==[12,18,24],'Training-memory hypothesis enforces declared windows')
    hs=normalize_hypothesis(dict(h,source='STAGE_SCIENTIST'),'RESEARCH_MEMORY',2)
    req(hs['source']=='STAGE_SCIENTIST','Stage Scientist provenance survives Research Memory rehydration')

    hp=validate_hypothesis({'kind':'SELECTIVITY_POLICY','payload':{'take_thresholds':[0.57,0.63]}},cfg)
    pcfg=apply_policy_agenda(cfg,[hp])
    req(0.57 in pcfg['deployment']['take_threshold_grid'],'Selectivity hypothesis reaches actual Full-WFA deployment threshold grid')

    # Different seed/selected threshold = different fitted-candidate identity.
    a=_hybrid_anchor('hybrid_gru_xgboost')
    c1=json.loads(json.dumps(cfg)); c2=json.loads(json.dumps(cfg)); c2['seed']=int(c1.get('seed',42))+1
    id1=trained_candidate_id(a,c1,.65,'C'); id2=trained_candidate_id(a,c2,.65,'C'); id3=trained_candidate_id(a,c1,.70,'C')
    req(len({id1,id2,id3})==3,'trained candidate identity includes seed and resolved threshold')

    # LightGBM subsampling must not be a no-op and regularizers must exist in registry.
    msrc=(ROOT/'models/models.py').read_text(encoding='utf-8'); hsrc=(ROOT/'research/hybrid_research.py').read_text(encoding='utf-8')
    req('p.setdefault("subsample_freq",1)' in msrc and 'subsample_freq=1 if subsample < 0.999999 else 0' in hsrc,'LightGBM row subsampling activates bagging frequency')
    req('policy_reg_alpha' in get_bounds()['hybrid_gru_lightgbm'] and 'policy_reg_lambda' in get_bounds()['hybrid_gru_xgboost'],'hybrid policy regularization is an executable search dimension')

    limits=cfg['champion_factory']['research_feedback']['max_exposures']
    req(all(int(limits.get(k,0))>0 for k in ('POOL','CPCV','TOURNAMENT','MONTE_CARLO')),'closed-loop failure learning has bounded per-stage exposure budgets')

    good={'next_discovery_plan':{'objective':'reduce tail risk','change':['stronger policy regularization'],'falsification':'no WFA lower-tail improvement'},'hypotheses':[h]}
    bad={'next_discovery_plan':{'objective':'reduce tail risk','change':['something'],'falsification':'no improvement'},'hypotheses':[{'kind':'REGIME_POLICY','executable':True,'payload':{'regime_modes':['TREND']}}]}
    req(cf._actionable_learning(good)[0] is True,'failure loop accepts a truly wired executable learning plan')
    req(cf._actionable_learning(bad)[0] is False,'failure loop rejects merely-labelled executable hypotheses that do not drive next Discovery')

    # API failure must pause learning without consuming the exact-contract exposure;
    # a later Scientist-only retry may commit the lesson without reopening CPCV.
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); root=td/'factory_runs'; root.mkdir(); fd=root/'F1'; fd.mkdir()
        contract='CONTRACT_X'
        (fd/'factory_manifest.json').write_text(json.dumps({'research_contract_hash':contract,'status':'CPCV_NO_SURVIVOR','stage':'CPCV'}),encoding='utf-8')
        (fd/'discovery_immutable.csv').write_text('signal_time,symbol,period,f1\n',encoding='utf-8')
        (fd/'cpcv_qualification_evidence.json').write_text(json.dumps({'rows':[{'pool_id':'P1','passed':False,'first_failed_gate':'CPCV_WORST_DD'}]}),encoding='utf-8')
        (fd/'cpcv_failure_topology.json').write_text(json.dumps({'candidate_rows':[{'pool_id':'P1','status':'FAIL'}],'all_failed_gate_counts':{'CPCV_WORST_DD':1},'dominant_failure_group':'survival'}),encoding='utf-8')
        tcfg=json.loads(json.dumps(cfg)); tcfg['agent']['llm']['enabled']=True; tcfg['agent']['llm']['model']='fake'
        cfgp=td/'cfg.json'; cfgp.write_text(json.dumps(tcfg),encoding='utf-8')
        # Stage-8 hardening requires Scientist retry to consume sealed, exact-contract
        # terminal failure evidence. Build the fixture with the same authority instead
        # of bypassing the CPCV terminal contract.
        ccontract={'schema':'TEST_CPCV_STAGE_CONTRACT_V1','scientific_contract':cf._critical_scientific_contract(tcfg)}
        cseal=cf._stage_seal(fd,'CPCV',contract=ccontract,files=['cpcv_qualification_evidence.json','cpcv_failure_topology.json'])
        fm=json.loads((fd/'factory_manifest.json').read_text(encoding='utf-8'))
        fm['cpcv']={'stage_contract':ccontract,'terminal_seal_hash':cseal['seal_hash']}
        (fd/'factory_manifest.json').write_text(json.dumps(fm),encoding='utf-8')
        class FailSci:
            def __init__(self,*a,**k): self.ready=True
            def stage_review(self,*a,**k): raise RuntimeError('fake api down')
        class GoodSci:
            def __init__(self,*a,**k): self.ready=True
            def stage_review(self,*a,**k):
                return {'summary':'post mortem','report':{},'strategy':{},'stop_research':False,
                        'next_discovery_plan':{'objective':'reduce tail survival failure','change':['regularize policy'],'falsification':'lower-tail WFA does not improve'},
                        'hypotheses':[h]}
        original=cf.LLMScientist
        try:
            cf.LLMScientist=FailSci
            e1=cf._stage_scientist_and_feedback(fd,tcfg,'CPCV','CPCV_NO_SURVIVOR',json.loads((fd/'cpcv_failure_topology.json').read_text()),[],learning_allowed=True)
            req(not e1['learning_ready'] and e1['feedback_exposure']==0,'Scientist API failure does not consume feedback exposure')
            before=(fd/'cpcv_qualification_evidence.json').read_text()
            cf.LLMScientist=GoodSci
            rr=cf.retry_failure_scientist_learning(fd,cfgp)
            after=(fd/'cpcv_qualification_evidence.json').read_text()
            req(rr['learning_ready'] and rr['scientist']['feedback_exposure']==1,'Scientist-only retry commits actionable failure learning')
            req(before==after,'Scientist retry does not reopen or mutate committed CPCV evidence')
        finally:
            cf.LLMScientist=original

    csrc=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('cpcv_live_split_results.json' in csrc and 'phase") or "")=="split_done"' in csrc,'CPCV worker commits live per-split telemetry')
    req('row={**_candidate_identity(c)' in csrc and '_write(fd/"cpcv_survivors.json",survivors)' in csrc and '_write(fd/"candidate_pool.json",pool)' not in csrc[csrc.index('def run_cpcv_qualification'):csrc.index('def run_tournament')],
        'CPCV PASS/FAIL persists in separate qualification/survivor evidence while frozen Discovery Pool remains immutable')
    print('R5_CLOSED_LOOP_SELFTEST PASS')

if __name__=='__main__': main()
