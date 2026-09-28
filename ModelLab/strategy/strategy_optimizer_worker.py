from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import argparse, hashlib, json, math, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from factory.factory_jobs import atomic_write_json
from mtf.mtf_names import EXPERT_SUBDIR, OPTIMIZER_METRICS_CSV, OPTIMIZER_REPORT_XML, TESTER_SET
from strategy.strategy_optimizer import (
    EA_SOURCE, RUNS_ROOT, EVIDENCE_ROOT, DEFAULT_SPACE, OPTIMIZER_PF_MIN, OPTIMIZER_RF_MIN, OPTIMIZER_EXPECTANCY_R_MIN, OPTIMIZER_WEIGHTED_R_MIN,
    build_set_text, build_tester_ini, parse_optimization_xml, select_champion, deterministic_refine,
    scientist_refine, scientist_propose_ranges, validate_scientist_ranges, champion_payload, validate_request, apply_champion_to_canonical_ea,
    discover_optimization_reports, optimization_report_identity, report_matches_request, best_near_miss,
    write_champion_tester_preset, assert_champion_ea_set_parity,
)
from strategy.strategy_geometry import persist_optimizer_champion_authority, RUNTIME_AUTHORITY


ROOT=MODELLAB_ROOT

def now(): return datetime.now(timezone.utc).isoformat()
def atomic(p:Path,obj:dict):
    atomic_write_json(Path(p),obj)

def evidence_dir(job:Path)->Path:
    p=EVIDENCE_ROOT/job.name; p.mkdir(parents=True,exist_ok=True); return p

def update(status_path:Path,st:dict,status:str,message:str,**extra):
    previous=str(st.get("status") or "IDLE")
    stamp=now()
    transition={"from":previous,"to":str(status),"utc":stamp,"reason":str(message)}
    if "round" in extra: transition["round"]=int(extra.get("round") or 0)
    transitions=list(st.get("state_transitions") or [])
    if not transitions or transitions[-1].get("from")!=transition["from"] or transitions[-1].get("to")!=transition["to"] or transitions[-1].get("reason")!=transition["reason"]:
        transitions.append(transition)
    st.update(extra); st["state_transitions"]=transitions; st["status"]=status; st["message"]=message; st["updated_utc"]=stamp
    st.setdefault("first_failed_gate",None)
    atomic(status_path,st)
    ev=evidence_dir(status_path.parent); st["evidence_dir"]=str(ev); atomic(ev/"status.json",st)

def _read_compile_log(path:Path)->str:
    if not path.exists(): return ""
    raw=path.read_bytes()
    for enc in ("utf-16","utf-8-sig","utf-8","cp1252"):
        try: return raw.decode(enc)
        except Exception: pass
    return raw.decode("utf-8",errors="replace")

def _compile_error_excerpt(text:str)->list[str]:
    lines=[]
    for line in text.splitlines():
        low=line.lower()
        if " error" in low or ": error" in low or "errors," in low or "failed" in low:
            lines.append(line.strip())
    return lines[-20:]

def write_diagnostic(job:Path,stage:str,exc:Exception,st:dict)->Path:
    ev=evidence_dir(job)
    compile_text=""
    for candidate in (job/"metaeditor_compile.log", ev/"metaeditor_compile.log"):
        if candidate.exists():
            compile_text=candidate.read_text(encoding="utf-8",errors="ignore"); break
    excerpt=_compile_error_excerpt(compile_text)
    payload={
        "schema":"MAX_STRATEGY_OPTIMIZER_DIAGNOSTIC_V1",
        "job_id":job.name,"generated_utc":now(),"stage":stage,
        "error_type":type(exc).__name__,"error":str(exc),
        "compile_error_excerpt":excerpt,
        "evidence_dir":str(ev),
        "next_action":"Read this diagnostic in the UI. No manual EA copy or log hunting is required.",
    }
    atomic(ev/"diagnostic.json",payload)
    text=[f"Stage: {stage}",f"Error: {type(exc).__name__}: {exc}"]
    if excerpt:
        text += ["", "MetaEditor errors:"] + excerpt
    text += ["",f"Evidence: {ev}"]
    (ev/"diagnostic.txt").write_text("\n".join(text)+"\n",encoding="utf-8")
    bundle_base=EVIDENCE_ROOT/f"{job.name}_diagnostic"
    bundle_path=Path(shutil.make_archive(str(bundle_base),"zip",root_dir=ev))
    payload["diagnostic_bundle"]=str(bundle_path)
    atomic(ev/"diagnostic.json",payload)
    return ev/"diagnostic.json"

def _compile_summary(text:str)->dict:
    import re
    matches=list(re.finditer(r"Result:\s*(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?",str(text or ""),re.I))
    if not matches:
        return {"found":False,"errors":None,"warnings":None}
    m=matches[-1]
    return {"found":True,"errors":int(m.group(1)),"warnings":int(m.group(2)),"line":m.group(0)}

