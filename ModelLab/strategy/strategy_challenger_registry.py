from __future__ import annotations
from core.project_paths import PACKAGE_ROOT

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategy.strategy_optimizer import (
    ABSOLUTE_BOUNDS,
    EA_SOURCE,
    RUNS_ROOT,
    apply_champion_to_canonical_ea,
    assert_champion_ea_set_parity,
    champion_payload,
    read_ea_optimizer_defaults,
    write_champion_tester_preset,
)
from strategy.strategy_geometry import RUNTIME_AUTHORITY, load_runtime_strategy_authority, persist_optimizer_champion_authority

SCHEMA = "MAX_MTF_STRATEGY_CHALLENGER_REGISTRY_V2"

from core.project_paths import EA_CHALLENGERS_DIR, EA_ARCHIVE_DIR
from mtf.mtf_names import TESTER_SET
ARTIFACT_ROOT = EA_CHALLENGERS_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same_number(a: Any, b: Any, tol: float = 1e-9) -> bool:
    try:
        aa=float(a); bb=float(b)
        return abs(aa-bb) <= tol*max(1.0,abs(aa),abs(bb))
    except Exception:
        return False


def _same_params(a: dict, b: dict) -> bool:
    for name, (_lo,_hi,_step,typ) in ABSOLUTE_BOUNDS.items():
        if name not in a or name not in b:
            return False
        if typ == "int":
            try:
                if int(round(float(a[name]))) != int(round(float(b[name]))): return False
            except Exception:
                return False
        elif not _same_number(a[name],b[name]):
            return False
    return True


def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    tmp=Path(tmp_name)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            json.dump(obj,f,indent=2,default=str); f.write("\n"); f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        os.replace(tmp,path)
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass


def registry_path(app_dir: str | Path) -> Path:
    return Path(app_dir) / "runtime" / "strategy_challenger_registry.json"


def _read_json(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def _with_lock(app_dir: str | Path, fn):
    p=registry_path(app_dir); lock=p.with_suffix(p.suffix+".lock"); lock.parent.mkdir(parents=True,exist_ok=True)
    fd=None
    for attempt in range(100):
        try:
            fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY); break
        except FileExistsError:
            if attempt==99: raise RuntimeError("Strategy Challenger registry is busy")
            time.sleep(0.02*min(10,attempt+1))
    try:
        if fd is not None:
            os.write(fd,f"pid={os.getpid()} utc={utc_now()}\n".encode()); os.close(fd); fd=None
        reg=_read_json(p,{"schema":SCHEMA,"baseline_strategy":None,"current_champion":None,"entries":[],"tombstones":[],"promotion_history":[],"updated_utc":None})
        if not isinstance(reg,dict): reg={}
        reg.setdefault("baseline_strategy",None); reg.setdefault("current_champion",None); reg.setdefault("entries",[]); reg.setdefault("tombstones",[]); reg.setdefault("promotion_history",[])
        result=fn(reg)
        reg["schema"]=SCHEMA; reg["updated_utc"]=utc_now(); _atomic_json(p,reg)
        return result
    finally:
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
        try: lock.unlink(missing_ok=True)
        except Exception: pass


def _kpi_from_payload(payload: dict | None) -> dict:
    p=payload or {}
    return {
        "profit_factor":p.get("profit_factor"),
        "recovery_factor":p.get("recovery_factor"),
        "mean_r":p.get("expectancy_r",p.get("mean_r")),
        "weighted_r":p.get("weighted_r"),
        "profit":p.get("profit"),
        "trades":p.get("trades"),
        "expected_payoff":p.get("expected_payoff"),
        "sharpe_ratio":p.get("sharpe_ratio"),
        "equity_dd_pct":p.get("equity_dd_pct"),
        "r_accounted_trades":p.get("r_accounted_trades"),
        "accounting_errors":p.get("accounting_errors"),
        "sum_initial_risk":p.get("sum_initial_risk"),
        "sum_net":p.get("sum_net"),
    }


