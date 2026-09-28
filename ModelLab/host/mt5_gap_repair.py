from __future__ import annotations

import json
import os
import subprocess
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from typing import Any

import pandas as pd

RUNTIME_DIR = MODELLAB_ROOT / "runtime"

from mtf.mtf_names import TRAINING_CSV, TESTER_SET, GAP_REPAIR_SET


def _period_label(period: Any) -> str:
    try: p=int(float(period))
    except Exception: return str(period or "H1")
    mapping={1:"M1",2:"M2",3:"M3",4:"M4",5:"M5",6:"M6",10:"M10",12:"M12",15:"M15",20:"M20",30:"M30",60:"H1",120:"H2",180:"H3",240:"H4",360:"H6",480:"H8",720:"H12",1440:"D1",10080:"W1",43200:"MN1",16385:"H1",16386:"H2",16387:"H3",16388:"H4",16390:"H6",16392:"H8",16396:"H12",16408:"D1",32769:"W1",49153:"MN1"}
    return mapping.get(p, f"P{p}")


def build_gap_fill_plan(report: dict, master_csv: str | Path) -> dict:
    broker=dict(report.get("broker_reconciliation") or {})
    if not broker.get("verified"):
        raise ValueError("Gap repair ditolak: broker reconciliation belum VERIFIED")
    missing=[pd.Timestamp(x) for x in (broker.get("missing_timestamps") or [])]
    if not missing:
        return {"schema":"MAX_MT5_GAP_FILL_PLAN_V1","status":"NO_GAPS","missing_count":0}
    ident=dict(report.get("identity") or {})
    master=Path(master_csv)
    # Gap repair must reproduce the same strategy geometry already present in CP32.
    # Read only the three embedded authority columns and fail closed on mixed/stale data.
    try:
        geo_df=pd.read_csv(master,sep=";",usecols=["sl_atr","tp_atr","max_hold_bars"])
    except Exception as exc:
        raise ValueError(f"Gap repair ditolak: CP32 strategy geometry tidak dapat dibaca: {exc}") from exc
    geometry={}
    for col in ("sl_atr","tp_atr","max_hold_bars"):
        vals=pd.to_numeric(geo_df[col],errors="coerce").dropna().unique().tolist()
        if len(vals)!=1:
            raise ValueError(f"Gap repair ditolak: CP32 mixed/stale strategy geometry pada {col}: {vals[:8]}")
        geometry[col]=int(round(float(vals[0]))) if col=="max_hold_bars" else float(vals[0])
    # Existing EA first-write-wins writer is the feature-authority. Run the tester
    # across a bounded envelope around all missing timestamps; existing rows remain
    # untouched and only absent CP32 rows are appended.
    first=min(missing); last=max(missing)
    from_date=(first-pd.Timedelta(days=10)).date()
    to_date=(last+pd.Timedelta(days=2)).date()
    return {
        "schema":"MAX_MT5_GAP_FILL_PLAN_V1",
        "status":"READY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "master_csv":str(master),
        "master_filename":master.name,
        "master_sha256_before":report.get("sha256"),
        "symbol":ident.get("symbol"),
        "period":ident.get("period"),
        "timeframe":ident.get("timeframe") or _period_label(ident.get("period")),
        "broker_server":broker.get("server"),
        "broker_terminal_path":broker.get("terminal_path"),
        "broker_terminal_data_path":broker.get("terminal_data_path"),
        "missing_count":len(missing),
        "first_missing":first.isoformat(),
        "last_missing":last.isoformat(),
        "from_date":str(from_date),
        "to_date":str(to_date),
        "missing_timestamps":[x.isoformat() for x in missing],
        "strategy_geometry":geometry,
        "repair_authority":"EA_STRATEGY_TESTER_FIRST_WRITE_WINS_CP32",
        "synthetic_fill_allowed":False,
    }


