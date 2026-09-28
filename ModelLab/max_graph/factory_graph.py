from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from factory.champion_factory import (
    retry_failure_scientist_learning,
    run_cpcv_qualification,
    run_discovery_pool,
    run_forward_championship,
    run_monte_carlo,
    run_tournament,
    verify_champion_terminal_authority,
)
from factory.factory_jobs import atomic_write_json
from factory.factory_challenger_bridge import register_factory_winner_as_model_challenger
from max_graph.runtime import sqlite_checkpointer
from max_graph.state import FactoryGraphState

SCHEMA="MAX_FACTORY_LANGGRAPH_V1"


def _utc(): return datetime.now(timezone.utc).isoformat()

def _factory_id(cycle:int)->str:
    return datetime.now(timezone.utc).strftime('FACTORY_%Y%m%d_%H%M%S_UTC')+f'_AUTO{cycle:03d}_'+uuid.uuid4().hex[:4].upper()

def _read(path:Path, default=None):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {} if default is None else deepcopy(default)

def _state_path(root:Path, orchestrator_id:str)->Path:
    p=root/'_orchestrators'; p.mkdir(parents=True,exist_ok=True); return p/f'{orchestrator_id}.json'

def _mirror(root:Path,state:dict):
    sp=_state_path(root,str(state.get('orchestrator_id') or 'AUTO'))
    payload={k:deepcopy(v) for k,v in state.items() if k not in {'result_payload','error'}}
    payload['updated_utc']=_utc(); atomic_write_json(sp,payload)
    return sp

def _record_completed(state:dict,factory_id:str,status:str):
    rows=list(state.get('completed_factories') or []); key=(str(factory_id),str(status))
    if not any((str((r or {}).get('factory_id')),str((r or {}).get('status')))==key for r in rows):
        rows.append({'factory_id':str(factory_id),'status':str(status)})
    return rows

def _feedback_exhausted(m:dict)->bool: return bool((m or {}).get('research_feedback_exhausted',False))

def _learning_ready(m:dict)->bool: return bool((m or {}).get('research_learning_ready',False))


class _Runtime:
    def __init__(self,*,root,dataset,config_path,discovery_from,discovery_to,tournament_from,tournament_to,
                 fresh_from,fresh_to,progress,llm_api_key,resume,max_cycles):
        self.root=Path(root); self.dataset=dataset; self.config_path=config_path
        self.discovery_from=discovery_from; self.discovery_to=discovery_to
        self.tournament_from=tournament_from; self.tournament_to=tournament_to
        self.fresh_from=fresh_from; self.fresh_to=fresh_to
        self.progress=progress; self.llm_api_key=llm_api_key; self.resume=bool(resume); self.max_cycles=int(max_cycles or 0)


