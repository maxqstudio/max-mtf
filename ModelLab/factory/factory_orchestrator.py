from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from factory.champion_factory import run_discovery_pool, run_cpcv_qualification, run_tournament, run_monte_carlo, run_forward_championship, retry_failure_scientist_learning, verify_champion_terminal_authority
from factory.factory_jobs import atomic_write_json


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {} if default is None else default


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _factory_id(cycle: int) -> str:
    return datetime.now(timezone.utc).strftime('FACTORY_%Y%m%d_%H%M%S_UTC') + f'_AUTO{cycle:03d}_' + uuid.uuid4().hex[:4].upper()


def _state_path(root: Path, orchestrator_id: str) -> Path:
    p=root/'_orchestrators'; p.mkdir(parents=True,exist_ok=True)
    return p/f'{orchestrator_id}.json'


def _save(path: Path, state: dict):
    out=dict(state); out['updated_utc']=_utc(); atomic_write_json(path,out)


def _feedback_exhausted(manifest: dict) -> bool:
    return bool((manifest or {}).get('research_feedback_exhausted',False))


def _learning_ready(manifest: dict) -> bool:
    return bool((manifest or {}).get('research_learning_ready',False))


def _record_completed_factory(state: dict, factory_id: str, status: str) -> None:
    """Idempotent orchestrator history across WAIT/RESUME boundaries."""
    rows=list(state.get('completed_factories') or [])
    key=(str(factory_id),str(status))
    if not any((str((r or {}).get('factory_id')),str((r or {}).get('status')))==key for r in rows):
        rows.append({'factory_id':str(factory_id),'status':str(status)})
    state['completed_factories']=rows


def _wait_for_scientist(state: dict, sp: Path, orchestrator_id: str, fd: Path, cycle: int, stage: str, manifest: dict) -> dict:
    state.update({
        'status':'WAITING_FOR_SCIENTIST_REVIEW','stage':'WAIT_SCIENTIST_REVIEW',
        'terminal_factory':fd.name,'terminal_failure_stage':str(stage).upper(),
        'scientist_error':str((manifest or {}).get('next_required') or 'WAIT_SCIENTIST_REVIEW'),
    })
    _save(sp,state)
    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp),'failure_stage':str(stage).upper()}


def _retry_learning_if_needed(fd: Path, manifest: dict, config_path, llm_api_key):
    if _learning_ready(manifest) or _feedback_exhausted(manifest):
        return manifest
    try:
        rr=retry_failure_scientist_learning(fd,config_path,llm_api_key=llm_api_key)
        return dict(rr.get('manifest') or _read(fd/'factory_manifest.json',{}))
    except Exception:
        return _read(fd/'factory_manifest.json',manifest)