def discover_mt5_gap_fill_targets(expert_filename: str = "Max.ex5") -> list[dict]:
    if os.name != "nt":
        return []
    appdata=os.environ.get("APPDATA")
    if not appdata:
        return []
    root=Path(appdata)/"MetaQuotes"/"Terminal"
    if not root.exists():
        return []
    out=[]
    for td in root.iterdir():
        if not td.is_dir() or td.name.lower()=="common":
            continue
        experts=td/"MQL5"/"Experts"
        if not experts.exists():
            continue
        hits=list(experts.rglob(expert_filename))
        if not hits:
            continue
        origin=td/"origin.txt"
        install=None
        try:
            text=origin.read_text(encoding="utf-16",errors="ignore").strip("\x00\r\n ")
            if not text:
                text=origin.read_text(encoding="utf-8",errors="ignore").strip("\x00\r\n ")
            if text:
                install=Path(text)
        except Exception:
            pass
        terminal=(install/"terminal64.exe") if install else None
        if not terminal or not terminal.exists():
            continue
        for hit in hits:
            rel=hit.relative_to(experts).with_suffix("")
            out.append({
                "terminal_exe":str(terminal),
                "data_dir":str(td),
                "expert_ex5":str(hit),
                "expert_relative":str(rel).replace("/","\\"),
                "origin":str(install),
            })
    # Stable de-duplication.
    seen=set(); uniq=[]
    for row in out:
        k=(row["terminal_exe"].lower(),row["expert_relative"].lower())
        if k not in seen:
            seen.add(k); uniq.append(row)
    return uniq



def matching_mt5_gap_fill_targets(targets: list[dict], report: dict) -> list[dict]:
    """Return only tester targets belonging to the terminal verified by audit.

    Never let a user accidentally fill gaps from another installed MT5 terminal.
    Matching by both installation path and terminal data directory is accepted; if
    neither provenance value is available, fail closed with no selectable target.
    """
    broker=dict(report.get("broker_reconciliation") or {})
    install=str(broker.get("terminal_path") or "").strip()
    data=str(broker.get("terminal_data_path") or "").strip()
    if not install and not data:
        return []
    def norm(x: str) -> str:
        try:
            return os.path.normcase(os.path.normpath(str(x or ""))).rstrip("\\/")
        except Exception:
            return str(x or "").lower().rstrip("\\/")
    ni, nd=norm(install), norm(data)
    out=[]
    for row in targets:
        terminal_parent=norm(str(Path(str(row.get("terminal_exe") or "")).parent))
        row_data=norm(str(row.get("data_dir") or ""))
        if (ni and terminal_parent==ni) or (nd and row_data==nd):
            out.append(row)
    return out


def _read_mt5_text(path: Path) -> tuple[str,str]:
    """Read MT5 text/preset files without assuming UTF-8.

    MetaTrader commonly writes .set files as UTF-16 LE with BOM (FF FE), while
    some installations/tools produce UTF-8/UTF-8-BOM.  Preserve the detected
    encoding when creating the repair preset.
    """
    raw=path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        # A BOM-less UTF-16 LE preset normally has NULs in every second byte.
        if b"\x00" in raw[:256]:
            try:
                return raw.decode("utf-16-le"), "utf-16-le"
            except UnicodeDecodeError:
                pass
        raise


def _write_mt5_text(path: Path, text: str, encoding: str) -> None:
    if encoding == "utf-16":
        path.write_text(text,encoding="utf-16")
    elif encoding == "utf-16-le":
        path.write_bytes(text.encode("utf-16-le"))
    elif encoding == "utf-8-sig":
        path.write_text(text,encoding="utf-8-sig")
    else:
        path.write_text(text,encoding="utf-8")


def _set_scalar_override(text: str, name: str, value: str) -> str:
    """Replace/append one MT5 preset input while preserving unrelated Champion inputs."""
    lines=str(text or "").splitlines()
    out=[]; found=False
    for raw in lines:
        line=raw.strip()
        is_target=bool(line and not line.startswith(";") and "=" in line and line.split("=",1)[0].strip()==name)
        if is_target:
            out.append(f"{name}={value}"); found=True
        else:
            out.append(raw)
    if not found:
        out.append(f"{name}={value}")
    return "\n".join(out).rstrip()+"\n"


