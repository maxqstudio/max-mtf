from __future__ import annotations
import json, tempfile
from pathlib import Path

from models.model_lab import load_cfg
from research.research_memory import build_research_memory, seed_candidates_from_memory
from research.scientific_hypotheses import validate_hypothesis, apply_policy_agenda
from scientist.core.scientist import LLMScientist
from data.feature_label_audit import _merge_scientist_guided_hypotheses


def write(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,indent=2),encoding='utf-8')


def main():
    cfg=load_cfg('config.json')
    # This legacy memory test intentionally exercises standalone XGB/LGBM paths.
    # R5 production defaults keep them disabled, so enable them only inside the test.
    cfg['models']['xgboost']=True; cfg['models']['lightgbm']=True
    with tempfile.TemporaryDirectory() as td:
        runs=Path(td)/'runs'; runs.mkdir()
        agent=runs/'AGENT_PARENT'; agent.mkdir()
        write(agent/'model_manifest.json',{'run_id':'AGENT_PARENT','run_type':'SUPERVISOR_AGENT','research_source_csv_sha256':'abc123'})
        write(agent/'run_config.json',cfg)
        xgb_params={
          'n_estimators':300,'max_depth':4,'learning_rate':0.05,'min_child_weight':3.0,
          'subsample':0.8,'colsample_bytree':0.8,'training_memory_months':18}
        lgb_params={
          'n_estimators':400,'learning_rate':0.04,'num_leaves':31,'max_depth':6,'min_child_samples':30,
          'subsample':0.8,'colsample_bytree':0.8,'training_memory_months':18}
        write(agent/'cv_leaderboard.json',[
          {'name':'elite_xgb','family':'xgboost','params':xgb_params,'cv_gate_pass':True,'selection_score':72.0,'cv_first_failed_gate':None,'total_validation_trades':220,'median_profit_factor':2.0,'median_expectancy_r':0.3,'worst_expectancy_r':0.12,'worst_fold_max_drawdown_r':8.0},
          {'name':'almost_lgb','family':'lightgbm','params':lgb_params,'cv_gate_pass':False,'selection_score':50.0,'cv_first_failed_gate':'CV_MIN_TRADES','total_validation_trades':73,'median_profit_factor':2.8,'median_expectancy_r':0.5,'worst_expectancy_r':0.2,'worst_fold_max_drawdown_r':7.0},
        ])
        agenda=[
          validate_hypothesis({'kind':'LABEL_GEOMETRY','title':'edge separation','rationale':'test plateau','expected_observation':'worst fold improves','payload':{'min_edge_r':0.20}},cfg),
          validate_hypothesis({'kind':'TRAINING_MEMORY','title':'recent memory','rationale':'history dilutes edge','expected_observation':'better stability','payload':{'months':[12,18,24]}},cfg),
          validate_hypothesis({'kind':'OBJECTIVE_RESEARCH','title':'conditional utility objective','rationale':'separate opportunity from direction','payload':{'idea':'two-head utility objective'}},cfg),
        ]
        write(agent/'scientific_agenda.json',agenda)
        audit=runs/'AUDIT_CHILD'; audit.mkdir(); write(audit/'model_manifest.json',{'run_id':'AUDIT_CHILD','source_run_id':'AGENT_PARENT','model_source_run_id':'AGENT_PARENT'})
        guided=runs/'GUIDED_CHILD'; guided.mkdir(); write(guided/'model_manifest.json',{'run_id':'GUIDED_CHILD','source_run_id':'AUDIT_CHILD','audit_run_id':'AUDIT_CHILD','model_source_run_id':'AGENT_PARENT'})
        write(guided/'guided_leaderboard.json',[{'name':'LABEL · min_edge_r_0.20','cv_gate_pass':True,'selection_score':80.0,'label':dict(cfg['label'],min_edge_r=0.20),'zero_features':[]}])
        rec=json.loads(json.dumps(cfg)); rec['label']['min_edge_r']=0.20
        memory=build_research_memory(guided,runs,rec)
        assert memory['contract_changed'] is True
        assert memory['elites'][0]['family']=='xgboost'
        assert memory['failure_gate_counts']['CV_MIN_TRADES']==1
        assert any(h['kind']=='LABEL_GEOMETRY' for h in memory['scientist_agenda'])
        seeds=seed_candidates_from_memory(memory,rec,2)
        assert seeds and seeds[0].family=='xgboost'
        assert seeds[0].params['training_memory_months']==18

        policy=apply_policy_agenda(cfg,[
            validate_hypothesis({'kind':'SELECTIVITY_POLICY','payload':{'take_thresholds':[0.57,0.62,0.77]}},cfg),
            validate_hypothesis({'kind':'REGIME_POLICY','payload':{'regime_modes':['TREND','RANGE','NON_SHOCK']}},cfg),
        ])
        assert 0.57 in policy['agent']['policy_discovery']['take_threshold_grid']
        assert 'NON_SHOCK' in policy['agent']['policy_discovery']['regime_modes']

        modelrun=Path(td)/'modelrun'; modelrun.mkdir(); write(modelrun/'scientific_agenda.json',agenda)
        merged, accepted=_merge_scientist_guided_hypotheses(modelrun,cfg,[{'name':'BASELINE FROZEN','label':cfg['label'],'zero_features':[]}])
        assert len(merged)>=2 and any('SCIENTIST LABEL' in h['name'] for h in merged)
        assert any(h['kind']=='LABEL_GEOMETRY' for h in accepted)

        fake={
          'summary':'Edge tampak conditional; uji memory dan label separation.',
          'report':{'condition':'trade coverage tinggi mengencerkan edge','interpretation':'opportunity sparse','next_action':'uji recent memory dan edge plateau','confidence':0.82},
          'stop_research':False,
          'strategy':{'exploration_ratio':0.4,'family_priorities':{'xgboost':1.4}},
          'proposals':[],
          'hypotheses':[
            {'kind':'TRAINING_MEMORY','title':'recent-memory frontier','rationale':'long history dilutes edge','expected_observation':'worst fold improves','payload':{'months':[12,18,24]}},
            {'kind':'OBJECTIVE_RESEARCH','title':'opportunity utility head','rationale':'direction alone is insufficient','expected_observation':'better abstention','payload':{'idea':'joint direction + utility head'}},
          ]}
        class FakeScientist(LLMScientist):
            def _call(self,messages): return json.dumps(fake)
        sci=FakeScientist({'base_url':'http://local/v1/','model':'fake','provider':'custom'})
        out=sci.propose({'budget_remaining':6,'round':2,'dataset':{},'top_results':[],'family_stats':{},'research_memory':memory},cfg,max_n=0)
        assert len(out['hypotheses'])==2
        assert out['strategy']['preferred_training_memory_months']==[12,18,24]
        assert out['hypotheses'][1]['executable'] is False
    print('LEARNING_MEMORY_SELFTEST PASS')

if __name__=='__main__': main()
