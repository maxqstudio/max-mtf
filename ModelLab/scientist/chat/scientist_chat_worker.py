from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from scientist.chat.scientist_chat import discuss
from max_graph.scientist_chat_graph import run_scientist_chat_graph
from scientist.chat.scientist_chat_jobs import paths_for, utcnow, _read_json, update_active_job, commit_terminal_job


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--app-dir",required=True); ap.add_argument("--job-id",required=True); args=ap.parse_args()
    app_dir=Path(args.app_dir); pp=paths_for(app_dir,args.job_id); job=_read_json(pp["job"],{}); req=_read_json(pp["request"],{})
    if not job or not req: return 2
    job=update_active_job(app_dir,args.job_id,{"status":"RUNNING","phase":"BUILDING_CONTEXT","phase_label":"Reading research evidence"}) or dict(job)
    last_flush=[0.0]
    def progress(ev):
        nonlocal job
        ev=dict(ev or {})
        patch={
            "phase":str(ev.get("phase") or job.get("phase") or "RUNNING"),
            "phase_label":str(ev.get("label") or job.get("phase_label") or "Scientist working"),
        }
        if ev.get("partial_text") is not None:
            patch["partial_text"]=str(ev.get("partial_text") or "")
        if isinstance(ev.get("process_steps"),list):
            patch["process_steps"]=ev.get("process_steps")
        if ev.get("model"):
            patch["active_model"]=str(ev.get("model"))
        if patch["phase"]=="STREAMING" and not job.get("first_token_utc") and patch.get("partial_text"):
            patch["first_token_utc"]=utcnow()
        now=time.monotonic()
        if now-last_flush[0] >= 0.12 or patch["phase"] in {"BUILDING_CONTEXT","CALLING_MODEL","WAITING_FIRST_TOKEN","BUFFERED_RESPONSE","COMPLETED"}:
            current=update_active_job(app_dir,args.job_id,patch)
            if current:
                job=current
            last_flush[0]=now
    try:
        if os.environ.get("MAX_LANGGRAPH_ACCEPTANCE_LEGACY_COMPAT")=="1":
            answer=discuss(
                req.get("llm_cfg") or {}, selected_model=str(req.get("selected_model") or ""),
                api_key=os.environ.get("MAX_SCIENTIST_CHAT_API_KEY", ""), history=req.get("history") or [],
                user_prompt=str(req.get("user_prompt") or ""), context=req.get("context") or {},
                allow_fallback=bool(req.get("allow_fallback",False)), progress_callback=progress,
            )
        else:
            answer=run_scientist_chat_graph(
                app_dir=app_dir, request_id=str(req.get("request_id") or args.job_id),
                thread_id=str(req.get("thread_id") or args.job_id), discuss_fn=discuss,
                llm_cfg=req.get("llm_cfg") or {}, selected_model=str(req.get("selected_model") or ""),
                api_key=os.environ.get("MAX_SCIENTIST_CHAT_API_KEY", ""), history=req.get("history") or [],
                user_prompt=str(req.get("user_prompt") or ""), context=req.get("context") or {},
                allow_fallback=bool(req.get("allow_fallback",False)), progress_callback=progress,
            )
        final=commit_terminal_job(app_dir,args.job_id,"COMPLETED",{
            "phase":"COMPLETED","phase_label":"Analysis complete",
            "partial_text":str((answer or {}).get("content") or job.get("partial_text") or ""),
            "process_steps":((answer or {}).get("process") or {}).get("steps") or job.get("process_steps") or [],
            "result":answer,"error":None,"completed_utc":utcnow(),
        })
        return 0 if str(final.get("status") or "")=="COMPLETED" else 1
    except Exception as exc:
        final=commit_terminal_job(app_dir,args.job_id,"FAILED",{
            "phase":"FAILED","phase_label":"Request failed","result":None,
            "error":f"{type(exc).__name__}: {exc}","attempts":getattr(exc,"attempts",[]) or [],"failed_utc":utcnow(),
        })
        return 1 if str(final.get("status") or "")!="COMPLETED" else 0


if __name__=="__main__": raise SystemExit(main())