def compile_ea(req:dict,job:Path)->tuple[Path,str]:
    data=Path(req["installation"]["data_dir"]); meta=Path(req["installation"]["metaeditor"])
    src=EA_SOURCE.resolve()
    frozen=req.get("ea_source") or {}
    source_sha=hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else ""
    if not src.exists():
        raise FileNotFoundError(f"Canonical Strategy Optimizer EA missing: {src}")
    if str(frozen.get("sha256") or "") != source_sha:
        raise RuntimeError("Canonical EA source changed after Optimizer request freeze")

    # MT5 Strategy Tester only sees Experts under its data directory. Deploy an exact
    # byte-for-byte copy of the canonical Max MTF v2.0 baseline EA source; never generate or rewrite it.
    expert_dir=data/"MQL5"/"Experts"/EXPERT_SUBDIR; expert_dir.mkdir(parents=True,exist_ok=True)
    mq5=expert_dir/src.name
    shutil.copy2(src,mq5); os.utime(mq5,None)
    deployed_sha=hashlib.sha256(mq5.read_bytes()).hexdigest()
    if deployed_sha != source_sha:
        raise RuntimeError("Deployed MT5 EA differs from canonical Max MTF v2.0 baseline EA source")
    ex5=mq5.with_suffix(".ex5")
    if ex5.exists(): ex5.unlink()

    ev=evidence_dir(job)
    compile_cmd=[str(meta),f'/compile:{mq5}',"/log"]
    (ev/"compile_command.txt").write_text(subprocess.list2cmdline(compile_cmd)+"\n",encoding="utf-8")
    shutil.copy2(src,ev/"canonical_ea_source.mq5")
    cp=subprocess.run(compile_cmd,capture_output=True,text=True,timeout=180)
    log=mq5.with_suffix(".log")
    log_text=_read_compile_log(log) if log.exists() else (cp.stdout or "")+(cp.stderr or "")
    (job/"metaeditor_compile.log").write_text(log_text,encoding="utf-8")
    (ev/"metaeditor_compile.log").write_text(log_text,encoding="utf-8")
    summary=_compile_summary(log_text)
    context={
        "metaeditor":str(meta),"terminal_data_dir":str(data),
        "canonical_ea_source":str(src),"canonical_source_sha256":source_sha,
        "deployed_mq5":str(mq5),"deployed_source_sha256":deployed_sha,
        "deployment_authority":"BYTE_IDENTICAL_COPY_OF_MAX_MTF_V2_BASELINE_EA; NEVER_GENERATED",
        "expected_ex5":str(ex5),"returncode":cp.returncode,"compile_summary":summary,
        "returncode_authority":"DIAGNOSTIC_ONLY; compile summary + EX5 own PASS/FAIL",
    }
    atomic(ev/"compile_context.json",context)
    failed=(not summary.get("found") or int(summary.get("errors") or 0)>0 or not ex5.exists() or re_search_error(log_text))
    if failed:
        excerpt=_compile_error_excerpt(log_text)
        detail=(" | ".join(excerpt[-5:]) if excerpt else f"compile_summary={summary}, returncode={cp.returncode}, ex5_exists={ex5.exists()}")
        raise RuntimeError(f"MetaEditor compile failed: {detail}")
    shutil.copy2(ex5,ev/"compiled_ea.ex5")
    return ex5,EXPERT_SUBDIR+"\\"+mq5.stem

def re_search_error(text:str)->bool:
    import re
    m=re.search(r"(\d+)\s+errors?",text,re.I)
    return bool(m and int(m.group(1))>0)

class ReportPending(RuntimeError):
    pass


def _round_state_path(job:Path, round_no:int)->Path:
    return job/f"round_{round_no}_state.json"


def _load_round_state(job:Path, round_no:int)->dict:
    p=_round_state_path(job,round_no)
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _save_round_state(job:Path, round_no:int, obj:dict)->dict:
    payload=dict(obj); payload["schema"]="MAX_STRATEGY_OPTIMIZER_ROUND_STATE_V1"; payload["round"]=int(round_no); payload["updated_utc"]=now()
    atomic(_round_state_path(job,round_no),payload)
    ev=evidence_dir(job)/f"round_{round_no:02d}"; ev.mkdir(parents=True,exist_ok=True)
    atomic(ev/"round_state.json",payload)
    return payload


def _report_stat_fingerprint(path:Path)->dict:
    st=path.stat()
    return {"path":str(path.resolve()),"size":int(st.st_size),"mtime_ns":int(st.st_mtime_ns)}

def _report_snapshot(req:dict)->list[dict]:
    out=[]
    for path in discover_optimization_reports(req):
        try: out.append(_report_stat_fingerprint(path))
        except Exception: pass
    return out

def _snapshot_index(snapshot:list|None)->dict[str,tuple[int,int]]:
    out={}
    for row in snapshot or []:
        try:
            key=str(Path(str(row.get("path") or "")).resolve()).lower()
            out[key]=(int(row.get("size") or 0),int(row.get("mtime_ns") or 0))
        except Exception:
            pass
    return out

def _is_new_or_changed_report(path:Path, snapshot:list|None)->bool:
    try:
        fp=_report_stat_fingerprint(path)
    except Exception:
        return False
    key=str(Path(fp["path"]).resolve()).lower()
    prior=_snapshot_index(snapshot).get(key)
    return prior is None or prior!=(int(fp["size"]),int(fp["mtime_ns"]))

