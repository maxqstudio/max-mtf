from __future__ import annotations
import json
import tempfile
from pathlib import Path
import scientist.chat.scientist_chat as sc
def req(cond,msg):
    if not cond: raise AssertionError(msg)

cfg={
    'seed':42,
    'cpu_threads':6,
    'label':{'horizon_bars':12,'tp_atr':2.0,'sl_atr':1.0},
    'split':{'walk_forward_folds':5,'cpcv_enabled':True},
    'acceptance':{'min_profit_factor':1.5,'cpcv_min_worst_expectancy_r':0.0},
    'research_architecture':{
        'family_selection_mode':'AUTO','allowed_families':['gru','lightgbm'],'hybrid_priority':0.65,
        'family_size_priorities':{'gru':0.8,'lightgbm':0.35},'safe_ram_fraction':0.75,
    },
    'models':{'gru':{'hidden_sizes':[32,64,128]},'lightgbm':{'num_leaves':[15,31]},'secret_model':{'password':'NO'}},
    'agent':{
        'max_experiments':36,'round_size':6,'max_rounds':6,'patience_rounds':2,'min_improvement':0.5,'min_experiments_before_stop':12,
        'search':{'scientific_creativity':0.5,'llm_research_influence':0.45},
        'policy_discovery':{'enabled':True},'window_discovery':{'min_months':6,'max_months':72},
        'research_memory':{'enabled':True},'fidelity_ladder':{'enabled':True},'experiment_blocks':{'enabled':True},
        'promotion':{'auto_promote_if_all_gates_pass':False},
        'llm':{
            'enabled':True,'scientist_scope':'SCIENTIFIC_HYPOTHESES_V2','max_proposals_per_round':5,
            'hypothesis_kinds':['MODEL_ARCHITECTURE'],'fallback_on':['RATE_LIMIT'],'model_health_enabled':True,
            'api_key':'SECRET','api_key_env':'SECRET_ENV','token':'SECRET_TOKEN',
            'stack':[{'provider':'gemini','model':'research-model','enabled':True,'api_key':'STACK_SECRET','base_url':'https://example.invalid'}],
        },
    },
    'compute':{'mode':'AUTO','allow_cuda':True},
    'trade_sample_policy':{'mode':'TIMEFRAME_ADAPTIVE'},
    'champion_factory':{'target_pool':8},
}
settings=sc.build_research_settings_snapshot(cfg)
blob=json.dumps(settings,sort_keys=True)
req(settings['authority']['read_only'] is True and settings['authority']['can_modify_settings'] is False,'settings authority must be read-only')
req(settings['owner_current_config']['research_architecture']['family_size_priorities']['gru']==0.8,'family size settings missing')
req(settings['owner_current_config']['agent_research']['search']['scientific_creativity']==0.5,'research search controls missing')
req(settings['owner_current_config']['model_family_config']['gru']['hidden_sizes']==[32,64,128],'family model config missing')
req('SECRET' not in blob and 'api_key' not in blob and 'token' not in blob,'credential-like settings leaked')
req(settings['owner_current_config']['autonomous_scientist_llm']['stack'][0]['model']=='research-model','safe autonomous routing identity missing')


# Scientist must know current-host hardware before any Factory exists. Configured
# accelerator allowances are not evidence that a GPU/runtime is actually usable.
live_hw={
    'schema':'CP_HARDWARE_PROFILE_V1','captured_utc':'2026-09-14T00:00:00Z','profile_hash':'HW1',
    'os':{'system':'Windows','release':'11'},
    'cpu':{'name':'AMD Ryzen Test','physical_cores':6,'logical_threads':12,'planning_cores':6,'core_count_source':'PSUTIL','architecture':'AMD64'},
    'memory':{'total_gib':32.0,'available_gib':20.0,'source':'PSUTIL'},
    'nvidia':{'detected':False,'devices':[]},
    'torch':{'installed':True,'torch_version':'2.x+cpu','cuda_available':False,'cuda_version':None},
}
live_compute={
    'schema':'CP_COMPUTE_BACKEND_V1','mode':'AUTO','fallback_cpu':True,
    'temporal_dl':{'backend':'CPU','torch_device':'cpu'},'xgboost':{'backend':'CPU'},'lightgbm':{'backend':'CPU'},'random_forest':{'backend':'CPU'},
    'vulkan':{'state':'UNAVAILABLE','training_backend':False},'notes':[],
    'capabilities':{'torch':{'accelerator':None,'torch_device':'cpu'},'xgboost_cuda':{'usable':False},'lightgbm_gpu':{'usable':False},'opencl':{'device_evidence':False},'vulkan':{'detected':False},'cpu':{'usable':True}},
}
ctx0=sc.build_read_only_context(None,scope='AUTO',research_settings=settings,live_hardware=live_hw,live_compute_plan=live_compute)
req(ctx0['factory']['status']=='NO_FACTORY_CONTEXT','pre-Factory context status wrong')
req(ctx0['live_hardware']['cpu']['name']=='AMD Ryzen Test','current-host CPU missing before Factory exists')
req(ctx0['live_hardware']['memory']['total_gib']==32.0,'current-host RAM missing before Factory exists')
req(ctx0['live_hardware']['nvidia']['detected'] is False,'GPU absence must be explicit hardware truth')
req(ctx0['live_compute_plan']['temporal_dl']['backend']=='CPU','resolved temporal backend missing')
req(ctx0['live_compute_plan']['xgboost']['backend']=='CPU','resolved XGBoost backend missing')
req(any(x.get('id')=='LIVE_HW' for x in ctx0['sources']),'LIVE_HW provenance missing')
req(any(x.get('id')=='LIVE_COMPUTE' for x in ctx0['sources']),'LIVE_COMPUTE provenance missing')

with tempfile.TemporaryDirectory() as td:
    fd=Path(td)/'F'; fd.mkdir()
    (fd/'factory_manifest.json').write_text(json.dumps({'status':'RUNNING','stage':'DISCOVERY'}),encoding='utf-8')
    (fd/'research_plan.json').write_text(json.dumps({'topology_priority':{'hybrid':0.5},'family_size_priorities':{'gru':0.5}}),encoding='utf-8')
    ctx=sc.build_read_only_context(fd,scope='RESEARCH SETTINGS',research_settings=settings)
    req('research_settings' in ctx,'RESEARCH SETTINGS scope missing current settings')
    req(ctx['research_plan']['family_size_priorities']['gru']==0.5,'frozen active plan not visible alongside current settings')
    req(ctx['research_settings']['owner_current_config']['research_architecture']['family_size_priorities']['gru']==0.8,'current Owner config missing')
    req(any(x.get('id')=='SETTINGS' for x in ctx['sources']),'SETTINGS provenance source missing')

prompt=sc._chat_system_prompt()
for token in ('CURRENT OWNER CONFIG','FROZEN ACTIVE research_plan','Current → Suggested → Why → Trade-off/Effect','Never recommend lowering scientific KPI gates','LIVE_HW','LIVE_COMPUTE','do not ask the Owner to repeat hardware specs'):
    req(token in prompt,f'settings-advice prompt contract missing: {token}')

app=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')
req('"RESEARCH SETTINGS"' in app and '"SETTINGS"' in app,'Research Settings context selector not wired')
req('build_research_settings_snapshot(cfg)' in app,'current config snapshot not passed to Scientist Chat')
req('live_hardware=_chat_live_hw' in app and 'live_compute_plan=_chat_live_compute' in app,'live hardware/compute not wired into Scientist Chat')
print('PASS scientist_chat_settings_context_selftest')