def _recover_matching_current_kpi(params: dict) -> tuple[dict,str,dict]:
    if RUNS_ROOT.exists():
        rows=[]
        for p in RUNS_ROOT.glob("*/status.json"):
            try:
                st=json.loads(p.read_text(encoding="utf-8")); ch=st.get("champion") or st.get("strategy_challenger") or {}
                if isinstance(ch,dict) and isinstance(ch.get("params"),dict) and _same_params(params,ch["params"]):
                    rows.append((str(st.get("updated_utc") or ""),st,ch))
            except Exception: pass
        if rows:
            _stamp,st,ch=max(rows,key=lambda x:x[0])
            return _kpi_from_payload(ch),"RECOVERED_FROM_MATCHING_OPTIMIZER_EVIDENCE",{
                "job_id":st.get("job_id"),"round":ch.get("round"),"pass":ch.get("pass")
            }

    return _kpi_from_payload(None),"BASELINE_NOT_CHAMPION_NO_OPTIMIZER_EVIDENCE",{}



def _portable_project_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PACKAGE_ROOT.resolve()).as_posix()
    except Exception:
        # Acceptance/promotion selftests monkeypatch EA_SOURCE into an isolated
        # temporary project.  Keep those sandbox records portable without ever
        # embedding the builder absolute path. Production EA_SOURCE resolves
        # inside PACKAGE_ROOT and therefore never takes this branch.
        try:
            return resolved.relative_to(resolved.parent).as_posix()
        except Exception as exc:
            raise RuntimeError(f"Strategy registry artifact cannot be made portable: {path}") from exc


def _baseline_record() -> dict:
    params=read_ea_optimizer_defaults(EA_SOURCE)
    return {
        "strategy_id":"BASELINE-MTF-V2",
        "display_name":EA_SOURCE.name,
        "status":"BASELINE_NOT_CHAMPION",
        "ea_file":_portable_project_path(EA_SOURCE),
        "ea_sha256":_sha(EA_SOURCE),
        "params":params,
        "kpi":_kpi_from_payload(None),
        "kpi_status":"BASELINE_NOT_CHAMPION_NO_OPTIMIZER_EVIDENCE",
        "source_job_id":None,"source_round":None,"source_pass":None,
        "promoted_utc":None,
        "authority_source":"MAX_MTF_V2_BASELINE",
    }


def ensure_strategy_registry(app_dir: str | Path) -> dict:
    def mutate(reg: dict):
        # Max MTF v2 bootstrap rule: baseline is active authority but is NOT a Champion.
        reg["baseline_strategy"]=_baseline_record()
        if "current_champion" not in reg:
            reg["current_champion"]=None
        reg.setdefault("entries",[])
        reg.setdefault("tombstones",[])
        reg.setdefault("promotion_history",[])
        return reg
    _with_lock(app_dir,mutate)
    return load_strategy_registry(app_dir,ensure=False)


def load_strategy_registry(app_dir: str | Path, *, ensure: bool=True) -> dict:
    if ensure and not registry_path(app_dir).exists():
        return ensure_strategy_registry(app_dir)
    obj=_read_json(registry_path(app_dir),{"schema":SCHEMA,"baseline_strategy":None,"current_champion":None,"entries":[],"tombstones":[]})
    if not isinstance(obj,dict): obj={}
    obj.setdefault("baseline_strategy",None); obj.setdefault("current_champion",None); obj.setdefault("entries",[]); obj.setdefault("tombstones",[]); obj.setdefault("promotion_history",[]); obj["schema"]=SCHEMA
    return obj


def _code(job_id: str, round_no: int, pass_no: int, *, suffix: str="") -> str:
    m=re.search(r"(20\d{6})[_-]?(\d{6})",str(job_id or ""))
    stamp=f"{m.group(1)}-{m.group(2)}" if m else datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    core=f"STRAT-{stamp}-R{int(round_no):02d}-P{int(pass_no)}"
    return core+(f"-{suffix}" if suffix else "")


