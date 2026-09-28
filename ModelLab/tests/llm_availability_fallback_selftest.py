from __future__ import annotations
import tempfile
from pathlib import Path
import factory.champion_factory as cf
def req(x,msg):
    if not x: raise AssertionError(msg)

class ExhaustedScientist:
    ready=True
    def __init__(self,*a,**k):
        self.last_call_provenance={'attempts':[{'status':'FAIL','category':'QUOTA_OR_RATE_LIMIT'},{'status':'SKIP','category':'DAILY_QUOTA_EXHAUSTED'}]}
    def stage_review(self,*a,**k):
        raise RuntimeError('all models exhausted')

class AuthScientist:
    ready=True
    def __init__(self,*a,**k):
        self.last_call_provenance={'attempts':[{'status':'FAIL','category':'AUTH'}]}
    def stage_review(self,*a,**k):
        raise RuntimeError('401 invalid key')


def cfg():
    return {'agent':{'llm':{'enabled':True}},'champion_factory':{'research_feedback':{'max_exposures':{'CPCV':2}}}}


def main():
    req(cf._llm_stack_exhausted({'attempts':[{'status':'FAIL','category':'TIMEOUT'},{'status':'FAIL','category':'MODEL_UNAVAILABLE'}]}),'retryable full stack must be exhausted')
    req(not cf._llm_stack_exhausted({'attempts':[{'status':'FAIL','category':'AUTH'}]}),'auth failure must not masquerade as exhaustion')
    old=cf.LLMScientist
    try:
        with tempfile.TemporaryDirectory() as td:
            fd=Path(td)/'F'; fd.mkdir(); (fd/'factory_manifest.json').write_text('{}',encoding='utf-8')
            cf.LLMScientist=ExhaustedScientist
            e=cf._stage_scientist_and_feedback(fd,cfg(),'CPCV','CPCV_NO_SURVIVOR',{'dominant_first_failed_gate':'PF'},[],learning_allowed=True,contract_hash_override='abc')
            req(e['learning_ready'] and e['learning_source']=='DETERMINISTIC_FALLBACK','all API routes exhausted must continue deterministic research')
            req((e.get('next_discovery_plan') or {}).get('mode')=='DETERMINISTIC_FALLBACK','deterministic plan provenance missing')
        with tempfile.TemporaryDirectory() as td:
            fd=Path(td)/'F'; fd.mkdir(); (fd/'factory_manifest.json').write_text('{}',encoding='utf-8')
            cf.LLMScientist=AuthScientist
            e=cf._stage_scientist_and_feedback(fd,cfg(),'CPCV','CPCV_NO_SURVIVOR',{'dominant_first_failed_gate':'PF'},[],learning_allowed=True,contract_hash_override='abc')
            req(not e['learning_ready'] and e['error'],'invalid auth must remain fail-closed')
    finally:
        cf.LLMScientist=old
    src=Path(cf.__file__).read_text(encoding='utf-8')
    req('llm_route_preflight.json' in src and 'ALL_LLM_EXHAUSTED_DETERMINISTIC' in src,'START RESEARCH route preflight missing')
    req('Research Director pre-flight fail-closed' in src and 'Research Director generation review fail-closed' in src,'non-retryable Director errors must fail closed')
    req('data_quality_profile' in src and '_stage_evidence["data_quality_profile"]' in src,'LLM DATA review must receive deterministic data-quality evidence before Director pre-flight')
    print('LLM_AVAILABILITY_FALLBACK PASS')

if __name__=='__main__': main()
