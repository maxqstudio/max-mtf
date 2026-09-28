from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_MODELLAB_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_MODELLAB_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_MODELLAB_BOOTSTRAP))

from core.project_paths import EA_CHALLENGERS_DIR, MODELLAB_ROOT
from host.mt5_installation import validate_mt5_data_root
from mtf.mtf_names import EXPERT_SUBDIR
from strategy.mtf4_strategy import MTF4_PARAM_BOUNDS, evaluate_mtf4_strategy
from strategy.strategy_challenger_registry import _same_params
from strategy.strategy_optimizer import (
    ABSOLUTE_BOUNDS,
    EA_SOURCE,
    _bounds_for_params,
    _normalized_strategy_logic,
    build_set_text,
    discover_mt5_installations,
    optimizer_default_space,
)
from strategy.strategy_optimizer_worker import _compile_summary, _read_compile_log, re_search_error

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
DEFAULT_CONFIG = PKG / "owner_acceptance/runtime/OWNER_MTF4_STRATEGY_ACCEPTANCE_CONFIG.json"
EVIDENCE_ROOT = PKG / "owner_acceptance/evidence/mtf4"
FINAL_EVIDENCE = PKG / "owner_acceptance/evidence/mtf4/OWNER_MTF4_STRATEGY_ACCEPTANCE.json"
SCHEMA = "MAX_MTF4_STRATEGY_OWNER_ACCEPTANCE_V1"
MIN_PARITY_ROWS = 10


class MTF4OwnerAcceptanceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MTF4OwnerAcceptanceError(f"JSON_READ_FAILED:{path}") from exc
    if not isinstance(obj,dict):
        raise MTF4OwnerAcceptanceError(f"JSON_OBJECT_REQUIRED:{path}")
    return obj


