from __future__ import annotations
import json
from pathlib import Path
from research.research_architect import recommended_parameter_envelopes, capability_catalog, compile_research_plan
from models.model_registry import registry_for_scientist


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    cfg['research_architecture']['family_selection_mode']='MANUAL'
    cfg['research_architecture']['allowed_families']=['patchtst','itransformer','tft','lightgbm']
    profile={
      'profile_hash':'selftest','memory':{'total_gib':32,'available_gib':20},
      'nvidia':{'devices':[{'memory_total_gib':8.0,'memory_free_gib':7.0}]},
      'torch':{'cuda_available':True},'cpu':{'physical_cores':6,'logical_threads':12},
    }
    cap={'reference_scenario':{'preferred_total_params':[158000,420000],'extended_total_params':[105000,788000],'training_memory_months':18,'estimated_train_rows':10500,'sequence_length':128}}
    env=recommended_parameter_envelopes(profile,cap)
    for fam in ('patchtst','itransformer','tft'):
        req(fam in env and 'd_model' in env[fam],f'{fam} dataset/hardware capacity envelope')
    catalog=capability_catalog(profile,cfg)
    for fam in ('patchtst','itransformer','tft'):
        req(catalog['families'][fam]['eligible'] is True,f'{fam} manual allowed + hardware eligible')
    strategy={
      'active_families':['patchtst','itransformer','tft'],
      'hybrid_compositions':[{'temporal':'patchtst','policy':'lightgbm'}],
      'parameter_envelopes':{
        'patchtst':{'d_model':[32,72],'patch_len':[8,24]},
        'itransformer':{'d_model':[32,80]},
        'tft':{'d_model':[24,64],'tft_lstm_layers':[1,2]},
      }
    }
    plan=compile_research_plan(strategy,profile,cfg,cap)
    for fam in ('patchtst','itransformer','tft','hybrid::patchtst::lightgbm'):
        req(fam in plan['active_families'],f'{fam} compiled into executable research plan')
    reg=registry_for_scientist()['base_families']
    req('PatchTST' in str(reg['patchtst'].get('architecture_note')) or 'patch' in str(reg['patchtst'].get('architecture_note')).lower(),'Scientist receives PatchTST inductive-bias metadata')
    app=Path('app.py').read_text(encoding='utf-8')
    req(all(x in app for x in ('"patchtst":"PatchTST"','"itransformer":"iTransformer"','"tft":"TFT"')),'Advanced UI exposes Transformer family checklist labels')
    sci=Path('scientist.py').read_text(encoding='utf-8')
    req(all(x in sci for x in ('PatchTST','iTransformer','TFT','Transformer MoE')),'Scientist prompt compares Transformer family inductive biases')
    print('TRANSFORMER_FAMILY_CAPACITY_SELFTEST PASS')

if __name__=='__main__': main()
