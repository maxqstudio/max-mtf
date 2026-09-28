from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

import factory.champion_factory as cf
import factory.factory_jobs as fj
import factory.factory_orchestrator as fo
def req(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ', msg)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding='utf-8')


def test_discovery_commit_order():
    src=inspect.getsource(cf.run_discovery_pool)
    seal=src.rfind('_stage_seal(run,"DISCOVERY"')
    manifest=src.rfind('_write(run/"factory_manifest.json",manifest)')
    req(seal >= 0 and manifest > seal, 'Discovery publishes terminal manifest only after terminal seal exists')


def test_retry_rejects_tampered_failure_evidence():
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/'F'; fd.mkdir()
        contract={'schema':'TEST_CPCV_CONTRACT','x':1}
        write_json(fd/'cpcv_qualification_evidence.json',{'rows':[{'pool_id':'P1'}]})
        write_json(fd/'cpcv_failure_topology.json',{'stage':'CPCV'})
        seal=cf._stage_seal(fd,'CPCV',contract=contract,files=['cpcv_qualification_evidence.json'])
        write_json(fd/'factory_manifest.json',{
            'status':'CPCV_NO_SURVIVOR','stage':'CPCV','research_contract_hash':'',
            'cpcv':{'stage_contract':contract,'terminal_seal_hash':seal['seal_hash']},
        })
        cfg=Path(td)/'config/config.json'; write_json(cfg,{})
        write_json(fd/'cpcv_qualification_evidence.json',{'rows':[{'pool_id':'TAMPER'}]})
        try:
            cf.retry_failure_scientist_learning(fd,cfg)
        except RuntimeError as exc:
            req('artifact tamper' in str(exc), 'Scientist failure-learning retry rejects tampered terminal evidence')
        else:
            raise AssertionError('tampered CPCV evidence was accepted by Scientist retry')


def test_champion_terminal_consumer_verifies_seal():
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/'F'; fd.mkdir()
        champion={'pool_id':'P1','family':'LightGBM'}
        write_json(fd/'champion.json',champion)
        seal=cf._stage_seal(fd,'CHAMPION',contract={'schema':'TEST_CHAMPION'},files=['champion.json'])
        write_json(fd/'factory_manifest.json',{
            'status':'CHAMPION','champion':'P1',
            'champion_terminal_seal':'champion_terminal_seal.json',
            'champion_terminal_seal_hash':seal['seal_hash'],
        })
        out=cf.verify_champion_terminal_authority(fd)
        req(out['champion']['pool_id']=='P1', 'Champion terminal consumer accepts exact sealed artifact')
        write_json(fd/'champion.json',{'pool_id':'P1','family':'TAMPER'})
        try:
            cf.verify_champion_terminal_authority(fd)
        except RuntimeError as exc:
            req('artifact tamper' in str(exc), 'Champion terminal consumer rejects post-promotion artifact tamper')
        else:
            raise AssertionError('tampered Champion artifact was trusted')


def test_completed_factory_history_idempotent():
    state={}
    fo._record_completed_factory(state,'F1','CPCV_NO_SURVIVOR')
    fo._record_completed_factory(state,'F1','CPCV_NO_SURVIVOR')
    req(len(state['completed_factories'])==1, 'Orchestrator completed-factory history is idempotent across WAIT/RESUME')


def test_resume_rejects_other_active_job():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); app=root/'app'; app.mkdir()
        target={'schema':'CP_FACTORY_JOB_V3','job_id':'TARGET','action':'AUTO','status':'PAUSED','created_utc':fj.utcnow(),'updated_utc':fj.utcnow(),'payload':{},'pid':None}
        other={'schema':'CP_FACTORY_JOB_V3','job_id':'OTHER','action':'MANUAL','status':'RUNNING','created_utc':fj.utcnow(),'updated_utc':fj.utcnow(),'payload':{},'pid':123}
        fj.atomic_write_json(fj.job_paths(root,'TARGET')['job'],target)
        fj.atomic_write_json(fj.job_paths(root,'OTHER')['job'],other)
        old_alive=fj._alive_worker_pids
        old_spawn=fj._spawn_worker
        fj._alive_worker_pids=lambda _root,j: [int(j.get('pid') or 123)] if str(j.get('status')) in fj.ACTIVE_STATUSES else []
        fj._spawn_worker=lambda *a,**k: (_ for _ in ()).throw(AssertionError('spawn must not run'))
        try:
            try:
                fj.resume_job(root,app,'TARGET')
            except RuntimeError as exc:
                req('job aktif lain' in str(exc), 'RESUME cannot create a second concurrent Factory worker')
            else:
                raise AssertionError('resume allowed while another job was active')
        finally:
            fj._alive_worker_pids=old_alive
            fj._spawn_worker=old_spawn


