from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def req(c,m):
    if not c: raise AssertionError(m)
    print('PASS',m)

cfg=json.loads((ROOT/'config/config.json').read_text())
req((cfg.get('agent',{}).get('orchestration') or {}).get('backend')=='LANGGRAPH','LangGraph is configured orchestration backend')
req((cfg.get('agent',{}).get('orchestration') or {}).get('required') is True,'LangGraph runtime is required in v1.3.0')
req((ROOT/'requirements/requirements-langgraph.txt').exists(),'Pinned LangGraph requirements exist')
req('langgraph==1.2.11' in (ROOT/'requirements/requirements-langgraph.txt').read_text(),'LangGraph version pinned')
req('langgraph-checkpoint-sqlite==3.1.1' in (ROOT/'requirements/requirements-langgraph.txt').read_text(),'SQLite checkpointer version pinned')

fac=(ROOT/'max_graph'/'factory_graph.py').read_text()
dirsrc=(ROOT/'max_graph'/'scientist_director_graph.py').read_text()
chat=(ROOT/'max_graph'/'scientist_chat_graph.py').read_text()
orch=(ROOT/'factory/factory_orchestrator.py').read_text()
worker=(ROOT/'scientist/chat/scientist_chat_worker.py').read_text()
sup=(ROOT/'factory/supervisor_agent.py').read_text()
req('StateGraph(FactoryGraphState)' in fac and "run_auto_factory_graph" in fac,'AUTO Factory uses explicit StateGraph')
req("sqlite_checkpointer" in fac and "factory_orchestrator.sqlite" in fac,'Factory graph has durable SQLite checkpoint')
req('_run_auto_factory_v126_legacy_reference' in orch and 'run_auto_factory_graph' in orch,'v1.2.6 orchestrator retained only as parity reference; v1.3 delegates AUTO to graph')
req('StateGraph(ScientistDirectorState)' in dirsrc and 'plan_inspection' in dirsrc and 'inspect_evidence' in dirsrc and 'validate_and_remember' in dirsrc,'Scientist Director graph has inspect-design-validate loop')
req('attribute_previous_proposals' in dirsrc and 'proposal_lineage' in dirsrc and 'hypothesis_memory' in dirsrc,'Scientist graph persists attribution, proposal lineage and hypothesis memory')
req('run_agentic_scientist_round' in sup,'Supervisor invokes agentic Scientist graph')
req('StateGraph(ScientistChatGraphState)' in chat and 'read_only_answer' in chat,'Scientist Chat is isolated LangGraph')
state_src=(ROOT/'max_graph'/'state.py').read_text()
req('api_key:' not in state_src and '"api_key":str(api_key)' not in chat and 'runtime_api_key' in chat,'Scientist Chat API key is runtime-only and cannot enter checkpoint state')
req('run_scientist_chat_graph' in worker,'Scientist Chat worker enters graph runtime')
for forbidden in ('run_auto_factory','run_cpcv_qualification','run_tournament','run_monte_carlo','run_forward_championship','promote'):
    req(forbidden not in chat,f'Scientist Chat graph has no execution edge/token: {forbidden}')
req('LANGGRAPH_STRICT_MSGPACK' in (ROOT/'max_graph'/'runtime.py').read_text(),'Strict checkpoint deserialization enabled')
runtime_acc=(ROOT/'acceptance/runners/langgraph_runtime_acceptance.py').read_text()
req('LANGGRAPH_RUNTIME_ACCEPTANCE_v1_3_3.json' in runtime_acc and 'first_failed_gate' in runtime_acc,'One-click LangGraph runtime acceptance emits machine-readable evidence with first failed gate')
req('SCIENTIST_CHAT_SECRET_NON_PERSISTENCE' in runtime_acc and 'secret.encode' in runtime_acc,'Runtime acceptance proves Scientist Chat API key is not checkpoint-persisted')
print('v1.3.0 LangGraph architecture selftest PASS')
