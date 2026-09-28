from __future__ import annotations
import json
from models.capacity_governor import build_dataset_capacity_profile
from research.research_architect import compile_research_plan, apply_strategy_parameter_envelopes
from models.model_registry import effective_bounds


def req(x,msg):
    if not x: raise AssertionError(msg)


def profile():
    return {'memory':{'total_gib':32},'nvidia':{'devices':[{'memory_total_gib':8}]},'torch':{'cuda_available':True},'cpu':{'physical_cores':6},'profile_hash':'gpu8'}


def main():
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    cap=build_dataset_capacity_profile({'rows':35000,'start':'2021-01-01','end':'2025-12-31','symbol':'XAUUSD','period':60},cfg)
    strategy={
        'active_families':['transformer_moe'],
        'preferred_training_memory_months':[18],
        'capacity_intent':{'reference_training_memory_months':18,'target_total_params':[180000,380000],'rationale':'35k history; ~10k rows per 18m fit'},
        'parameter_envelopes':{'transformer_moe':{'d_model':[48,80],'num_layers':[2,4],'num_experts':[4,4],'expert_ffn':[96,256],'training_memory_months':[12,24]}},
    }
    plan=compile_research_plan(strategy,profile(),cfg,cap)
    req('transformer_moe' in plan['active_families'],'Scientist MoE family missing')
    req(plan['dataset_capacity_profile']['reference_scenario']['estimated_train_rows']>9000,'dataset capacity missing')
    req(plan['parameter_envelopes']['transformer_moe']['num_experts']==[4,4],'Scientist envelope not compiled')
    cfg.setdefault('agent',{})['research_plan']=plan
    b=effective_bounds(cfg,'transformer_moe')
    req(b['d_model'][0]>=48 and b['d_model'][1]<=80,'training generator does not consume compiled envelope')
    next_plan=apply_strategy_parameter_envelopes(plan,{'parameter_envelopes':{'transformer_moe':{'d_model':[32,64],'expert_ffn':[64,192]}}})
    cfg['agent']['research_plan']=next_plan; b2=effective_bounds(cfg,'transformer_moe')
    req(b2['d_model'][0]==32 and b2['d_model'][1]==64,'generation review envelope override not applied')
    print('SCIENTIST_CAPACITY_PLAN_SELFTEST PASS')

if __name__=='__main__': main()