def _allocate_code(base_code: str) -> tuple[str,Path]:
    ARTIFACT_ROOT.mkdir(parents=True,exist_ok=True)
    for i in range(1,1000):
        code=base_code if i==1 else f"{base_code}-{i:02d}"
        mq5=ARTIFACT_ROOT/f"Max_Challenger_{code}.mq5"
        if not mq5.exists(): return code,mq5
    raise RuntimeError("Could not allocate Strategy Challenger code")


def _write_challenger_bundle(*, req: dict, params: dict, code: str, mq5: Path, kpi: dict, provenance: dict, hard_gates: dict, role_origin: str) -> dict:
    shutil.copy2(EA_SOURCE,mq5)
    apply=apply_champion_to_canonical_ea(params,source=mq5)
    set_path=mq5.with_suffix(".set")
    preset=write_champion_tester_preset(req,params,path=set_path)
    parity=assert_champion_ea_set_parity(params,set_path,ea_source=mq5)
    meta_path=mq5.with_suffix(".json")
    entry={
        "challenger_id":code,"display_name":mq5.name,"status":"CHALLENGER","role_origin":role_origin,
        "ea_file":str(mq5),"ea_sha256":_sha(mq5),"set_file":str(set_path),"set_sha256":_sha(set_path),"metadata_file":str(meta_path),
        "params":dict(params),"kpi":dict(kpi),"hard_gates":dict(hard_gates or {}),"source_request":{
            k:req.get(k) for k in ("installation","symbol","confirm_symbol","period","from_date","to_date","deposit","leverage","model","optimization","optimizer_kpi","optimizer_trade_sample")
        },
        **provenance,
        "created_utc":utc_now(),"updated_utc":utc_now(),
        "parity":parity,"apply":apply,"preset":preset,
    }
    _atomic_json(meta_path,entry)
    return entry


def register_optimizer_challenger(app_dir: str | Path, req: dict, job: Path, ch, round_records: list[dict]) -> dict:
    payload=champion_payload(ch)
    base=_code(job.name,int(ch.round_no),int(ch.pass_no))
    code,mq5=_allocate_code(base)
    entry=_write_challenger_bundle(
        req=req,params=ch.params,code=code,mq5=mq5,kpi=_kpi_from_payload(payload),hard_gates=payload.get("hard_gates") or {},
        provenance={"source_job_id":job.name,"source_round":int(ch.round_no),"source_pass":int(ch.pass_no),"optimizer_payload":payload},
        role_origin="OPTIMIZER_WINNER",
    )
    entry["round_records"]=[{"round":r.get("round"),"report_sha256":r.get("report_sha256"),"optimizer_metrics_sha256":r.get("optimizer_metrics_sha256")} for r in round_records]
    _atomic_json(Path(entry["metadata_file"]),entry)
    def mutate(reg: dict):
        reg["baseline_strategy"]=_baseline_record()
        rows=[r for r in reg.get("entries",[]) if str(r.get("challenger_id"))!=code]
        rows.append(entry); reg["entries"]=rows; return entry
    _with_lock(app_dir,mutate)
    return entry


def _archive_baseline_before_first_promotion(req: dict, baseline: dict) -> dict:
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    out=EA_ARCHIVE_DIR/f"BASELINE-MTF-V2_{stamp}"
    out.mkdir(parents=True,exist_ok=False)
    mq5=out/EA_SOURCE.name
    shutil.copy2(EA_SOURCE,mq5)
    meta={
        "schema":"MAX_MTF_BASELINE_ARCHIVE_V1",
        "archive_id":out.name,
        "status":"ARCHIVED_PRE_FIRST_STRATEGY_CHAMPION",
        "ea_file":str(mq5),
        "ea_sha256":_sha(mq5),
        "params":dict(baseline.get("params") or read_ea_optimizer_defaults(EA_SOURCE)),
        "archived_utc":utc_now(),
        "reason":"FIRST_STRATEGY_CHALLENGER_PROMOTION",
    }
    _atomic_json(out/"manifest.json",meta)
    return meta


