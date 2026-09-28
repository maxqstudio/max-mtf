from pathlib import Path
import tempfile
from factory.supervisor_agent import _supervisor_initial_strategy
from core.settings_store import UserSettingsStore

ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    cfg={
      'seed':42,
      'agent':{
        'llm':{'temperature':0.35,'max_proposals_per_round':7},
        'search':{'exploration_ratio':0.55,'crossover_ratio':0.4,'llm_strategy_weight':0.6,'llm_research_influence':0.6,'scientific_creativity':0.65,'min_family_weight':0.09},
      }
    }
    ctx={'symbol':'EURUSD.m','period':16385,'start':'2021-01-01','end':'2022-12-31','rows_raw':10000,'rows_labeled':9900,'classes':{'SELL':2200,'SKIP':5500,'BUY':2200}}
    mem={'elites':[{'family':'hybrid_gru_lightgbm','params':{'training_memory_months':18}},{'family':'hybrid_gru_xgboost','params':{'training_memory_months':24}}], 'learning_summary':{'best_family':'hybrid_gru_lightgbm'}, 'downstream_failures':[{'stage':'FORWARD'}], 'last_downstream_failure_stage':'FORWARD'}
    s1,seed1,p1=_supervisor_initial_strategy(ctx,mem,cfg,10)
    s2,seed2,p2=_supervisor_initial_strategy(ctx,mem,cfg,20)
    req(seed1!=seed2,'Cross-Factory fingerprint history changes reproducible initial-plan seed')
    req(s1['family_priorities'].get('hybrid_gru_lightgbm',0)>0,'Research Memory biases initial family plan')
    req(18 in s1.get('preferred_training_memory_months',[]) and 24 in s1.get('preferred_training_memory_months',[]),'Training-memory evidence enters initial plan')
    req(p1['creativity']['scientific_creativity']==0.65 and p1['creativity']['scientist_proposals']==7 and p1['creativity'].get('adaptive_profile'),'phase-aware scientific creativity enters initial-plan evidence')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    for token in ('_subsection_header("Creativity"','Scientist proposals / round','Scientific creativity','Base exploration','Crossover','Min family weight','LLM influence'):
        req(token in app,f'Advanced grouped creativity control present: {token}')
    with tempfile.TemporaryDirectory() as td:
        store=UserSettingsStore(Path(td))
        store.save(cfg,'',{})
        loaded,_,_,_=store.load({'seed':1,'agent':{'llm':{},'search':{}}})
        req(float(loaded['agent']['search']['scientific_creativity'])==0.65,'Scientific creativity persists to disk')
        req(float(loaded['agent']['search']['exploration_ratio'])==0.55,'Supervisor exploration persists to disk')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('_supervisor_initial_strategy' in sup and 'SUPERVISOR_INITIAL_PLAN' in sup,'Supervisor owns initial research plan')
    print('CREATIVITY_BASELINE_SELFTEST PASS')

if __name__=='__main__': main()