def test_forward_wait_resumes_same_factory():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); fid='FACTORY_WAIT'; fd=root/fid; fd.mkdir(parents=True)
        state={
            'schema':'CP_MASTER_ORCHESTRATOR_V1','orchestrator_id':'JOB_WAIT','status':'WAITING_FOR_NEW_FORWARD_DATA',
            'cycle':1,'current_factory_id':fid,'stage':'WAIT_FORWARD_DATA','completed_factories':[],
            'created_utc':fo._utc(),'max_cycles':0,'consecutive_empty_cycles':0,
        }
        fo._save(fo._state_path(root,'JOB_WAIT'),state)
        write_json(fd/'factory_manifest.json',{'status':'FORWARD_INSUFFICIENT_SAMPLE','factory_id':fid})
        old=fo.run_forward_championship
        seen=[]
        def fake_forward(factory_dir,*args,**kwargs):
            seen.append(Path(factory_dir).name)
            write_json(fd/'factory_manifest.json',{'status':'NO_CHAMPION_FORWARD_FAIL','factory_id':fid})
            return {'status':'NO_CHAMPION_FORWARD_FAIL','factory':str(fd)}
        fo.run_forward_championship=fake_forward
        try:
            out=fo.run_auto_factory(root,'dataset.csv','config.json','2020-01-01','2021-01-01','2021-01-02','2022-01-01','2022-01-02','2023-01-01',orchestrator_id='JOB_WAIT',resume=True)
        finally:
            fo.run_forward_championship=old
        req(seen==[fid] and Path(out['factory']).name==fid, 'WAITING_FOR_NEW_FORWARD_DATA resumes the same Factory, not a new research cycle')


def test_worker_wait_states_are_resumable():
    src=(Path(__file__).resolve().parents[1]/'factory/factory_worker.py').read_text(encoding='utf-8')
    req('WAITING_FOR_NEW_FORWARD_DATA' in src and 'FORWARD_INSUFFICIENT_SAMPLE' in src and 'job["status"]="PAUSED"' in src,
        'Worker persists Forward wait states as resumable PAUSED jobs')


def test_registry_lock_is_enforced_at_create_and_resume():
    a=inspect.getsource(fj.start_job); b=inspect.getsource(fj.resume_job)
    req('with _job_registry_lock(factory_root)' in a and 'with _job_registry_lock(factory_root)' in b,
        'Job create and resume share one cross-process registry mutex')


def test_stage_chain_fail_closed_markers():
    csrc=(Path(__file__).resolve().parents[1]/'factory/champion_factory.py').read_text(encoding='utf-8')
    required=[
        '_verify_stage_seal(fd,"DISCOVERY"',
        '_verify_stage_seal(fd,"CPCV"',
        '_verify_stage_seal(fd,"TOURNAMENT"',
        '_verify_stage_seal(fd,"MONTE_CARLO"',
        'verify_champion_terminal_authority',
    ]
    req(all(x in csrc for x in required), 'Cross-stage handoffs require sealed upstream authority through Champion')


if __name__=='__main__':
    test_discovery_commit_order()
    test_retry_rejects_tampered_failure_evidence()
    test_champion_terminal_consumer_verifies_seal()
    test_completed_factory_history_idempotent()
    test_resume_rejects_other_active_job()
    test_forward_wait_resumes_same_factory()
    test_worker_wait_states_are_resumable()
    test_registry_lock_is_enforced_at_create_and_resume()
    test_stage_chain_fail_closed_markers()
    print('STAGE8_E2E_WORKFLOW_BACKEND_CONTRACT PASS')