def _expected_report_candidates(req:dict, report_name:str)->list[Path]:
    if not str(report_name or "").strip(): return []
    data=Path(req["installation"]["data_dir"]); terminal=Path(req["installation"]["terminal"])
    roots=[data/"MQL5"/"Profiles"/"Tester",data,terminal.parent]
    out=[]; seen=set()
    for root in roots:
        p=root/report_name
        key=str(p).lower()
        if key not in seen:
            seen.add(key); out.append(p)
    return out

def _wait_for_fresh_report(req:dict, *, report_name:str, prelaunch_snapshot:list|None, timeout_sec:int=90)->tuple[Path|None,str]:
    """Wait for this round's report without trusting MT5's Created timestamp.

    MT5 SpreadsheetML Created timestamps are not a safe freshness clock on every
    Windows/terminal timezone combination.  A later round must therefore prove
    that its report path is new or that an existing compatible file changed after
    the pre-launch snapshot.  The canonical requested report filename is preferred,
    but internal EA/symbol/TF/date identity is still mandatory.
    """
    deadline=time.time()+max(0,int(timeout_sec)); last=None; stable=0; last_mode=""
    baseline=list(prelaunch_snapshot or [])
    while True:
        candidates=[]
        for p in _expected_report_candidates(req,report_name):
            if p.is_file() and report_matches_request(p,req) and _is_new_or_changed_report(p,baseline):
                candidates.append((p,"EXPECTED_CANONICAL_REPORT"))
        if not candidates:
            for p in discover_optimization_reports(req):
                if _is_new_or_changed_report(p,baseline):
                    candidates.append((p,"FRESH_FINGERPRINT"))
        if candidates:
            candidates.sort(key=lambda item:item[0].stat().st_mtime_ns,reverse=True)
            p,mode=candidates[0]
            sig=(str(p.resolve()).lower(),p.stat().st_size,p.stat().st_mtime_ns)
            if sig==last and mode==last_mode: stable+=1
            else: last=sig; last_mode=mode; stable=0
            if stable>=2: return p,mode
        if time.time()>=deadline: return None,""
        time.sleep(1.0)

def _sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def _eligibility_audit(rows:list)->dict:
    if not rows:
        return {"parsed_passes":0,"eligible_passes":0,"champion_pass":None,"gate_counts":{}}
    r0=rows[0]
    gates={
        "minimum_trades":sum(1 for r in rows if int(r.trades)>=int(r.minimum_trades_required)),
        "profit_factor":sum(1 for r in rows if float(r.profit_factor)>=float(r.min_profit_factor_required)),
        "recovery_factor":sum(1 for r in rows if float(r.recovery_factor)>=float(r.min_recovery_factor_required)),
        "expectancy_r":sum(1 for r in rows if float(r.expectancy_r)>=float(r.min_expectancy_r_required)),
        "weighted_r":sum(1 for r in rows if float(r.weighted_r)>=float(r.min_weighted_r_required)),
    }
    eligible=[r for r in rows if r.passed]
    complete=sum(1 for r in rows if math.isfinite(float(r.weighted_r)))
    unresolved=sum(1 for r in rows if (r.trades >= int(r.minimum_trades_required) and float(r.profit_factor) >= float(r.min_profit_factor_required) and float(r.recovery_factor) >= float(r.min_recovery_factor_required) and float(r.expectancy_r) >= float(r.min_expectancy_r_required) and not math.isfinite(float(r.weighted_r))))
    ch=select_champion(rows)
    return {
        "parsed_passes":len(rows),"eligible_passes":len(eligible),
        "weighted_evidence_complete_passes":complete,
        "weighted_evidence_incomplete_passes":len(rows)-complete,
        "unresolved_nonweighted_contenders":unresolved,
        "champion_pass":int(ch.pass_no) if ch is not None else None,
        "thresholds":{
            "minimum_trades":int(r0.minimum_trades_required),
            "min_profit_factor":float(r0.min_profit_factor_required),
            "min_recovery_factor":float(r0.min_recovery_factor_required),
            "min_expectancy_r":float(r0.min_expectancy_r_required),
            "min_weighted_r":float(r0.min_weighted_r_required),
        },
        "gate_counts":gates,
    }


