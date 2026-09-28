from __future__ import annotations
import json
from models.capacity_governor import build_dataset_capacity_profile, recommended_capacity_envelopes
from research.research_architect import recommended_parameter_envelopes


def req(x,msg):
    if not x: raise AssertionError(msg)


def main():
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    ident={'rows':35000,'start':'2021-01-01','end':'2025-12-31','symbol':'XAUUSD','period':60}
    cap=build_dataset_capacity_profile(ident,cfg,feature_count=32,sequence_hint=128)
    ref=cap['reference_scenario']
    req(9000 <= int(ref['estimated_train_rows']) <= 12000, f"18m reference not ~10k rows: {ref}")
    lo,hi=ref['preferred_total_params']
    req(140000 <= lo <= 220000, f"preferred low unexpected: {lo}")
    req(350000 <= hi <= 500000, f"preferred high unexpected: {hi}")
    req(len(cap['wfa']['train_rows_by_fold'])==int(cfg['split']['walk_forward_folds']),'WFA fold count mismatch')
    gpu={'memory':{'total_gib':32},'nvidia':{'devices':[{'memory_total_gib':8}]},'torch':{'cuda_available':True},'cpu':{'physical_cores':6},'profile_hash':'gpu8'}
    guide=recommended_capacity_envelopes(cap,gpu)
    req(int(guide['compute']['soft_absolute_parameter_ceiling'])>=20_000_000,'8GB compute ceiling too narrow')
    env=recommended_parameter_envelopes(gpu,cap)['transformer_moe']
    req(env['num_experts'][0] <= 4 <= env['num_experts'][1],'4-expert MoE not in recommended envelope')
    req(env['top_k']==[1,2],'MoE top-k envelope mismatch')
    print('CAPACITY_GOVERNOR_SELFTEST PASS')
    print(json.dumps({'reference':ref,'guidance':guide,'moe_envelope':env},indent=2))

if __name__=='__main__': main()
