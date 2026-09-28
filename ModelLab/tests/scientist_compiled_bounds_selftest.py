from copy import deepcopy
from scientist.core.scientist import _sanitize_director_parameter_claims
from research.research_architect import compile_research_plan, apply_research_plan
from models.model_registry import effective_bounds


def req(c,m):
    if not c: raise AssertionError(m)

text='Gunakan GRU ringkas hidden_size 16-28 dan max_depth 2-6.'
clean=_sanitize_director_parameter_claims(text)
req('16-28' not in clean and '2-6' not in clean,'Director prose still exposes uncompiled numeric bounds')
req('compiled bounds' in clean or 'compiled authority' in clean,'Director prose did not redirect to deterministic authority')

profile={
    'profile_hash':'cpu32',
    'memory':{'total_gib':32.0,'available_gib':24.0,'source':'TEST'},
    'nvidia':{'devices':[]},
    'torch':{'cuda_available':False},
    'cpu':{'physical_cores':6,'logical_threads':12,'planning_cores':6,'core_count_source':'TEST'},
}
cfg={
    'research_architecture':{
        'family_selection_mode':'MANUAL','allowed_families':['gru','lightgbm','xgboost'],
        'hybrid_priority':1.0,'require_baseline':False,
        'family_size_priorities':{'gru':0.0,'lightgbm':0.0,'xgboost':0.0},
        'safe_ram_fraction':0.75,'safe_vram_fraction':0.8,'max_single_experiment_minutes':120,
    },
    'agent':{'max_experiments':36},
    'split':{'walk_forward_folds':3},
}
capacity={'dataset':{'rows_per_month':518},'wfa':{'median_train_rows':8200,'fold_count':3},'reference_scenario':{'estimated_train_rows':8200}}
strategy={
    'active_families':['hybrid::gru::lightgbm'],
    'parameter_envelopes':{'hybrid::gru::lightgbm':{'temporal_hidden_size':[16,28],'policy_max_depth':[1,2]}}
}
plan=compile_research_plan(strategy,profile,deepcopy(cfg),capacity)
local=deepcopy(cfg); apply_research_plan(local,plan)
eb=effective_bounds(local,'hybrid::gru::lightgbm')
# Dataset/hardware safe GRU recommendation starts at 32; a disjoint LLM proposal may
# not drag the executable lower bound below it. Owner SMALL then narrows inside safety.
req(eb['temporal_hidden_size'][0] >= 32,'LLM widened/bypassed deterministic GRU safe lower bound')
req(eb['policy_max_depth'][0] >= 3,'LLM widened/bypassed deterministic LightGBM safe lower bound')
print('SCIENTIST COMPILED BOUNDS SELF-TEST PASS')
