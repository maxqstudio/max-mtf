from __future__ import annotations
import json, tempfile
from pathlib import Path

from models.models import CandidateSpec
from research.research_engine_v3 import (
    cheap_screen_spec, cheap_screen_cfg, gate_failure_margins,
    failure_topology, select_full_wfa_promotions, write_jsonl, read_jsonl,
)

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    f=CFG['agent']['fidelity_ladder']
    req(f['enabled'] is True and f['qualification_authority']=='FULL_WFA_ONLY','Fidelity ladder enabled; full WFA remains sole Discovery qualification authority')
    req(int(cheap_screen_cfg(CFG)['split']['walk_forward_folds']) < int(CFG['split']['walk_forward_folds']),'Cheap screen uses fewer chronological WFA folds than full authority')

    x=CandidateSpec('xgboost','x',{
        'n_estimators':1000,'max_depth':4,'learning_rate':.04,'min_child_weight':10,
        'subsample':.8,'colsample_bytree':.8,'training_memory_months':24})
    xs=cheap_screen_spec(x,CFG)
    req(xs.params['n_estimators'] < x.params['n_estimators'] and x.params['n_estimators']==1000,'Cheap screen reduces only disposable training resource; original CandidateSpec is unchanged')
    req(xs.params['max_depth']==x.params['max_depth'] and xs.params['training_memory_months']==24,'Cheap screen does not mutate scientific search dimensions')

    acc={'passed':False,'first_failed_gate':'CV_MEDIAN_MAX_DD','reasons':['CV_MEDIAN_MAX_DD','CV_MEDIAN_PF'],'gates':[
        {'name':'CV_MEDIAN_MAX_DD','passed':False,'actual':15.0,'threshold':12.0,'group':'survival','severity':'CRITICAL'},
        {'name':'CV_MEDIAN_PF','passed':False,'actual':1.20,'threshold':1.25,'group':'economic','severity':'MANDATORY'},
        {'name':'CV_MEDIAN_EXPECTANCY','passed':True,'actual':.11,'threshold':.10,'group':'economic','severity':'MANDATORY'},
    ]}
    m=gate_failure_margins(acc)
    by={g['gate']:g for g in m['gates']}
    req(by['CV_MEDIAN_MAX_DD']['relative_margin']<0 and by['CV_MEDIAN_PF']['relative_margin']<0,'Failure Margin direction is correct for lower- and higher-is-better gates')
    req(m['failed_gate_count']==2 and m['closest_failed_gate']['gate']=='CV_MEDIAN_PF','Failure Margin preserves hard failures and identifies closest miss diagnostically')

    rows=[]
    for i,(passed,gate,score) in enumerate([(False,'CV_MEDIAN_PF',10),(False,'CV_MEDIAN_PF',9),(False,'CV_MEDIAN_MAX_DD',8),(True,None,7)],1):
        a={'passed':passed,'first_failed_gate':gate,'reasons':[] if passed else [gate],'gates':[] if passed else [{'name':gate,'passed':False,'actual':1.0,'threshold':1.25 if gate=='CV_MEDIAN_PF' else 12.0,'group':'economic' if gate=='CV_MEDIAN_PF' else 'survival','severity':'MANDATORY'}]}
        rows.append({'name':f'm{i}','family':'xgboost','cv_gate_pass':passed,'cv_first_failed_gate':gate,'cv_gate_reasons':a['reasons'],'selection_score':score,'failure_margins':gate_failure_margins(a)})
    t=failure_topology(rows)
    req(t['candidate_count']==4 and t['passed_count']==1 and t['dominant_first_failed_gate']=='CV_MEDIAN_PF','Failure Topology reports deterministic WFA blocker distribution')

    screens=[]
    for i,score in enumerate([6,5,4,3,2,1],1):
        screens.append({'name':f's{i}__screen','original_name':f's{i}','cv_gate_pass':i==2,'selection_score':score})
    promote=select_full_wfa_promotions(screens,CFG)
    req(len(promote)==2 and 's2' in promote,'Fidelity promotion is bounded and prioritizes cheap-screen PASS without granting qualification')

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'all_trials.jsonl'; data=[{'schema':'X','trial_stage':'CHEAP_SCREEN','name':'a'},{'schema':'X','trial_stage':'FULL_WFA','name':'a'}]
        write_jsonl(p,data); got=read_jsonl(p)
        req(got==data,'All-trial ledger round-trips screen and full-WFA records')

    src=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('screen_board.append(sr)' in src and 'board.append(row)' in src and 'fidelity_stage":"FULL_WFA"' in src,'Supervisor separates cheap-screen evidence from authoritative full-WFA leaderboard')
    req('all_trials.jsonl' in src and 'failure_topology.json' in src and 'screen_failure_topology.json' in src,'Supervisor persists all-trial ledger and separate failure topologies')
    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('_merge_factory_trial_ledger' in cf and 'FACTORY_FULL_WFA' in cf,'Factory aggregates trial history and full-WFA Failure Topology across generations')
    print('RESEARCH ENGINE V3 R2 SELFTEST PASS')

if __name__=='__main__': main()
