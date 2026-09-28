from __future__ import annotations
import json
import tempfile
import time
from pathlib import Path

from factory.factory_jobs import start_job, load_job
from core.settings_store import sanitize_ui_state

ROOT=Path(__file__).resolve().parents[1]


def check(cond,msg):
    if not cond: raise AssertionError(msg)


def main():
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    worker=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')
    check('disable_pass_early_stop' in sup and '(not disable_pass_early_stop)' in sup,'Supervisor PASS early-stop guard missing')
    check('type(e).__name__' in worker and 'job[\"error\"]' in worker,'Factory worker persists explicit exception type instead of blank failure')
    check('ac["disable_pass_early_stop"] = True' in cf or 'ac["disable_pass_early_stop"]=True' in cf,'Champion Factory must disable first-winner early stop')
    check('factory_generation_done' in cf,'generation completion progress missing')
    check('@st.fragment(run_every="2s")' in app,'Discovery monitor must refresh without blocking whole app')
    check('Live candidate leaderboard' in app and 'read_factory_candidates' in app,'live candidate leaderboard missing')
    check('start_factory_job' in app and 'STARTED_BACKGROUND' in app,'Scientist/Discovery background routing missing')
    check('else "STOP"' in app and 'request_factory_stop' in app and 'pending_research_stop' in app,'explicit verified stop control / immediate stop state missing')
    check('result_row' in worker and 'candidates' in worker,'worker must persist live candidate rows')
    clean=sanitize_ui_state({'factory_auto_start':True,'factory_start_btn':True,'missing_FAKE_gate':False,'factory_stop_JOB_X':False,'factory_pause_JOB_X':False,'factory_resume_JOB_X':False,'factory_force_stop_JOB_X':False,'factory_discovery_from':'2021-01-01','factory_selected':'FACTORY_X'})
    check(all(k not in clean for k in ('factory_auto_start','factory_start_btn','missing_FAKE_gate','factory_stop_JOB_X','factory_pause_JOB_X','factory_resume_JOB_X','factory_force_stop_JOB_X','factory_discovery_from')) and clean.get('factory_selected')=='FACTORY_X','transient lifecycle button persistence regression')

    # Prove start_job returns while a child keeps running: UI/navigation lifecycle is not the worker lifecycle.
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); appdir=td/'app'; appdir.mkdir(); froot=td/'factory'
        stub=appdir/'factory/factory_worker.py'
        stub.write_text('''import argparse,time\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument("--factory-root");p.add_argument("--job-id");a=p.parse_args()\ntime.sleep(.45)\nPath(a.factory_root).mkdir(parents=True,exist_ok=True)\n(Path(a.factory_root)/"worker_survived_ui_return.txt").write_text(a.job_id)\n''',encoding='utf-8')
        t0=time.perf_counter(); job=start_job(froot,appdir,'DISCOVERY',{'target':12}); elapsed=time.perf_counter()-t0
        check(elapsed<0.35,f'background start blocked caller for {elapsed:.3f}s')
        disk_status=load_job(froot,job['job_id']).get('status')
        check(job.get('status')=='DATA_QUALITY_PREFLIGHT' and disk_status=='DATA_QUALITY_PREFLIGHT','launcher/sidecar must expose Data Quality preflight before research RUNNING')
        deadline=time.time()+3
        marker=froot/'worker_survived_ui_return.txt'
        while time.time()<deadline and not marker.exists(): time.sleep(.05)
        check(marker.exists(),'child worker did not survive after start_job returned')
    print('FACTORY_BACKGROUND_CONTINUITY PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
