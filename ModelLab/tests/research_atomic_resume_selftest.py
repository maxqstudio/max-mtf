from __future__ import annotations

import json
import tempfile
from pathlib import Path

import factory.factory_jobs as factory_jobs
from factory.factory_jobs import atomic_write_json, job_paths, load_job, request_pause, resume_job
from research.research_checkpoint import commit_checkpoint, load_checkpoint


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'factory_runs'; root.mkdir()
        cp=root/'F1'/'discovery_checkpoint.json'; cp.parent.mkdir()
        commit_checkpoint(cp,{'phase':'GENERATION_COMMITTED','pool':[{'pool_id':'CAND_01'}],'next_generation':2})
        first=load_checkpoint(cp); req(first and first['phase']=='GENERATION_COMMITTED','checkpoint primary loads')
        commit_checkpoint(cp,{'phase':'POOL_COMMITTED','pool':[{'pool_id':'CAND_01'}],'next_generation':2})
        second=load_checkpoint(cp); req(second and second['phase']=='POOL_COMMITTED','new checkpoint committed')
        cp.write_text('{broken',encoding='utf-8')
        fallback=load_checkpoint(cp); req(fallback and fallback['phase']=='GENERATION_COMMITTED','corrupt newest checkpoint falls back to prior committed backup')

        jid='JOB_TEST'; paths=job_paths(root,jid)
        job={'schema':'CP_FACTORY_JOB_V2','job_id':jid,'action':'DISCOVERY','status':'RUNNING','created_utc':'2020-01-01T00:00:00+00:00','updated_utc':'2020-01-01T00:00:00+00:00','pid':99999999,'factory_id':'F1','payload':{},'target':12}
        atomic_write_json(paths['job'],job)
        orphan=load_job(root,jid)
        req(orphan['status']=='INTERRUPTED','dead worker reconciles to resumable INTERRUPTED')
        req(orphan.get('interruption_reason')=='WORKER_NOT_ALIVE_AFTER_RESTART_OR_CRASH','orphan reason explicit')

        orphan['status']='RUNNING'; orphan['pid']=factory_jobs.os.getpid(); atomic_write_json(paths['job'],orphan)
        paused=request_pause(root,jid); req(paused['status']=='PAUSE_REQUESTED' and paths['pause'].exists(),'pause is out-of-band sentinel')

        # Resume contract: monkeypatch spawn so no real subprocess is created.
        paused_job=dict(orphan); paused_job['status']='PAUSED'; paused_job['pid']=None; atomic_write_json(paths['job'],paused_job)
        try: paths['pause'].unlink()
        except FileNotFoundError: pass
        old_spawn=factory_jobs._spawn_worker
        factory_jobs._spawn_worker=lambda factory_root,app_dir,job,resume=False: {**job,'status':'RUNNING','pid':12345,'resume_spawned':resume}
        try:
            resumed=resume_job(root,Path(td),jid)
        finally:
            factory_jobs._spawn_worker=old_spawn
        req(resumed['status']=='RUNNING' and resumed.get('resume_spawned') is True,'PAUSED job resumes same job id')
        disk=json.loads(paths['job'].read_text())
        req(int(disk.get('resume_count',0))==1,'resume count persisted')

        src=((Path(__file__).resolve().parents[1]/'factory/champion_factory.py')).read_text(encoding='utf-8')
        req('SUPERVISOR_COMMITTED' in src and 'POOL_COMMITTED' in src and 'GENERATION_COMMITTED' in src,'Discovery has WFA-pool atomic commit boundaries')
        req('Resume ditolak: immutable Discovery snapshot hash berubah' in src,'resume validates immutable source hash')
        app=((Path(__file__).resolve().parents[1]/'ui/app.py')).read_text(encoding='utf-8')
        req('button("RESUME"' in app and 'button("PAUSE"' in app and 'button("FORCE STOP"' in app,'UI exposes global pause/resume/force-stop lifecycle')

    print('RESEARCH_ATOMIC_RESUME_SELFTEST PASS')

if __name__=='__main__':
    main()
