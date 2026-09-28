from __future__ import annotations
from pathlib import Path
from models.model_lab import load_cfg
from scientist.core.scientist import LLMScientist

ROOT=Path(__file__).resolve().parents[1]

def check(cond,msg):
    if not cond:
        raise AssertionError(msg)

class FakeDirector(LLMScientist):
    def _call(self,messages):
        return '''{
          "summary":"Fokus hybrid GRU + LightGBM, jangan reset baseline.",
          "report":{"condition":"CPCV robustness menjadi bottleneck","interpretation":"Search perlu diarahkan ke family hybrid yang stabil","next_action":"Prioritaskan hybrid dan memory menengah","confidence":0.91},
          "strategy":{"exploration_ratio":0.22,"family_priorities":{"hybrid_gru_lightgbm":2.6,"not_a_family":9},"preferred_training_memory_months":[24,36],"focus":"robust hybrid refinement"},
          "hypotheses":[],"stop_research":false
        }'''

def main():
    cfg=load_cfg(ROOT/'config/config.json')
    llm=dict((cfg.get('agent') or {}).get('llm') or {})
    llm.update({'enabled':True,'model':'fake-model','base_url':'https://example.invalid/v1'})
    d=FakeDirector(llm,api_key='x')
    r=d.factory_preflight({'factory_id':'F','factory_generation':0,'dataset':{'symbol':'EURUSD.m','period':16385},'research_memory':{'failure_gate_counts':{'CPCV':9}},'remaining_budget':216},cfg)
    check(r['summary'].startswith('Fokus hybrid'),'preflight summary missing')
    check(abs(float(r['strategy']['exploration_ratio'])-0.22)<1e-9,'exploration directive changed unexpectedly')
    check('hybrid_gru_lightgbm' in r['strategy'].get('family_priorities',{}),'valid family priority missing')
    check('not_a_family' not in r['strategy'].get('family_priorities',{}),'invalid family escaped deterministic clamp')
    check(r['strategy'].get('preferred_training_memory_months')==[24,36],'memory directive missing')

    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    sa=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    check(cf.index('director.factory_preflight') < cf.index('for gen in range(next_generation'), 'Factory pre-flight must occur before Generation 1 planning')
    check('director.factory_generation_review' in cf, 'generation review hook missing')
    check('ac["factory_director"]' in cf, 'next-generation directive not injected into Supervisor config')
    check('factory_director=deepcopy' in sa and 'SUPERVISOR_DIRECTED_INITIAL_PLAN' in sa, 'Supervisor does not consume Factory Director directive')
    check('if scientist_enabled and scientist is not None:' in sa, 'Scientist final-round review hook missing')
    check('and experiments<max_exp' not in sa, 'final Supervisor round still suppresses Scientist report')
    check('FACTORY GEN {gen}' in app and 'FACTORY PRE-FLIGHT' in app, 'UI does not expose Director generation/phase identity')
    check('key="global_research_start"' in app and 'key=f"factory_global_pause_' in app and 'key=f"factory_global_stop_' in app and 'request_factory_pause' in app and '_queue_global_research_stop' in app, 'global research lifecycle controls missing')
    print('RESEARCH_DIRECTOR_SELFTEST PASS')

if __name__=='__main__':
    main()