def _set_fixed_optimizer_value(text: str, name: str, value: Any) -> str:
    """Pin an optimizer-owned input to one fixed value with optimization disabled."""
    sval=str(int(value)) if isinstance(value,int) else (f"{float(value):.10g}" if isinstance(value,float) else str(value))
    lines=str(text or "").splitlines()
    out=[]; found=False
    for raw in lines:
        line=raw.strip()
        if line and not line.startswith(";") and "=" in line and line.split("=",1)[0].strip()==name:
            out.append(f"{name}={sval}||{sval}||0||{sval}||N"); found=True
        else:
            out.append(raw)
    if not found:
        raise ValueError(f"Canonical Max_MTF.set tidak memiliki optimizer input wajib: {name}")
    return "\n".join(out).rstrip()+"\n"


def _read_set_value(text: str, name: str) -> str | None:
    for raw in str(text or "").splitlines():
        line=raw.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        lhs,rhs=line.split("=",1)
        if lhs.strip()==name:
            return rhs.split("||",1)[0].strip()
    return None


def _write_gap_repair_set(plan: dict, target: dict) -> Path:
    """Create a dedicated non-optimizing tester preset that can actually write CP32.

    v0.9.0 canonical Champion Max_MTF.set deliberately disables training output. Gap repair
    must never rely on MT5's implicit Max_MTF.set fallback, otherwise a tester run can finish
    without appending the missing rows.  Start from the exact Champion preset, preserve
    all strategy parameters, pin dataset geometry, and override only repair/runtime I/O.
    """
    data_dir=Path(str(target.get("data_dir") or ""))
    src=data_dir/"MQL5"/"Profiles"/"Tester"/TESTER_SET
    if not src.is_file():
        raise FileNotFoundError(
            f"Canonical Champion Tester preset tidak ditemukan: {src}. "
            "Gap repair membutuhkan Max_MTF.set agar seluruh strategy parameters identik dengan dataset authority."
        )
    text,source_encoding=_read_mt5_text(src)
    # A repair run must be a single fixed point, never a leftover optimizer range.
    optimized=[raw.strip() for raw in text.splitlines() if raw.strip() and not raw.lstrip().startswith(";") and raw.rstrip().upper().endswith("||Y")]
    if optimized:
        raise ValueError(f"Canonical Max_MTF.set masih memiliki optimization-enabled rows: {optimized[:5]}")
    geo=dict(plan.get("strategy_geometry") or {})
    for name,key in (("InpSL_ATR","sl_atr"),("InpTP_ATR","tp_atr"),("InpMaxHoldBars","max_hold_bars")):
        if key not in geo:
            raise ValueError(f"Gap-fill plan tidak memiliki strategy geometry: {key}")
        current=_read_set_value(text,name)
        if current is None:
            raise ValueError(f"Canonical Max_MTF.set missing {name}")
        try:
            if abs(float(current)-float(geo[key])) > 1e-9*max(1.0,abs(float(current)),abs(float(geo[key]))):
                raise ValueError(f"Strategy geometry mismatch {name}: Max_MTF.set={current} dataset={geo[key]}")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Invalid canonical Max_MTF.set value {name}={current}") from exc
        text=_set_fixed_optimizer_value(text,name,geo[key])
    overrides={
        "InpAllowLiveTrading":"false",
        "InpWriteTelemetry":"false",
        "InpWriteTrainingData":"true",
        "InpTrainingFile":TRAINING_CSV,
        "InpWriteChampionTrades":"false",
        "InpWriteShadowTrades":"false",
        "InpUseOnnxChampion":"false",
        "InpUseOnnxChallenger":"false",
        "InpOptimizerRunNonce":"0",
    }
    for name,value in overrides.items():
        text=_set_scalar_override(text,name,value)
    # Explicit post-write authority assertions before MT5 ever sees the preset.
    expected={"InpWriteTrainingData":"true","InpTrainingFile":TRAINING_CSV,"InpAllowLiveTrading":"false"}
    for name,value in expected.items():
        if str(_read_set_value(text,name) or "").lower()!=value.lower():
            raise RuntimeError(f"Gap repair preset parity failed: {name}")
    dest=src.with_name(GAP_REPAIR_SET)
    tmp=dest.with_suffix(dest.suffix+".tmp")
    _write_mt5_text(tmp,text,source_encoding)
    tmp.replace(dest)
    return dest


