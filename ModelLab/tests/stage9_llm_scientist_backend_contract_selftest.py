from __future__ import annotations

import json
import tempfile
from pathlib import Path

import factory.champion_factory as cf
import scientist.core.scientist as sm
from host.provider_catalog import ProviderRequestError


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_internal_typeerror_is_not_retried():
    calls=[]
    old=sm.chat_completion
    def bad(base,model,key,messages,**kwargs):
        calls.append((base,model))
        # Deliberately resembles the message the historical compatibility shim caught.
        raise TypeError("unexpected keyword argument 'internal_provider_bug'")
    sm.chat_completion=bad
    try:
        sc=sm.LLMScientist({'stack':[{'provider':'x','base_url':'https://one.example/v1','model':'m'}]},api_key='k')
        try:
            sc.test()
            raise AssertionError('internal TypeError must fail closed')
        except TypeError:
            pass
        req(len(calls)==1,'internal TypeError caused duplicate LLM request')
    finally:
        sm.chat_completion=old


def test_legacy_override_compat_is_preclassified():
    class Legacy(sm.LLMScientist):
        def __init__(self):
            self.last_call_provenance={'attempts':[]}
        def _call(self,messages):
            return '{"ok":true,"role":"research_scientist"}'
    r=Legacy().test()
    req(r['ok'] is True,'legacy _call(messages) compatibility broken')


def test_route_health_is_endpoint_scoped():
    with tempfile.TemporaryDirectory() as td:
        hp=str(Path(td)/'health.json'); calls=[]
        cfg={
            'model_health_enabled':True,'model_health_path':hp,'transient_cooldown_sec':60,
            'stack':[
                {'provider':'gemini','base_url':'https://account-a.example/v1','model':'same-model','api_key_env':'KEY_A'},
                {'provider':'gemini','base_url':'https://account-b.example/v1','model':'same-model','api_key_env':'KEY_B'},
            ],
        }
        old=sm.chat_completion
        def fake(base,model,key,messages,**kwargs):
            calls.append(base)
            if 'account-a' in base:
                raise ProviderRequestError('HTTP 429: quota exhausted',status_code=429)
            return {'choices':[{'message':{'content':'{"ok":true,"role":"research_scientist"}'}}]}
        sm.chat_completion=fake
        try:
            out=sm.LLMScientist(cfg,api_key='primary').test()
            req(out['ok'] is True,'second endpoint did not recover first endpoint quota failure')
            req(len(calls)==2 and 'account-b' in calls[1],'same model on distinct endpoint was incorrectly cooldown-skipped')
            attempts=out['llm_provenance']['attempts']
            req(attempts[0]['status']=='FAIL' and attempts[1]['status']=='PASS','route-scoped provenance wrong')
        finally:
            sm.chat_completion=old


def test_stop_research_is_advisory_only_for_learning():
    class AdvisoryScientist:
        ready=True
        def __init__(self,*a,**k): self.last_call_provenance={'attempts':[{'status':'PASS'}]}
        def stage_review(self,*a,**k):
            return {
                'summary':'advisory stop',
                'stop_research':True,
                'stop_research_advisory':True,
                'next_discovery_plan':{'objective':'repair','change':['architecture'],'falsification':'no improvement'},
                'hypotheses':[{'kind':'MODEL_ARCHITECTURE','executable':True,'payload':{'variable_keys_by_family':{'gru':['hidden_size']}}}],
            }
    old=cf.LLMScientist
    cf.LLMScientist=AdvisoryScientist
    try:
        with tempfile.TemporaryDirectory() as td:
            fd=Path(td)/'F'; fd.mkdir()
            cfg={'agent':{'llm':{'enabled':True}},'champion_factory':{'research_feedback':{'max_exposures':{'CPCV':2}}}}
            e=cf._stage_scientist_and_feedback(fd,cfg,'CPCV','CPCV_NO_SURVIVOR',{'candidate_rows':[{'pool_id':'p'}]},[],learning_allowed=True,contract_hash_override='abc')
            req(e['stop_research'] is False and e['stop_research_advisory'] is True,'stop request gained execution authority')
            req(e['learning_ready'] is True,'advisory stop incorrectly cancelled actionable failure learning')
    finally:
        cf.LLMScientist=old


