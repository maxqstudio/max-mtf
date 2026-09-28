from __future__ import annotations
import tempfile
from pathlib import Path
from unittest.mock import patch
import factory.factory_jobs as factory_jobs
def req(x,msg):
    if not x: raise AssertionError(msg)
    print("PASS ",msg)

def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/"factory"; app=Path(td)/"app"; app.mkdir(parents=True)
        (app/'factory/factory_worker.py').write_text("# fake",encoding="utf-8")
        jid="JOB_ABORT"; paths=factory_jobs.job_paths(root,jid)
        job={"schema":"CP_FACTORY_JOB_V2","job_id":jid,"action":"AUTO","status":"PAUSED","created_utc":factory_jobs.utcnow(),"updated_utc":factory_jobs.utcnow(),"pid":None,"payload":{},"target":12}
        factory_jobs.atomic_write_json(paths["job"],job)
        result={"terminated":True,"pids":[],"alive_after":[],"details":[]}
        with patch.object(factory_jobs,"_terminate_worker_tree",return_value=result):
            out=factory_jobs.abort_job(root,jid)
        req(out["status"]=="ABORTED","ABORT commits terminal ABORTED after verified termination")
        req("ABORTED" not in factory_jobs.RESUMABLE_STATUSES,"ABORTED is never resumable")
        req("ABORTED" in factory_jobs.TERMINAL_STATUSES,"ABORTED is terminal authority")
        latest=factory_jobs.latest_job(root,"AUTO",active_only=False)
        req(latest and latest["status"]=="ABORTED","latest job remains auditable as ABORTED")
        # New research must be allowed after abort.
        fake={"job_id":"NEW","status":"RUNNING","pid":123}
        with patch.object(factory_jobs,"_spawn_worker",return_value=fake):
            started=factory_jobs.start_job(root,app,"AUTO",{"target":12})
        req(started["status"]=="RUNNING","new START is allowed after ABORTED job")
        appsrc=((Path(__file__).resolve().parents[1]/'ui/app.py')).read_text(encoding="utf-8")
        req("abort_factory_job(FACTORY_DIR,jid)" in appsrc,"sidebar ABORT uses terminal abort authority")
        req("force_factory_stop(FACTORY_DIR,jid); st.rerun()" not in appsrc.split('factory_global_abort_')[-1][:220],"sidebar ABORT no longer aliases FORCE STOP")
    print("ABORT_LIFECYCLE_SELFTEST PASS")

if __name__=="__main__": main()
