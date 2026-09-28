from __future__ import annotations
import json
import tempfile
from pathlib import Path

import scientist.chat.scientist_chat as sc
from host.provider_catalog import ProviderRequestError


def req(cond,msg):
    if not cond: raise AssertionError(msg)

with tempfile.TemporaryDirectory() as td:
    root=Path(td); fd=root/'FACTORY_TEST'; fd.mkdir()
    (fd/'factory_manifest.json').write_text(json.dumps({'status':'DISCOVERY','stage':'DISCOVERY','research_contract_hash':'abc','total_experiments':8,'max_total_experiments':36}),encoding='utf-8')
    (fd/'research_plan.json').write_text(json.dumps({'active_families':['gru','lightgbm'],'topology_priority':{'hybrid':1.0},'family_size_priorities':{'gru':0.0,'lightgbm':0.0},'parameter_envelopes':{'gru':{'hidden_size':[32,64]}}}),encoding='utf-8')
    (fd/'dataset_quality_context.json').write_text(json.dumps({'quality_status':'VALID','unexpected_missing':0}),encoding='utf-8')
    (fd/'candidate_pool.json').write_text(json.dumps([{'pool_id':'P1','family':'hybrid::gru::lightgbm','status':'PASS','profit_factor':2.1}]),encoding='utf-8')
    (fd/'failure_topology.json').write_text(json.dumps({'dominant_failure_group':'survival','all_failed_gate_counts':{'CV_CVAR':8}}),encoding='utf-8')
    (fd/'forward_evidence_001.json').write_text(json.dumps({'SECRET_LOCKED_FORWARD_SHOULD_NOT_LEAK':True}),encoding='utf-8')
    rr=fd/'research_runs'/'R1'; rr.mkdir(parents=True)
    (rr/'cv_leaderboard.json').write_text(json.dumps([{'candidate_id':'C1','family':'hybrid::gru::lightgbm','status':'FAIL','first_failed_gate':'CV_CVAR'}]),encoding='utf-8')
    ctx=sc.build_read_only_context(fd,scope='AUTO',live_job={'job_id':'J1','status':'RUNNING','last_event':{'factory_generation':2,'stage':'screen'}},live_candidates=[])
    blob=json.dumps(ctx)
    req(ctx['authority']['can_execute'] is False,'chat context must be non-executing')
    req(ctx['authority']['tools']==[],'chat context must expose no tools')
    req('SECRET_LOCKED_FORWARD_SHOULD_NOT_LEAK' not in blob,'locked/fresh Forward evidence leaked into chat')
    req(ctx['research_plan']['family_size_priorities']['gru']==0.0,'frozen research plan missing')
    req(any(x.get('id')=='PLAN' for x in ctx['sources']),'internal evidence source IDs missing')

    store=sc.ScientistChatStore(root/'chat')
    store.save('FACTORY_A',[{'role':'user','content':'A'}])
    store.save('FACTORY_B',[{'role':'user','content':'B'}])
    req(store.load('FACTORY_A')[0]['content']=='A','per-Factory history A corrupted')
    req(store.load('FACTORY_B')[0]['content']=='B','per-Factory history B corrupted')

    cfg={'provider':'gemini','base_url':'https://example.test/v1/','model':'m1','stack':[{'provider':'gemini','base_url':'https://example.test/v1/','model':'m1','enabled':True},{'provider':'gemini','base_url':'https://example.test/v1/','model':'research_flash','enabled':True}], 'chat_fallback_stack':[{'provider':'gemini','base_url':'https://example.test/v1/','model':'m2','enabled':True}], 'chat_model_profiles':{'m1':{'streaming':False},'m2':{'streaming':False}}}
    calls=[]
    def fail_then_pass(base,model,key,messages,temperature=0.2,timeout=60):
        calls.append(model)
        if model=='m1': raise ProviderRequestError('HTTP 429 quota',status_code=429)
        return {'choices':[{'message':{'content':'read-only answer'}}],'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}}
    old=sc.chat_completion; sc.chat_completion=fail_then_pass
    try:
        calls.clear()
        try:
            sc.discuss(cfg,selected_model='m1',api_key='x',history=[],user_prompt='why?',context=ctx,allow_fallback=False)
            raise AssertionError('manual exact-model chat should fail when fallback OFF')
        except RuntimeError:
            pass
        req(calls==['m1'],'fallback OFF tried another model')
        calls.clear()
        out=sc.discuss(cfg,selected_model='m1',api_key='x',history=[],user_prompt='why?',context=ctx,allow_fallback=True)
        req(calls==['m1','m2'],'manual Chat fallback did not use its explicit ordered stack')
        req('research_flash' not in calls,'manual Chat illegally borrowed autonomous research fallback')
        req(out['answered_by']=='m2' and out['fallback_used'] is True,'fallback provenance incorrect')
    finally:
        sc.chat_completion=old


# Provider-visible answer must never expose explicit hidden reasoning wrappers.
raw="<thought>private scratchpad</thought>\n## Status\nDATA_READY"
clean=sc._sanitize_response_text(raw)
req('private scratchpad' not in clean and '<thought>' not in clean and 'DATA_READY' in clean,'hidden reasoning sanitizer failed')
prompt=sc._chat_system_prompt()
req('Never invent a cause' in prompt and 'warning details are not available' in prompt,'grounding/no-invention contract missing')
req('Markdown tables' in prompt and 'chain-of-thought' in prompt,'AI-chat formatting or hidden-reasoning contract missing')

app=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')
req('Scientist' in app and 'Read-only' in app and 'scientist_chat_drawer' in app,'right Scientist Chat read-only drawer UI missing')
req('scientist_chat_discuss' in app,'chat call not wired')
req('_execute_scientist_action' not in (Path(__file__).resolve().parents[1]/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8'),'read-only chat imports execution authority')
req('locked_or_fresh_forward_evidence_exposed' in (Path(__file__).resolve().parents[1]/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8'),'locked Forward boundary missing')
print('PASS scientist_chat_readonly_selftest')