def run_round(req:dict,job:Path,expert_name:str,round_no:int,space:dict,*,launch_mt5:bool=True,report_override:str|Path|None=None)->tuple[list,Path]:
    data=Path(req["installation"]["data_dir"]); terminal=Path(req["installation"]["terminal"])
    preset_dir=data/"MQL5"/"Profiles"/"Tester"; preset_dir.mkdir(parents=True,exist_ok=True)
    set_name=TESTER_SET; set_path=preset_dir/set_name
    ev_round=evidence_dir(job)/f"round_{round_no:02d}"; ev_round.mkdir(parents=True,exist_ok=True)
    state=_load_round_state(job,round_no)
    if not state:
        run_nonce=int(hashlib.sha256(f"{job.name}:{round_no}".encode("utf-8")).hexdigest()[:8],16) & 0x7fffffff
        metrics_file=OPTIMIZER_METRICS_CSV
        metrics_path=data/"MQL5"/"Files"/metrics_file
        metrics_path.parent.mkdir(parents=True,exist_ok=True)
        set_path.write_text(build_set_text(
            space,confirm_symbol=req["confirm_symbol"],optimize_params=req.get("optimize_params"),
            fixed_param_values=req.get("fixed_param_values"),
            optimizer_metrics_file=metrics_file,optimizer_run_nonce=run_nonce,
        ),encoding="utf-8")
        # Report intentionally uses the canonical EA stem. Round ownership/freshness is
        # proven by the pre-launch fingerprint and per-round evidence directory, not by
        # encoding the round number into the external MT5 filename.
        report_name=OPTIMIZER_REPORT_XML
        ini=job/f"round_{round_no}.ini"
        ini.write_text(build_tester_ini(expert=expert_name,set_name=set_name,symbol=req["symbol"],period=req["period"],from_date=req["from_date"],to_date=req["to_date"],deposit=req["deposit"],leverage=req["leverage"],model=req["model"],report_path=report_name,optimization=req["optimization"]),encoding="utf-8")
        shutil.copy2(set_path,ev_round/set_path.name); shutil.copy2(ini,ev_round/ini.name)
        (ev_round/"search_space.json").write_text(json.dumps(space,indent=2),encoding="utf-8")
        state=_save_round_state(job,round_no,{
            "phase":"PREPARED","search_space":space,"set_path":str(set_path),"ini_path":str(ini),
            "report_name":report_name,"optimize_params":req.get("optimize_params") or [],
            "optimizer_metrics_file":metrics_file,"optimizer_metrics_path":str(metrics_path),
            "optimizer_run_nonce":run_nonce,
        })
    else:
        ini=Path(state["ini_path"]); set_path=Path(state["set_path"]); space=state.get("search_space") or space
        metrics_file=str(state.get("optimizer_metrics_file") or OPTIMIZER_METRICS_CSV)
        metrics_path=Path(state.get("optimizer_metrics_path") or (data/"MQL5"/"Files"/metrics_file))
        run_nonce=int(state.get("optimizer_run_nonce") or 0)

    if report_override is not None:
        rp=Path(report_override)
        if not report_matches_request(rp,req):
            raise RuntimeError(f"Recovery XML identity does not match frozen Optimizer request: {rp}")
        state=_save_round_state(job,round_no,{**state,"phase":"MT5_COMPLETE","report_override":str(rp),"mt5_finished_utc":state.get("mt5_finished_utc") or now()})
        launch_mt5=False

    phase=str(state.get("phase") or "PREPARED")
    if launch_mt5 and phase=="PREPARED":
        launch_epoch=time.time()
        prelaunch_snapshot=_report_snapshot(req)
        # A new run nonce plus removal of the terminal-side frame CSV prevents
        # stale/cached R metrics from being mistaken for this native MT5 round.
        try:
            if metrics_path.exists(): metrics_path.unlink()
        except OSError:
            raise RuntimeError(f"Cannot clear stale optimizer R-metrics sidecar: {metrics_path}")
        state=_save_round_state(job,round_no,{**state,"phase":"MT5_RUNNING","mt5_started_utc":now(),"mt5_started_epoch":launch_epoch,"prelaunch_report_snapshot":prelaunch_snapshot})
        timeout_sec=int(req.get("round_timeout_sec") or 21600)
        cp=subprocess.run([str(terminal),f"/config:{ini}"],cwd=str(terminal.parent),timeout=timeout_sec)
        if cp.returncode not in (0,None): raise RuntimeError(f"MT5 exited with code {cp.returncode}")
        state=_save_round_state(job,round_no,{**state,"phase":"MT5_COMPLETE","mt5_finished_utc":now(),"mt5_returncode":cp.returncode})
        phase="MT5_COMPLETE"
    elif phase=="MT5_RUNNING":
        # A worker restart while MT5 was running cannot prove whether the external
        # terminal is still alive. Never relaunch the same round. Resolve evidence first.
        state=_save_round_state(job,round_no,{**state,"phase":"MT5_COMPLETE_UNCONFIRMED"})
        phase="MT5_COMPLETE_UNCONFIRMED"

    if phase in {"MT5_COMPLETE","MT5_COMPLETE_UNCONFIRMED","WAITING_FOR_REPORT","REPORT_READY"}:
        report=None; selection_mode=str(state.get("report_selection_mode") or "")
        if state.get("report_path") and Path(state["report_path"]).exists():
            report=Path(state["report_path"]); selection_mode=selection_mode or "CHECKPOINTED_REPORT"
        if report is None and state.get("report_override") and Path(state["report_override"]).exists():
            report=Path(state["report_override"]); selection_mode="EXPLICIT_EXISTING_EVIDENCE"
        launch_epoch=float(state.get("mt5_started_epoch") or 0.0)
        baseline=state.get("prelaunch_report_snapshot") if isinstance(state.get("prelaunch_report_snapshot"),list) else None
        if report is None:
            wait=int(req.get("report_wait_sec") or 90)
            if baseline is not None:
                report,selection_mode=_wait_for_fresh_report(req,report_name=str(state.get("report_name") or ""),prelaunch_snapshot=baseline,timeout_sec=wait)
            else:
                # Legacy v0.8.2/v0.8.3 checkpoints may not contain a pre-launch snapshot.
                # Keep them resumable, but mark the weaker time-based provenance explicitly.
                hits=discover_optimization_reports(req,not_before_epoch=launch_epoch or None)
                report=hits[0] if hits else None
                selection_mode="LEGACY_TIME_FALLBACK" if report is not None else ""
        if report is None:
            checked=[str(Path(req["installation"]["data_dir"])/"MQL5"/"Profiles"/"Tester")]
            _save_round_state(job,round_no,{**state,"phase":"WAITING_FOR_REPORT","checked_roots":checked})
            raise ReportPending("MT5 finished but this round has no fresh compatible optimization XML yet; checkpoint is preserved and the same MT5 round will not be relaunched")
        if not report_matches_request(report,req):
            raise RuntimeError(f"Optimization XML identity mismatch: {report}")
        if baseline is not None and selection_mode not in {"EXPLICIT_EXISTING_EVIDENCE","CHECKPOINTED_REPORT"} and not _is_new_or_changed_report(report,baseline):
            raise RuntimeError(f"Stale optimization XML rejected for round {round_no}: {report}")
        fp=_report_stat_fingerprint(report)
        state=_save_round_state(job,round_no,{**state,"phase":"REPORT_READY","report_path":str(report),"report_identity":optimization_report_identity(report),"report_selection_mode":selection_mode or "IDENTITY_MATCH","report_fingerprint":fp})
    else:
        raw_report=str(state.get("report_path") or "").strip()
        if not raw_report:
            raise ReportPending("Round checkpoint exists but report is not yet available")
        report=Path(raw_report)
        if not report.is_file():
            raise ReportPending("Round checkpoint exists but report is not yet available")

    local_report=ev_round/Path(report).name
    if report.resolve()!=local_report.resolve(): shutil.copy2(report,local_report)
    if not metrics_path.is_file():
        raise RuntimeError(
            f"Optimizer weighted-R evidence missing for round {round_no}: {metrics_path}. "
            "v0.8.5 requires fresh MT5 frame evidence; legacy XML alone is not Champion-compatible."
        )
    local_metrics=ev_round/OPTIMIZER_METRICS_CSV
    if metrics_path.resolve()!=local_metrics.resolve(): shutil.copy2(metrics_path,local_metrics)
    rows=parse_optimization_xml(
        local_report,round_no=round_no,metrics_path=local_metrics,
        expected_nonce=run_nonce,require_weighted_metrics=True,
    )
    if rows and all(float(r.expectancy_r) <= -1.0e8 for r in rows):
        raise RuntimeError("MT5 Custom/OnTester Expectancy-R is invalid for every optimization pass; refusing to refine or promote sentinel results")
    sample=req.get("optimizer_trade_sample") or {}; kpi=sample.get("kpi_profile") or {}
    minimum=int(sample.get("minimum_trades",1) or 1)
    for row in rows:
        row.minimum_trades_required=minimum
        row.min_profit_factor_required=float(kpi.get("min_profit_factor",1.0))
        row.min_recovery_factor_required=float(kpi.get("min_recovery_factor",0.0))
        row.min_expectancy_r_required=float(kpi.get("min_expectancy_r",0.0))
        row.min_weighted_r_required=float(kpi.get("min_weighted_r",0.0))
    eligibility=_eligibility_audit(rows)
    _save_round_state(job,round_no,{
        **state,"phase":"PARSED","report_path":str(local_report),"passes":len(rows),
        "eligible_passes":int(eligibility.get("eligible_passes") or 0),"eligibility_audit":eligibility,
        "report_sha256":_sha256_file(local_report),"optimizer_metrics_path":str(local_metrics),
        "optimizer_metrics_sha256":_sha256_file(local_metrics),
    })
    return rows,local_report

