from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import json
import csv
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.sample_policy import scaled_trade_requirement
from strategy.mtf4_strategy import MTF4_PARAM_BOUNDS, MTF4_PARAM_DEFAULTS

ROOT = MODELLAB_ROOT
PACKAGE_ROOT = ROOT.parent
RUNS_ROOT = ROOT / "runtime" / "strategy_optimizer_runs"
EVIDENCE_ROOT = PACKAGE_ROOT / "owner_acceptance" / "evidence" / "strategy_optimizer"
from core.project_paths import EA_SOURCE
from mtf.mtf_names import OPTIMIZER_METRICS_CSV, OPTIMIZER_REPORT_XML, TESTER_SET

FAMILY_WEIGHT_PARAMS = (
    "InpWeightTrend", "InpWeightRange", "InpWeightBreakout", "InpWeightPullback",
    "InpWeightSession", "InpWeightShock", "InpWeightRelative",
)

# Hard compiler bounds. Scientist may narrow/shift inside these limits, never exceed them.
ABSOLUTE_BOUNDS: dict[str, tuple[float, float, float, str]] = {
    "InpWeightTrend": (0.20, 2.00, 0.10, "float"),
    "InpWeightRange": (0.20, 2.00, 0.10, "float"),
    "InpWeightBreakout": (0.20, 2.00, 0.10, "float"),
    "InpWeightPullback": (0.20, 2.00, 0.10, "float"),
    "InpWeightSession": (0.10, 1.50, 0.10, "float"),
    "InpWeightShock": (0.10, 1.50, 0.10, "float"),
    "InpWeightRelative": (0.10, 1.50, 0.10, "float"),
    "InpEntryThreshold": (0.18, 0.60, 0.02, "float"),
    "InpExitReverseThreshold": (0.20, 0.75, 0.05, "float"),
    "InpMinConsensus": (0.10, 0.70, 0.05, "float"),
    "InpSL_ATR": (1.00, 3.20, 0.20, "float"),
    "InpTP_ATR": (1.20, 5.00, 0.20, "float"),
    "InpMaxHoldBars": (6, 72, 6, "int"),
    "InpShockHaltATR": (2.50, 7.00, 0.50, "float"),
    "InpRelativeLookback": (8, 60, 4, "int"),
    "InpMinRelativeCorr": (0.10, 0.80, 0.05, "float"),
}

DEFAULT_SPACE: dict[str, dict[str, float | int]] = {
    k: {"start": lo, "step": step, "stop": hi} for k, (lo, hi, step, _typ) in ABSOLUTE_BOUNDS.items()
}

MTF4_DEFAULT_SPACE: dict[str, dict[str, float | int]] = {
    k: {"start": lo, "step": step, "stop": hi} for k, (lo, hi, step, _typ) in MTF4_PARAM_BOUNDS.items()
}


def optimizer_bounds(mtf_strategy_enabled: bool = False) -> dict[str, tuple[float, float, float, str]]:
    out=dict(ABSOLUTE_BOUNDS)
    if mtf_strategy_enabled:
        out.update(MTF4_PARAM_BOUNDS)
    return out


def optimizer_default_space(mtf_strategy_enabled: bool = False) -> dict[str, dict[str, float | int]]:
    out={k:dict(v) for k,v in DEFAULT_SPACE.items()}
    if mtf_strategy_enabled:
        out.update({k:dict(v) for k,v in MTF4_DEFAULT_SPACE.items()})
    return out


def _bounds_for_space(space: dict[str, Any]) -> dict[str, tuple[float, float, float, str]]:
    keys=set(space or {})
    legacy=set(ABSOLUTE_BOUNDS)
    mtf=set(optimizer_bounds(True))
    if keys==legacy:
        return dict(ABSOLUTE_BOUNDS)
    if keys==mtf:
        return optimizer_bounds(True)
    raise ValueError(
        "search space keys mismatch; "
        f"missing_legacy={sorted(legacy-keys)} "
        f"missing_mtf={sorted(set(MTF4_PARAM_BOUNDS)-keys)} "
        f"extra={sorted(keys-mtf)}"
    )


def _bounds_for_params(params: dict[str, Any]) -> dict[str, tuple[float, float, float, str]]:
    keys=set(params or {})
    legacy=set(ABSOLUTE_BOUNDS)
    mtf_names=set(MTF4_PARAM_BOUNDS)
    if not legacy.issubset(keys):
        raise ValueError(f"optimizer parameter vector missing legacy parameters: {sorted(legacy-keys)}")
    present=mtf_names & keys
    if present and present!=mtf_names:
        raise ValueError(f"partial MTF-4 parameter vector is forbidden: missing={sorted(mtf_names-present)}")
    return optimizer_bounds(bool(present))


def search_space_cardinality(space: dict[str, Any], optimize_params: Any = None) -> dict:
    """Return deterministic raw-grid cardinality for operator/scientist context."""
    validated=validate_search_space(space) if 'validate_search_space' in globals() else space
    selected=set(normalize_optimize_params(optimize_params,allowed_names=validated)) if optimize_params is not None else set(validated)
    counts: dict[str,int]={}
    total=1
    for name,spec in validated.items():
        if name not in selected:
            continue
        start=float(spec["start"]); step=float(spec["step"]); stop=float(spec["stop"])
        n=max(1,int(math.floor(((stop-start)/step)+1e-9))+1)
        counts[name]=n
        total*=n
    return {
        "optimized_inputs":len(counts),
        "values_per_input":counts,
        "raw_complete_grid_combinations":int(total),
        "authority":"RAW_CARTESIAN_GRID_ONLY_NOT_MT5_GENETIC_TASK_COUNT",
    }

OPTIMIZER_PF_MIN = 1.0
OPTIMIZER_RF_MIN = 0.0
OPTIMIZER_EXPECTANCY_R_MIN = 0.0
OPTIMIZER_WEIGHTED_R_MIN = 0.0
OPTIMIZER_H1_TRADES_PER_MONTH = 20
MT5_OPTIMIZATION_CRITERION_CUSTOM_MAX = 6

FIXED_INPUTS: dict[str, Any] = {
    "InpAllowLiveTrading": True,
    "InpOneDecisionPerBar": True,
    "InpRiskPct": 0.50,
    "InpUseOnnxChampion": False,
    "InpUseOnnxChallenger": False,
    "InpWriteTelemetry": False,
    "InpWriteTrainingData": False,
    "InpWriteChampionTrades": False,
    "InpWriteShadowTrades": False,
}

@dataclass(frozen=True)
class MT5Installation:
    terminal: str
    metaeditor: str
    data_dir: str
    label: str

@dataclass
class OptimizationPass:
    round_no: int
    pass_no: int
    profit_factor: float
    recovery_factor: float
    expectancy_r: float
    profit: float
    trades: int
    params: dict[str, Any]
    raw: dict[str, str]
    weighted_r: float = float("nan")
    r_accounted_trades: int = 0
    total_initial_risk: float = float("nan")
    r_sum_net: float = float("nan")
    minimum_trades_required: int = 1
    min_profit_factor_required: float = OPTIMIZER_PF_MIN
    min_recovery_factor_required: float = OPTIMIZER_RF_MIN
    min_expectancy_r_required: float = OPTIMIZER_EXPECTANCY_R_MIN
    min_weighted_r_required: float = float("-inf")

    @property
    def passed(self) -> bool:
        weighted_ok = (
            (not math.isfinite(self.min_weighted_r_required) and self.min_weighted_r_required < 0.0)
            or (math.isfinite(self.weighted_r) and self.weighted_r >= float(self.min_weighted_r_required))
        )
        return (
            self.trades >= int(self.minimum_trades_required)
            and math.isfinite(self.profit_factor) and self.profit_factor >= float(self.min_profit_factor_required)
            and math.isfinite(self.recovery_factor) and self.recovery_factor >= float(self.min_recovery_factor_required)
            and math.isfinite(self.expectancy_r) and self.expectancy_r >= float(self.min_expectancy_r_required)
            and weighted_ok
        )


