from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_STATUSES={"QUEUED","RUNNING"}
TERMINAL_STATUSES={"COMPLETED","FAILED","CANCELLED"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, obj: Any) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    tmp=Path(tmp_name)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
            json.dump(obj,f,ensure_ascii=False,indent=2,default=str)
            f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        os.replace(tmp,path)
    finally:
        try:
            if tmp.exists(): tmp.unlink()
        except OSError: pass


def _read_json(path: Path, default=None):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return {} if default is None else default


def root_for(app_dir: str|Path) -> Path:
    p=Path(app_dir)/".scientist_chat_jobs"; p.mkdir(parents=True,exist_ok=True); return p


@contextlib.contextmanager
def _registry_lock(app_dir: str|Path):
    """OS-backed cross-process mutex for Chat request/job lifecycle authority."""
    lock_path=root_for(app_dir)/".registry.lock"
    f=open(lock_path,"a+b")
    try:
        f.seek(0,os.SEEK_END)
        if f.tell()==0:
            f.write(b"0"); f.flush()
        f.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name=="nt":
                import msvcrt
                f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        finally:
            f.close()


def paths_for(app_dir: str|Path, job_id: str) -> dict[str,Path]:
    root=root_for(app_dir); stem=str(job_id)
    return {
        "job":root/f"{stem}.json",
        "request":root/f"{stem}.request.json",
        "log":root/f"{stem}.log",
    }


def _pid_alive(pid: Any) -> bool:
    try: pid=int(pid)
    except Exception: return False
    if pid<=0: return False
    if os.name=="nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
            PROCESS_QUERY_LIMITED_INFORMATION=0x1000; STILL_ACTIVE=259
            kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
            kernel32.OpenProcess.restype=wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype=wintypes.BOOL
            kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,False,pid)
            if not handle: return ctypes.get_last_error()==5
            try:
                code=wintypes.DWORD(0)
                return bool(kernel32.GetExitCodeProcess(handle,ctypes.byref(code))) and int(code.value)==STILL_ACTIVE
            finally: kernel32.CloseHandle(handle)
        except Exception: return True
    try: os.kill(pid,0); return True
    except PermissionError: return True
    except OSError: return False


def _terminate_pid(pid: Any) -> None:
    try: pid=int(pid)
    except Exception: return
    if pid<=0 or not _pid_alive(pid): return
    if os.name=="nt":
        try: subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=8,check=False)
        except Exception: pass
    else:
        try:
            try: os.killpg(pid,signal.SIGKILL)
            except Exception: os.kill(pid,signal.SIGKILL)
        except Exception: pass
    deadline=time.monotonic()+4.0
    while _pid_alive(pid) and time.monotonic()<deadline: time.sleep(.08)


def _age_seconds(value: Any) -> float:
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
    except Exception: return 1e9


def _find_request_job_unlocked(app_dir: str|Path, request: dict) -> dict:
    request_id=str(request.get("request_id") or "").strip()
    if not request_id:
        return {}
    factory_id=str(request.get("factory_id") or "NO_FACTORY")
    thread_id=str(request.get("thread_id") or "")
    for p in sorted(root_for(app_dir).glob("CHAT_*.json")):
        if p.name.endswith(".request.json"):
            continue
        job=_read_json(p,{})
        if not isinstance(job,dict) or not job:
            continue
        if (str(job.get("request_id") or "")==request_id
            and str(job.get("factory_id") or "NO_FACTORY")==factory_id
            and str(job.get("thread_id") or "")==thread_id):
            return dict(job)
    return {}


def update_active_job(app_dir: str|Path, job_id: str, patch: dict) -> dict:
    """Merge progress only while the persisted job remains non-terminal."""
    pp=paths_for(app_dir,job_id)
    with _registry_lock(app_dir):
        job=_read_json(pp["job"],{})
        if not isinstance(job,dict) or not job:
            return {}
        if str(job.get("status") or "") in TERMINAL_STATUSES:
            return dict(job)
        out=dict(job); out.update(dict(patch or {})); out["updated_utc"]=utcnow()
        _atomic_write_json(pp["job"],out)
        return out


def commit_terminal_job(app_dir: str|Path, job_id: str, status: str, patch: dict|None=None) -> dict:
    """Monotonic terminal compare-and-set. First terminal writer wins permanently."""
    status=str(status or "").upper()
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Invalid Scientist Chat terminal status: {status}")
    pp=paths_for(app_dir,job_id)
    with _registry_lock(app_dir):
        job=_read_json(pp["job"],{})
        if not isinstance(job,dict) or not job:
            return {}
        if str(job.get("status") or "") in TERMINAL_STATUSES:
            return dict(job)
        out=dict(job); out.update(dict(patch or {})); out["status"]=status; out["pid"]=None; out["updated_utc"]=utcnow()
        _atomic_write_json(pp["job"],out)
        return out