def _upsert_round_record(records:list, rec:dict)->list:
    out=[dict(x) for x in records if isinstance(x,dict) and int(x.get("round") or 0)!=int(rec["round"])]
    out.append(dict(rec))
    return sorted(out,key=lambda x:int(x.get("round") or 0))


def _load_scientist_secret() -> str:
    """Load only the credential at execution time; route/config stays frozen in request."""
    try:
        from core.settings_store import UserSettingsStore
        settings_root=(Path(os.environ.get("LOCALAPPDATA"))/"ComplexPolicy"/"ModelLab") if os.environ.get("LOCALAPPDATA") else (ROOT/"runtime"/"user_data")
        store=UserSettingsStore(settings_root)
        _cfg,key,_meta,_ui=store.load({"agent":{"llm":{}}})
        return str(key or "")
    except Exception:
        return ""


def _write_proposal(job:Path, round_no:int, proposal:dict):
    atomic(job/f"round_{round_no}_next_range_proposal.json",proposal)
    ev=evidence_dir(job)/f"round_{round_no:02d}"; ev.mkdir(parents=True,exist_ok=True)
    atomic(ev/"next_range_proposal.json",proposal)


def _round_record(req:dict, round_no:int, rows:list, report:Path, space:dict, prior:dict|None=None)->dict:
    rec=dict(prior or {})
    eligibility=_eligibility_audit(rows)
    rec.update({
        "round":int(round_no),"report":str(report),"report_identity":optimization_report_identity(report),
        "report_sha256":_sha256_file(report),
        "passes":len(rows),"pass_count":int(eligibility.get("eligible_passes") or 0),"eligibility_audit":eligibility,"search_space":space,
        "optimizer_kpi":req.get("optimizer_kpi"),"optimizer_trade_sample":req.get("optimizer_trade_sample"),
        "optimize_params":list(req.get("optimize_params") or []),
    })
    return rec


