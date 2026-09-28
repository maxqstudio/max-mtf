from __future__ import annotations
import tempfile
from pathlib import Path
import scientist.core.scientist as scientist
from scientist.core.scientist import LLMScientist
from host.provider_catalog import ProviderRequestError

def req(cond,msg):
    if not cond: raise AssertionError(msg)

def main():
    with tempfile.TemporaryDirectory() as td:
        hp=str(Path(td)/'health.json'); calls=[]
        cfg={'timeout_sec':5,'temperature':0.0,'api_key_env':'TEST_KEY','model_health_enabled':True,'model_health_path':hp,'transient_cooldown_sec':60,
             'stack':[{'provider':'gemini','base_url':'https://example/v1/','model':'models/gemini-3.8-flash','enabled':True},
                      {'provider':'gemini','base_url':'https://example/v1/','model':'models/gemini-3.5-flash','enabled':True}]}
        orig=scientist.chat_completion
        def fake(base,model,key,messages,**kw):
            calls.append(model)
            if model.endswith('3.8-flash'):
                raise ProviderRequestError('HTTP 429: requestsPerDay daily quota exceeded',status_code=429)
            return {'choices':[{'message':{'content':'{"ok":true,"role":"research_scientist"}'}}],
                    'usage':{'prompt_tokens':123,'completion_tokens':9,'total_tokens':132}}
        scientist.chat_completion=fake
        try:
            r=LLMScientist(cfg,api_key='x').test(); p=r['llm_provenance']
            req(p['selected_model'].endswith('3.5-flash'),'fallback model not selected')
            req(p['fallback_used'] is True,'fallback flag missing')
            req(p['usage']['input_tokens']==123 and p['usage']['output_tokens']==9,'input/output usage not persisted')
            req(p['attempts'][0]['status']=='FAIL' and p['attempts'][1]['status']=='PASS','attempt provenance wrong')
            calls.clear(); r2=LLMScientist(cfg,api_key='x').test(); p2=r2['llm_provenance']
            req(calls==['models/gemini-3.5-flash'],'quota-exhausted primary was called again despite cooldown')
            req(p2['attempts'][0]['status']=='SKIP' and p2['attempts'][1]['status']=='PASS','cooldown skip provenance wrong')
        finally:
            scientist.chat_completion=orig
    print('LLM_QUOTA_PROVENANCE_SELFTEST PASS')
    return 0
if __name__=='__main__': raise SystemExit(main())
