import scientist.chat.scientist_chat as sc
captured={}

def fake_chat(base_url, model, api_key, messages, temperature=0.2, timeout=60):
    captured['messages']=messages
    return {'choices':[{'message':{'content':'ok'}}], 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
sc.chat_completion=fake_chat
history=[]
for i in range(80):
    history.append({'role':'user' if i%2==0 else 'assistant','content':('turn-%02d '%i)+('x'*6500)})
ans=sc.discuss({'provider':'mock','base_url':'https://example.invalid/v1','timeout_sec':5,'chat_model_profiles':{'mock-model':{'streaming':False}}},selected_model='mock-model',api_key='x',history=history,user_prompt='status?',context={'sources':[],'blob':'y'*120000},allow_fallback=False)
msgs=captured['messages']
prior=msgs[2:-1]
assert len(prior) <= sc.MAX_REQUEST_HISTORY_MESSAGES, len(prior)
assert sum(len(m['content']) for m in prior) <= sc.MAX_REQUEST_HISTORY_CHARS, sum(len(m['content']) for m in prior)
assert len(msgs[1]['content']) <= len('CURRENT READ-ONLY RESEARCH CONTEXT:\n') + sc.MAX_CONTEXT_CHARS
assert ans['content']=='ok'
print('SCIENTIST_CHAT_REQUEST_BUDGET_SELFTEST PASS',len(prior),sum(len(m['content']) for m in prior))