def _apply_winner(req:dict,job:Path,status_path:Path,st:dict,round_no:int,ch,round_records:list)->int:
    """v0.11.0: eligible Optimizer winner becomes a Strategy Challenger, never auto-Champion.

    Canonical Max_MTF.mq5 / Max_MTF.set / runtime strategy authority remain untouched until
    explicit Owner promotion from the Strategy Challenger registry.
    """
    from strategy.strategy_challenger_registry import register_optimizer_challenger
    payload=champion_payload(ch)
    ev=evidence_dir(job)/"strategy_challenger"; ev.mkdir(parents=True,exist_ok=True)
    before_sha=_sha256_file(EA_SOURCE)
    authority_before=_sha256_file(RUNTIME_AUTHORITY) if RUNTIME_AUTHORITY.exists() else None
    entry=register_optimizer_challenger(ROOT,req,job,ch,round_records)
    # Scientific boundary: Challenger creation must never mutate current Champion authority.
    after_sha=_sha256_file(EA_SOURCE)
    authority_after=_sha256_file(RUNTIME_AUTHORITY) if RUNTIME_AUTHORITY.exists() else None
    if after_sha != before_sha or authority_after != authority_before:
        raise RuntimeError("Strategy Challenger registration mutated current Champion authority")
    atomic(job/"strategy_challenger.json",entry)
    atomic(ev/"strategy_challenger.json",entry)
    for key in ("ea_file","set_file","metadata_file"):
        src=Path(str(entry.get(key) or ""))
        if src.is_file(): shutil.copy2(src,ev/src.name)
    update(
        status_path,st,"STRATEGY_CHALLENGER_FOUND",
        f"Eligible Strategy Challenger {entry.get('challenger_id')} found in round {round_no}; current Max.mq5 Champion was not changed. Optimizer stopped for explicit Owner promotion.",
        champion=None,strategy_challenger=payload,strategy_challenger_entry=entry,rounds=round_records,round=round_no,
        first_failed_gate=None,report_identity=round_records[-1].get("report_identity"),frozen_config=req,
    )
    return 0

def _evaluate_completed_round(req:dict,job:Path,status_path:Path,st:dict,round_no:int,space:dict,rows:list,report:Path)->int|None:
    records=list(st.get("rounds") or [])
    old=next((x for x in records if isinstance(x,dict) and int(x.get("round") or 0)==int(round_no)),None)
    rec=_round_record(req,round_no,rows,report,space,old)
    rs=_load_round_state(job,round_no)
    rec["report_selection_mode"]=str(rs.get("report_selection_mode") or rec.get("report_selection_mode") or "")
    rec["source_report_fingerprint"]=dict(rs.get("report_fingerprint") or rec.get("source_report_fingerprint") or {})
    rec["optimizer_metrics_path"]=str(rs.get("optimizer_metrics_path") or rec.get("optimizer_metrics_path") or "")
    rec["optimizer_metrics_sha256"]=str(rs.get("optimizer_metrics_sha256") or rec.get("optimizer_metrics_sha256") or "")
    rec["optimizer_run_nonce"]=int(rs.get("optimizer_run_nonce") or rec.get("optimizer_run_nonce") or 0)
    records=_upsert_round_record(records,rec); st["rounds"]=records
    ch=select_champion(rows)
    audit=rec.get("eligibility_audit") or {}
    eligible_count=int(audit.get("eligible_passes") or 0)
    if (ch is None) != (eligible_count==0):
        raise RuntimeError(f"Optimizer eligibility invariant failed in round {round_no}: eligible_count={eligible_count}, champion={getattr(ch,'pass_no',None)}")
    if ch is not None:
        # Hard stop contract: once an eligible winner exists, Scientist and every later MT5 round are forbidden.
        return _apply_winner(req,job,status_path,st,round_no,ch,records)

    sample=req.get("optimizer_trade_sample") or {}
    kpi=sample.get("kpi_profile") or req.get("optimizer_kpi") or {}
    required=int(sample.get("minimum_trades",1) or 1)
    pf_min=float(kpi.get("min_profit_factor",OPTIMIZER_PF_MIN))
    rf_min=float(kpi.get("min_recovery_factor",OPTIMIZER_RF_MIN))
    exp_min=float(kpi.get("min_expectancy_r",OPTIMIZER_EXPECTANCY_R_MIN))
    weighted_min=float(kpi.get("min_weighted_r",OPTIMIZER_WEIGHTED_R_MIN))
    near=best_near_miss(rows)
    if int(round_no) >= int(req.get("max_rounds") or 1):
        update(
            status_path,st,"NO_CHAMPION_MAX_ROUNDS",
            f"Round {round_no} parsed {len(rows)} passes and found 0 eligible at frozen KPI PF>={pf_min:g}, RF>={rf_min:g}, Mean R>={exp_min:g}, Weighted R>={weighted_min:g}, minimum {required} trades. Report {Path(report).name} SHA {str(rec.get('report_sha256') or '')[:12]}. Maximum MT5 round budget reached; Optimizer stopped without Champion.",
            rounds=records,round=round_no,near_miss=(champion_payload(near) if near else None),optimizer_trade_sample=sample,
            first_failed_gate="OPTIMIZER_KPI_ELIGIBILITY",auto_continue_next_round=False,
            report_identity=records[-1].get("report_identity") if records else None,frozen_config=req,
            scientist_path=(st.get("scientist_path") or "NOT_APPLICABLE"),
            scientist_reason=(st.get("scientist_reason") or "No eligible winner and the frozen maximum-round budget is exhausted."),
        )
        return 2

    update(
        status_path,st,"ROUND_COMPLETE_NO_CHAMPION",
        f"Round {round_no} parsed {len(rows)} passes and found 0 eligible at frozen KPI PF>={pf_min:g}, RF>={rf_min:g}, Mean R>={exp_min:g}, Weighted R>={weighted_min:g}, minimum {required} trades. Report {Path(report).name} SHA {str(rec.get('report_sha256') or '')[:12]}. Automatically refining and continuing to round {round_no+1}/{req['max_rounds']}.",
        rounds=records,round=round_no,near_miss=(champion_payload(near) if near else None),optimizer_trade_sample=sample,
        first_failed_gate="OPTIMIZER_KPI_ELIGIBILITY",auto_continue_next_round=True,
        report_identity=records[-1].get("report_identity") if records else None,frozen_config=req,
        scientist_path=(st.get("scientist_path") or ("SCIENTIST_PENDING" if bool(req.get("scientist_assist")) else "DETERMINISTIC_ONLY")),
        scientist_reason=(st.get("scientist_reason") or ("No eligible winner; Scientist will propose the next bounded range automatically." if bool(req.get("scientist_assist")) else "No eligible winner; deterministic bounded refinement will run automatically.")),
    )
    return None