def test_factory_deterministic_only_blocks_stage_llm_retries():
    class MustNotConstruct:
        def __init__(self,*a,**k):
            raise AssertionError('LLM was retried despite factory deterministic-only latch')
    old=cf.LLMScientist
    cf.LLMScientist=MustNotConstruct
    try:
        with tempfile.TemporaryDirectory() as td:
            fd=Path(td)/'F'; fd.mkdir()
            cfg={'agent':{'llm':{'enabled':True,'factory_session_deterministic_only':True}},'champion_factory':{'research_feedback':{'max_exposures':{'CPCV':2}}}}
            e=cf._stage_scientist_and_feedback(fd,cfg,'CPCV','CPCV_NO_SURVIVOR',{'dominant_first_failed_gate':'PF'},[],learning_allowed=True,contract_hash_override='abc')
            req(e['learning_source']=='DETERMINISTIC_FALLBACK' and e['learning_ready'] is True,'deterministic-only stage fallback not committed')
    finally:
        cf.LLMScientist=old


def test_corrupt_global_memory_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        (root/'_global_research_memory.json').write_text('{broken',encoding='utf-8')
        try:
            cf._load_global_contract(root,'abc')
            raise AssertionError('corrupt global memory silently reset')
        except RuntimeError as exc:
            req('Global Research Memory corrupt' in str(exc),'wrong corrupt-memory failure')


def test_connection_failure_falls_back_but_auth_with_quota_text_does_not():
    from host.provider_catalog import fallback_error_category, ProviderRequestError
    req(fallback_error_category(ProviderRequestError('Connection failed: refused',category='CONNECTION'))=='PROVIDER_UNREACHABLE','connection failure did not become fallback-safe')
    req(fallback_error_category(ProviderRequestError('401 invalid key quota message',status_code=401,category='HTTP')) is None,'auth error was misclassified as quota fallback')
    req(fallback_error_category(ProviderRequestError('HTTP 404: endpoint not found',status_code=404,category='HTTP')) is None,'generic endpoint 404 was misclassified as model-unavailable fallback')
    req(fallback_error_category(ProviderRequestError('HTTP 404: model foo not found',status_code=404,category='HTTP'))=='MODEL_UNAVAILABLE','model 404 did not remain fallback-safe')

def test_supervisor_midrun_exhaustion_latch_marker():
    src=Path('supervisor_agent.py').read_text(encoding='utf-8')
    req('DETERMINISTIC_ONLY_AFTER_LLM_EXHAUSTION' in src,'mid-run stack exhaustion is not latched deterministic-only')
    req('scientist_enabled=False' in src and 'scientist=None' in src,'mid-run Scientist remains callable after stack exhaustion')


def test_source_contract_markers():
    sup=Path('supervisor_agent.py').read_text(encoding='utf-8')
    fac=Path('champion_factory.py').read_text(encoding='utf-8')
    req('SCIENTIST_STOP_CONFIRMED_BY_NO_IMPROVEMENT' not in sup,'Scientist can still stop deterministic Supervisor')
    req('factory_session_deterministic_only' in sup and 'factory_session_deterministic_only' in fac,'deterministic-only latch not propagated into Supervisor/stage Scientist')
    req('START_PREFLIGHT_ALL_LLM_EXHAUSTED' in fac,'START exhaustion latch provenance missing')
    req('LLM enabled but provider/model stack is invalid or empty' in fac,'malformed enabled LLM stack is not fail-closed')


def main():
    test_internal_typeerror_is_not_retried()
    test_legacy_override_compat_is_preclassified()
    test_route_health_is_endpoint_scoped()
    test_stop_research_is_advisory_only_for_learning()
    test_factory_deterministic_only_blocks_stage_llm_retries()
    test_corrupt_global_memory_fails_closed()
    test_connection_failure_falls_back_but_auth_with_quota_text_does_not()
    test_supervisor_midrun_exhaustion_latch_marker()
    test_source_contract_markers()
    print('STAGE9_LLM_SCIENTIST_BACKEND_CONTRACT PASS')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