def _running_target_terminal_pids(terminal: Path) -> list[int] | None:
    """Return PIDs for the exact terminal64.exe path; None means process state unknown."""
    if os.name != "nt":
        return []
    target=os.path.normcase(os.path.normpath(str(terminal)))
    escaped=target.replace("'","''")
    script=(
        "$t='"+escaped+"'; "
        "$p=Get-CimInstance Win32_Process -Filter \"Name='terminal64.exe'\" -ErrorAction SilentlyContinue | "
        "Where-Object { $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath)).ToLowerInvariant() -eq ([IO.Path]::GetFullPath($t)).ToLowerInvariant() }; "
        "$p | ForEach-Object { $_.ProcessId }"
    )
    try:
        cp=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],capture_output=True,text=True,timeout=8,check=False)
        if cp.returncode!=0:
            return None
        out=[]
        for line in cp.stdout.splitlines():
            line=line.strip()
            if line.isdigit(): out.append(int(line))
        return out
    except Exception:
        return None


def _write_ini(plan: dict, target: dict) -> tuple[Path,Path,Path]:
    if plan.get("status")!="READY":
        raise ValueError("Gap-fill plan belum READY")
    # Current EA default input must point to the canonical Common Files master.
    # Do not silently write a different file and claim repair success.
    if str(plan.get("master_filename")) != TRAINING_CSV:
        raise ValueError(
            "One-click tester repair saat ini hanya diotorisasi untuk canonical Common Files "
            "Max_MTF_Training.csv. Dataset custom harus direpair melalui EA preset eksplisit."
        )
    repair_set=_write_gap_repair_set(plan,target)
    data_dir=Path(str(target.get("data_dir") or ""))
    config_dir=data_dir/"config"; config_dir.mkdir(parents=True,exist_ok=True)
    reports_dir=data_dir/"reports"; reports_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    ini=config_dir/f"Max_GapRepair_{stamp}.ini"
    report_name=f"Max_GapFill_{stamp}.htm"
    report_path=reports_dir/report_name
    text=(
        "[Experts]\n"
        "AllowLiveTrading=0\n"
        "Enabled=1\n\n"
        "[Tester]\n"
        f"Expert={target['expert_relative']}\n"
        f"ExpertParameters={repair_set.name}\n"
        f"Symbol={plan['symbol']}\n"
        f"Period={plan['timeframe']}\n"
        "Model=1\n"
        "ExecutionMode=0\n"
        "Optimization=0\n"
        f"FromDate={str(plan['from_date']).replace('-','.')}\n"
        f"ToDate={str(plan['to_date']).replace('-','.')}\n"
        "ForwardMode=0\n"
        f"Report=reports\\{report_name}\n"
        "ReplaceReport=1\n"
        "ShutdownTerminal=1\n"
        "UseLocal=1\n"
        "UseRemote=0\n"
        "UseCloud=0\n"
        "Visual=0\n"
    )
    # Keep the startup file deliberately ASCII: all canonical MAX tester keys and
    # current broker symbol identifiers are expected to be ASCII-compatible.
    ini.write_text(text,encoding="ascii")
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    (RUNTIME_DIR/f"max_gap_fill_{stamp}.json").write_text(json.dumps({"plan":plan,"target":target,"ini":str(ini),"repair_set":str(repair_set),"report":str(report_path)},indent=2,ensure_ascii=False),encoding="utf-8")
    return ini,repair_set,report_path