def _build_graph(rt:_Runtime):
    from langgraph.graph import END, START, StateGraph

    def prepare(state:FactoryGraphState):
        s=deepcopy(state)
        # A terminal result must be immutable across graph routing/resume.
        # In particular, failure -> prepare is used for learning cycles; if the failure
        # node already terminalized the run, do not overwrite that status with RUNNING.
        if str(s.get('stage') or '') == 'TERMINAL' and isinstance(s.get('result_payload'), dict):
            _mirror(rt.root,s)
            return s
        cycle=int(s.get('cycle',1) or 1); cap=int(s.get('max_cycles',rt.max_cycles) or 0)
        if cap>0 and cycle>cap:
            s.update({'status':'ORCHESTRATOR_BUDGET_EXHAUSTED','stage':'TERMINAL','result_payload':{'status':'ORCHESTRATOR_BUDGET_EXHAUSTED','cycles':cycle-1}})
            _mirror(rt.root,s); return s
        fid=str(s.get('current_factory_id') or '')
        if not fid:
            fid=_factory_id(cycle); s.update({'current_factory_id':fid,'stage':'DISCOVERY'})
        fd=rt.root/fid; manifest=_read(fd/'factory_manifest.json',{}) if fd.exists() else {}
        s.update({'factory_dir':str(fd),'manifest_status':str(manifest.get('status') or ''),'status':'RUNNING'})
        if rt.progress:
            rt.progress({'stage':'orchestrator','current':cycle,'total':cap or cycle,'message':f'LangGraph Auto Factory cycle {cycle} · {s.get("stage")}', 'factory_id':fid,'orchestrator_cycle':cycle,'orchestration_backend':'LANGGRAPH'})
        _mirror(rt.root,s); return s

    def router(state:FactoryGraphState):
        if str(state.get('stage') or '')=='REGISTER_MODEL_CHALLENGER':
            return 'register_model_challenger'
        if str(state.get('stage') or '')=='TERMINAL' or str(state.get('status') or '') in {
            'ORCHESTRATOR_BUDGET_EXHAUSTED','RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','RESEARCH_SPACE_EXHAUSTED',
            'WAITING_FOR_SCIENTIST_REVIEW','WAITING_FOR_NEW_FORWARD_DATA','NO_CHAMPION_FORWARD_FAIL',
            'FACTORY_WINNER','FACTORY_WINNER_RUNTIME_BLOCKED','MODEL_CHALLENGER_REGISTRATION_FAILED','FAILED'}:
            return 'terminal'
        st=str(state.get('manifest_status') or '')
        if st in {'','INSUFFICIENT_QUALIFIED_POOL'} and str(state.get('stage') or '')=='DISCOVERY': return 'discovery'
        if st=='DISCOVERY_POOL_READY': return 'cpcv'
        if st=='CPCV_SURVIVORS_READY': return 'tournament'
        if st=='TOURNAMENT_SURVIVORS_READY': return 'monte_carlo'
        if st in {'MONTE_CARLO_SURVIVORS_READY','FORWARD_INSUFFICIENT_SAMPLE'}: return 'forward'
        if st in {'INSUFFICIENT_QUALIFIED_POOL','CPCV_NO_SURVIVOR','TOURNAMENT_NO_SURVIVOR','MONTE_CARLO_NO_SURVIVOR'}: return 'failure'
        if st in {'NO_CHAMPION_FORWARD_FAIL','FACTORY_WINNER','FACTORY_WINNER_RUNTIME_BLOCKED','CHAMPION','CHAMPION_RUNTIME_BLOCKED'}: return 'terminalize_manifest'
        return 'unknown'

    def discovery(state:FactoryGraphState):
        s=deepcopy(state); fid=str(s['current_factory_id']); fd=rt.root/fid
        r=run_discovery_pool(rt.dataset,rt.config_path,rt.root,rt.discovery_from,rt.discovery_to,rt.tournament_from,rt.tournament_to,
                             rt.fresh_from,rt.fresh_to,progress=rt.progress,llm_api_key=rt.llm_api_key,factory_id=fid,
                             resume=bool(rt.resume and fd.exists()))
        m=dict(r.get('manifest') or _read(fd/'factory_manifest.json',{})); ms=str(r.get('status') or m.get('status') or '')
        s.update({'manifest_status':ms,'stage':'CPCV' if ms=='DISCOVERY_POOL_READY' else 'DISCOVERY_TERMINAL'})
        if ms=='DISCOVERY_POOL_READY': s['consecutive_empty_cycles']=0
        _mirror(rt.root,s); return s

    def cpcv(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); s['stage']='CPCV'; _mirror(rt.root,s)
        r=run_cpcv_qualification(fd,rt.config_path,progress=rt.progress,llm_api_key=rt.llm_api_key)
        s['manifest_status']=str(r.get('status') or _read(fd/'factory_manifest.json',{}).get('status') or '')
        _mirror(rt.root,s); return s

    def tournament(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); s['stage']='TOURNAMENT'; _mirror(rt.root,s)
        r=run_tournament(fd,rt.dataset,rt.config_path,progress=rt.progress,llm_api_key=rt.llm_api_key)
        s['manifest_status']=str(r.get('status') or _read(fd/'factory_manifest.json',{}).get('status') or '')
        _mirror(rt.root,s); return s

    def monte_carlo(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); s['stage']='MONTE_CARLO'; _mirror(rt.root,s)
        r=run_monte_carlo(fd,rt.config_path,progress=rt.progress,llm_api_key=rt.llm_api_key)
        s['manifest_status']=str(r.get('status') or _read(fd/'factory_manifest.json',{}).get('status') or '')
        _mirror(rt.root,s); return s

    def forward(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); s['stage']='FORWARD_CHAMPIONSHIP'; _mirror(rt.root,s)
        r=run_forward_championship(fd,rt.dataset,rt.config_path,progress=rt.progress,llm_api_key=rt.llm_api_key)
        ms=str(r.get('status') or _read(fd/'factory_manifest.json',{}).get('status') or '')
        s['manifest_status']=ms
        if ms=='NO_CHAMPION_FORWARD_FAIL':
            s.update({'status':ms,'stage':'TERMINAL','terminal_factory':str(s['current_factory_id']),'terminal_failure_stage':'FORWARD','result_payload':{'status':ms,'result':r}})
        elif ms=='FORWARD_INSUFFICIENT_SAMPLE':
            s.update({'status':'WAITING_FOR_NEW_FORWARD_DATA','stage':'TERMINAL','result_payload':{'status':'WAITING_FOR_NEW_FORWARD_DATA','result':r}})
        elif ms in {'FACTORY_WINNER','CHAMPION','FACTORY_WINNER_RUNTIME_BLOCKED','CHAMPION_RUNTIME_BLOCKED'}:
            canonical='FACTORY_WINNER' if ms in {'FACTORY_WINNER','CHAMPION'} else 'FACTORY_WINNER_RUNTIME_BLOCKED'
            if canonical=='FACTORY_WINNER':
                verified=verify_champion_terminal_authority(fd); r=dict(r); r['champion']=verified['champion']
                s.update({'status':'FACTORY_WINNER_PENDING_REGISTRATION','stage':'REGISTER_MODEL_CHALLENGER','champion_factory':str(s['current_factory_id']),
                          'completed_factories':_record_completed(s,str(s['current_factory_id']),ms),
                          'result_payload':{'status':'FACTORY_WINNER_PENDING_REGISTRATION','result':r,'champion':r.get('champion')}})
            else:
                s.update({'status':canonical,'stage':'TERMINAL','champion_factory':str(s['current_factory_id']),
                          'completed_factories':_record_completed(s,str(s['current_factory_id']),ms),
                          'result_payload':{'status':canonical,'result':r,'champion':r.get('champion')}})
        _mirror(rt.root,s); return s

    def failure(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); ms=str(s.get('manifest_status') or '')
        manifest=_read(fd/'factory_manifest.json',{})
        if not _learning_ready(manifest) and not _feedback_exhausted(manifest):
            try:
                rr=retry_failure_scientist_learning(fd,rt.config_path,llm_api_key=rt.llm_api_key)
                manifest=dict(rr.get('manifest') or _read(fd/'factory_manifest.json',{}))
            except Exception:
                manifest=_read(fd/'factory_manifest.json',manifest)
        stage=('POOL' if ms=='INSUFFICIENT_QUALIFIED_POOL' else ('CPCV' if ms=='CPCV_NO_SURVIVOR' else ('TOURNAMENT' if ms=='TOURNAMENT_NO_SURVIVOR' else 'MONTE_CARLO')))
        completed=_record_completed(s,str(s['current_factory_id']),ms)
        if _feedback_exhausted(manifest):
            s.update({'completed_factories':completed,'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':str(s['current_factory_id']),'terminal_failure_stage':stage,
                      'result_payload':{'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','failure_stage':stage}})
            _mirror(rt.root,s); return s
        if not _learning_ready(manifest):
            s.update({'completed_factories':completed,'status':'WAITING_FOR_SCIENTIST_REVIEW','stage':'TERMINAL','terminal_factory':str(s['current_factory_id']),'terminal_failure_stage':stage,
                      'result_payload':{'status':'WAITING_FOR_SCIENTIST_REVIEW','failure_stage':stage,'scientist_error':str(manifest.get('next_required') or 'WAIT_SCIENTIST_REVIEW')}})
            _mirror(rt.root,s); return s
        if stage=='POOL':
            ex=int(manifest.get('total_experiments',0) or 0); empty=int(s.get('consecutive_empty_cycles',0) or 0)+(1 if ex==0 else 0)
            s['consecutive_empty_cycles']=empty
            if empty>=2:
                s.update({'completed_factories':completed,'status':'RESEARCH_SPACE_EXHAUSTED','stage':'TERMINAL','result_payload':{'status':'RESEARCH_SPACE_EXHAUSTED'}})
                _mirror(rt.root,s); return s
        s.update({'completed_factories':completed,'cycle':int(s.get('cycle',1) or 1)+1,'current_factory_id':None,'factory_dir':None,
                  'manifest_status':'','stage':'DISCOVERY','last_learning_stage':stage,'status':'RUNNING'})
        rt.resume=False; _mirror(rt.root,s); return s

    def terminalize_manifest(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir'])); ms=str(s.get('manifest_status') or '')
        if ms=='NO_CHAMPION_FORWARD_FAIL':
            s.update({'status':ms,'stage':'TERMINAL','terminal_factory':str(s['current_factory_id']),'terminal_failure_stage':'FORWARD','result_payload':{'status':ms}})
        elif ms in {'FACTORY_WINNER','CHAMPION'}:
            verified=verify_champion_terminal_authority(fd)
            s.update({'status':'FACTORY_WINNER_PENDING_REGISTRATION','stage':'REGISTER_MODEL_CHALLENGER','champion_factory':str(s['current_factory_id']),'result_payload':{'status':'FACTORY_WINNER_PENDING_REGISTRATION','champion':verified['champion']}})
        else:
            s.update({'status':'FACTORY_WINNER_RUNTIME_BLOCKED','stage':'TERMINAL','champion_factory':str(s['current_factory_id']),'result_payload':{'status':'FACTORY_WINNER_RUNTIME_BLOCKED','champion':_read(fd/'champion.json',{})}})
        _mirror(rt.root,s); return s

    def register_model_challenger(state:FactoryGraphState):
        s=deepcopy(state); fd=Path(str(s['factory_dir']))
        try:
            reg=register_factory_winner_as_model_challenger(fd,Path(__file__).resolve().parents[1])
            ev=dict(reg.get('evidence') or {}); entry=dict(reg.get('entry') or {})
            s.update({
                'status':'FACTORY_WINNER',
                'stage':'TERMINAL',
                'model_challenger_id':ev.get('challenger_id'),
                'model_challenger_run':ev.get('challenger_run_dir'),
                'result_payload':{
                    'status':'FACTORY_WINNER',
                    'champion':(s.get('result_payload') or {}).get('champion'),
                    'challenger_id':ev.get('challenger_id'),
                    'challenger_run':ev.get('challenger_run_dir'),
                    'challenger_registry_status':entry.get('status'),
                    'promotion_performed':False,
                },
            })
        except Exception as exc:
            s.update({
                'status':'MODEL_CHALLENGER_REGISTRATION_FAILED',
                'stage':'TERMINAL',
                'error':{'type':'MODEL_CHALLENGER_REGISTRATION_FAILED','message':str(exc)},
                'result_payload':{
                    'status':'MODEL_CHALLENGER_REGISTRATION_FAILED',
                    'factory_winner_preserved':True,
                    'champion':(s.get('result_payload') or {}).get('champion'),
                    'error':str(exc),
                },
            })
        _mirror(rt.root,s); return s

    def unknown(state:FactoryGraphState):
        s=deepcopy(state); msg=f"LangGraph orchestrator state tidak dikenali: factory={s.get('current_factory_id')} status={s.get('manifest_status')!r} stage={s.get('stage')!r}"
        s.update({'status':'FAILED','stage':'TERMINAL','error':{'type':'UNKNOWN_ORCHESTRATOR_STATE','message':msg},'result_payload':{'status':'FAILED','error':msg}})
        _mirror(rt.root,s); return s

    def final(state:FactoryGraphState):
        s=deepcopy(state); _mirror(rt.root,s); return s

    g=StateGraph(FactoryGraphState)
    for name,fn in (("prepare",prepare),("route",lambda s:s),("discovery",discovery),("cpcv",cpcv),("tournament",tournament),
                    ("monte_carlo",monte_carlo),("forward",forward),("failure",failure),("terminalize_manifest",terminalize_manifest),
                    ("register_model_challenger",register_model_challenger),("unknown",unknown),("terminal",final)):
        g.add_node(name,fn)
    g.add_edge(START,'prepare'); g.add_edge('prepare','route')
    g.add_conditional_edges('route',router,{
        'discovery':'discovery','cpcv':'cpcv','tournament':'tournament','monte_carlo':'monte_carlo','forward':'forward',
        'failure':'failure','terminalize_manifest':'terminalize_manifest','register_model_challenger':'register_model_challenger','unknown':'unknown','terminal':'terminal',
    })
    for n in ('discovery','cpcv','tournament','monte_carlo','forward','terminalize_manifest','register_model_challenger','unknown'):
        g.add_edge(n,'route')
    g.add_edge('failure','prepare')
    g.add_edge('terminal',END)
    return g


def run_auto_factory_graph(factory_root, dataset, config_path, discovery_from, discovery_to,
                           tournament_from, tournament_to, fresh_from, fresh_to,
                           progress=None, llm_api_key=None, orchestrator_id='AUTO', resume=False, max_cycles=0):
    root=Path(factory_root); root.mkdir(parents=True,exist_ok=True)
    rt=_Runtime(root=root,dataset=dataset,config_path=config_path,discovery_from=discovery_from,discovery_to=discovery_to,
                tournament_from=tournament_from,tournament_to=tournament_to,fresh_from=fresh_from,fresh_to=fresh_to,
                progress=progress,llm_api_key=llm_api_key,resume=resume,max_cycles=max_cycles)
    legacy=_read(_state_path(root,str(orchestrator_id)),{}) if resume else {}
    state:FactoryGraphState=legacy if legacy else {
        'schema':SCHEMA,'orchestrator_id':str(orchestrator_id),'status':'RUNNING','cycle':1,'current_factory_id':None,
        'stage':'DISCOVERY','manifest_status':'','completed_factories':[],'created_utc':_utc(),'max_cycles':int(max_cycles or 0),
        'consecutive_empty_cycles':0,
    }
    state['schema']=SCHEMA; state['orchestrator_id']=str(orchestrator_id); state['max_cycles']=int(state.get('max_cycles',max_cycles) or 0)
    db=root/'_langgraph'/'factory_orchestrator.sqlite'
    with sqlite_checkpointer(db) as saver:
        graph=_build_graph(rt).compile(checkpointer=saver)
        final=graph.invoke(state,config={'configurable':{'thread_id':f'FACTORY::{orchestrator_id}'},'recursion_limit':512})
    payload=deepcopy(final.get('result_payload') or {'status':final.get('status')})
    payload.update({'orchestrator_id':str(orchestrator_id),'factory':str(final.get('factory_dir') or ''),'cycles':int(final.get('cycle',1) or 1),'state_file':str(_state_path(root,str(orchestrator_id))),
                    'langgraph_checkpoint_db':str(db),'orchestration_backend':'LANGGRAPH'})
    if final.get('champion_factory'): payload['champion_factory']=final.get('champion_factory')
    return payload
