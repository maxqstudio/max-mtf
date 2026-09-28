from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import (
    configured_family_size_priorities, effective_bounds, family_spec,
    family_size_priority, dynamic_hybrid_families,
)
from research.research_architect import compile_research_plan
from models.models import CandidateSpec, candidate_capacity_contract

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def profile():
    return {
        'profile_hash':'R14_GPU8',
        'cpu':{'name':'test','physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'detected':True,'devices':[{'name':'RTX','memory_total_gib':8.0,'memory_free_gib':7.0}]},
        'torch':{'installed':True,'cuda_available':True},
    }


def with_plan(priority_map, envs=None, active=None):
    cfg=deepcopy(BASE)
    cfg.setdefault('research_architecture',{})['family_size_priorities']=dict(priority_map)
    cfg.setdefault('agent',{})['research_plan']={
        'family_size_priority_schema':'CP_FAMILY_SIZE_PRIORITY_V1',
        'family_size_priorities':dict(priority_map),
        'parameter_envelopes':envs or {},
        'active_families':active or ['gru','lightgbm','hybrid::gru::lightgbm'],
        'capacity_guidance':{'preferred_total_params':[1000,10_000_000],'extended_total_params':[1000,20_000_000]},
    }
    return cfg


def main():
    fsp=(BASE.get('research_architecture') or {}).get('family_size_priorities') or {}
    required={'lightgbm','xgboost','random_forest','gru','lstm','tcn','transformer','transformer_moe','patchtst','itransformer','tft'}
    req(required.issubset(fsp),'all base families have Owner size-priority defaults')
    req(all(abs(float(fsp[k])-0.50)<1e-12 for k in required),'all default size priorities are neutral 0.50')

    # Registry explicitly declares executable size dimensions; optimizer knobs are not model-size knobs.
    req(set(family_spec('gru').get('size_parameters') or [])=={'hidden_size','num_layers'},'GRU size dimensions explicit')
    req('learning_rate' not in set(family_spec('transformer').get('size_parameters') or []),'learning rate excluded from size dimensions')
    req('training_memory_months' not in set(family_spec('tcn').get('size_parameters') or []),'training memory excluded from size dimensions')

    env={'gru':{'hidden_size':[32,128],'num_layers':[1,3],'dropout':[0.05,0.35],'learning_rate':[0.0002,0.002]}}
    neutral=with_plan({'gru':0.50},env,['gru'])
    b=effective_bounds(neutral,'gru')
    req(b['hidden_size'][:2]==(32,128) and b['num_layers'][:2]==(1,3),'0.50 preserves full safe size envelope')
    req(abs(b['dropout'][0]-0.05)<1e-12 and abs(b['dropout'][1]-0.35)<1e-12,'neutral preserves non-size envelope')

    small=with_plan({'gru':0.00},env,['gru'])
    bs=effective_bounds(small,'gru')
    req(bs['hidden_size'][:2]==b['hidden_size'][:2] and bs['num_layers'][:2]==b['num_layers'][:2],'0.00 is search preference, not a hard GRU bound slice')
    req(bs['dropout'][:2]==b['dropout'][:2] and bs['learning_rate'][:2]==b['learning_rate'][:2],'Small does not touch optimizer/regularization knobs')

    large=with_plan({'gru':1.00},env,['gru'])
    bl=effective_bounds(large,'gru')
    req(bl['hidden_size'][:2]==b['hidden_size'][:2] and bl['num_layers'][:2]==b['num_layers'][:2],'1.00 is search preference, not a hard GRU bound slice')
    req(bl['dropout'][:2]==b['dropout'][:2],'Large does not touch dropout')

    # Compiled plan freezes Owner values; mutable UI config changes cannot alter an active Factory.
    cfg=deepcopy(BASE)
    cfg['research_architecture']['family_size_priorities']['gru']=0.00
    strategy={'active_families':['gru','lightgbm'],'parameter_envelopes':{'gru':env['gru']}}
    plan=compile_research_plan(strategy,profile(),cfg)
    req(abs(float(plan['family_size_priorities']['gru'])-0.0)<1e-12,'compiled plan freezes GRU size priority')
    cfg.setdefault('agent',{})['research_plan']=plan
    cfg['research_architecture']['family_size_priorities']['gru']=1.00
    req(abs(configured_family_size_priorities(cfg)['gru']-0.0)<1e-12,'running plan wins over mutable UI slider')

    # Hybrid inherits temporal and policy component sliders independently.
    fam='hybrid::gru::lightgbm'
    req(fam in dynamic_hybrid_families(),'dynamic hybrid available')
    hcfg=with_plan({'gru':0.00,'lightgbm':1.00},{},[fam])
    hb=effective_bounds(hcfg,fam)
    legal_low=family_spec(fam)['search']['temporal_hidden_size']['min']; legal_high=family_spec(fam)['search']['temporal_hidden_size']['max']
    req(hb['temporal_hidden_size'][0]==legal_low and hb['temporal_hidden_size'][1]==legal_high,'hybrid temporal size priority is preference, not a hard bound slice')
    p_lo=family_spec(fam)['search']['policy_num_leaves']['min']; p_hi=family_spec(fam)['search']['policy_num_leaves']['max']
    req(hb['policy_num_leaves'][0]==p_lo and hb['policy_num_leaves'][1]==p_hi,'hybrid policy priority is preference, not a hard bound slice')
    req(family_size_priority(hcfg,fam)=={'temporal':0.0,'policy':1.0},'hybrid size-priority provenance component-aware')

    # Capacity contract carries provenance but hard capacity remains separate authority.
    spec=CandidateSpec('gru','r14_gru',{
        'sequence_length':64,'hidden_size':64,'num_layers':1,'dropout':0.1,
        'learning_rate':0.001,'batch_size':64,'epochs':8,'weight_decay':0.001,'training_memory_months':12,
    })
    cc=candidate_capacity_contract(spec,small)
    req(cc.get('owner_size_priority')=={'family':0.0},'candidate capacity evidence records Owner size priority')
    req('hidden_size' in (cc.get('size_parameters') or []),'candidate evidence records size dimensions')

    print('FAMILY_SIZE_PRIORITY_SELFTEST PASS')

if __name__=='__main__': main()
