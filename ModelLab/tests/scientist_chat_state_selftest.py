from __future__ import annotations

import tempfile
from pathlib import Path

from scientist.chat.scientist_chat import ScientistChatStore
from scientist.chat.scientist_chat_jobs import _atomic_write_json, cancel_job, paths_for

ROOT = Path(__file__).resolve().parents[1]


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


# 1) Clear Chat must rotate a persistent thread id and stale history must be unable
# to write back into the new thread.
with tempfile.TemporaryDirectory() as td:
    store = ScientistChatStore(Path(td) / "chat")
    fid = "F_CHAT_STATE"
    store.save(fid, [{"role": "user", "content": "old"}])
    old_thread = store.current_thread_id(fid)
    req(store.load(fid)[0]["content"] == "old", "precondition: old chat missing")
    store.clear(fid)
    new_thread = store.current_thread_id(fid)
    req(new_thread and new_thread != old_thread, "Clear Chat must rotate persistent thread id")
    req(store.load(fid) == [], "Clear Chat must leave canonical empty history")
    stale_blocked = False
    try:
        store.save(fid, [{"role": "assistant", "content": "stale resurrection"}], thread_id=old_thread)
    except RuntimeError as exc:
        stale_blocked = "STALE_SCIENTIST_CHAT_THREAD" in str(exc)
    req(stale_blocked, "stale pre-clear thread must not be able to repopulate history")
    req(store.load(fid) == [], "stale save attempt changed cleared history")
    store.save(fid, [{"role": "user", "content": "new"}], thread_id=new_thread)
    req(store.load(fid)[0]["content"] == "new", "current thread save failed")

# 2) A late Stop click must never mutate a terminal COMPLETED result to CANCELLED.
with tempfile.TemporaryDirectory() as td:
    app_dir = Path(td)
    jid = "CHAT_TERMINAL_IMMUTABLE"
    pp = paths_for(app_dir, jid)
    _atomic_write_json(pp["job"], {
        "job_id": jid,
        "status": "COMPLETED",
        "pid": None,
        "thread_id": "THREAD_X",
        "result": {"content": "done"},
    })
    out = cancel_job(app_dir, jid)
    req(out.get("status") == "COMPLETED", "late Stop overwrote COMPLETED terminal state")

# 3) Client must force reconciliation while pending; do not depend only on
# Streamlit fragment run_every, which was observed to stall with the V2 component.
component = (ROOT / "scientist/chat/scientist_chat_component.py").read_text(encoding="utf-8")
app = (ROOT / "ui/app.py").read_text(encoding="utf-8")
jobs = (ROOT / "scientist/chat/scientist_chat_jobs.py").read_text(encoding="utf-8")
req('setStateValue("reconcile"' in component and '_scientistReconcileInterval' in component and 'setInterval(' in component and '"reconcile": ""' in component and 'on_reconcile_change=lambda: None' in component,
    "stable client state reconciliation heartbeat missing")
req('setTriggerValue("poll"' not in component and 'on_poll_change=' not in component,
    "legacy poll trigger/callback must remain absent because it broke owner V2 runtime mounting")
req('thread_id:threadId' in component, "component events do not carry persistent thread identity")
req('event_thread != thread_id' in app and 'Stale send ignored after chat reset.' in app,
    "server does not reject stale SEND events after Clear Chat")
req('job_thread != current_thread' in app and 'Stale generation discarded after chat reset.' in app,
    "server does not discard stale terminal/active jobs after Clear Chat")
req('keep scientist_component_last_* nonce markers' in app,
    "Clear Chat must retain event dedupe markers so V2 trigger replay cannot resurrect old SEND")
req('if str(job.get("status") or "") in TERMINAL_STATUSES' in jobs,
    "terminal chat job state is not immutable")

print("SCIENTIST_CHAT_STATE_SELFTEST PASS")
