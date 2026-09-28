from __future__ import annotations
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class MT5DataRoot:
    data_root: str
    terminal_id: str
    mql5_dir: str
    experts_dir: str
    models_dir: str
    tester_profiles_dir: str
    verified: bool
    authority: str = "VERIFIED_MT5_TERMINAL_DATA_ROOT"


def _candidate_base() -> Path | None:
    appdata=os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata)/"MetaQuotes"/"Terminal"


def validate_mt5_data_root(path: str | Path, *, create_subdirs: bool=False) -> MT5DataRoot:
    p=Path(path).expanduser()
    # Deployment is never allowed to a drive root such as C:\ or /.
    if p.parent == p or (p.drive and str(p).rstrip("\\/").upper()==p.drive.upper()):
        raise ValueError("Raw drive/filesystem root is not a valid MT5 terminal data root")
    if p.name in {"", ".", ".."}:
        raise ValueError("Invalid MT5 terminal data root")
    mql5=p/"MQL5"
    if not mql5.is_dir():
        raise ValueError(f"MT5 data root must already contain MQL5: {p}")
    experts=mql5/"Experts"/"MaxMTF"
    models=mql5/"Files"/"models"/"MaxMTF"
    tester=mql5/"Profiles"/"Tester"
    if create_subdirs:
        experts.mkdir(parents=True,exist_ok=True); models.mkdir(parents=True,exist_ok=True); tester.mkdir(parents=True,exist_ok=True)
    terminal_id=p.name
    return MT5DataRoot(str(p),terminal_id,str(mql5),str(experts),str(models),str(tester),True)


def discover_mt5_data_roots() -> list[MT5DataRoot]:
    base=_candidate_base()
    if base is None or not base.is_dir():
        return []
    out=[]
    for p in sorted(base.iterdir()):
        if not p.is_dir() or p.name.lower() in {"common","community"}:
            continue
        try:
            out.append(validate_mt5_data_root(p))
        except Exception:
            continue
    return out
