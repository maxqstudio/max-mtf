from __future__ import annotations
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import factory.factory_jobs as factory_jobs
def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def test_retry_atomic_replace():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'job.json'
        real=factory_jobs.os.replace
        calls={'n':0}
        def flaky(src,dst):
            calls['n']+=1
            if calls['n'] <= 3:
                raise PermissionError(5,'Access is denied',str(dst))
            return real(src,dst)
        with patch.object(factory_jobs.os,'replace',side_effect=flaky):
            factory_jobs.atomic_write_json(p,{'ok':True,'n':7})
        req(json.loads(p.read_text(encoding='utf-8'))=={'ok':True,'n':7},'atomic JSON survives transient WinError 5 / PermissionError')
        req(calls['n']==4,'atomic writer retries instead of failing on first Windows lock')
        req(not list(Path(td).glob('*.tmp')),'atomic writer removes temporary files')


def test_stop_is_verified_hard_stop():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        jid='JOB_TEST'
        paths=factory_jobs.job_paths(root,jid)
        job={'schema':'CP_FACTORY_JOB_V2','job_id':jid,'action':'DISCOVERY','status':'RUNNING','created_utc':factory_jobs.utcnow(),'updated_utc':factory_jobs.utcnow(),'pid':4242}
        factory_jobs.atomic_write_json(paths['job'],job)
        result={'terminated':True,'pids':[4242],'alive_after':[],'details':[{'pid':4242,'returncode':0,'output':'ok'}]}
        with patch.object(factory_jobs,'_terminate_worker_tree',return_value=result):
            view=factory_jobs.request_stop(root,jid)
        req(paths['stop'].exists(),'STOP writes operator sentinel before termination')
        req(view.get('status')=='STOPPED','STOP commits STOPPED only after verified termination')
        req((view.get('stop_verification') or {}).get('terminated') is True,'STOP stores termination evidence')

        factory_jobs.atomic_write_json(paths['job'],job)
        failed={'terminated':False,'pids':[4242],'alive_after':[4242],'details':[{'pid':4242,'returncode':5,'output':'denied'}]}
        with patch.object(factory_jobs,'_terminate_worker_tree',return_value=failed):
            view=factory_jobs.request_stop(root,jid)
        req(view.get('status')=='STOP_FAILED','STOP must fail loud while worker remains alive')
        req(view.get('pid')==4242,'STOP_FAILED retains live worker pid')


def test_parent_does_not_rewrite_after_spawn():
    class FakeProc:
        pid=4242
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'factory'; app=Path(td)/'app'; app.mkdir()
        (app/'factory/factory_worker.py').write_text('# fake',encoding='utf-8')
        writes=[]
        real_atomic=factory_jobs.atomic_write_json
        def track(path,obj):
            writes.append((Path(path).name,str(obj.get('status')) if isinstance(obj,dict) else ''))
            return real_atomic(path,obj)
        with patch.object(factory_jobs,'atomic_write_json',side_effect=track), patch.object(factory_jobs.subprocess,'Popen',return_value=FakeProc()):
            view=factory_jobs.start_job(root,app,'DISCOVERY',{'target':12})
        req(len([x for x in writes if x[0]==view['job_id']+'.json'])==1,'parent writes authoritative job JSON only once before worker spawn')
        req(view.get('status')=='DATA_QUALITY_PREFLIGHT' and view.get('pid')==4242,'START must expose Data Quality preflight before research RUNNING without competing job JSON write')
        req(factory_jobs.job_paths(root,view['job_id'])['process'].exists(),'launcher persists process-owner sidecar immediately after spawn')
        with patch.object(factory_jobs,'_pid_alive',return_value=True):
            disk=factory_jobs.load_job(root,view['job_id'])
        req(disk.get('status')=='DATA_QUALITY_PREFLIGHT' and disk.get('pid')==4242,'sidecar must preserve Data Quality preflight authority during worker claim race')


def main():
    test_retry_atomic_replace()
    test_stop_is_verified_hard_stop()
    test_parent_does_not_rewrite_after_spawn()
    print('FACTORY_JOB_IO_SELFTEST PASS')

if __name__=='__main__':
    main()