def optimizer_kpi_policy(cfg: dict | None = None) -> dict:
    """Return the Strategy Optimizer KPI authority.

    The UI/request may provide an in-memory config snapshot; workers must use the
    frozen request copy and never re-read mutable UI state mid-run.
    """
    if cfg is None:
        try:
            cfg=json.loads((ROOT/"config"/"config.json").read_text(encoding="utf-8"))
        except Exception:
            cfg={}
    raw=((cfg.get("strategy_optimizer") or {}).get("kpi") or {}) if isinstance(cfg,dict) else {}
    return {
        "schema":str(raw.get("schema") or "MAX_STRATEGY_OPTIMIZER_KPI_V2"),
        "min_profit_factor":float(raw.get("min_profit_factor",OPTIMIZER_PF_MIN)),
        "min_recovery_factor":float(raw.get("min_recovery_factor",OPTIMIZER_RF_MIN)),
        "min_expectancy_r":float(raw.get("min_expectancy_r",OPTIMIZER_EXPECTANCY_R_MIN)),
        "min_weighted_r":float(raw.get("min_weighted_r",OPTIMIZER_WEIGHTED_R_MIN)),
        "base_h1_trades_per_month":int(raw.get("base_h1_trades_per_month",OPTIMIZER_H1_TRADES_PER_MONTH)),
        "timeframe_scaling":str(raw.get("timeframe_scaling","SQRT")),
        "min_timeframe_factor":float(raw.get("min_timeframe_factor",0.20)),
        "max_timeframe_factor":float(raw.get("max_timeframe_factor",4.00)),
        "rounding":"CEIL_MONTHLY_RATE_AND_FINAL_REQUIREMENT",
    }


def optimizer_trade_sample(period: str, from_date: str, to_date: str, *, kpi_profile: dict | None = None) -> dict:
    k=dict(kpi_profile or optimizer_kpi_policy())
    meta=scaled_trade_requirement(period,from_date.replace(".","-"),to_date.replace(".","-"),
        base_h1_trades_per_month=int(k["base_h1_trades_per_month"]),observed_fraction=1.0,
        timeframe_scaling=str(k.get("timeframe_scaling","SQRT")),min_timeframe_factor=float(k.get("min_timeframe_factor",0.20)),
        max_timeframe_factor=float(k.get("max_timeframe_factor",4.00)),absolute_floor=0)
    meta.update({"schema":"MAX_STRATEGY_OPTIMIZER_TRADE_SAMPLE_V1","kpi_profile":k})
    return meta


def canonical_ea_source() -> Path:
    """Return and validate the exact Strategy Optimizer EA shipped in the Max EA folder.

    The optimizer parameter universe is intentionally coupled to this EA contract.
    Max may deploy an unchanged copy into MT5 for compile/tester execution, but it
    must never synthesize a replacement EA or silently optimize an unrelated EA.
    """
    src=EA_SOURCE.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Canonical Strategy Optimizer EA missing: {src}")
    text=src.read_text(encoding="utf-8",errors="ignore")
    missing=[name for name in optimizer_bounds(True) if name not in text]
    required_fixed=("InpConfirmSymbol","InpAllowLiveTrading","InpUseMtfStrategy","InpUseOnnxChampion","InpWriteTrainingData","InpOptimizerMetricsFile","InpOptimizerRunNonce")
    missing += [name for name in required_fixed if name not in text]
    if missing:
        raise ValueError("Canonical Max MTF v2.0 EA input contract is incomplete: missing "+", ".join(sorted(set(missing))))
    return src


def canonical_ea_identity() -> dict:
    src=canonical_ea_source()
    return {
        "path":str(src),
        "package_relative_path":str(src.relative_to(PACKAGE_ROOT)).replace("\\","/"),
        "sha256":hashlib.sha256(src.read_bytes()).hexdigest(),
    }

def _atomic_write_text(path: Path, text: str) -> None:
    """Windows-safe same-directory atomic text replacement with retry/backoff."""
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    tmp=Path(tmp_name)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
            f.write(text); f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        last=None
        for attempt in range(24):
            try:
                os.replace(tmp,path); return
            except PermissionError as exc:
                last=exc
            except OSError as exc:
                if getattr(exc,"winerror",None) not in (5,32):
                    raise
                last=exc
            time.sleep(min(0.025*(attempt+1),0.30))
        if last is not None: raise last
        raise RuntimeError(f"atomic replace failed: {path}")
    finally:
        try:
            if tmp.exists(): tmp.unlink()
        except OSError:
            pass


def _format_ea_input_value(name: str, value: Any) -> str:
    _lo,_hi,_step,typ=ABSOLUTE_BOUNDS[name]
    if typ == "int":
        return str(int(round(float(value))))
    # Stable decimal representation; MQL accepts decimal literals without suffixes.
    out=f"{float(value):.10f}".rstrip("0").rstrip(".")
    return out if "." in out else out+".0"


def _normalized_strategy_logic(text: str) -> str:
    """Normalize only optimizer-owned default literals so logic mutations remain detectable."""
    out=text
    for name in ABSOLUTE_BOUNDS:
        pat=rf"(input\s+(?:double|int)\s+{re.escape(name)}\s*=\s*)([-+0-9.eE]+)(\s*;)"
        out,n=re.subn(pat,lambda m:m.group(1)+"<OPTIMIZED_DEFAULT>"+m.group(3),out,count=1)
        if n != 1:
            raise ValueError(f"EA optimizer input declaration not uniquely found: {name}")
    return out