def _demote_current(req: dict, current: dict) -> dict:
    params=dict(current.get("params") or read_ea_optimizer_defaults(EA_SOURCE))
    base=_code("",0,0,suffix="FORMER-CHAMPION")
    code,mq5=_allocate_code(base)
    return _write_challenger_bundle(
        req=req,params=params,code=code,mq5=mq5,kpi=dict(current.get("kpi") or {}),hard_gates=dict(current.get("hard_gates") or {}),
        provenance={"source_job_id":current.get("source_job_id"),"source_round":current.get("source_round"),"source_pass":current.get("source_pass"),"demoted_from_strategy_id":current.get("strategy_id")},
        role_origin="DEMOTED_CHAMPION",
    )


def promote_strategy_challenger(app_dir: str | Path, challenger_id: str, *, installation: dict | None=None) -> dict:
    app_dir=Path(app_dir); reg=ensure_strategy_registry(app_dir)
    selected=next((dict(r) for r in reg.get("entries",[]) if str(r.get("challenger_id"))==str(challenger_id)),None)
    if not selected: raise KeyError(f"Unknown Strategy Challenger: {challenger_id}")
    if str(selected.get("status") or "") != "CHALLENGER": raise RuntimeError("Only active Strategy Challenger can be promoted")
    mq5=Path(str(selected.get("ea_file") or "")); set_src=Path(str(selected.get("set_file") or ""))
    if not mq5.is_file() or not set_src.is_file(): raise FileNotFoundError("Strategy Challenger artifact bundle is incomplete")
    if _sha(mq5)!=str(selected.get("ea_sha256") or "") or _sha(set_src)!=str(selected.get("set_sha256") or ""):
        raise RuntimeError("Strategy Challenger artifact integrity mismatch")
    req=dict(selected.get("source_request") or {})
    if installation: req["installation"]=dict(installation)
    if not isinstance(req.get("installation"),dict): raise RuntimeError("Promotion requires MT5 installation authority")
    current=dict(reg.get("current_champion") or {})
    baseline=dict(reg.get("baseline_strategy") or _baseline_record())
    params=dict(selected.get("params") or {})
    data=Path(req["installation"]["data_dir"]); tester_set=data/"MQL5"/"Profiles"/"Tester"/TESTER_SET
    before_ea=EA_SOURCE.read_bytes(); before_set=tester_set.read_bytes() if tester_set.exists() else None
    before_auth=RUNTIME_AUTHORITY.read_bytes() if RUNTIME_AUTHORITY.exists() else None
    before_reg=registry_path(app_dir).read_bytes() if registry_path(app_dir).exists() else None
    demoted=None
    baseline_archive=None
    promotion_job=RUNS_ROOT/("PROMOTE_"+datetime.now().strftime("%Y%m%d_%H%M%S")); promotion_job.mkdir(parents=True,exist_ok=True)
    try:
        if current:
            demoted=_demote_current(req,current)
        else:
            baseline_archive=_archive_baseline_before_first_promotion(req,baseline)
        apply=apply_champion_to_canonical_ea(params)
        preset=write_champion_tester_preset(req,params,path=tester_set)
        parity=assert_champion_ea_set_parity(params,tester_set,ea_source=EA_SOURCE)
        compile_req=dict(req); compile_req["ea_source"]={"path":str(EA_SOURCE),"sha256":apply["after_sha256"]}
        from strategy.strategy_optimizer_worker import compile_ea
        compile_ea(compile_req,promotion_job)
        auth=persist_optimizer_champion_authority(params=params,ea_sha256=apply["after_sha256"],job_id=str(selected.get("source_job_id") or promotion_job.name),champion_pass=int(selected.get("source_pass") or 0))
        expected={"sl_atr":float(params["InpSL_ATR"]),"tp_atr":float(params["InpTP_ATR"]),"max_hold_bars":int(round(float(params["InpMaxHoldBars"])))}
        if dict(auth.get("geometry") or {}) != expected: raise RuntimeError("Promoted Strategy authority geometry mismatch")
        new_champion={
            "strategy_id":str(challenger_id),"display_name":EA_SOURCE.name,"status":"CHAMPION","ea_file":str(EA_SOURCE),"ea_sha256":_sha(EA_SOURCE),
            "params":params,"kpi":dict(selected.get("kpi") or {}),"kpi_status":"OPTIMIZER_EVIDENCE","hard_gates":dict(selected.get("hard_gates") or {}),
            "source_job_id":selected.get("source_job_id"),"source_round":selected.get("source_round"),"source_pass":selected.get("source_pass"),"promoted_utc":utc_now(),"authority_source":"OWNER_MANUAL_STRATEGY_PROMOTION",
        }
        def mutate(reg2: dict):
            rows=[]
            for row in reg2.get("entries",[]):
                if str(row.get("challenger_id"))==str(challenger_id):
                    continue
                rows.append(row)
            if demoted:
                rows.append(demoted)
            reg2["entries"]=rows; reg2["current_champion"]=new_champion; reg2["baseline_strategy"]=_baseline_record()
            reg2.setdefault("promotion_history",[]).append({"utc":utc_now(),"promoted":challenger_id,"demoted_to":demoted.get("challenger_id") if demoted else None,"baseline_archive":baseline_archive.get("archive_id") if baseline_archive else None,"canonical_ea_sha256":new_champion["ea_sha256"]})
            return new_champion
        _with_lock(app_dir,mutate)
        return {"status":"PROMOTED","champion":new_champion,"demoted_champion":demoted,"baseline_archive":baseline_archive,"parity":parity,"preset":preset,"strategy_authority":auth}
    except Exception:
        EA_SOURCE.write_bytes(before_ea)
        if before_set is None: tester_set.unlink(missing_ok=True)
        else: tester_set.parent.mkdir(parents=True,exist_ok=True); tester_set.write_bytes(before_set)
        if before_auth is None: RUNTIME_AUTHORITY.unlink(missing_ok=True)
        else: RUNTIME_AUTHORITY.parent.mkdir(parents=True,exist_ok=True); RUNTIME_AUTHORITY.write_bytes(before_auth)
        if before_reg is None: registry_path(app_dir).unlink(missing_ok=True)
        else: registry_path(app_dir).parent.mkdir(parents=True,exist_ok=True); registry_path(app_dir).write_bytes(before_reg)
        if baseline_archive:
            try:
                shutil.rmtree(Path(str(baseline_archive.get("ea_file") or "")).parent,ignore_errors=True)
            except Exception:
                pass
        if demoted:
            for key in ("ea_file","set_file","metadata_file"):
                try: Path(str(demoted.get(key) or "")).unlink(missing_ok=True)
                except Exception: pass
        raise


