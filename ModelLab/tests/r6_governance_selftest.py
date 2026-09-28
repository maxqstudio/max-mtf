from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from research.cpcv import canonical_cpcv_pairings, cpcv_worst_expectancy_pass
from research.evaluation import metrics_from_trades
from research.experiment_blocks import compile_experiment_block, evaluate_block, resolve_decisive_hypotheses
from models.models import CandidateSpec
import scientist.core.scientist as scientist_module
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


# Owner lock: WFA/CV and CPCV share the same zero-floor Worst R authority.
req(abs(float(CFG['acceptance']['cpcv_min_worst_expectancy_r']))<1e-15,'CPCV Worst R authority = 0.00R')
req(abs(float(CFG['acceptance']['cv_min_worst_expectancy_r']))<1e-15,'WFA worst-fold expectancy authority = 0.00R')
req(cpcv_worst_expectancy_pass(0.0,CFG),'CPCV exact 0.00R passes')
req(cpcv_worst_expectancy_pass(0.01,CFG),'CPCV positive Worst R passes')
req(not cpcv_worst_expectancy_pass(-0.03,CFG),'CPCV -0.03R fails under zero floor')
req(cpcv_worst_expectancy_pass(-0.0000000005,CFG),'CPCV floating noise inside epsilon passes deterministically')
req(not cpcv_worst_expectancy_pass(-0.00001,CFG),'CPCV clear breach below zero fails')

# N=6,k=2 canonical reconstruction = 5 chronology-covering paths from 15 unique split pairs.
pairings=canonical_cpcv_pairings(6,2)
req(len(pairings)==5,'CPCV N=6,k=2 reconstructs 5 canonical paths')
flat=[tuple(p) for path in pairings for p in path]
req(len(flat)==15 and len(set(flat))==15,'all 15 stress split pairs are consumed exactly once in canonical reconstruction')
for i,path in enumerate(pairings,1):
    covered=sorted(g for pair in path for g in pair)
    req(covered==list(range(6)),f'canonical path {i} covers each chronological group exactly once')

# Deterministic risk-adjusted metrics: seven Owner-approved metrics are mandatory gates where stage semantics are valid.
trades=np.array([1.0,0.8,-0.5,1.2,-0.2,0.6,-0.4,1.1,0.3,-0.1],dtype=float)
ts=pd.date_range('2024-01-01',periods=len(trades),freq='30D')
m=metrics_from_trades(trades,n_rows=len(trades),timestamps=ts,multiple_testing_trials=216)
for k in ('sharpe_ratio','sortino_ratio','calmar_mar_ratio','probabilistic_sharpe_ratio','deflated_sharpe_ratio','ulcer_index_r','cvar95_r','daily_cvar95_r'):
    req(k in m and m[k] is not None and np.isfinite(float(m[k])),f'{k} deterministic metric available')
req(0.0<=m['probabilistic_sharpe_ratio']<=1.0,'PSR is a probability')
req(0.0<=m['deflated_sharpe_ratio']<=1.0,'DSR is a probability')
req(m['deflated_sharpe_ratio']<=m['probabilistic_sharpe_ratio'],'DSR deflates PSR under multiple testing')
req(abs(float(m['cvar95_r'])-(-0.5))<1e-12,'legacy per-trade CVaR diagnostic is deterministic')
req(m['daily_cvar95_r'] is not None,'daily aggregated CVaR gate metric is emitted')

# CPCV-origin hypothesis: WFA is only a proxy and cannot mark it SUPPORTED.
h={
    'hypothesis_id':'H_CPCV_1','kind':'MODEL_ARCHITECTURE','title':'CPCV lower-tail repair','payload':{},
    'status':'PROPOSED','source_stage':'CPCV','source_factory':'FACTORY_OLD','source_status':'CPCV_NO_SURVIVOR',
    'source_failure_topology':{'dominant_first_failed_gate':'CPCV_WORST_EXPECTANCY'},'executable':True,
}
anchor=CandidateSpec('xgboost','anchor',{'n_estimators':300,'max_depth':4,'learning_rate':0.05,'min_child_weight':5.0,'subsample':0.8,'colsample_bytree':0.8,'reg_alpha':1.0,'reg_lambda':2.0})
block=compile_experiment_block(h,anchor,CFG,generation=2,block_no=1,budget=2)
wfa_rows=[{'experiment_block_id':block['block_id'],'cv_gate_pass':True,'failure_margins':{}}]
out=evaluate_block(block,wfa_rows,CFG)
req(out['status']=='AWAITING_CPCV' and out['proxy_status']=='SUPPORTED','CPCV hypothesis remains pending after WFA proxy success')

life=[deepcopy(h)]; life[0]['status']='AWAITING_CPCV'
fail_row={'hypothesis_id':'H_CPCV_1','passed':False,'evidence':{'gates':{'CPCV_WORST_EXPECTANCY':False}}}
resolved,dec=resolve_decisive_hypotheses(life,[fail_row],'CPCV','CPCV_NO_SURVIVOR')
req(resolved[0]['status']=='FALSIFIED','CPCV persistent originating failure falsifies hypothesis')
life2=[deepcopy(h)]; life2[0]['status']='AWAITING_CPCV'
partial_row={'hypothesis_id':'H_CPCV_1','passed':False,'evidence':{'gates':{'CPCV_WORST_EXPECTANCY':True,'CPCV_WORST_DD':False}}}
resolved2,_=resolve_decisive_hypotheses(life2,[partial_row],'CPCV','CPCV_NO_SURVIVOR')
req(resolved2[0]['status']=='PARTIALLY_SUPPORTED','originating CPCV gate can be cleared without falsely claiming full stage support')
life3=[deepcopy(h)]; life3[0]['status']='AWAITING_CPCV'
pass_row={'hypothesis_id':'H_CPCV_1','passed':True,'evidence':{'gates':{'CPCV_WORST_EXPECTANCY':True}}}
resolved3,_=resolve_decisive_hypotheses(life3,[pass_row],'CPCV','CPCV_SURVIVORS_READY')
req(resolved3[0]['status']=='SUPPORTED','matching CPCV PASS provides decisive support')