def apply_champion_to_canonical_ea(params: dict[str, Any], *, source: str | Path | None = None) -> dict:
    """Apply champion values to the active Max MTF v2.0 baseline EA source, and nothing else.

    The EA is not regenerated. Only the whitelisted optimizer input default literals
    are changed atomically. A normalized strategy-logic hash proves strategy code did
    not change while champion defaults were applied.
    """
    src=Path(source).resolve() if source is not None else canonical_ea_source()
    if not src.is_file():
        raise FileNotFoundError(f"EA source missing: {src}")
    before=src.read_text(encoding="utf-8")
    missing=[name for name in ABSOLUTE_BOUNDS if name not in params]
    if missing:
        raise ValueError("Champion parameter set incomplete: "+", ".join(missing))
    before_logic=hashlib.sha256(_normalized_strategy_logic(before).encode("utf-8")).hexdigest()
    after=before
    changes={}
    for name in ABSOLUTE_BOUNDS:
        value=params[name]
        literal=_format_ea_input_value(name,value)
        pat=rf"(input\s+(?:double|int)\s+{re.escape(name)}\s*=\s*)([-+0-9.eE]+)(\s*;)"
        m=re.search(pat,after)
        if not m:
            raise ValueError(f"EA optimizer input declaration missing: {name}")
        old=m.group(2)
        after,n=re.subn(pat,lambda x:x.group(1)+literal+x.group(3),after,count=1)
        if n != 1:
            raise ValueError(f"EA optimizer input declaration not unique: {name}")
        changes[name]={"from":old,"to":literal}
    after_logic=hashlib.sha256(_normalized_strategy_logic(after).encode("utf-8")).hexdigest()
    if after_logic != before_logic:
        raise RuntimeError("Champion apply attempted to mutate EA strategy logic")
    before_sha=hashlib.sha256(before.encode("utf-8")).hexdigest()
    _atomic_write_text(src,after)
    after_sha=hashlib.sha256(src.read_bytes()).hexdigest()
    return {
        "schema":"MAX_STRATEGY_OPTIMIZER_EA_CHAMPION_APPLY_V1",
        "ea_path":str(src),
        "before_sha256":before_sha,
        "after_sha256":after_sha,
        "strategy_logic_sha256":after_logic,
        "changed_inputs":changes,
        "mutation_scope":"WHITELISTED_OPTIMIZER_INPUT_DEFAULTS_ONLY",
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_path(p: Path) -> str:
    try:
        return str(p.resolve())
    except Exception:
        return str(p)


def discover_mt5_installations() -> list[MT5Installation]:
    if os.name != "nt":
        return []
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        raw = os.environ.get(env_name)
        if raw:
            base = Path(raw)
            for pattern in ("MetaTrader*", "*MetaTrader*", "*MT5*"):
                candidates.extend(base.glob(pattern))
    # Also accept explicit override for non-standard broker installations.
    explicit = os.environ.get("MAX_MT5_TERMINAL")
    if explicit:
        candidates.insert(0, Path(explicit).parent)

    appdata = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    data_dirs: list[Path] = []
    if appdata.exists():
        data_dirs = [p for p in appdata.iterdir() if p.is_dir() and (p / "MQL5").exists()]

    found: dict[str, MT5Installation] = {}
    for item in candidates:
        terminal = item if item.is_file() else item / "terminal64.exe"
        if not terminal.exists():
            continue
        meta = terminal.parent / "metaeditor64.exe"
        if not meta.exists():
            continue
        matched_data: Path | None = None
        install_norm = _norm_path(terminal.parent).lower()
        for d in data_dirs:
            origin = d / "origin.txt"
            if origin.exists():
                try:
                    origin_text = origin.read_text(encoding="utf-16", errors="ignore").strip() or origin.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    origin_text = ""
                if origin_text and _norm_path(Path(origin_text)).lower() == install_norm:
                    matched_data = d
                    break
        if matched_data is None and len(data_dirs) == 1:
            matched_data = data_dirs[0]
        if matched_data is None:
            # Runtime validation will require an actual MQL5 data folder.
            continue
        key = _norm_path(terminal).lower()
        found[key] = MT5Installation(
            terminal=_norm_path(terminal), metaeditor=_norm_path(meta), data_dir=_norm_path(matched_data),
            label=f"{terminal.parent.name} · {terminal}",
        )
    return list(found.values())



def read_ea_optimizer_defaults(source: str | Path | None = None, *, mtf_strategy_enabled: bool = False) -> dict[str, Any]:
    """Read current optimizer-owned input defaults for the selected strategy profile."""
    src=Path(source).resolve() if source is not None else canonical_ea_source()
    text=src.read_text(encoding="utf-8",errors="ignore")
    bounds=optimizer_bounds(mtf_strategy_enabled)
    out: dict[str,Any]={}
    for name,(_lo,_hi,_step,typ) in bounds.items():
        m=re.search(rf"input\s+(?:double|int)\s+{re.escape(name)}\s*=\s*([-+0-9.eE]+)\s*;",text)
        if not m:
            raise ValueError(f"EA optimizer input declaration not found: {name}")
        out[name]=int(round(float(m.group(1)))) if typ=="int" else float(m.group(1))
    return out

def normalize_optimize_params(values: Any, *, allowed_names: Any = None) -> list[str]:
    allowed=list(allowed_names) if allowed_names is not None else list(ABSOLUTE_BOUNDS)
    allowed_set=set(allowed)
    if values is None:
        return list(allowed)
    if not isinstance(values,(list,tuple,set)):
        raise ValueError("optimize_params must be a list")
    out=[]
    for raw in values:
        name=str(raw)
        if name not in allowed_set:
            raise ValueError(f"unsupported optimizer parameter for selected profile: {name}")
        if name not in out:
            out.append(name)
    if not out:
        raise ValueError("Select at least one parameter to optimize")
    return out

def optimization_report_identity(path: str | Path) -> dict:
    """Read MT5 SpreadsheetML report identity without trusting filename."""
    p=Path(path)
    if not p.is_file() or p.stat().st_size < 50:
        raise FileNotFoundError(p)
    root=ET.parse(p).getroot()
    vals={}
    for elem in root.iter():
        tag=_strip_ns(elem.tag)
        if tag in {"Title","Created","Server","Deposit","Leverage"} and tag not in vals:
            vals[tag]=(elem.text or "").strip()
    title=str(vals.get("Title") or "")
    m=re.match(r"^(?P<expert>.+?)\s+(?P<symbol>\S+),(?P<period>[A-Z0-9]+)\s+(?P<from>\d{4}\.\d{2}\.\d{2})-(?P<to>\d{4}\.\d{2}\.\d{2})$",title)
    ident={"path":str(p),"title":title,"created_utc":str(vals.get("Created") or ""),"size":p.stat().st_size,"mtime":p.stat().st_mtime}
    if m: ident.update(m.groupdict())
    return ident


def expected_report_identity(req: dict) -> dict:
    return {"expert":EA_SOURCE.stem,"symbol":str(req["symbol"]),"period":str(req["period"]),"from":str(req["from_date"]),"to":str(req["to_date"])}


def report_matches_request(path: str | Path, req: dict, *, not_before_epoch: float | None = None) -> bool:
    try: ident=optimization_report_identity(path)
    except Exception: return False
    exp=expected_report_identity(req)
    if any(str(ident.get(k) or "") != str(exp[k]) for k in ("expert","symbol","period","from","to")):
        return False
    if not_before_epoch is not None:
        # MT5 SpreadsheetML <Created> is not a trustworthy UTC freshness clock on
        # every terminal/timezone combination.  It remains provenance metadata only.
        # Legacy freshness filtering therefore uses the filesystem mtime epoch; new
        # rounds use the stronger pre-launch fingerprint authority in the worker.
        modified=float(ident.get("mtime") or 0.0)
        if modified < float(not_before_epoch)-120.0:
            return False
    return True


def discover_optimization_reports(req: dict, *, not_before_epoch: float | None = None) -> list[Path]:
    data=Path(req["installation"]["data_dir"])
    terminal=Path(req["installation"]["terminal"])
    roots=[data/"MQL5"/"Profiles"/"Tester", data, terminal.parent]
    seen=set(); hits=[]
    for root in roots:
        if not root.exists(): continue
        for pat in ("ReportOptimizer*.xml",OPTIMIZER_REPORT_XML,"Max_MTF_R*.xml","MAX_MTF_StrategyOptimizer*.xml","*.xml"):
            for p in root.glob(pat):
                key=str(p.resolve()).lower()
                if key in seen: continue
                seen.add(key)
                if report_matches_request(p,req,not_before_epoch=not_before_epoch): hits.append(p)
    return sorted(hits,key=lambda p:p.stat().st_mtime,reverse=True)


def is_max_generated_optimizer_report(path: str | Path) -> bool:
    """True only for XML reports generated by MAX Strategy Optimizer itself.

    These reports are valid round evidence only for the job that owns them.  They must
    never be auto-consumed as bootstrap evidence for a brand-new Optimizer job, because
    a stale prior-job R2/R3 can otherwise outrank the Owner's manual ReportOptimizer XML
    solely by filesystem mtime and silently change the scientific evidence being judged.
    """
    name=Path(path).name.lower()
    return name=="max.xml" or name.startswith("max_strategyoptimizer_") or bool(re.fullmatch(r"max_r\d+\.xml", name))


def optimizer_metrics_sidecar_for_report(path: str | Path) -> Path:
    """Return the only bootstrap-safe Weighted-R sidecar name for an external XML."""
    p=Path(path)
    return p.with_name(p.stem+".metrics.csv")


def discover_bootstrap_optimization_reports(req: dict) -> list[Path]:
    """Discover external/manual XML that is scientifically complete for v0.8.5.

    Weighted R is an independent hard gate and is not present in native SpreadsheetML.
    Therefore XML-only legacy evidence is no longer Champion-compatible. START may
    bootstrap only an external report with an explicitly paired `<stem>.metrics.csv`
    sidecar; same-job Max_MTF.xml/Max_MTF_metrics.csv recovery remains checkpoint-owned.
    """
    return [
        p for p in discover_optimization_reports(req)
        if not is_max_generated_optimizer_report(p) and optimizer_metrics_sidecar_for_report(p).is_file()
    ]

def validate_search_space(space: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    if not isinstance(space,dict):
        raise ValueError("search_space must be an object")
    bounds=_bounds_for_space(space)
    out={}
    for name in bounds:
        spec=space[name]
        if not isinstance(spec,dict):
            raise ValueError(f"{name}: range must be an object")
        lo,hi,base_step,typ=bounds[name]
        try:
            start=float(spec["start"]); step=float(spec["step"]); stop=float(spec["stop"])
        except Exception as exc:
            raise ValueError(f"{name}: start/step/stop required") from exc
        if not all(math.isfinite(v) for v in (start,step,stop)):
            raise ValueError(f"{name}: non-finite range")
        if step<=0 or start<lo-1e-12 or stop>hi+1e-12 or stop<start:
            raise ValueError(f"{name}: range outside hard bounds")
        if step < base_step*0.5 - 1e-12:
            raise ValueError(f"{name}: step below deterministic floor")
        if name in FAMILY_WEIGHT_PARAMS and start<=0.0:
            raise ValueError(f"{name}: seven-family contract forbids zero/negative weight")
        if typ=="int":
            start=int(round(start)); step=int(round(step)); stop=int(round(stop))
            if step<1:
                raise ValueError(f"{name}: integer step must be >=1")
        out[name]={"start":start,"step":step,"stop":stop}
    return out

def _format_set_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def build_set_text(space: dict[str, Any], *, confirm_symbol: str, champion_params: dict[str, Any] | None = None, training: bool = False, optimize_params: Any = None, fixed_param_values: dict[str,Any] | None = None, optimizer_metrics_file: str = OPTIMIZER_METRICS_CSV, optimizer_run_nonce: int = 0) -> str:
    space=validate_search_space(space)
    bounds=_bounds_for_space(space)
    mtf_strategy_enabled=set(MTF4_PARAM_BOUNDS).issubset(bounds)
    confirm_symbol=str(confirm_symbol or "").strip()
    if not confirm_symbol:
        raise ValueError("Confirm Symbol wajib diisi agar 7 strategi aktif")
    lines=["; MAX Strategy Optimizer V2","; 7 strategy families remain active as one system"]
    selected=set(normalize_optimize_params(optimize_params,allowed_names=bounds)) if optimize_params is not None else set(bounds)
    frozen=dict(fixed_param_values or read_ea_optimizer_defaults(mtf_strategy_enabled=mtf_strategy_enabled))
    fixed=dict(FIXED_INPUTS)
    fixed["InpConfirmSymbol"]=confirm_symbol
    fixed["InpUseMtfStrategy"]=bool(mtf_strategy_enabled)
    fixed["InpOptimizerMetricsFile"]=str(optimizer_metrics_file or OPTIMIZER_METRICS_CSV)
    fixed["InpOptimizerRunNonce"]=int(optimizer_run_nonce)
    if training:
        fixed["InpWriteTelemetry"]=True
        fixed["InpWriteTrainingData"]=True
    if champion_params is None:
        for name,spec in space.items():
            if name in selected:
                default=(float(spec["start"])+float(spec["stop"]))/2.0
                typ=bounds[name][3]
                if typ=="int":
                    default=int(round(default))
                lines.append(f"{name}={_format_set_value(default)}||{_format_set_value(spec['start'])}||{_format_set_value(spec['step'])}||{_format_set_value(spec['stop'])}||Y")
            else:
                val=frozen[name]
                lines.append(f"{name}={_format_set_value(val)}||{_format_set_value(val)}||0||{_format_set_value(val)}||N")
    else:
        for name in bounds:
            if name not in champion_params:
                raise ValueError(f"champion missing optimized parameter {name}")
            val=champion_params[name]
            lines.append(f"{name}={_format_set_value(val)}||{_format_set_value(val)}||0||{_format_set_value(val)}||N")
    for name,val in fixed.items():
        lines.append(f"{name}={_format_set_value(val)}")
    return "\n".join(lines)+"\n"

def _same_numeric(a: Any, b: Any, tol: float = 1e-9) -> bool:
    try:
        aa=float(a); bb=float(b)
    except Exception:
        return False
    return math.isfinite(aa) and math.isfinite(bb) and abs(aa-bb) <= tol * max(1.0,abs(aa),abs(bb))


def parse_set_optimizer_entries(text: str) -> dict[str, dict[str, Any]]:
    """Parse optimizer-owned .set rows including MT5 optimize flag."""
    out: dict[str, dict[str, Any]]={}
    for raw in str(text or "").splitlines():
        line=raw.strip()
        if not line or line.startswith(';') or '=' not in line:
            continue
        name,rhs=line.split('=',1)
        name=name.strip()
        if name not in ABSOLUTE_BOUNDS:
            continue
        parts=rhs.split('||')
        if len(parts) != 5:
            raise ValueError(f"{name}: malformed MT5 set row")
        typ=ABSOLUTE_BOUNDS[name][3]
        value=int(round(float(parts[0]))) if typ=='int' else float(parts[0])
        out[name]={
            'value':value,
            'start':parts[1],
            'step':parts[2],
            'stop':parts[3],
            'optimize':parts[4].strip().upper(),
        }
    return out


def validate_champion_tester_preset_text(text: str, champion_params: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless every optimizer-owned input is the exact Champion and non-optimized."""
    missing=[name for name in ABSOLUTE_BOUNDS if name not in champion_params]
    if missing:
        raise ValueError('Champion parameter set incomplete: '+', '.join(missing))
    entries=parse_set_optimizer_entries(text)
    if set(entries) != set(ABSOLUTE_BOUNDS):
        missing_rows=sorted(set(ABSOLUTE_BOUNDS)-set(entries))
        extra_rows=sorted(set(entries)-set(ABSOLUTE_BOUNDS))
        raise ValueError(f"Champion Max_MTF.set optimizer rows mismatch; missing={missing_rows}, extra={extra_rows}")
    mismatches=[]
    for name,(_lo,_hi,_step,typ) in ABSOLUTE_BOUNDS.items():
        expected=int(round(float(champion_params[name]))) if typ=='int' else float(champion_params[name])
        actual=entries[name]['value']
        if (typ=='int' and int(actual)!=int(expected)) or (typ!='int' and not _same_numeric(actual,expected)):
            mismatches.append(f"{name}: set={actual} champion={expected}")
        if entries[name]['optimize'] != 'N':
            mismatches.append(f"{name}: optimize={entries[name]['optimize']} expected=N")
        # A Champion preset must be a single fixed point, never a leftover search range.
        try:
            start=float(entries[name]['start']); stop=float(entries[name]['stop']); step=float(entries[name]['step'])
            if not (_same_numeric(start,expected) and _same_numeric(stop,expected) and _same_numeric(step,0.0)):
                mismatches.append(f"{name}: stale range start={start} step={step} stop={stop}")
        except Exception:
            mismatches.append(f"{name}: non-numeric Champion range fields")
    if mismatches:
        raise RuntimeError('Champion Max_MTF.set parity failed: '+'; '.join(mismatches[:12]))
    return {
        'schema':'MAX_STRATEGY_OPTIMIZER_CHAMPION_SET_PARITY_V1',
        'optimizer_owned_parameter_count':len(ABSOLUTE_BOUNDS),
        'all_values_match_champion':True,
        'all_optimization_flags_disabled':True,
    }


def write_champion_tester_preset(req: dict[str, Any], champion_params: dict[str, Any], *, path: str | Path | None = None) -> dict[str, Any]:
    """Atomically replace canonical Tester Max_MTF.set with the exact Champion fixed point.

    This is the Owner manual-backtest preset committed when a Champion is selected.
    It intentionally keeps tester trading enabled while disabling optimization on all
    optimizer-owned inputs.
    """
    data_dir=Path((req.get('installation') or {}).get('data_dir') or '')
    if path is None:
        if not str(data_dir):
            raise ValueError('MT5 installation data_dir missing for Champion Max_MTF.set commit')
        dest=data_dir/'MQL5'/'Profiles'/'Tester'/TESTER_SET
    else:
        dest=Path(path)
    text=build_set_text(
        req.get('search_space') or DEFAULT_SPACE,
        confirm_symbol=str(req.get('confirm_symbol') or ''),
        champion_params=champion_params,
        fixed_param_values=req.get('fixed_param_values'),
        optimizer_metrics_file=OPTIMIZER_METRICS_CSV,
        optimizer_run_nonce=0,
    )
    parity=validate_champion_tester_preset_text(text,champion_params)
    _atomic_write_text(dest,text)
    persisted=dest.read_text(encoding='utf-8')
    validate_champion_tester_preset_text(persisted,champion_params)
    return {
        **parity,
        'schema':'MAX_STRATEGY_OPTIMIZER_CHAMPION_TESTER_PRESET_V1',
        'path':str(dest),
        'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
        'preset_name':TESTER_SET,
        'purpose':'OWNER_MANUAL_STRATEGY_TESTER_BACKTEST_EXACT_CHAMPION',
    }


def assert_champion_ea_set_parity(champion_params: dict[str, Any], set_path: str | Path, *, ea_source: str | Path | None = None) -> dict[str, Any]:
    """Prove exact Champion parity between canonical EA defaults and Tester Max_MTF.set."""
    ea=read_ea_optimizer_defaults(ea_source)
    preset=validate_champion_tester_preset_text(Path(set_path).read_text(encoding='utf-8'),champion_params)
    mismatches=[]
    for name,(_lo,_hi,_step,typ) in ABSOLUTE_BOUNDS.items():
        expected=int(round(float(champion_params[name]))) if typ=='int' else float(champion_params[name])
        actual=ea[name]
        if (typ=='int' and int(actual)!=int(expected)) or (typ!='int' and not _same_numeric(actual,expected)):
            mismatches.append(f"{name}: ea={actual} champion={expected}")
    if mismatches:
        raise RuntimeError('Champion EA/Max_MTF.set parity failed: '+'; '.join(mismatches[:12]))
    return {
        'schema':'MAX_STRATEGY_OPTIMIZER_CHAMPION_EA_SET_PARITY_V1',
        'parameter_count':len(ABSOLUTE_BOUNDS),
        'ea_defaults_match_champion':True,
        'tester_preset_matches_champion':bool(preset.get('all_values_match_champion')),
        'tester_optimization_disabled':bool(preset.get('all_optimization_flags_disabled')),
    }


def build_tester_ini(*, expert: str, set_name: str, symbol: str, period: str, from_date: str, to_date: str,
                     deposit: float, leverage: int, model: int, report_path: str, optimization: int = 2) -> str:
    if optimization not in (1, 2):
        raise ValueError("V2 only allows native MT5 complete/genetic optimization")
    return "\n".join([
        "[Tester]",
        f"Expert={expert}",
        f"ExpertParameters={set_name}",
        f"Symbol={symbol}",
        f"Period={period}",
        f"Deposit={float(deposit):.2f}",
        f"Leverage=1:{int(leverage)}",
        f"Model={int(model)}",
        "ExecutionMode=0",
        f"Optimization={optimization}",
        f"OptimizationCriterion={MT5_OPTIMIZATION_CRITERION_CUSTOM_MAX}",
        f"FromDate={from_date}",
        f"ToDate={to_date}",
        "ForwardMode=0",
        f"Report={report_path}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        "UseCloud=0",
        "Visual=0",
        "",
    ])


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _row_values(row: ET.Element) -> list[str]:
    vals=[]
    for elem in row.iter():
        if _strip_ns(elem.tag) == "Data":
            vals.append((elem.text or "").strip())
    return vals


def _f(v: Any, default: float = float("nan")) -> float:
    s = str(v or "").strip().replace("\u00a0", " ").replace(" ", "")
    if not s: return default
    if s.endswith("%"):
        s = s[:-1]
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try: return float(s)
    except Exception: return default


def _i(v: Any, default: int = 0) -> int:
    try: return int(round(_f(v, float(default))))
    except Exception: return default



def _parameter_signature(params: dict[str, Any]) -> tuple[tuple[str, int | float], ...]:
    """Canonical identity for one legacy or MTF Strategy Optimizer parameter vector."""
    bounds=_bounds_for_params(params)
    out=[]
    for name,(_lo,_hi,_step,typ) in bounds.items():
        value=params[name]
        value=int(round(float(value))) if typ=="int" else round(float(value),10)
        out.append((name,value))
    return tuple(out)

def _parse_frame_inputs_blob(blob: str) -> dict[str, Any]:
    raw: dict[str,str]={}
    for token in str(blob or "").split("|"):
        token=token.strip()
        if not token or "=" not in token:
            continue
        name,value=token.split("=",1)
        raw[name.strip()]=value.strip()
    mtf_names=set(MTF4_PARAM_BOUNDS)
    present=mtf_names & set(raw)
    if present and present!=mtf_names:
        raise ValueError(f"Optimizer FrameInputs contains partial MTF-4 vector: missing={sorted(mtf_names-present)}")
    bounds=optimizer_bounds(bool(present))
    params: dict[str,Any]={}
    missing=[]
    for name,(_lo,_hi,_step,typ) in bounds.items():
        if name not in raw:
            missing.append(name)
            continue
        value=raw[name]
        params[name]=_i(value) if typ=="int" else _f(value)
        if not math.isfinite(float(params[name])):
            raise ValueError(f"Non-finite optimizer FrameInputs value for {name}: {value!r}")
    if missing:
        raise ValueError(f"Optimizer FrameInputs missing profile parameters: {missing}")
    return params

def parse_optimizer_metrics_csv(path: str | Path, *, expected_nonce: int | None = None) -> dict[tuple[tuple[str, int | float], ...], dict[str, Any]]:
    """Read parameter-bound Weighted-R evidence exported by ``Max.mq5``.

    The frame pass id is preserved as an exact unsigned integer for provenance but
    is deliberately *not* used to join against the MT5 XML ``Pass`` column. Real
    Fast Genetic evidence proved those are different pass namespaces. ``FrameInputs``
    is the authoritative bridge between the optimization frame and XML row.
    """
    p=Path(path)
    if not p.is_file() or p.stat().st_size < 20:
        raise FileNotFoundError(f"Optimizer R-metrics sidecar missing/empty: {p}")
    out: dict[tuple[tuple[str,int|float],...],dict[str,Any]]={}
    seen_frame_ids:set[int]=set()
    with p.open("r",encoding="utf-8-sig",errors="strict",newline="") as f:
        rd=csv.DictReader(f)
        required={"frame_pass_id","frame_inputs","mean_expectancy_r","weighted_r","mt5_trades","r_accounted_trades","sum_net","sum_initial_risk","accounting_errors","run_nonce"}
        if not rd.fieldnames or not required.issubset({str(x).strip() for x in rd.fieldnames}):
            raise ValueError(f"Optimizer R-metrics sidecar schema mismatch (v0.8.8 FrameInputs identity required): {p}")
        for row in rd:
            try:
                # Never parse a 64-bit frame id through IEEE-754 float: adjacent
                # ids above 2^53 collapse to the same integer.
                frame_pass_id=int(str(row["frame_pass_id"]).strip(),10)
                nonce=int(str(row["run_nonce"]).strip(),10)
                frame_params=_parse_frame_inputs_blob(row["frame_inputs"])
                signature=_parameter_signature(frame_params)
                rec={
                    "frame_pass_id":frame_pass_id,
                    "frame_params":frame_params,
                    "mean_expectancy_r":float(row["mean_expectancy_r"]),
                    "weighted_r":float(row["weighted_r"]),
                    "mt5_trades":int(str(row["mt5_trades"]).strip(),10),
                    "r_accounted_trades":int(str(row["r_accounted_trades"]).strip(),10),
                    "sum_net":float(row["sum_net"]),
                    "sum_initial_risk":float(row["sum_initial_risk"]),
                    "accounting_errors":int(str(row["accounting_errors"]).strip(),10),
                    "run_nonce":nonce,
                }
            except Exception as exc:
                raise ValueError(f"Malformed optimizer R-metrics row: {row}") from exc
            if expected_nonce is not None and nonce != int(expected_nonce):
                continue
            if frame_pass_id in seen_frame_ids:
                raise ValueError(f"Duplicate exact optimizer frame pass id: {frame_pass_id}")
            seen_frame_ids.add(frame_pass_id)
            if signature in out:
                raise ValueError(f"Duplicate optimizer parameter-vector metrics evidence: {dict(signature)}")
            if rec["accounting_errors"] != 0 or rec["mt5_trades"] != rec["r_accounted_trades"]:
                raise ValueError(f"R-accounting parity failure in frame {frame_pass_id}: {rec}")
            if rec["sum_initial_risk"] <= 0.0:
                raise ValueError(f"Invalid summed initial risk in frame {frame_pass_id}")
            if not all(math.isfinite(float(rec[k])) for k in ("mean_expectancy_r","weighted_r","sum_net","sum_initial_risk")):
                raise ValueError(f"Non-finite optimizer R metrics in frame {frame_pass_id}")
            derived=float(rec["sum_net"])/float(rec["sum_initial_risk"])
            if abs(derived-float(rec["weighted_r"])) > 1e-9*max(1.0,abs(derived),abs(float(rec["weighted_r"]))):
                raise ValueError(f"Weighted-R arithmetic mismatch in frame {frame_pass_id}")
            out[signature]=rec
    if not out:
        raise ValueError("Optimizer R-metrics sidecar contains no rows for the frozen run nonce")
    return out

def parse_optimization_xml(path: str | Path, *, round_no: int, metrics_path: str | Path | None = None, expected_nonce: int | None = None, require_weighted_metrics: bool = False) -> list[OptimizationPass]:
    p = Path(path)
    if not p.exists() or p.stat().st_size < 50:
        raise FileNotFoundError(f"MT5 optimization report missing/empty: {p}")
    tree = ET.parse(p)
    metrics_map = parse_optimizer_metrics_csv(metrics_path,expected_nonce=expected_nonce) if metrics_path is not None else {}
    rows = [_row_values(r) for r in tree.getroot().iter() if _strip_ns(r.tag) == "Row"]
    rows = [r for r in rows if r]
    header_idx = None
    for idx, row in enumerate(rows):
        low = [x.strip().lower() for x in row]
        if "pass" in low and any("profit factor" in x for x in low):
            header_idx = idx; break
    if header_idx is None:
        raise ValueError("MT5 XML header not recognized (Pass / Profit Factor required)")
    headers = rows[header_idx]
    norm = {re.sub(r"\s+", " ", h.strip().lower()): i for i, h in enumerate(headers)}
    def col(*names: str) -> int | None:
        for n in names:
            n = n.lower()
            if n in norm: return norm[n]
        return None
    pass_col=col("pass"); pf_col=col("profit factor"); rf_col=col("recovery factor")
    custom_col=col("custom"); result_col=col("result"); profit_col=col("profit"); trades_col=col("trades", "total trades")
    if pass_col is None or pf_col is None or (custom_col is None and result_col is None):
        raise ValueError("MT5 XML lacks required optimizer columns")
    # v0.8.4 uses Custom max as native MT5 genetic fitness, so Result is Expectancy R.
    # Recovery Factor remains an independent hard gate and therefore must come from
    # the dedicated Recovery Factor column. Falling back to Result would silently
    # turn the RF gate into a second Expectancy gate.
    if rf_col is None:
        raise ValueError("MT5 XML lacks dedicated Recovery Factor required by Custom-max optimizer contract")
    parsed: list[OptimizationPass] = []
    for row in rows[header_idx+1:]:
        if pass_col >= len(row): continue
        pass_no = _i(row[pass_col], -1)
        if pass_no < 0: continue
        def value_at(ix: int | None) -> str:
            return row[ix] if ix is not None and ix < len(row) else ""
        # Custom is the canonical exported OnTester value when present. Under the
        # v0.8.4 Custom-max criterion, Result is the same Expectancy-R fitness and is
        # a safe fallback only for exports that omit a dedicated Custom column.
        expectancy = _f(value_at(custom_col if custom_col is not None else result_col))
        if not math.isfinite(expectancy) and result_col is not None:
            expectancy = _f(value_at(result_col))
        params: dict[str, Any] = {}
        all_bounds=optimizer_bounds(True)
        for name, (_lo,_hi,_st,typ) in all_bounds.items():
            ix = None
            for candidate in (name.lower(), name.replace("Inp", "").lower()):
                if candidate in norm: ix = norm[candidate]; break
            if ix is not None and ix < len(row):
                raw = row[ix]
                params[name] = _i(raw) if typ == "int" else _f(raw)
        # Some MT5 builds put all optimized inputs in a single Inputs column.
        inputs_col=col("inputs", "optimized inputs")
        if len(params) < len(all_bounds) and inputs_col is not None and inputs_col < len(row):
            blob=row[inputs_col]
            for name, (_lo,_hi,_st,typ) in all_bounds.items():
                m=re.search(rf"(?:^|[;,\s]){re.escape(name)}\s*=\s*([-+0-9.eE]+)",blob)
                if m: params[name]=_i(m.group(1)) if typ=="int" else _f(m.group(1))
        mtf_present=set(MTF4_PARAM_BOUNDS) & set(params)
        if mtf_present and mtf_present!=set(MTF4_PARAM_BOUNDS):
            continue
        bounds=optimizer_bounds(bool(mtf_present))
        if not set(bounds).issubset(params):
            continue
        params={name:params[name] for name in bounds}
        signature=_parameter_signature(params)
        metric=metrics_map.get(signature) or {}
        if metric:
            side_mean=float(metric["mean_expectancy_r"])
            if math.isfinite(expectancy) and abs(side_mean-expectancy) > 5e-6*max(1.0,abs(side_mean),abs(expectancy)):
                raise ValueError(f"Mean-R XML/frame mismatch in pass {pass_no}: xml={expectancy} frame={side_mean}")
            xml_trades=_i(value_at(trades_col),0)
            if int(metric["mt5_trades"]) != int(xml_trades):
                raise ValueError(f"Trade-count XML/frame mismatch in pass {pass_no}: xml={xml_trades} frame={metric['mt5_trades']}")
            xml_profit=_f(value_at(profit_col),0.0)
            if abs(float(metric["sum_net"])-float(xml_profit)) > 0.011:
                raise ValueError(f"Net-profit XML/frame mismatch in pass {pass_no}: xml={xml_profit} frame={metric['sum_net']}")
            expectancy=side_mean
        parsed.append(OptimizationPass(
            round_no=round_no, pass_no=pass_no,
            profit_factor=_f(value_at(pf_col)), recovery_factor=_f(value_at(rf_col)),
            expectancy_r=expectancy, profit=_f(value_at(profit_col),0.0), trades=_i(value_at(trades_col),0),
            params=params, raw={headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))},
            weighted_r=float(metric.get("weighted_r",float("nan"))),
            r_accounted_trades=int(metric.get("r_accounted_trades",0) or 0),
            total_initial_risk=float(metric.get("sum_initial_risk",float("nan"))),
            r_sum_net=float(metric.get("sum_net",float("nan"))),
        ))
    if not parsed:
        raise ValueError("MT5 optimization report contains no parseable passes with a complete optimizer profile")
    if require_weighted_metrics:
        # v0.8.9: MT5 optimization cache can populate XML rows without replaying
        # OnTesterPass/OnTesterDeinit frames. Missing sidecar evidence therefore
        # makes only those rows ineligible; it must not destroy an otherwise useful
        # multi-hour round. Sidecar vectors that do not exist in XML are still a
        # hard provenance error. Fresh runs disable tester cache in Max.mq5.
        sidecar_keys=set(metrics_map)
        xml_keys={_parameter_signature(r.params) for r in parsed}
        extra=sidecar_keys-xml_keys
        if extra:
            extra_preview=[dict(x) for x in list(extra)[:3]]
            raise ValueError(f"Optimizer weighted-R sidecar contains non-XML parameter vectors: {extra_preview}")
    return parsed


def _passes_nonweighted_gates(r: OptimizationPass) -> bool:
    return (
        r.trades >= int(r.minimum_trades_required)
        and math.isfinite(r.profit_factor) and r.profit_factor >= float(r.min_profit_factor_required)
        and math.isfinite(r.recovery_factor) and r.recovery_factor >= float(r.min_recovery_factor_required)
        and math.isfinite(r.expectancy_r) and r.expectancy_r >= float(r.min_expectancy_r_required)
    )

def _refinement_score(r: OptimizationPass) -> tuple:
    if not all(math.isfinite(x) for x in (r.profit_factor,r.recovery_factor,r.expectancy_r)):
        return (-1,-1,float("-inf"),float("-inf"),float("-inf"),float("-inf"))
    known_count=(
        int(r.trades >= int(r.minimum_trades_required))
        + int(r.profit_factor >= float(r.min_profit_factor_required))
        + int(r.recovery_factor >= float(r.min_recovery_factor_required))
        + int(r.expectancy_r >= float(r.min_expectancy_r_required))
    )
    weighted_pass=int(math.isfinite(r.weighted_r) and r.weighted_r >= float(r.min_weighted_r_required))
    return (known_count,r.expectancy_r,r.profit_factor,r.recovery_factor,weighted_pass,r.weighted_r if math.isfinite(r.weighted_r) else float("-inf"))

def select_champion(rows: list[OptimizationPass]) -> OptimizationPass | None:
    # Never promote a complete row while another row already clears every XML/native
    # gate but lacks Weighted-R evidence; that unresolved contender could outrank it.
    # Historical/unit rows may explicitly disable Weighted R with -inf.
    def weighted_required(r: OptimizationPass) -> bool:
        return math.isfinite(r.min_weighted_r_required) or not (r.min_weighted_r_required < 0.0)
    unresolved=[r for r in rows if weighted_required(r) and _passes_nonweighted_gates(r) and not math.isfinite(r.weighted_r)]
    if unresolved:
        return None
    eligible=[r for r in rows if r.passed and all(math.isfinite(x) for x in (r.profit_factor,r.recovery_factor,r.expectancy_r))
              and (not weighted_required(r) or math.isfinite(r.weighted_r))]
    if not eligible: return None
    return max(eligible, key=lambda r: (r.weighted_r if math.isfinite(r.weighted_r) else float("-inf"), r.expectancy_r, r.profit_factor, r.recovery_factor, -r.pass_no))


def best_near_miss(rows: list[OptimizationPass]) -> OptimizationPass | None:
    finite=[r for r in rows if all(math.isfinite(x) for x in (r.profit_factor,r.recovery_factor,r.expectancy_r))]
    if not finite: return None
    return max(finite,key=lambda r: (*_refinement_score(r),-r.pass_no))


def deterministic_refine(space: dict[str, Any], rows: list[OptimizationPass], optimize_params: Any = None) -> dict[str, dict[str, float | int]]:
    current=validate_search_space(space)
    best=best_near_miss(rows)
    if best is None:
        return current
    out={k:dict(v) for k,v in current.items()}
    bounds=_bounds_for_space(current)
    selected=set(normalize_optimize_params(optimize_params,allowed_names=bounds)) if optimize_params is not None else set(current)
    for name, spec in current.items():
        if name not in selected: continue
        lo, hi, floor_step, typ=bounds[name]
        center=float(best.params[name]); old_width=float(spec["stop"])-float(spec["start"])
        width=max(floor_step*4.0, old_width*0.50)
        start=max(lo, center-width/2.0); stop=min(hi, center+width/2.0)
        step=max(floor_step, float(spec["step"]))
        if typ=="int":
            start=int(round(start)); stop=int(round(stop)); step=max(1,int(round(step)))
            if stop < start: stop=start
        else:
            start=round(start,10); stop=round(stop,10); step=round(step,10)
        out[name]={"start":start,"step":step,"stop":stop}
    return validate_search_space(out)


def _extract_json_object(text: str) -> dict:
    text=str(text or "").strip()
    text=re.sub(r"^```(?:json)?\s*", "", text, flags=re.I); text=re.sub(r"\s*```$", "", text)
    try:
        obj=json.loads(text)
        if isinstance(obj,dict): return obj
    except Exception: pass
    a=text.find("{"); b=text.rfind("}")
    if a>=0 and b>a:
        obj=json.loads(text[a:b+1])
        if isinstance(obj,dict): return obj
    raise ValueError("Scientist optimizer proposal is not a JSON object")


def sanitize_scientist_llm_config(raw: dict | None) -> dict:
    """Freeze non-secret Scientist routing state into an Optimizer request.

    Credentials remain in DPAPI/environment storage and are never serialized into
    Strategy Optimizer request/evidence JSON. ``api_key_env`` is configuration, not a
    secret value, so it remains legal.
    """
    blocked={"api_key","secret","token","password","credential","access_token","refresh_token"}
    def clean(value):
        if isinstance(value,dict):
            return {str(k):clean(v) for k,v in value.items() if str(k).lower() not in blocked}
        if isinstance(value,list):
            return [clean(v) for v in value]
        return value
    return clean(dict(raw or {}))


def scientist_propose_ranges(space: dict[str, Any], rows: list[OptimizationPass], llm_cfg: dict, *, round_no: int, kpi_profile: dict | None = None, minimum_trades: int = 1, optimize_params: Any = None, api_key: str | None = None) -> tuple[dict, dict]:
    """Perform exactly one Scientist proposal call and return the untrusted proposal.

    Deterministic validation is intentionally separate so accepted/rejected proposal
    evidence can be persisted without conflating provider success with authority.
    """
    from scientist.core.scientist import LLMScientist
    sci=LLMScientist(llm_cfg,api_key=api_key)
    if not sci.ready:
        raise RuntimeError("Scientist route is not configured")
    current=validate_search_space(space)
    bounds=_bounds_for_space(current)
    selected=normalize_optimize_params(optimize_params,allowed_names=bounds) if optimize_params is not None else list(current)
    top=sorted(rows,key=lambda r:(*_refinement_score(r),-r.pass_no),reverse=True)[:12]
    evidence=[{
        "pass":r.pass_no,"pf":r.profit_factor,"rf":r.recovery_factor,"expectancy_r":r.expectancy_r,"weighted_r":r.weighted_r,
        "params":r.params,
    } for r in top]
    system=(
        "You are a read-only search-space adviser for an MT5 strategy optimizer. Return JSON only. "
        "You may change only start/step/stop for the exact parameter keys supplied. Never change KPI gates, strategy count, "
        "EA logic, date range, symbol, validation workflow, or add/remove parameters. Seven strategy family weights must remain >0. "
        "The deterministic compiler will reject anything outside hard_bounds."
    )
    kpi=dict(kpi_profile or optimizer_kpi_policy())
    user={
        "round":round_no,"hard_gates":{"profit_factor_gte":float(kpi.get("min_profit_factor",OPTIMIZER_PF_MIN)),"recovery_factor_gte":float(kpi.get("min_recovery_factor",OPTIMIZER_RF_MIN)),"expectancy_r_gte":float(kpi.get("min_expectancy_r",OPTIMIZER_EXPECTANCY_R_MIN)),"weighted_r_gte":float(kpi.get("min_weighted_r",OPTIMIZER_WEIGHTED_R_MIN)),"minimum_closed_trades":int(minimum_trades)},
        "current_space":{k:current[k] for k in selected},
        "search_space_context":{**search_space_cardinality(space,selected),"frozen_inputs":[k for k in current if k not in selected],"native_scheduler":"MT5_FAST_GENETIC_OWNS_POPULATION_JOB_TASK_DISTRIBUTION; RAW_GRID_IS_NOT_TASK_COUNT"},
        "hard_bounds":{k:{"min":bounds[k][0],"max":bounds[k][1],"min_step":bounds[k][2],"type":bounds[k][3]} for k in selected},
        "top_mt5_passes":evidence,
        "request":"Return {\"ranges\":{parameter:{\"start\":x,\"step\":y,\"stop\":z},...},\"reason\":\"short evidence-based reason\"}.",
    }
    text=sci._call_with_phase([
        {"role":"system","content":system},{"role":"user","content":json.dumps(user,separators=(",",":"),default=str)}
    ],temperature=0.10,phase="STRATEGY_OPTIMIZER_RANGE_PROPOSAL")
    obj=_extract_json_object(text)
    return obj, {
        "reason":str(obj.get("reason") or "Scientist returned a proposal without a narrative reason."),
        "llm_provenance":sci.last_call_provenance,
        "optimized_params":selected,
    }


def validate_scientist_ranges(space: dict[str, Any], proposal: dict, optimize_params: Any = None) -> dict[str, dict[str, float | int]]:
    """Deterministically compile an untrusted Scientist range proposal."""
    current=validate_search_space(space)
    selected=normalize_optimize_params(optimize_params) if optimize_params is not None else list(current)
    ranges=proposal.get("ranges") if isinstance(proposal,dict) else None
    if not isinstance(ranges,dict) or set(ranges)!=set(selected):
        raise ValueError("Scientist optimizer proposal must contain exactly the Owner-selected optimization parameters")
    merged={k:dict(v) for k,v in current.items()}; merged.update(ranges)
    return validate_search_space(merged)


def scientist_refine(space: dict[str, Any], rows: list[OptimizationPass], llm_cfg: dict, *, round_no: int, kpi_profile: dict | None = None, minimum_trades: int = 1, optimize_params: Any = None, api_key: str | None = None) -> tuple[dict[str, dict[str, float | int]], dict]:
    """Compatibility wrapper: one LLM call followed by deterministic validation."""
    proposal,meta=scientist_propose_ranges(space,rows,llm_cfg,round_no=round_no,kpi_profile=kpi_profile,minimum_trades=minimum_trades,optimize_params=optimize_params,api_key=api_key)
    validated=validate_scientist_ranges(space,proposal,optimize_params)
    meta={**meta,"proposal":proposal,"validation":{"status":"ACCEPTED"}}
    return validated,meta


def champion_payload(ch: OptimizationPass) -> dict:
    return {
        "schema":"MAX_STRATEGY_OPTIMIZER_CHAMPION_V2",
        "selected_utc":utc_now(),
        "hard_gates":{
            "profit_factor_gte":float(ch.min_profit_factor_required),
            "recovery_factor_gte":float(ch.min_recovery_factor_required),
            "expectancy_r_gte":float(ch.min_expectancy_r_required),
            "weighted_r_gte":float(ch.min_weighted_r_required),
            "minimum_closed_trades":int(ch.minimum_trades_required),
        },
        "round":ch.round_no,"pass":ch.pass_no,
        "profit_factor":ch.profit_factor,"recovery_factor":ch.recovery_factor,"expectancy_r":ch.expectancy_r,"weighted_r":ch.weighted_r,
        "profit":ch.profit,"trades":ch.trades,"params":ch.params,
        "authority":"MT5_NATIVE_OPTIMIZATION_RESULT_PLUS_DETERMINISTIC_SELECTOR",
        "validation_status":"OPTIMIZER_CHAMPION_ONLY_OWNER_MANUAL_BACKTEST_THEN_RESEARCH",
    }


def validate_request(req: dict) -> dict:
    out=dict(req or {})
    symbol=str(out.get("symbol") or "").strip(); confirm=str(out.get("confirm_symbol") or "").strip()
    if not symbol or not confirm: raise ValueError("Main Symbol dan Relative reference symbol wajib diisi")
    if symbol.lower()==confirm.lower(): raise ValueError("Relative reference symbol harus berbeda dari Main Symbol")
    out["symbol"]=symbol; out["confirm_symbol"]=confirm
    out["mtf_strategy_enabled"]=bool(out.get("mtf_strategy_enabled",False))
    out["period"]=str(out.get("period") or ("M15" if out["mtf_strategy_enabled"] else "H1")).upper()
    if out["period"] not in {"M1","M2","M3","M4","M5","M6","M10","M12","M15","M20","M30","H1","H2","H3","H4","H6","H8","H12","D1","W1","MN1"}: raise ValueError("unsupported timeframe")
    if out["mtf_strategy_enabled"] and out["period"]!="M15": raise ValueError("MTF-4 Strategy Optimizer requires M15 primary period")
    out["from_date"]=str(out.get("from_date") or "2021.01.01")
    out["to_date"]=str(out.get("to_date") or "2024.12.31")
    for x in (out["from_date"],out["to_date"]):
        if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}",x): raise ValueError("dates must use YYYY.MM.DD")
    out["deposit"]=float(out.get("deposit") or 10000.0); out["leverage"]=int(out.get("leverage") or 100)
    out["model"]=int(out.get("model",0))
    if out["model"] not in {0,1,2,4}: raise ValueError("unsupported MT5 tick model")
    out["optimization"]=int(out.get("optimization",2))
    if out["optimization"] not in {1,2}: raise ValueError("optimization must be complete(1) or genetic(2)")
    out["max_rounds"]=max(1,min(5,int(out.get("max_rounds") or 3)))
    out["scientist_assist"]=bool(out.get("scientist_assist",False))
    out["scientist_llm"]=sanitize_scientist_llm_config(out.get("scientist_llm") if isinstance(out.get("scientist_llm"),dict) else {})
    expected_bounds=optimizer_bounds(out["mtf_strategy_enabled"])
    default_space=optimizer_default_space(out["mtf_strategy_enabled"])
    out["search_space"]=validate_search_space(out.get("search_space") or default_space)
    if set(out["search_space"])!=set(expected_bounds):
        raise ValueError("search-space profile does not match mtf_strategy_enabled")
    out["optimize_params"]=normalize_optimize_params(out.get("optimize_params"),allowed_names=expected_bounds)
    current_defaults=read_ea_optimizer_defaults(mtf_strategy_enabled=out["mtf_strategy_enabled"])
    supplied_fixed=out.get("fixed_param_values") if isinstance(out.get("fixed_param_values"),dict) else {}
    out["fixed_param_values"]={name:(supplied_fixed.get(name,current_defaults[name])) for name in expected_bounds}
    out["search_space_cardinality"]=search_space_cardinality(out["search_space"],out["optimize_params"])
    inst=out.get("installation") or {}
    for k in ("terminal","metaeditor","data_dir"):
        if not str(inst.get(k) or "").strip(): raise ValueError(f"MT5 installation missing {k}")
    out["installation"]={k:str(inst[k]) for k in ("terminal","metaeditor","data_dir")}
    # Strategy Optimizer is coupled to the canonical Max MTF v2.0 baseline EA parameter contract.
    # Freeze source identity into the request so runtime evidence can prove the exact
    # package EA that was deployed unchanged into MT5.
    out["ea_source"]=canonical_ea_identity()
    kpi=optimizer_kpi_policy({"strategy_optimizer":{"kpi":dict(out.get("optimizer_kpi") or {})}})
    if int(kpi["base_h1_trades_per_month"]) < 1:
        raise ValueError("Optimizer H1 minimum trades/month must be >= 1")
    out["optimizer_kpi"]=kpi
    out["mt5_optimization_criterion"]={
        "code":MT5_OPTIMIZATION_CRITERION_CUSTOM_MAX,
        "name":"CUSTOM_MAX",
        "fitness":"MEAN_EXPECTANCY_R",
        "result_column":"MEAN_EXPECTANCY_R",
        "weighted_r_authority":"MAX_OPTIMIZATION_FRAME_SIDECAR",
        "recovery_factor_authority":"DEDICATED_RECOVERY_FACTOR_COLUMN",
    }
    out["optimizer_trade_sample"]=optimizer_trade_sample(out["period"],out["from_date"],out["to_date"],kpi_profile=kpi)
    return out