def _refine_for_next_round(req:dict,job:Path,status_path:Path,st:dict,current_round:int,current_space:dict,rows:list)->tuple[dict,dict]:
    next_round=current_round+1
    scientist_requested=bool(req.get("scientist_assist"))
    sample=req.get("optimizer_trade_sample") or {}; kpi=sample.get("kpi_profile") or req.get("optimizer_kpi") or {}
    if not scientist_requested:
        next_space=deterministic_refine(current_space,rows,req.get("optimize_params"))
        proposal={
            "schema":"MAX_STRATEGY_OPTIMIZER_RANGE_PROPOSAL_V2","source_round":current_round,"target_round":next_round,
            "mode":"DETERMINISTIC_ONLY","actual_llm_call":False,"accepted":True,
            "reason":"Scientist OFF in the frozen Optimizer request; no-winner round automatically uses deterministic bounded refinement for the next MT5 round.",
            "proposed_ranges":next_space,"effective_ranges":next_space,
        }
        _write_proposal(job,current_round,proposal)
        return next_space,proposal

    llm_cfg=dict(req.get("scientist_llm") or {})
    update(status_path,st,"SCIENTIST_REFINING",f"Round {current_round} has no Champion; calling LLM Scientist once for bounded range proposal for automatic round {next_round}",round=current_round,scientist_path="SCIENTIST_PROPOSAL")
    try:
        raw,meta=scientist_propose_ranges(current_space,rows,llm_cfg,round_no=next_round,kpi_profile=kpi,minimum_trades=int(sample.get("minimum_trades",1) or 1),optimize_params=req.get("optimize_params"),api_key=_load_scientist_secret())
        proposal={
            "schema":"MAX_STRATEGY_OPTIMIZER_RANGE_PROPOSAL_V2","source_round":current_round,"target_round":next_round,
            "mode":"SCIENTIST_PROPOSAL","actual_llm_call":True,"reason":str((meta or {}).get("reason") or "Scientist returned a proposal."),
            "proposal":raw,"llm_provenance":dict((meta or {}).get("llm_provenance") or {}),
        }
        try:
            next_space=validate_scientist_ranges(current_space,raw,req.get("optimize_params"))
            proposal.update({"accepted":True,"validation":{"status":"ACCEPTED","reason":"Proposal passed deterministic hard-bounds and frozen-parameter validation."},"effective_ranges":next_space})
        except Exception as vex:
            next_space=deterministic_refine(current_space,rows,req.get("optimize_params"))
            proposal.update({"accepted":False,"validation":{"status":"REJECTED","reason":str(vex)[:500]},"effective_range_source":"DETERMINISTIC_REFINEMENT_AFTER_REJECTED_SCIENTIST_PROPOSAL","effective_ranges":next_space})
        _write_proposal(job,current_round,proposal)
        return next_space,proposal
    except Exception as exc:
        next_space=deterministic_refine(current_space,rows,req.get("optimize_params"))
        err=str(exc)
        actual_call=not err.startswith("Scientist route is not configured")
        proposal={
            "schema":"MAX_STRATEGY_OPTIMIZER_RANGE_PROPOSAL_V2","source_round":current_round,"target_round":next_round,
            "mode":"DETERMINISTIC_FALLBACK","actual_llm_call":actual_call,"accepted":False,
            "reason":(("Scientist was requested, but provider/model route is unavailable; deterministic bounded refinement used without changing frozen KPI or parameter universe.") if not actual_call else ("Scientist was requested, but provider/model/call failed; deterministic bounded refinement used without changing frozen KPI or parameter universe.")),
            "scientist_error":err[:500],"effective_ranges":next_space,
        }
        _write_proposal(job,current_round,proposal)
        return next_space,proposal