def _stop_target_terminal_if_repair_started_it(terminal: Path, preexisting_pids: set[int]) -> None:
    """Close only target-terminal processes that did not exist before repair audit."""
    current=_running_target_terminal_pids(terminal)
    if current is None:
        raise RuntimeError("Gap repair fail-closed: status process target MT5 tidak dapat diverifikasi")
    new_pids=[int(x) for x in current if int(x) not in preexisting_pids]
    if not new_pids:
        return
    if os.name!="nt":
        return
    ids=",".join(str(x) for x in new_pids)
    cp=subprocess.run(
        ["powershell.exe","-NoProfile","-NonInteractive","-Command",
         f"$ids=@({ids}); foreach($id in $ids){{ Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }}"],
        capture_output=True,text=True,timeout=10,check=False,
    )
    if cp.returncode!=0:
        raise RuntimeError("MT5 repair audit membuka terminal tetapi terminal tidak dapat ditutup untuk Strategy Tester /config")
    deadline=time.time()+8.0
    while time.time()<deadline:
        now=_running_target_terminal_pids(terminal)
        if now is not None and not [x for x in now if int(x) in new_pids]:
            return
        time.sleep(0.25)
    raise RuntimeError("MT5 repair audit terminal masih berjalan; Strategy Tester /config tidak boleh diluncurkan")


def run_gap_repair_cycle(master_csv: str | Path, *, target: dict | None = None, timeout_seconds: int = 1800) -> dict:
    """Verify/repair an exact dataset only after the local audit has failed.

    This is the only staged path allowed to open MT5:
      local audit -> FAIL -> live broker verify -> optional tester repair ->
      live broker verify -> exact-SHA broker proof cache.
    """
    from data.data_quality import audit_dataset, research_readiness

    master=Path(master_csv)
    available=discover_mt5_gap_fill_targets()
    if target is None:
        if len(available)!=1:
            raise RuntimeError(
                f"DATA_QUALITY_REPAIR_TARGET_REQUIRED: ditemukan {len(available)} target Max.ex5; "
                "pilih exact MT5 target secara manual."
            )
        target=available[0]
    target=dict(target)
    terminal=Path(str(target.get("terminal_exe") or ""))
    if not terminal.is_file():
        raise FileNotFoundError(f"terminal64.exe tidak ditemukan: {terminal}")

    before_pids=set(_running_target_terminal_pids(terminal) or [])
    live=audit_dataset(
        master,
        broker_reconcile=True,
        use_cached_broker_proof=False,
        broker_terminal_exe=terminal,
    )
    ready,reasons=research_readiness(live)
    if ready:
        # If this REPAIR/VERIFY invocation started MT5 only to establish proof,
        # close that new instance again. Never terminate an Owner-preexisting terminal.
        if not before_pids:
            _stop_target_terminal_if_repair_started_it(terminal,before_pids)
        return {
            "status":"VERIFIED_NO_REPAIR_NEEDED",
            "report":live,
            "repair_launched":False,
            "target":target,
        }

    broker=dict(live.get("broker_reconciliation") or {})
    if not broker.get("verified"):
        raise RuntimeError("DATA_QUALITY_REPAIR_BROKER_UNVERIFIED: "+str(broker.get("reason") or "unknown"))
    non_gap=[r for r in reasons if not str(r).startswith("SOURCE_BACKED_MISSING_BARS:")]
    if non_gap:
        raise RuntimeError("DATA_QUALITY_NOT_GAP_REPAIRABLE: "+" · ".join(non_gap))
    if int(broker.get("source_backed_missing_count",0) or 0)<=0:
        raise RuntimeError("DATA_QUALITY_REPAIR_REQUIRED_BUT_NO_SOURCE_BACKED_GAPS")

    # The selected target itself must be the terminal/feed that produced live proof.
    matched=matching_mt5_gap_fill_targets([target],live)
    if len(matched)!=1:
        raise RuntimeError("DATA_QUALITY_REPAIR_TARGET_FEED_MISMATCH")

    # mt5.initialize(path=...) may start the terminal. /config tester startup is
    # reliable only against a closed target. Never kill a terminal that was
    # already running before the repair operation.
    running_after=_running_target_terminal_pids(terminal)
    if running_after is None:
        raise RuntimeError("Gap repair fail-closed: status process target MT5 tidak dapat diverifikasi")
    if running_after:
        if before_pids:
            raise RuntimeError(
                "Target MT5 sudah berjalan sebelum REPAIR. Tutup terminal target lalu jalankan REPAIR lagi; "
                "Max tidak akan mematikan terminal Owner yang sudah aktif."
            )
        _stop_target_terminal_if_repair_started_it(terminal,before_pids)

    plan=build_gap_fill_plan(live,master)
    launched=launch_gap_fill_tester(plan,target,wait=True,timeout_seconds=timeout_seconds)

    # Strategy Tester has ShutdownTerminal=1. Verify the repaired bytes against
    # the same broker/feed. This creates exact-SHA cached proof used by future
    # AUDIT/AUTO RESEARCH without opening MT5.
    post_preexisting=set(_running_target_terminal_pids(terminal) or [])
    post=audit_dataset(
        master,
        broker_reconcile=True,
        use_cached_broker_proof=False,
        broker_terminal_exe=terminal,
    )
    if not post_preexisting:
        _stop_target_terminal_if_repair_started_it(terminal,post_preexisting)
    post_ready,post_reasons=research_readiness(post)
    if not post_ready:
        raise RuntimeError("DATA_QUALITY_REPAIR_POST_AUDIT_FAILED: "+" · ".join(post_reasons))
    return {
        "status":"REPAIRED_AND_VERIFIED",
        "report":post,
        "repair_launched":True,
        "launch":launched,
        "target":target,
    }