# Tournament/Monte-Carlo use acceptance.gates rather than CPCV evidence.gates and must
# therefore close against their own decisive authority as well.
for stage,awaiting,target,terminal in [
    ('TOURNAMENT','AWAITING_TOURNAMENT','MIN_EXPECTANCY','TOURNAMENT_NO_SURVIVOR'),
    ('MONTE_CARLO','AWAITING_MONTE_CARLO','MIN_PF','MONTE_CARLO_NO_SURVIVOR'),
]:
    hh=deepcopy(h); hh['hypothesis_id']=f'H_{stage}'; hh['status']=awaiting; hh['source_stage']=stage
    hh['source_failure_topology']={'dominant_first_failed_gate':target}
    fail={'hypothesis_id':hh['hypothesis_id'],'acceptance':{'passed':False,'gates':{target:False},'first_failed_gate':target,'reasons':[target]}}
    rr,_=resolve_decisive_hypotheses([hh],[fail],stage,terminal)
    req(rr[0]['status']=='FALSIFIED',f'{stage} originating failure is decisively falsified from acceptance gates')
    hh2=deepcopy(hh)
    partial={'hypothesis_id':hh2['hypothesis_id'],'acceptance':{'passed':False,'gates':{target:True,'OTHER_GATE':False},'first_failed_gate':'OTHER_GATE','reasons':['OTHER_GATE']}}
    rr2,_=resolve_decisive_hypotheses([hh2],[partial],stage,terminal)
    req(rr2[0]['status']=='PARTIALLY_SUPPORTED',f'{stage} can clear originating gate without false full support')

# Scientist observation must be deterministic even if the LLM tries to assert a causal guess as observation.
class FakeScientist:
    def _with_provenance(self,payload): return payload
    def _call(self, _messages):
        return json.dumps({
            'summary':'test','report':{'condition':'fail','interpretation':'volatility regime caused it','next_action':'test','confidence':0.7},
            'scientific_method':{'observation':'VOLATILITY CAUSED FAILURE','hypothesis':'volatility hypothesis','experiment':'bounded test','falsification':'split improves','conclusion':'PROVEN'},
            'strategy':{},'hypotheses':[],
            'next_discovery_plan':{'objective':'bounded treatment','freeze':['labels'],'change':['policy complexity'],'falsification':'CPCV failure persists','do_not_do':'change gates'},
            'stop_research':False,
        })

ctx={'status':'CPCV_NO_SURVIVOR','dataset':{},'stage_evidence':{'evaluated':12},'failure_topology':{'dominant_first_failed_gate':'CPCV_WORST_EXPECTANCY','worst_split_combination':{'test_groups':'(1,2)'}},'candidate_summaries':[],'research_memory':{},'feedback_exposure':1}
sci=scientist_module._stage_review(FakeScientist(),'CPCV',ctx,CFG,learning_allowed=True)
sm=sci['scientific_method']
req('dominant_first_failed_gate=CPCV_WORST_EXPECTANCY' in sm['observation'],'Scientist OBSERVATION is reconstructed from deterministic evidence')
req('VOLATILITY CAUSED FAILURE' not in sm['observation'],'LLM causal claim cannot contaminate OBSERVATION')
req(sm['conclusion']=='PENDING_DECISIVE_EXPERIMENT','Scientist cannot claim causal conclusion before decisive experiment')

# Source-level UX/governance invariants.
app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
factory=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
req('ACTIVE RESEARCH CYCLE' in app and 'PREVIOUS CYCLE' in app,'Research UI separates active and previous cycles')
req('active_family_provenance' in factory and 'MANUAL_ENABLED' in factory,'per-cycle active-family provenance is frozen in manifest')
req('decisive_outcomes=_resolve_committed_hypotheses(fd,"TOURNAMENT",status,rows)' in factory,'Tournament executes decisive hypothesis closure')
req('decisive_outcomes=_resolve_committed_hypotheses(fd,"MONTE_CARLO",status,rows)' in factory,'Monte Carlo executes decisive hypothesis closure')
req('"hypothesis_id"' in factory[factory.index('def _candidate_identity'):factory.index('def _assert_same_candidate')] and factory.count('_candidate_identity(c)') >= 4,'hypothesis lineage propagates through centralized candidate identity into CPCV/Tournament/Monte Carlo/Forward')
req('Ranking Score' in app,'visible ranking terminology cannot imply PASS authority')
req('CPCV Methodology Audit · dual report' in app,'CPCV inspector exposes stress-split vs canonical-path audit')
req('scientific_method' in app and '**OBSERVATION**' in app and '**FALSIFICATION**' in app,'Scientist scientific-method schema is visible in UI')

print('R6_GOVERNANCE_SELFTEST PASS')
