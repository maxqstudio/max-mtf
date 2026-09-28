from __future__ import annotations
import json, tempfile, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import factory.factory_jobs as factory_jobs
from core.inherited_v147 import sha256_file



def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def write_fixture(root:Path):
    fid='FACTORY_KEEP_ME'; fd=root/fid; (fd/'research_runs').mkdir(parents=True)
    snapshot=fd/'discovery_immutable.csv'; snapshot.write_text('contract;symbol;sl_atr;tp_atr;max_hold_bars\nCP32;XAUUSD;3.2;4.8;54\n',encoding='utf-8'); snapsha=sha256_file(snapshot)
    pool=[]
    for i in range(1,13):
        run=f'RUN_{i:02d}'; pool.append({'pool_id':f'CAND_{i:02d}','source_run':run,'family':'xgboost','name':f'm{i}','params':{},'research_overrides':{},'wfa_evidence':{'cv_gate_pass':True,'fidelity_stage':'FULL_WFA'},'discovery_acceptance':{'passed':True}})
        d=fd/'research_runs'/run; d.mkdir(parents=True); (d/'run_config.json').write_text(json.dumps({'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54},'split':{'purge_bars':54,'embargo_bars':54},'research_window':{'authority_snapshot_sha256':snapsha}}),encoding='utf-8')
        (d/'cv_leaderboard.json').write_text(json.dumps([{'family':'xgboost','name':f'm{i}','params':{},'cv_gate_pass':True,'fidelity_stage':'FULL_WFA'}]),encoding='utf-8')
    (fd/'candidate_pool.json').write_text(json.dumps(pool,sort_keys=True),encoding='utf-8')
    (fd/'factory_manifest.json').write_text(json.dumps({'status':'DISCOVERY_POOL_READY'}),encoding='utf-8')
    return fid,fd

with tempfile.TemporaryDirectory() as td0:
    root=Path(td0)/'factories'; root.mkdir(); app=Path(td0)/'app'; app.mkdir()
    fid,fd=write_fixture(root); pool_before=(fd/'candidate_pool.json').read_bytes(); dirs_before=sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith('_'))
    jid='JOB_RECOVER'; paths=factory_jobs.job_paths(root,jid)
    job={'schema':'CP_FACTORY_JOB_V3','job_id':jid,'action':'AUTO','status':'FAILED','factory_id':fid,'payload':{},'created_utc':'2026-09-18T00:00:00+00:00','updated_utc':'2026-09-18T00:01:00+00:00','pid':None,'error':'ValueError: STRATEGY_GEOMETRY_RUNTIME_MISMATCH: sl_atr cfg=1.8 dataset=3.2','traceback':'ORIGINAL_TRACE','resume_count':0}
    factory_jobs.atomic_write_json(paths['job'],job); factory_jobs.atomic_write_json(paths['candidates'],[{'sentinel':'committed'}])
    orch=root/'_orchestrators'/f'{jid}.json'; orch.parent.mkdir(parents=True,exist_ok=True)
    factory_jobs.atomic_write_json(orch,{'schema':'MAX_FACTORY_LANGGRAPH_V1','orchestrator_id':jid,'status':'RUNNING','cycle':1,'current_factory_id':fid,'factory_dir':str(fd),'stage':'CPCV','manifest_status':'DISCOVERY_POOL_READY','completed_factories':[],'max_cycles':1,'consecutive_empty_cycles':0})
    rc=factory_jobs.failed_recovery_contract(root,job)
    req(rc.get('recoverable') is True and rc.get('failure_class')=='STRATEGY_GEOMETRY_RUNTIME_MISMATCH','known geometry FAILED job is recoverable only with committed WFA proof and zero CPCV progress')
    req(rc.get('candidate_count')==12 and rc.get('source_wfa_geometry')==(3.2,4.8,54,54,54),'recovery contract binds all 12 candidates to canonical source WFA geometry')
    req(rc.get('restart_stage')=='CPCV' and rc.get('skip_data_quality_preflight') is True,'recovery contract restarts exactly at CPCV and skips redundant AUTO DQ preflight')

    missing_state={**job,'job_id':'JOB_NO_ORCHESTRATOR'}
    ms=factory_jobs.failed_recovery_contract(root,missing_state)
    req(ms.get('recoverable') is False and ms.get('reason')=='ORCHESTRATOR_STATE_MISSING','AUTO recovery fails closed when same-job orchestrator checkpoint is missing')

    wrong_state={**job,'job_id':'JOB_WRONG_STAGE'}
    ws=root/'_orchestrators'/'JOB_WRONG_STAGE.json'; factory_jobs.atomic_write_json(ws,{'current_factory_id':fid,'stage':'DISCOVERY','manifest_status':'DISCOVERY_POOL_READY'})
    wr=factory_jobs.failed_recovery_contract(root,wrong_state)
    req(wr.get('recoverable') is False and wr.get('reason')=='ORCHESTRATOR_NOT_AT_FAILED_CPCV_STAGE','AUTO recovery fails closed unless committed orchestrator stage is CPCV')

    # Any START path must be blocked while safe recovery is available, including
    # advanced DISCOVERY ONLY so the operator cannot accidentally fork lineage.
    try: factory_jobs.start_job(root,app,'AUTO',{}); started=True
    except RuntimeError as e: started=False; start_err=str(e)
    req(not started and 'RESUME' in start_err,'START AUTO RESEARCH cannot create a duplicate Factory while recovery is available')
    try: factory_jobs.start_job(root,app,'DISCOVERY',{}); disc_started=True
    except RuntimeError as e: disc_started=False; disc_start_err=str(e)
    req(not disc_started and 'RESUME' in disc_start_err,'DISCOVERY ONLY cannot bypass a recoverable FAILED AUTO Factory')
    req(sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith('_'))==dirs_before,'blocked START paths do not create a new Factory directory')

    # Recovery availability itself requires source Full-WFA PASS evidence, not merely
    # a run_config claiming canonical geometry.
    proof=fd/'research_runs'/'RUN_01'/'cv_leaderboard.json'; proof_bytes=proof.read_bytes(); proof.unlink()
    no_pass=factory_jobs.failed_recovery_contract(root,job)
    req(no_pass.get('recoverable') is False and no_pass.get('reason')=='FULL_WFA_SOURCE_PASS_EVIDENCE_MISSING','FAILED recovery is not offered without source Full-WFA PASS evidence')
    proof.write_bytes(proof_bytes)

    original_spawn=factory_jobs._spawn_worker
    factory_jobs._spawn_worker=lambda factory_root,app_dir,j,resume=False:{**j,'resume_spawned':resume}
    try: view=factory_jobs.resume_job(root,app,jid)
    finally: factory_jobs._spawn_worker=original_spawn
    disk=factory_jobs.read_json(paths['job'],{})
    req(view['job_id']==jid and disk['job_id']==jid and disk['factory_id']==fid,'RESUME reuses the same job_id and factory_id')
    req(int(disk['resume_count'])==1,'RESUME increments resume_count exactly once')
    req(len(disk.get('failure_history') or [])==1 and disk['failure_history'][0]['error']==job['error'] and disk['failure_history'][0]['traceback']=='ORIGINAL_TRACE','original error and traceback are preserved in failure history')
    req((fd/'candidate_pool.json').read_bytes()==pool_before,'RESUME does not mutate committed candidate Pool')
    dirs_after=sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith('_'))
    graph_src=(ROOT/'max_graph/factory_graph.py').read_text(encoding='utf-8')
    req("legacy=_read(_state_path(root,str(orchestrator_id)),{}) if resume else {}" in graph_src,'production AUTO resume reloads the same persisted orchestrator state')
    req("if st=='DISCOVERY_POOL_READY': return 'cpcv'" in graph_src,'production router sends committed Discovery Pool directly to CPCV')
    req("if st in {'','INSUFFICIENT_QUALIFIED_POOL'} and str(state.get('stage') or '')=='DISCOVERY': return 'discovery'" in graph_src,'production router cannot re-enter Discovery from a CPCV-stage recovery checkpoint')

    unrelated={**job,'job_id':'JOB_OTHER','error':'RuntimeError: random unrelated failure'}
    req(factory_jobs.failed_recovery_contract(root,unrelated).get('recoverable') is False,'unrelated FAILED error cannot automatically RESUME')

    # Committed CPCV progress blocks recovery even for the known error.
    (fd/'cpcv_live_split_results.json').write_text(json.dumps({'rows':[{'split':1,'expectancy_r':0.1}]}),encoding='utf-8')
    blocked={**job,'job_id':'JOB_BLOCKED'}
    bc=factory_jobs.failed_recovery_contract(root,blocked)
    req(bc.get('recoverable') is False and bc.get('reason')=='CPCV_PROGRESS_ALREADY_COMMITTED','known failure with committed CPCV progress fails closed instead of resetting progress')

app_src=(ROOT/'ui/app.py').read_text(encoding='utf-8')
req('FAILED · recovery available' in app_src and 'factory_job_is_resumable(FACTORY_DIR,cand)' in app_src,'UI exposes FAILED recovery as RESUME/ABORT instead of primary START')
req('resumable_auto=latest_auto if latest_auto and factory_job_is_resumable(FACTORY_DIR,latest_auto) else None' in app_src and 'blocked=bool(active_any or resumable_auto or resumable_disc)' in app_src,'DISCOVERY ONLY UI is disabled for recognized FAILED recovery authority')
print('V201_INHERITED_V147_FAILED_CPCV_RESUME PASS')