def launch_gap_fill_tester(plan: dict, target: dict, *, wait: bool = False, timeout_seconds: int = 1800) -> dict:
    if os.name != "nt":
        raise RuntimeError("MT5 gap-fill launch hanya tersedia pada Windows Owner machine")
    terminal=Path(str(target.get("terminal_exe") or ""))
    if not terminal.exists():
        raise FileNotFoundError(f"terminal64.exe tidak ditemukan: {terminal}")
    running=_running_target_terminal_pids(terminal)
    if running is None:
        raise RuntimeError("Gap repair fail-closed: status process target MT5 tidak dapat diverifikasi")
    if running:
        raise RuntimeError(
            "Target MT5 masih berjalan (PID " + ",".join(str(x) for x in running) + "). "
            "MT5 tidak menjalankan startup Strategy Tester /config secara andal pada instance terminal yang sudah aktif. "
            "Tutup terminal target ini terlebih dahulu lalu klik REPAIR MISSING FROM MT5 lagi."
        )
    ini,repair_set,report_path=_write_ini(plan,target)
    before=Path(str(plan.get("master_csv") or ""))
    before_sha=hashlib.sha256(before.read_bytes()).hexdigest() if before.is_file() else None
    proc=subprocess.Popen([str(terminal),f"/config:{ini}"],cwd=str(terminal.parent))
    status="TESTER_STARTED_PENDING_AUDIT"
    returncode=None
    if wait:
        try:
            returncode=int(proc.wait(timeout=max(30,int(timeout_seconds))))
        except subprocess.TimeoutExpired as exc:
            try: proc.terminate()
            except Exception: pass
            raise RuntimeError(f"MT5 gap-repair tester timeout setelah {timeout_seconds}s") from exc
        if returncode!=0:
            raise RuntimeError(f"MT5 gap-repair tester exit code {returncode}")
        status="TESTER_COMPLETED_PENDING_AUDIT"
    # A process handle only proves startup/completion.  Never claim the dataset
    # repaired until deterministic broker audit proves all gaps are gone.
    return {
        "status":status,
        "pid":int(proc.pid),
        "returncode":returncode,
        "terminal_exe":str(terminal),
        "config":str(ini),
        "repair_set":str(repair_set),
        "report":str(report_path),
        "master_sha256_before":before_sha,
        "missing_count":int(plan.get("missing_count",0) or 0),
        "from_date":plan.get("from_date"),
        "to_date":plan.get("to_date"),
        "authority":"MT5_STRATEGY_TESTER_FIRST_WRITE_WINS_DEDICATED_REPAIR_PRESET",
    }