def _write_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(dict(obj),indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")


def _git(*args: str) -> str:
    cp=subprocess.run(["git",*args],cwd=PKG,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if cp.returncode!=0:
        raise MTF4OwnerAcceptanceError("GIT_COMMAND_FAILED:"+" ".join(args))
    return cp.stdout.strip()


def source_binding(*, require_main: bool=True) -> dict[str, Any]:
    head=_git("rev-parse","HEAD")
    status=_git("status","--porcelain","--untracked-files=normal")
    if status:
        raise MTF4OwnerAcceptanceError("SOURCE_WORKTREE_NOT_CLEAN")
    if require_main:
        try:
            origin_main=_git("rev-parse","origin/main")
        except MTF4OwnerAcceptanceError:
            origin_main=""
        if origin_main and origin_main!=head:
            raise MTF4OwnerAcceptanceError(f"SOURCE_HEAD_NOT_ORIGIN_MAIN:{head}:{origin_main}")
    ea=EA_SOURCE.resolve()
    if not ea.is_file():
        raise MTF4OwnerAcceptanceError("CANONICAL_EA_MISSING")
    return {
        "git_head":head,
        "git_tree":_git("rev-parse","HEAD^{tree}"),
        "ea_relative_path":ea.relative_to(PKG).as_posix(),
        "ea_sha256":sha256_file(ea),
        "worktree_clean":True,
    }


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    obj=_json(path)
    return {
        "terminal_exe":str(obj.get("terminal_exe") or "").strip(),
        "metaeditor_exe":str(obj.get("metaeditor_exe") or "").strip(),
        "mt5_data_root":str(obj.get("mt5_data_root") or "").strip(),
        "challenger_metadata":str(obj.get("challenger_metadata") or "").strip(),
        "challenger_id":str(obj.get("challenger_id") or "").strip(),
        "timeout_seconds":max(120,min(7200,int(obj.get("timeout_seconds") or 1800))),
    }


def _resolve_installation(cfg: Mapping[str, Any]) -> dict[str,str]:
    explicit=[str(cfg.get(k) or "").strip() for k in ("terminal_exe","metaeditor_exe","mt5_data_root")]
    if any(explicit):
        if not all(explicit):
            raise MTF4OwnerAcceptanceError("EXPLICIT_MT5_INSTALLATION_REQUIRES_TERMINAL_METAEDITOR_DATA_ROOT")
        terminal=Path(explicit[0]).expanduser().resolve()
        meta=Path(explicit[1]).expanduser().resolve()
        if not terminal.is_file() or not meta.is_file():
            raise MTF4OwnerAcceptanceError("EXPLICIT_MT5_EXECUTABLE_MISSING")
        verified=validate_mt5_data_root(explicit[2])
        return {"terminal":str(terminal),"metaeditor":str(meta),"data_dir":verified.data_root,"resolution":"EXPLICIT_CONFIG"}
    installs=discover_mt5_installations()
    if len(installs)!=1:
        raise MTF4OwnerAcceptanceError(f"MT5_INSTALLATION_NOT_UNIQUE:{len(installs)}")
    inst=installs[0]
    verified=validate_mt5_data_root(inst.data_dir)
    return {"terminal":inst.terminal,"metaeditor":inst.metaeditor,"data_dir":verified.data_root,"resolution":"AUTO_DETECT_UNIQUE"}


def _candidate_metadata(path: Path) -> dict[str,Any] | None:
    try:
        obj=_json(path)
        params=obj.get("params")
        request=obj.get("source_request")
        bounds=_bounds_for_params(params if isinstance(params,dict) else {})
        if len(bounds)!=23 or not set(MTF4_PARAM_BOUNDS).issubset(bounds):
            return None
        if str(obj.get("status") or "").upper()!="CHALLENGER":
            return None
        if not isinstance(request,dict) or request.get("mtf_strategy_enabled") is not True or str(request.get("period") or "").upper()!="M15":
            return None
        if set(request.get("search_space") or {})!=set(bounds):
            return None
        if set(request.get("fixed_param_values") or {})!=set(bounds):
            return None
        if set(request.get("optimize_params") or {})-set(bounds):
            return None
        parity=obj.get("parity")
        apply=obj.get("apply")
        if not isinstance(parity,dict) or int(parity.get("parameter_count") or 0)!=23:
            return None
        if not isinstance(apply,dict) or int(apply.get("parameter_count") or 0)!=23:
            return None
        return obj
    except Exception:
        return None


def resolve_challenger(cfg: Mapping[str,Any]) -> tuple[Path,dict[str,Any]]:
    raw=str(cfg.get("challenger_metadata") or "").strip()
    wanted=str(cfg.get("challenger_id") or "").strip()
    candidates:list[tuple[Path,dict[str,Any]]]=[]
    if raw:
        path=Path(raw).expanduser()
        if not path.is_absolute():
            path=(PKG/path).resolve()
        obj=_candidate_metadata(path)
        if obj is None:
            raise MTF4OwnerAcceptanceError("CONFIGURED_CHALLENGER_NOT_MTF23_OR_LINEAGE_INCOMPLETE")
        candidates=[(path,obj)]
    else:
        for path in sorted(EA_CHALLENGERS_DIR.glob("*.json")):
            obj=_candidate_metadata(path)
            if obj is not None:
                candidates.append((path,obj))
    if wanted:
        candidates=[row for row in candidates if str(row[1].get("challenger_id") or "")==wanted]
    if len(candidates)!=1:
        raise MTF4OwnerAcceptanceError(f"MTF4_CHALLENGER_NOT_UNIQUE:{len(candidates)}")
    return candidates[0]


def verify_challenger_source_identity(path: Path, obj: Mapping[str,Any], binding: Mapping[str,Any]) -> dict[str,Any]:
    params=obj.get("params")
    payload=obj.get("optimizer_payload")
    if not isinstance(params,dict) or len(_bounds_for_params(params))!=23:
        raise MTF4OwnerAcceptanceError("CHALLENGER_PARAMETER_PROFILE_INVALID")
    if not isinstance(payload,dict) or not isinstance(payload.get("params"),dict) or not _same_params(params,payload["params"]):
        raise MTF4OwnerAcceptanceError("CHALLENGER_OPTIMIZER_PAYLOAD_VECTOR_MISMATCH")
    ea_file=Path(str(obj.get("ea_file") or "")).expanduser()
    if not ea_file.is_file() or sha256_file(ea_file)!=str(obj.get("ea_sha256") or ""):
        raise MTF4OwnerAcceptanceError("CHALLENGER_EA_ARTIFACT_MISSING_OR_SHA_MISMATCH")
    canonical_text=EA_SOURCE.read_text(encoding="utf-8")
    challenger_text=ea_file.read_text(encoding="utf-8")
    canonical_logic=hashlib.sha256(_normalized_strategy_logic(canonical_text).encode("utf-8")).hexdigest()
    challenger_logic=hashlib.sha256(_normalized_strategy_logic(challenger_text).encode("utf-8")).hexdigest()
    if canonical_logic!=challenger_logic:
        raise MTF4OwnerAcceptanceError("CHALLENGER_STRATEGY_LOGIC_NOT_CURRENT_CANONICAL")
    request=obj.get("source_request") or {}
    if str(request.get("period") or "").upper()!="M15" or request.get("mtf_strategy_enabled") is not True:
        raise MTF4OwnerAcceptanceError("CHALLENGER_REQUEST_NOT_MTF4_M15")
    return {
        "metadata_path":str(path),
        "metadata_sha256":sha256_file(path),
        "challenger_id":str(obj.get("challenger_id") or ""),
        "challenger_ea_sha256":str(obj.get("ea_sha256") or ""),
        "canonical_source_sha256":str(binding["ea_sha256"]),
        "strategy_logic_sha256":canonical_logic,
        "parameter_count":23,
    }


def _compile_current_ea(installation: Mapping[str,str], evidence_dir: Path) -> tuple[str,dict[str,Any]]:
    data=Path(installation["data_dir"])
    meta=Path(installation["metaeditor"])
    src=EA_SOURCE.resolve()
    expert_dir=data/"MQL5"/"Experts"/EXPERT_SUBDIR
    expert_dir.mkdir(parents=True,exist_ok=True)
    deployed=expert_dir/src.name
    shutil.copy2(src,deployed)
    if sha256_file(deployed)!=sha256_file(src):
        raise MTF4OwnerAcceptanceError("DEPLOYED_EA_BYTE_MISMATCH")
    ex5=deployed.with_suffix(".ex5")
    if ex5.exists():
        ex5.unlink()
    cmd=[str(meta),f"/compile:{deployed}","/log"]
    cp=subprocess.run(cmd,cwd=str(meta.parent),capture_output=True,text=True,timeout=300)
    log=deployed.with_suffix(".log")
    log_text=_read_compile_log(log) if log.exists() else (cp.stdout or "")+(cp.stderr or "")
    summary=_compile_summary(log_text)
    if not summary.get("found") or int(summary.get("errors") or 0)!=0 or re_search_error(log_text) or not ex5.is_file():
        raise MTF4OwnerAcceptanceError(f"METAEDITOR_COMPILE_FAILED:{summary}")
    evidence_dir.mkdir(parents=True,exist_ok=True)
    compile_log=evidence_dir/"metaeditor_compile.log"
    compile_log.write_text(log_text,encoding="utf-8",newline="\n")
    archived_ex5=evidence_dir/"Max_MTF.ex5"
    shutil.copy2(ex5,archived_ex5)
    return EXPERT_SUBDIR+"\\"+src.stem,{
        "command":cmd,
        "process_returncode":cp.returncode,
        "returncode_authority":"DIAGNOSTIC_ONLY",
        "compile_summary":summary,
        "canonical_source_sha256":sha256_file(src),
        "deployed_source_sha256":sha256_file(deployed),
        "compile_log":"metaeditor_compile.log",
        "compile_log_sha256":sha256_file(compile_log),
        "ex5":"Max_MTF.ex5",
        "ex5_sha256":sha256_file(archived_ex5),
        "ex5_size_bytes":archived_ex5.stat().st_size,
    }


def _append_acceptance_inputs(text: str, *, metrics_file: str, audit_file: str) -> str:
    return text + f"InpAcceptanceMetricsFile={metrics_file}\nInpMtf4AuditFile={audit_file}\n"


def _build_backtest_ini(*, expert:str,set_name:str,request:Mapping[str,Any],report_name:str) -> str:
    return "\n".join([
        "[Tester]",
        f"Expert={expert}",
        f"ExpertParameters={set_name}",
        f"Symbol={request['symbol']}",
        "Period=M15",
        f"Deposit={float(request['deposit']):.2f}",
        f"Leverage=1:{int(request['leverage'])}",
        f"Model={int(request['model'])}",
        "ExecutionMode=0",
        "Optimization=0",
        f"FromDate={request['from_date']}",
        f"ToDate={request['to_date']}",
        "ForwardMode=0",
        f"Report={report_name}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        "UseCloud=0",
        "Visual=0",
        "",
    ])


def _common_files_dir() -> Path:
    raw=os.environ.get("APPDATA","").strip()
    if not raw:
        raise MTF4OwnerAcceptanceError("APPDATA_REQUIRED_FOR_MT5_COMMON_FILES")
    path=Path(raw)/"MetaQuotes"/"Terminal"/"Common"/"Files"
    path.mkdir(parents=True,exist_ok=True)
    return path


def _wait_file(path: Path, timeout: int=30) -> None:
    end=time.time()+timeout
    while time.time()<end:
        if path.is_file() and path.stat().st_size>20:
            return
        time.sleep(0.25)
    raise MTF4OwnerAcceptanceError(f"EXPECTED_MT5_EVIDENCE_MISSING:{path.name}")


def _run_backtest(*,installation:Mapping[str,str],ini:Path,metrics_path:Path,timeout:int) -> int:
    metrics_path.unlink(missing_ok=True)
    terminal=Path(installation["terminal"])
    cp=subprocess.run([str(terminal),f"/config:{ini}"],cwd=str(terminal.parent),timeout=timeout)
    _wait_file(metrics_path)
    return int(cp.returncode)


def read_metrics(path: Path, expected_mode: str) -> dict[str,Any]:
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=1:
        raise MTF4OwnerAcceptanceError(f"ACCEPTANCE_METRICS_ROW_COUNT:{len(rows)}")
    row=rows[0]
    if str(row.get("mode") or "")!=expected_mode:
        raise MTF4OwnerAcceptanceError("ACCEPTANCE_METRICS_MODE_MISMATCH")
    numeric=("trades","net_profit","profit_factor","recovery_factor","expected_payoff","equity_dd_rel_pct","sharpe_ratio","mean_r","weighted_r","r_accounted_trades","sum_net","sum_initial_risk","accounting_errors")
    out={k:float(row[k]) for k in numeric}
    out.update({"mode":expected_mode,"symbol":row.get("symbol"),"period":row.get("period"),"valid":str(row.get("valid") or "")=="1"})
    if not out["valid"] or out["trades"]<=0 or out["accounting_errors"]!=0 or out["r_accounted_trades"]!=out["trades"] or out["sum_initial_risk"]<=0:
        raise MTF4OwnerAcceptanceError(f"ACCEPTANCE_METRICS_INVALID:{expected_mode}")
    if any(not math.isfinite(float(out[k])) for k in ("net_profit","profit_factor","recovery_factor","expected_payoff","equity_dd_rel_pct","sharpe_ratio","mean_r","weighted_r")):
        raise MTF4OwnerAcceptanceError(f"ACCEPTANCE_METRICS_NONFINITE:{expected_mode}")
    return out


def challenger_hard_gates(metrics: Mapping[str,Any], hard: Mapping[str,Any]) -> dict[str,bool]:
    gates={
        "profit_factor":float(metrics["profit_factor"])>=float(hard["profit_factor_gte"]),
        "recovery_factor":float(metrics["recovery_factor"])>=float(hard["recovery_factor_gte"]),
        "expectancy_r":float(metrics["mean_r"])>=float(hard["expectancy_r_gte"]),
        "weighted_r":float(metrics["weighted_r"])>=float(hard["weighted_r_gte"]),
        "minimum_closed_trades":int(round(float(metrics["trades"])))>=int(hard["minimum_closed_trades"]),
    }
    if not all(gates.values()):
        raise MTF4OwnerAcceptanceError("FIXED_CHALLENGER_BACKTEST_FAILED_FROZEN_OPTIMIZER_GATES:"+json.dumps(gates,sort_keys=True))
    return gates


def replay_mtf4_audit(path: Path) -> dict[str,Any]:
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if len(rows)<MIN_PARITY_ROWS:
        raise MTF4OwnerAcceptanceError(f"MTF4_PARITY_ROWS_TOO_FEW:{len(rows)}<{MIN_PARITY_ROWS}")
    mismatches=[]
    reason_counts:dict[str,int]={}
    for idx,row in enumerate(rows,2):
        try:
            direction=int(row["m15_direction"])
            decision_epoch=int(row["decision_time_mt5"])
            def stamp(name:str) -> str:
                return datetime.fromtimestamp(int(row[name]),timezone.utc).isoformat()
            params={
                "InpMtfH4MinADX":float(row["p_h4_min_adx"]),
                "InpMtfH4MinATRRatio":float(row["p_h4_min_atr_ratio"]),
                "InpMtfH4MaxATRRatio":float(row["p_h4_max_atr_ratio"]),
                "InpMtfH1MinADX":float(row["p_h1_min_adx"]),
                "InpMtfH1MaxAbsBBZ":float(row["p_h1_max_abs_bb_z"]),
                "InpMtfM5MinBodyATR":float(row["p_m5_min_body_atr"]),
                "InpMtfM5MaxOppWickATR":float(row["p_m5_max_opp_wick_atr"]),
            }
            result=evaluate_mtf4_strategy(
                m15_direction=direction,
                decision_time_utc=datetime.fromtimestamp(decision_epoch,timezone.utc).isoformat(),
                h4={"close_time_utc":stamp("h4_close_time_mt5"),"adx":float(row["h4_adx"]),"atr_ratio":float(row["h4_atr_ratio"]),"ma_fast":float(row["h4_ma_fast"]),"ma_slow":float(row["h4_ma_slow"])},
                h1={"close_time_utc":stamp("h1_close_time_mt5"),"adx":float(row["h1_adx"]),"bb_z":float(row["h1_bb_z"]),"ma_fast":float(row["h1_ma_fast"]),"ma_slow":float(row["h1_ma_slow"])},
                m5={"close_time_utc":stamp("m5_close_time_mt5"),"open":float(row["m5_open"]),"close":float(row["m5_close"]),"body_atr":float(row["m5_body_atr"]),"upper_wick_atr":float(row["m5_upper_wick_atr"]),"lower_wick_atr":float(row["m5_lower_wick_atr"])},
                params=params,
            )
            expected_decision=str(result["status"])
            expected_reason=str(result["reason"])
            actual_decision=str(row.get("gate_decision") or "")
            actual_reason=str(row.get("gate_reason") or "")
            reason_counts[actual_reason or "TAKE"]=reason_counts.get(actual_reason or "TAKE",0)+1
            if expected_decision!=actual_decision or expected_reason!=actual_reason:
                mismatches.append({"row":idx,"expected_decision":expected_decision,"actual_decision":actual_decision,"expected_reason":expected_reason,"actual_reason":actual_reason})
        except Exception as exc:
            mismatches.append({"row":idx,"error":str(exc)})
    if mismatches:
        raise MTF4OwnerAcceptanceError("MTF4_PYTHON_MT5_PARITY_MISMATCH:"+json.dumps(mismatches[:10],sort_keys=True))
    return {"rows":len(rows),"matches":len(rows),"mismatches":0,"reason_counts":reason_counts}


def _registry_snapshot() -> dict[str,Any]:
    path=ROOT/"runtime"/"strategy_challenger_registry.json"
    if not path.is_file():
        raise MTF4OwnerAcceptanceError("STRATEGY_CHALLENGER_REGISTRY_MISSING")
    obj=_json(path)
    return {
        "path":str(path),
        "sha256":sha256_file(path),
        "current_champion":obj.get("current_champion"),
        "entries":obj.get("entries") if isinstance(obj.get("entries"),list) else [],
    }


def run(config_path: Path=DEFAULT_CONFIG) -> dict[str,Any]:
    started=datetime.now(timezone.utc).isoformat()
    binding=source_binding(require_main=True)
    cfg=_read_config(config_path)
    installation=_resolve_installation(cfg)
    metadata_path,challenger=resolve_challenger(cfg)
    challenger_identity=verify_challenger_source_identity(metadata_path,challenger,binding)
    params=dict(challenger["params"])
    request=dict(challenger["source_request"])
    hard=dict(challenger.get("hard_gates") or {})
    required_hard={"profit_factor_gte","recovery_factor_gte","expectancy_r_gte","weighted_r_gte","minimum_closed_trades"}
    if set(hard)!=required_hard:
        raise MTF4OwnerAcceptanceError("CHALLENGER_HARD_GATE_SET_INVALID")

    before_registry=_registry_snapshot()
    cid=str(challenger.get("challenger_id") or "")
    matching=[x for x in before_registry["entries"] if isinstance(x,dict) and str(x.get("challenger_id") or "")==cid]
    if len(matching)!=1 or str(matching[0].get("status") or "").upper()!="CHALLENGER":
        raise MTF4OwnerAcceptanceError("SELECTED_CHALLENGER_NOT_ACTIVE_IN_REGISTRY")

    run_id=uuid.uuid4().hex
    evidence_dir=EVIDENCE_ROOT/f"{binding['git_head'][:8]}_{run_id}"
    evidence_dir.mkdir(parents=True,exist_ok=False)
    expert,compile_evidence=_compile_current_ea(installation,evidence_dir)

    control_params={k:params[k] for k in ABSOLUTE_BOUNDS}
    request["installation"]={k:installation[k] for k in ("terminal","metaeditor","data_dir")}
    control_text=build_set_text(
        optimizer_default_space(False),
        confirm_symbol=str(request["confirm_symbol"]),
        champion_params=control_params,
        fixed_param_values=control_params,
    )
    challenger_text=build_set_text(
        request["search_space"],
        confirm_symbol=str(request["confirm_symbol"]),
        champion_params=params,
        fixed_param_values=request["fixed_param_values"],
    )

    common=_common_files_dir()
    control_metrics_name=f"MAX_MTF4_{run_id}_CONTROL_METRICS.csv"
    challenger_metrics_name=f"MAX_MTF4_{run_id}_CHALLENGER_METRICS.csv"
    audit_name=f"MAX_MTF4_{run_id}_AUDIT.csv"
    control_metrics=common/control_metrics_name
    challenger_metrics=common/challenger_metrics_name
    audit_file=common/audit_name
    audit_file.unlink(missing_ok=True)

    control_text=_append_acceptance_inputs(control_text,metrics_file=control_metrics_name,audit_file="")
    challenger_text=_append_acceptance_inputs(challenger_text,metrics_file=challenger_metrics_name,audit_file=audit_name)

    preset_dir=Path(installation["data_dir"])/"MQL5"/"Profiles"/"Tester"
    preset_dir.mkdir(parents=True,exist_ok=True)
    control_set=preset_dir/f"MAX_MTF4_{run_id}_CONTROL.set"
    challenger_set=preset_dir/f"MAX_MTF4_{run_id}_CHALLENGER.set"
    control_set.write_text(control_text,encoding="utf-8",newline="\n")
    challenger_set.write_text(challenger_text,encoding="utf-8",newline="\n")

    assumptions={
        "symbol":str(request["symbol"]),
        "confirm_symbol":str(request["confirm_symbol"]),
        "period":"M15",
        "from_date":str(request["from_date"]),
        "to_date":str(request["to_date"]),
        "deposit":float(request["deposit"]),
        "leverage":int(request["leverage"]),
        "model":int(request["model"]),
        "execution_mode":0,
        "forward_mode":0,
        "expert":expert,
        "canonical_ea_sha256":binding["ea_sha256"],
        "legacy_parameter_vector":control_params,
    }

    control_ini=evidence_dir/"control.ini"
    challenger_ini=evidence_dir/"challenger.ini"
    control_ini.write_text(_build_backtest_ini(expert=expert,set_name=control_set.name,request=request,report_name=f"MAX_MTF4_{run_id}_CONTROL.xml"),encoding="utf-8",newline="\n")
    challenger_ini.write_text(_build_backtest_ini(expert=expert,set_name=challenger_set.name,request=request,report_name=f"MAX_MTF4_{run_id}_CHALLENGER.xml"),encoding="utf-8",newline="\n")

    timeout=int(cfg.get("timeout_seconds") or 1800)
    control_rc=_run_backtest(installation=installation,ini=control_ini,metrics_path=control_metrics,timeout=timeout)
    challenger_rc=_run_backtest(installation=installation,ini=challenger_ini,metrics_path=challenger_metrics,timeout=timeout)
    _wait_file(audit_file)

    control_archive=evidence_dir/"control_metrics.csv"; shutil.copy2(control_metrics,control_archive)
    challenger_archive=evidence_dir/"challenger_metrics.csv"; shutil.copy2(challenger_metrics,challenger_archive)
    audit_archive=evidence_dir/"mtf4_audit.csv"; shutil.copy2(audit_file,audit_archive)
    shutil.copy2(metadata_path,evidence_dir/"strategy_challenger.json")
    shutil.copy2(control_set,evidence_dir/"control.set")
    shutil.copy2(challenger_set,evidence_dir/"challenger.set")

    control=read_metrics(control_archive,"CONTROL")
    mtf=read_metrics(challenger_archive,"MTF4")
    hard_results=challenger_hard_gates(mtf,hard)
    parity=replay_mtf4_audit(audit_archive)

    after_registry=_registry_snapshot()
    if before_registry["current_champion"]!=after_registry["current_champion"]:
        raise MTF4OwnerAcceptanceError("OWNER_ACCEPTANCE_MUTATED_STRATEGY_CHAMPION")
    if before_registry["sha256"]!=after_registry["sha256"]:
        raise MTF4OwnerAcceptanceError("OWNER_ACCEPTANCE_MUTATED_STRATEGY_REGISTRY")

    payload={
        "schema":SCHEMA,
        "phase":"MTF_4_DETERMINISTIC_STRATEGY_CHALLENGER",
        "run_id":run_id,
        "started_utc":started,
        "completed_utc":datetime.now(timezone.utc).isoformat(),
        "overall_status":"PASS",
        "candidate_binding":binding,
        "challenger":challenger_identity,
        "installation_resolution":installation["resolution"],
        "scientific_assumptions":assumptions,
        "compile":compile_evidence,
        "control":{"process_returncode":control_rc,"returncode_authority":"DIAGNOSTIC_ONLY","metrics":control},
        "mtf_challenger":{"process_returncode":challenger_rc,"returncode_authority":"DIAGNOSTIC_ONLY","metrics":mtf,"frozen_optimizer_hard_gates":hard,"hard_gate_results":hard_results},
        "comparison":{
            "authority":"IDENTICAL_SYMBOL_WINDOW_COST_MODEL_AND_LEGACY_PARAMETER_VECTOR",
            "performance_winner_not_required_by_mtf4_contract":True,
            "delta_mean_r":float(mtf["mean_r"])-float(control["mean_r"]),
            "delta_weighted_r":float(mtf["weighted_r"])-float(control["weighted_r"]),
            "delta_profit_factor":float(mtf["profit_factor"])-float(control["profit_factor"]),
            "delta_equity_dd_rel_pct":float(mtf["equity_dd_rel_pct"])-float(control["equity_dd_rel_pct"]),
        },
        "mt5_python_parity":parity,
        "lifecycle":{
            "selected_role":"STRATEGY_CHALLENGER",
            "strategy_champion_before":before_registry["current_champion"],
            "strategy_champion_after":after_registry["current_champion"],
            "automatic_promotion":False,
        },
        "artifacts":{
            name:{"path":name,"sha256":sha256_file(evidence_dir/name)}
            for name in ("metaeditor_compile.log","Max_MTF.ex5","control.ini","challenger.ini","control_metrics.csv","challenger_metrics.csv","mtf4_audit.csv","strategy_challenger.json","control.set","challenger.set")
        },
        "evidence_dir":str(evidence_dir),
    }
    evidence_path=evidence_dir/"OWNER_MTF4_STRATEGY_ACCEPTANCE.json"
    _write_json(evidence_path,payload)
    FINAL_EVIDENCE.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(evidence_path,FINAL_EVIDENCE)
    print(json.dumps(payload,indent=2,sort_keys=True,default=str))
    return payload


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default=str(DEFAULT_CONFIG))
    args=ap.parse_args()
    try:
        run(Path(args.config))
        return 0
    except Exception as exc:
        print(f"OWNER_MTF4_ACCEPTANCE_FAIL: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
