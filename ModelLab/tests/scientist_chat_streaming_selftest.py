from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    provider=(ROOT/'host/provider_catalog.py').read_text(encoding='utf-8')
    chat=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
    worker=(ROOT/'scientist/chat/scientist_chat_worker.py').read_text(encoding='utf-8')
    jobs=(ROOT/'scientist/chat/scientist_chat_jobs.py').read_text(encoding='utf-8')
    comp=(ROOT/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    assert 'def stream_chat_completion' in provider and '"stream":True' in provider
    assert 'on_delta' in provider
    assert 'def chat_model_profile' in chat
    for phase in ('BUILDING_CONTEXT','CALLING_MODEL','WAITING_FIRST_TOKEN','STREAMING','COMPLETED'):
        assert phase in chat or phase in worker
    assert 'stream_chat_completion' in chat and 'progress_callback' in chat
    assert 'partial_text' in worker and 'process_steps' in worker
    assert 'MAX_SCIENTIST_CHAT_JOB_V3_CAS' in jobs and 'commit_terminal_job' in jobs and '_registry_lock' in jobs
    assert 'showStreaming' in comp and 'pending_partial_text' in app
    # Raw internal reasoning must not be deliberately rendered.
    assert 'reasoning_content' not in comp
    assert 'request_id' in jobs and 'Duplicate send ignored' in app
    # Owner runtime regression: partial text must reconcile automatically and render progressively.
    assert 'setStateValue("reconcile"' in comp and '_scientistReconcileInterval' in comp and 'setInterval(' in comp and 'on_reconcile_change=lambda: None' in comp
    assert 'Math.min(5,Math.ceil(remain/80))' in comp and 'setTimeout(tick,26)' in comp, 'visible typewriter cadence regression'
    assert 'setTriggerValue("poll"' not in comp
    print('SCIENTIST CHAT STREAMING CONTRACT PASS')

if __name__=='__main__':
    main()
