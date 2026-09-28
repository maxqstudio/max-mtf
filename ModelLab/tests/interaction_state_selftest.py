from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scientist.chat.scientist_chat_jobs import paths_for, load_job, cancel_job, _atomic_write_json, utcnow

ROOT=Path(__file__).resolve().parents[1]

def req(c,m):
    if not c: raise AssertionError(m)

app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
comp=(ROOT/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')
jobs=(ROOT/'scientist/chat/scientist_chat_jobs.py').read_text(encoding='utf-8')
worker=(ROOT/'scientist/chat/scientist_chat_worker.py').read_text(encoding='utf-8')

req('pending_research_start' in app and 'STARTING…' in app and 'disabled=(dataset is None or pending)' in app,'START RESEARCH does not switch immediately to disabled pending state')
req('cp-busy-spinner' in app and 'Preflight · Data Quality · freezing research plan…' in app,'visible START loading indicator missing')
req('pending_research_stop' in app and 'STOPPING…' in app,'research STOP immediate feedback missing')
req('pending_scientist_chat_job' in app and 'start_scientist_chat_job' in app and 'cancel_scientist_chat_job' in app,'Scientist generation is not cancellable/background')
req('setTriggerValue("stop"' in comp and 'thinking-stop' in comp,'chat Stop button missing from thinking state')
req('on_poll_change=' not in comp,'Scientist mount must not register the extra poll callback that can blank the V2 drawer in owner runtime')
req('on_clear_change=on_clear_change or (lambda: None)' in comp and '_scientist_chat_clear_requested' in app and 'on_clear_change=_request_scientist_clear' in app,'Scientist Clear is not pre-render server-authoritative')
req('draft.disabled=pending; send.disabled=model.disabled||pending||resetting' in comp,'Clear must keep textarea writable while SEND waits for new thread')
req('const wasResetting=root.dataset.resetting==="1"' in comp and 'sessionStorage.getItem(draftKey)||draft.value' in comp,'draft typed during Clear reset is not preserved')
req('_workspace_render_pending' in app and 'Rendering ' in app and 'st.toast(f\"{nav_page} ready\"' in app,'page render progress/ready feedback missing')
req('Data saved' in app and 'Settings saved' in app and 'Settings save failed' in app,'persistent Data/Settings save acknowledgement missing')
req('assistant-model-label' in comp and 'msg.answered_by' in comp,'actual answering model label missing from assistant bubble')
req('MAX_SCIENTIST_CHAT_API_KEY' in jobs and 'MAX_SCIENTIST_CHAT_API_KEY' in worker,'Chat worker must receive API key out-of-band')
req('hard_timeout_sec' in jobs and 'CHAT_HARD_TIMEOUT' in jobs,'infinite thinking hard-timeout guard missing')
req('cp-side-mark' not in app[app.index('with st.container(key="left_nav_header")'):app.index('with st.container(key="left_nav_nav")')],'CP mark still rendered in left header')
req('cp-side-build' in app and 'text-overflow:clip!important' in app,'left brand text no-clip contract missing')

# Process cancel authority: a live child must be killable without waiting for a provider.
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    proc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    jid='CHAT_TEST_CANCEL'
    p=paths_for(td,jid)['job']
    _atomic_write_json(p,{'schema':'MAX_SCIENTIST_CHAT_JOB_V1','job_id':jid,'status':'RUNNING','created_utc':utcnow(),'updated_utc':utcnow(),'pid':proc.pid,'requested_model':'mock'})
    out=cancel_job(td,jid)
    req(out.get('status')=='CANCELLED','cancel_job did not commit CANCELLED')
    deadline=time.time()+2
    while proc.poll() is None and time.time()<deadline: time.sleep(.05)
    req(proc.poll() is not None,'chat worker process survived cancel')

# Dead worker reconciliation must fail closed rather than leave the UI thinking forever.
with tempfile.TemporaryDirectory() as td:
    td=Path(td); jid='CHAT_TEST_DEAD'; p=paths_for(td,jid)['job']
    _atomic_write_json(p,{'schema':'MAX_SCIENTIST_CHAT_JOB_V1','job_id':jid,'status':'RUNNING','created_utc':utcnow(),'updated_utc':utcnow(),'pid':99999999,'requested_model':'mock','hard_timeout_sec':90})
    out=load_job(td,jid)
    req(out.get('status')=='FAILED' and out.get('error')=='CHAT_WORKER_NOT_ALIVE','dead chat worker did not fail closed')

print('PASS interaction_state_selftest')