def run_manual_factory(factory_root, dataset, config_path, discovery_from, discovery_to,
                       tournament_from, tournament_to, fresh_from, fresh_to,
                       progress=None, orchestrator_id='MANUAL', resume=False):
    """Owner-defined one-pass research with deterministic validation only.

    Contract:
    - zero LLM proposal/review calls;
    - zero deterministic candidate discovery/generation;
    - exact Owner candidates enter Full WFA;
    - survivors continue through CPCV -> Tournament -> Monte Carlo -> Forward;
    - no automatic research restart/learning loop is permitted.
    """
    root=Path(factory_root); root.mkdir(parents=True,exist_ok=True)
    safe=''.join(ch if ch.isalnum() or ch in {'_','-'} else '_' for ch in str(orchestrator_id))[:72]
    fid=f'MANUAL_{safe}'
    fd=root/fid
    if progress:
        progress({'stage':'orchestrator','current':1,'total':1,'message':'Manual Research · Owner exact candidates · deterministic validation','factory_id':fid,'orchestrator_cycle':1,'research_mode':'MANUAL'})

    manifest=_read(fd/'factory_manifest.json',{}) if fd.exists() else {}
    status=str(manifest.get('status') or '')
    if not manifest:
        r=run_discovery_pool(
            dataset,config_path,root,discovery_from,discovery_to,tournament_from,tournament_to,
            fresh_from,fresh_to,progress=progress,llm_api_key=None,factory_id=fid,resume=bool(resume and fd.exists()),
        )
        manifest=dict(r.get('manifest') or _read(fd/'factory_manifest.json',{})); status=str(r.get('status') or manifest.get('status') or '')
    if status=='MANUAL_WFA_NO_SURVIVOR':
        return {'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1,'qualified':int(manifest.get('qualified_candidates',0) or 0)}

    if status=='DISCOVERY_POOL_READY':
        r=run_cpcv_qualification(fd,config_path,progress=progress,llm_api_key=None)
        status=str(r.get('status') or '')
    else:
        status=str((_read(fd/'factory_manifest.json',{}) or {}).get('status') or status)
    if status=='CPCV_NO_SURVIVOR':
        return {'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1}

    if status=='CPCV_SURVIVORS_READY':
        r=run_tournament(fd,dataset,config_path,progress=progress,llm_api_key=None)
        status=str(r.get('status') or '')
    else:
        status=str((_read(fd/'factory_manifest.json',{}) or {}).get('status') or status)
    if status=='TOURNAMENT_NO_SURVIVOR':
        return {'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1}

    if status=='TOURNAMENT_SURVIVORS_READY':
        r=run_monte_carlo(fd,config_path,progress=progress,llm_api_key=None)
        status=str(r.get('status') or '')
    else:
        status=str((_read(fd/'factory_manifest.json',{}) or {}).get('status') or status)
    if status=='MONTE_CARLO_NO_SURVIVOR':
        return {'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1}

    if status in {'MONTE_CARLO_SURVIVORS_READY','FORWARD_INSUFFICIENT_SAMPLE'}:
        r=run_forward_championship(fd,dataset,config_path,progress=progress,llm_api_key=None)
        status=str(r.get('status') or '')
        out={'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1,'result':r}
        if isinstance(r,dict) and r.get('champion'):
            out['champion']=r.get('champion')
        return out

    # Already-terminal/resumed evidence.
    if status in {'FACTORY_WINNER','FACTORY_WINNER_RUNTIME_BLOCKED','CHAMPION','CHAMPION_RUNTIME_BLOCKED','NO_CHAMPION_FORWARD_FAIL','FORWARD_INSUFFICIENT_SAMPLE'}:
        out={'status':status,'research_mode':'MANUAL','factory':str(fd),'cycles':1}
        if status in {'FACTORY_WINNER','CHAMPION'}:
            out['champion']=verify_champion_terminal_authority(fd)['champion']
        else:
            champ=_read(fd/'champion.json',{})
            if champ: out['champion']=champ
        return out
    raise RuntimeError(f'Manual orchestrator state tidak dikenali: factory={fid} status={status!r}')

def run_auto_factory(factory_root, dataset, config_path, discovery_from, discovery_to,
                     tournament_from, tournament_to, fresh_from, fresh_to,
                     progress=None, llm_api_key=None, orchestrator_id='AUTO', resume=False,
                     max_cycles=0):
    """Full-auto Champion Factory orchestrator.

    Stage authority is persisted separately from the Streamlit/job process. A crash can
    resume the same Factory at the last stage whose manifest was committed. A new Factory
    is created only after a scientifically terminal no-survivor/no-champion result.
    """
    root=Path(factory_root); root.mkdir(parents=True,exist_ok=True)
    sp=_state_path(root,str(orchestrator_id))
    state=_read(sp,{}) if resume else {}
    if not state:
        state={
            'schema':'CP_MASTER_ORCHESTRATOR_V1','orchestrator_id':str(orchestrator_id),
            'status':'RUNNING','cycle':1,'current_factory_id':None,'stage':'DISCOVERY',
            'completed_factories':[],'created_utc':_utc(),'max_cycles':int(max_cycles or 0),
            'consecutive_empty_cycles':0,
        }
        _save(sp,state)
    else:
        state['status']='RUNNING'; _save(sp,state)

    while True:
        cycle=int(state.get('cycle',1) or 1)
        cap=int(state.get('max_cycles',max_cycles) or 0)
        if cap>0 and cycle>cap:
            state.update({'status':'ORCHESTRATOR_BUDGET_EXHAUSTED','stage':'TERMINAL'})
            _save(sp,state)
            return {'status':state['status'],'orchestrator_id':orchestrator_id,'cycles':cycle-1,'state_file':str(sp)}

        fid=str(state.get('current_factory_id') or '')
        if not fid:
            fid=_factory_id(cycle)
            state.update({'current_factory_id':fid,'stage':'DISCOVERY'})
            _save(sp,state)
        fd=root/fid
        if progress:
            progress({'stage':'orchestrator','current':cycle,'total':cap or cycle,'message':f'Auto Factory cycle {cycle} · {state.get("stage")}','factory_id':fid,'orchestrator_cycle':cycle})

        manifest=_read(fd/'factory_manifest.json',{}) if fd.exists() else {}
        mstatus=str(manifest.get('status') or '')

        # DISCOVERY: resume the in-flight checkpoint if the factory directory exists
        # without a completed manifest.
        if not manifest or mstatus in {'','INSUFFICIENT_QUALIFIED_POOL'} and str(state.get('stage'))=='DISCOVERY':
            r=run_discovery_pool(
                dataset,config_path,root,discovery_from,discovery_to,tournament_from,tournament_to,
                fresh_from,fresh_to,progress=progress,llm_api_key=llm_api_key,factory_id=fid,
                resume=bool(resume and fd.exists()),
            )
            manifest=dict(r.get('manifest') or _read(fd/'factory_manifest.json',{})); mstatus=str(r.get('status') or manifest.get('status') or '')
            state['stage']='CPCV' if mstatus=='DISCOVERY_POOL_READY' else 'DISCOVERY_TERMINAL'
            if mstatus=='INSUFFICIENT_QUALIFIED_POOL':
                if _feedback_exhausted(manifest):
                    state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'POOL'}); _save(sp,state)
                    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
                if not _learning_ready(manifest):
                    return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,'POOL',manifest)
                ex=int(manifest.get('total_experiments',0) or 0)
                state['consecutive_empty_cycles']=int(state.get('consecutive_empty_cycles',0) or 0)+(1 if ex==0 else 0)
                if state['consecutive_empty_cycles']>=2:
                    state.update({'status':'RESEARCH_SPACE_EXHAUSTED','stage':'TERMINAL'})
                    _save(sp,state)
                    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
                _record_completed_factory(state,fid,mstatus)
                state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':'POOL'})
                _save(sp,state); resume=False; continue
            state['consecutive_empty_cycles']=0; _save(sp,state)

        manifest=_read(fd/'factory_manifest.json',{}); mstatus=str(manifest.get('status') or '')
        if mstatus=='DISCOVERY_POOL_READY':
            state['stage']='CPCV'; _save(sp,state)
            r=run_cpcv_qualification(fd,config_path,progress=progress,llm_api_key=llm_api_key)
            mstatus=str(r.get('status') or '')
            if mstatus=='CPCV_NO_SURVIVOR':
                manifest=_read(fd/'factory_manifest.json',{})
                _record_completed_factory(state,fid,mstatus)
                if _feedback_exhausted(manifest):
                    state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'CPCV'}); _save(sp,state)
                    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
                if not _learning_ready(manifest):
                    return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,'CPCV',manifest)
                state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':'CPCV'}); _save(sp,state); resume=False; continue

        manifest=_read(fd/'factory_manifest.json',{}); mstatus=str(manifest.get('status') or '')
        if mstatus=='CPCV_SURVIVORS_READY':
            state['stage']='TOURNAMENT'; _save(sp,state)
            r=run_tournament(fd,dataset,config_path,progress=progress,llm_api_key=llm_api_key)
            mstatus=str(r.get('status') or '')
            if mstatus=='TOURNAMENT_NO_SURVIVOR':
                manifest=_read(fd/'factory_manifest.json',{})
                _record_completed_factory(state,fid,mstatus)
                if _feedback_exhausted(manifest):
                    state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'TOURNAMENT'}); _save(sp,state)
                    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
                if not _learning_ready(manifest):
                    return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,'TOURNAMENT',manifest)
                state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':'TOURNAMENT'}); _save(sp,state); resume=False; continue

        manifest=_read(fd/'factory_manifest.json',{}); mstatus=str(manifest.get('status') or '')
        if mstatus=='TOURNAMENT_SURVIVORS_READY':
            state['stage']='MONTE_CARLO'; _save(sp,state)
            r=run_monte_carlo(fd,config_path,progress=progress,llm_api_key=llm_api_key)
            mstatus=str(r.get('status') or '')
            if mstatus=='MONTE_CARLO_NO_SURVIVOR':
                manifest=_read(fd/'factory_manifest.json',{})
                _record_completed_factory(state,fid,mstatus)
                if _feedback_exhausted(manifest):
                    state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'MONTE_CARLO'}); _save(sp,state)
                    return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
                if not _learning_ready(manifest):
                    return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,'MONTE_CARLO',manifest)
                state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':'MONTE_CARLO'}); _save(sp,state); resume=False; continue

        manifest=_read(fd/'factory_manifest.json',{}); mstatus=str(manifest.get('status') or '')
        if mstatus in {'MONTE_CARLO_SURVIVORS_READY','FORWARD_INSUFFICIENT_SAMPLE'}:
            state['stage']='FORWARD_CHAMPIONSHIP'; _save(sp,state)
            r=run_forward_championship(fd,dataset,config_path,progress=progress,llm_api_key=llm_api_key)
            mstatus=str(r.get('status') or '')
            if mstatus=='NO_CHAMPION_FORWARD_FAIL':
                _record_completed_factory(state,fid,mstatus)
                state.update({'status':'NO_CHAMPION_FORWARD_FAIL','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'FORWARD'}); _save(sp,state)
                return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp),'result':r}
            if mstatus=='FORWARD_INSUFFICIENT_SAMPLE':
                state.update({'status':'WAITING_FOR_NEW_FORWARD_DATA','stage':'WAIT_FORWARD_DATA'})
                _save(sp,state)
                return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp),'result':r}
            if mstatus in {'FACTORY_WINNER','FACTORY_WINNER_RUNTIME_BLOCKED','CHAMPION','CHAMPION_RUNTIME_BLOCKED'}:
                if mstatus in {'FACTORY_WINNER','CHAMPION'}:
                    verified=verify_champion_terminal_authority(fd)
                    r=dict(r); r['champion']=verified['champion']
                canonical_status=('FACTORY_WINNER' if mstatus in {'FACTORY_WINNER','CHAMPION'} else 'FACTORY_WINNER_RUNTIME_BLOCKED')
                state.update({'status':canonical_status,'stage':'DONE','champion_factory':fid})
                _record_completed_factory(state,fid,mstatus)
                _save(sp,state)
                out={'status':canonical_status,'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp),'result':r}
                if r.get('champion'): out['champion']=r.get('champion')
                return out

        # Resume from already-committed downstream terminal statuses.
        manifest=_read(fd/'factory_manifest.json',{}); mstatus=str(manifest.get('status') or '')
        if mstatus in {'CPCV_NO_SURVIVOR','TOURNAMENT_NO_SURVIVOR','MONTE_CARLO_NO_SURVIVOR'}:
            manifest=_retry_learning_if_needed(fd,manifest,config_path,llm_api_key)
            stage_name=('CPCV' if mstatus=='CPCV_NO_SURVIVOR' else ('TOURNAMENT' if mstatus=='TOURNAMENT_NO_SURVIVOR' else 'MONTE_CARLO'))
            if _feedback_exhausted(manifest):
                state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':stage_name}); _save(sp,state)
                return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
            if not _learning_ready(manifest):
                return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,stage_name,manifest)
            _record_completed_factory(state,fid,mstatus)
            state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':stage_name}); _save(sp,state); resume=False; continue
        if mstatus=='NO_CHAMPION_FORWARD_FAIL':
            state.update({'status':'NO_CHAMPION_FORWARD_FAIL','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'FORWARD'}); _save(sp,state)
            return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
        if mstatus=='INSUFFICIENT_QUALIFIED_POOL':
            manifest=_retry_learning_if_needed(fd,manifest,config_path,llm_api_key)
            if _feedback_exhausted(manifest):
                state.update({'status':'RESEARCH_FEEDBACK_BUDGET_EXHAUSTED','stage':'TERMINAL','terminal_factory':fid,'terminal_failure_stage':'POOL'}); _save(sp,state)
                return {'status':state['status'],'orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}
            if not _learning_ready(manifest):
                return _wait_for_scientist(state,sp,orchestrator_id,fd,cycle,'POOL',manifest)
            _record_completed_factory(state,fid,mstatus)
            state.update({'cycle':cycle+1,'current_factory_id':None,'stage':'DISCOVERY','last_learning_stage':'POOL'}); _save(sp,state); resume=False; continue
        if mstatus in {'FACTORY_WINNER','CHAMPION'}:
            verified=verify_champion_terminal_authority(fd)
            state.update({'status':'FACTORY_WINNER','stage':'DONE','champion_factory':fid}); _save(sp,state)
            return {'status':'FACTORY_WINNER','orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp),'champion':verified['champion']}
        if mstatus in {'FACTORY_WINNER_RUNTIME_BLOCKED','CHAMPION_RUNTIME_BLOCKED'}:
            state.update({'status':'FACTORY_WINNER_RUNTIME_BLOCKED','stage':'DONE','champion_factory':fid}); _save(sp,state)
            return {'status':'FACTORY_WINNER_RUNTIME_BLOCKED','orchestrator_id':orchestrator_id,'factory':str(fd),'cycles':cycle,'state_file':str(sp)}

        raise RuntimeError(f'Orchestrator state tidak dikenali: factory={fid} status={mstatus!r} stage={state.get("stage")!r}')

# v1.3.0: LangGraph is the AUTO orchestration authority. The v1.2.6 function body
# above is intentionally retained as a frozen compatibility reference for parity
# auditing, but production AUTO calls enter the graph below.
_run_auto_factory_v126_legacy_reference = run_auto_factory

def run_auto_factory(factory_root, dataset, config_path, discovery_from, discovery_to,
                     tournament_from, tournament_to, fresh_from, fresh_to,
                     progress=None, llm_api_key=None, orchestrator_id='AUTO', resume=False,
                     max_cycles=0):
    if __import__('os').environ.get('MAX_LANGGRAPH_ACCEPTANCE_LEGACY_COMPAT')=='1':
        return _run_auto_factory_v126_legacy_reference(
            factory_root,dataset,config_path,discovery_from,discovery_to,tournament_from,tournament_to,
            fresh_from,fresh_to,progress=progress,llm_api_key=llm_api_key,orchestrator_id=orchestrator_id,
            resume=resume,max_cycles=max_cycles,
        )
    from max_graph.factory_graph import run_auto_factory_graph
    return run_auto_factory_graph(
        factory_root,dataset,config_path,discovery_from,discovery_to,tournament_from,tournament_to,
        fresh_from,fresh_to,progress=progress,llm_api_key=llm_api_key,orchestrator_id=orchestrator_id,
        resume=resume,max_cycles=max_cycles,
    )
