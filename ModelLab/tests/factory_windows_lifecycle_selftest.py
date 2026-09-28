from __future__ import annotations
import tempfile
from pathlib import Path
from unittest.mock import patch
import factory.factory_jobs as factory_jobs
def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    # Critical regression: Windows liveness checks must never call os.kill(pid,0).
    with patch.object(factory_jobs.os,'name','nt'), \
         patch.object(factory_jobs,'_windows_pid_alive',return_value=True) as winprobe, \
         patch.object(factory_jobs.os,'kill',side_effect=AssertionError('os.kill must not be used on Windows')):
        req(factory_jobs._pid_alive(12345) is True,'Windows liveness uses non-destructive Win32 probe')
        req(winprobe.call_count==1,'Win32 process probe invoked exactly once')

    with tempfile.TemporaryDirectory() as td:
        root=Path(td); jid='JOB_PAGE_SWITCH'; paths=factory_jobs.job_paths(root,jid)
        job={'schema':'CP_FACTORY_JOB_V2','job_id':jid,'action':'AUTO','status':'RUNNING','created_utc':factory_jobs.utcnow(),'updated_utc':factory_jobs.utcnow(),'pid':2222,'payload':{},'target':12}
        factory_jobs.atomic_write_json(paths['job'],job)
        factory_jobs.atomic_write_json(paths['process'],{'schema':'CP_FACTORY_PROCESS_OWNER_V1','job_id':jid,'pid':2222,'spawned_utc':factory_jobs.utcnow()})
        with patch.object(factory_jobs,'_pid_alive',return_value=True):
            a=factory_jobs.load_job(root,jid); b=factory_jobs.latest_job(root,active_only=True); c=factory_jobs.load_job(root,jid)
        req(a.get('status')=='RUNNING' and b and b.get('status')=='RUNNING' and c.get('status')=='RUNNING','repeated UI/page reads cannot mark a live worker INTERRUPTED')
        raw=factory_jobs.read_json(paths['job'],{})
        req(raw.get('status')=='RUNNING','page reads do not rewrite live worker state')

    src=Path(factory_jobs.__file__).read_text(encoding='utf-8')
    req('Never use os.kill(pid, 0) on Windows' in src,'source documents destructive Windows os.kill hazard')
    req('STOP_FAILED_WORKER_STILL_ALIVE' in src,'STOP cannot claim success while worker is alive')
    print('FACTORY_WINDOWS_LIFECYCLE_SELFTEST PASS')

if __name__=='__main__':
    main()