def load_job(app_dir: str|Path, job_id: str) -> dict:
    pp=paths_for(app_dir,job_id)
    with _registry_lock(app_dir):
        job=_read_json(pp["job"],{})
    if not isinstance(job,dict) or not job: return {}
    status=str(job.get("status") or "")
    if status in ACTIVE_STATUSES and _age_seconds(job.get("created_utc")) > float(job.get("hard_timeout_sec",90) or 90):
        # Hard timeout owns exactly one monotonic terminal transition. Never create
        # CANCELLED and then rewrite it to FAILED.
        _terminate_pid(job.get("pid"))
        return commit_terminal_job(app_dir,job_id,"FAILED",{
            "error":"CHAT_HARD_TIMEOUT","phase":"FAILED","phase_label":"Hard timeout",
            "failed_utc":utcnow(),
        })
    if status in ACTIVE_STATUSES and not _pid_alive(job.get("pid")):
        # Worker vanished without committing a terminal state. Fail closed so UI
        # can never remain in an infinite "thinking" state.
        return commit_terminal_job(app_dir,job_id,"FAILED",{
            "error":"CHAT_WORKER_NOT_ALIVE","phase":"FAILED","phase_label":"Worker exited",
            "failed_utc":utcnow(),
        })
    return job


def start_job(app_dir: str|Path, request: dict, api_key: str) -> dict:
    app_dir=Path(app_dir)
    with _registry_lock(app_dir):
        existing=_find_request_job_unlocked(app_dir,request)
        if existing:
            return existing

        job_id=datetime.now(timezone.utc).strftime("CHAT_%Y%m%d_%H%M%S_")+uuid.uuid4().hex[:8].upper()
        pp=paths_for(app_dir,job_id)
        _llm=request.get("llm_cfg") or {}; _model=str(request.get("selected_model") or "")
        _profiles=_llm.get("chat_model_profiles") if isinstance(_llm.get("chat_model_profiles"),dict) else {}
        _profile=_profiles.get(_model) if isinstance(_profiles.get(_model),dict) else {}
        try: _timeout=int(_profile.get("timeout_sec",_llm.get("timeout_sec",60)) or 60)
        except Exception: _timeout=60
        job={
            "schema":"MAX_SCIENTIST_CHAT_JOB_V3_CAS","job_id":job_id,"status":"QUEUED",
            "created_utc":utcnow(),"updated_utc":utcnow(),"pid":None,
            "factory_id":str(request.get("factory_id") or "NO_FACTORY"),
            "request_id":str(request.get("request_id") or ""),
            "thread_id":str(request.get("thread_id") or ""),
            "requested_model":_model,
            "hard_timeout_sec":max(20,min(240,_timeout+25)),
            "phase":"QUEUED","phase_label":"Queued","partial_text":"","process_steps":[],
            "result":None,"error":None,
        }
        _atomic_write_json(pp["request"],request); _atomic_write_json(pp["job"],job)
        worker=app_dir/"scientist_chat_worker.py"
        env=os.environ.copy(); env["MAX_SCIENTIST_CHAT_API_KEY"]=str(api_key or "")
        logf=pp["log"].open("ab",buffering=0)
        try:
            kwargs={"cwd":str(app_dir),"stdin":subprocess.DEVNULL,"stdout":logf,"stderr":subprocess.STDOUT,"close_fds":True,"env":env}
            if os.name=="nt": kwargs["creationflags"]=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|getattr(subprocess,"CREATE_NO_WINDOW",0)
            proc=subprocess.Popen([sys.executable,str(worker),"--app-dir",str(app_dir),"--job-id",job_id],**kwargs)
        except Exception as exc:
            job.update({"status":"FAILED","error":f"CHAT_WORKER_START_FAILED: {type(exc).__name__}: {exc}","phase":"FAILED","phase_label":"Worker start failed","failed_utc":utcnow(),"updated_utc":utcnow()})
            _atomic_write_json(pp["job"],job)
            raise
        finally:
            logf.close()
        job["pid"]=int(proc.pid); job["status"]="RUNNING"; job["updated_utc"]=utcnow(); _atomic_write_json(pp["job"],job)
        return dict(job)


def cancel_job(app_dir: str|Path, job_id: str) -> dict:
    pp=paths_for(app_dir,job_id)
    with _registry_lock(app_dir):
        job=_read_json(pp["job"],{})
        if not job: return {}
        if str(job.get("status") or "") in TERMINAL_STATUSES:
            return dict(job)
        pid=job.get("pid")
    # Do not hold lifecycle mutex while waiting on process termination. The worker
    # may be racing to commit COMPLETED; whichever terminal CAS wins is immutable.
    _terminate_pid(pid)
    return commit_terminal_job(app_dir,job_id,"CANCELLED",{
        "cancelled_utc":utcnow(),"error":"CANCELLED_BY_OPERATOR","phase":"CANCELLED","phase_label":"Generation stopped",
    })


def cleanup_job_files(app_dir: str|Path, job_id: str) -> None:
    pp=paths_for(app_dir,job_id)
    for key in ("request",):
        try: pp[key].unlink()
        except FileNotFoundError: pass
        except OSError: pass