def _advance_until_terminal(req:dict,job:Path,status_path:Path,st:dict,expert_name:str,round_no:int,space:dict,rows:list,report:Path)->int:
    current_round=int(round_no)
    current_space=space
    current_rows=rows
    current_report=report
    while True:
        decision=_evaluate_completed_round(req,job,status_path,st,current_round,current_space,current_rows,current_report)
        if decision is not None:
            return int(decision)

        # No Champion and round budget remains: automatic next-round refinement is the contract.
        # Scientist is advisory only for range refinement; it is never called after a winner exists.
        next_space,proposal=_refine_for_next_round(req,job,status_path,st,current_round,current_space,current_rows)
        records=list(st.get("rounds") or [])
        old=next((x for x in records if isinstance(x,dict) and int(x.get("round") or 0)==current_round),None) or _round_record(req,current_round,current_rows,current_report,current_space)
        old["next_space_proposal"]=proposal
        records=_upsert_round_record(records,old); st["rounds"]=records
        next_round=current_round+1
        _,expert_name=compile_ea(req,job)
        update(
            status_path,st,"MT5_OPTIMIZING",
            f"No Champion in round {current_round}; automatically running MT5 native optimization round {next_round}/{req['max_rounds']}",
            round=next_round,rounds=records,search_space=next_space,scientist_path=proposal.get("mode"),
            scientist_reason=proposal.get("reason"),first_failed_gate=None,
        )
        current_rows,current_report=run_round(req,job,expert_name,next_round,next_space,launch_mt5=True)
        current_round=next_round
        current_space=next_space


def main(job_id:str, *, resume:bool=False, report_override:str|None=None)->int:
    job=RUNS_ROOT/job_id; status_path=job/"status.json"
    st=json.loads(status_path.read_text(encoding="utf-8")); req=validate_request(json.loads((job/"request.json").read_text(encoding="utf-8")))
    st["frozen_config"]=req
    try:
        expert_name=EXPERT_SUBDIR+"\\"+EA_SOURCE.stem
        if resume:
            current_round=max(1,int(st.get("round") or 1))
            rs=_load_round_state(job,current_round)
            space=rs.get("search_space") or req.get("search_space") or DEFAULT_SPACE
            update(
                status_path,st,"RESUMING",
                f"Resume processes existing round {current_round} evidence without rerunning that round; if no Champion exists, later rounds continue automatically within the frozen maximum-round budget",
                round=current_round,first_failed_gate=None,
            )
            rows,report=run_round(req,job,expert_name,current_round,space,launch_mt5=False,report_override=report_override)
            return _advance_until_terminal(req,job,status_path,st,expert_name,current_round,space,rows,report)

        update(status_path,st,"COMPILING_EA","Deploying exact frozen Max MTF v2.0 baseline EA copy and compiling before MT5 round 1",round=1,first_failed_gate=None)
        _,expert_name=compile_ea(req,job)
        space=req.get("search_space") or DEFAULT_SPACE
        update(status_path,st,"MT5_OPTIMIZING",f"MT5 native optimization round 1/{req['max_rounds']}",round=1,search_space=space,first_failed_gate=None)
        rows,report=run_round(req,job,expert_name,1,space,launch_mt5=True)
        return _advance_until_terminal(req,job,status_path,st,expert_name,1,space,rows,report)
    except ReportPending as exc:
        update(status_path,st,"WAITING_FOR_REPORT",str(exc),round=max(1,int(st.get("round") or 1)),recoverable=True,first_failed_gate="REPORT_READY",frozen_config=req)
        return 3
    except Exception as exc:
        stage=str(st.get("status") or "UNKNOWN")
        diag=write_diagnostic(job,stage,exc,st)
        diag_obj=json.loads(diag.read_text(encoding="utf-8"))
        update(status_path,st,"FAILED",str(exc)[:1000],error=repr(exc),diagnostic_path=str(diag),diagnostic_bundle=str(diag_obj.get("diagnostic_bundle") or ""),evidence_dir=str(evidence_dir(job)),first_failed_gate=stage,frozen_config=req)
        return 1

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--job-id",required=True); ap.add_argument("--resume",action="store_true"); ap.add_argument("--report")
    args=ap.parse_args()
    raise SystemExit(main(args.job_id,resume=bool(args.resume),report_override=args.report))