def delete_strategy_challenger(app_dir: str | Path, challenger_id: str) -> dict:
    app_dir=Path(app_dir)
    def mutate(reg: dict):
        current=reg.get("current_champion") or {}
        if str(current.get("strategy_id"))==str(challenger_id): raise RuntimeError("Current Strategy Champion cannot be deleted")
        rows=list(reg.get("entries") or []); target=next((r for r in rows if str(r.get("challenger_id"))==str(challenger_id)),None)
        if target is None: raise KeyError(challenger_id)
        if str(target.get("status") or "CHALLENGER")!="CHALLENGER": raise RuntimeError("Only active Strategy Challenger can be deleted")
        tomb={k:target.get(k) for k in ("challenger_id","display_name","role_origin","ea_sha256","set_sha256","kpi","params","source_job_id","source_round","source_pass","created_utc")}
        tomb.update({"status":"DELETED","deleted_utc":utc_now()})
        for key in ("ea_file","set_file","metadata_file"):
            p=Path(str(target.get(key) or ""))
            if p.is_file(): p.unlink()
        reg["entries"]=[r for r in rows if str(r.get("challenger_id"))!=str(challenger_id)]
        reg.setdefault("tombstones",[]).append(tomb)
        return tomb
    return _with_lock(app_dir,mutate)
