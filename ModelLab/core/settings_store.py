from __future__ import annotations

import copy
import ctypes
import json
import os
import shutil
import tempfile
import time
from datetime import date, datetime
from ctypes import wintypes
from pathlib import Path

SCHEMA = "CPMF_USER_SETTINGS_V1"

# Persistent UI state uses an allowlist, not a blacklist.
# This is deliberate: Streamlit action widgets (especially buttons) must never be
# restored through st.session_state. New widget keys are therefore transient by
# default unless explicitly classified as safe operator navigation/selection state.
_PERSISTENT_UI_EXACT = {
    "nav_page_v071",
    "left_nav_open",
    "guided_run_select",
    "factory_selected",
    "factory_source",
    "factory_path",
    "scientist_chat_open",
    "scientist_chat_width",
    "scientist_chat_context_scope",
    "scientist_chat_model",
    "scientist_chat_fallback",
    # Strategy Optimizer form authority. These are durable operator settings only;
    # lifecycle/action widget keys remain transient and are intentionally excluded.
    "strategy_opt_mt5_installation",
    "strategy_opt_terminal",
    "strategy_opt_metaeditor",
    "strategy_opt_data_dir",
    "strategy_opt_symbol",
    "strategy_opt_confirm_symbol",
    "strategy_opt_period",
    "strategy_opt_from",
    "strategy_opt_to",
    "strategy_opt_tick_model",
    "strategy_opt_kpi_pf",
    "strategy_opt_kpi_rf",
    "strategy_opt_kpi_exp",
    "strategy_opt_kpi_weighted_r",
    "strategy_opt_kpi_h1_trades",
    "strategy_opt_params",
    "strategy_opt_rounds",
    "strategy_opt_scientist",
    "strategy_opt_method",
}
_PERSISTENT_UI_SUFFIXES = (
    "_research_date_range",
)
_SENSITIVE_UI_TOKENS = (
    "api_key", "apikey", "secret", "password", "token", "credential",
)

def is_persistable_ui_key(key: object) -> bool:
    k = str(key)
    lk = k.lower()
    if any(tok in lk for tok in _SENSITIVE_UI_TOKENS):
        return False
    if k in _PERSISTENT_UI_EXACT:
        return True
    return any(k.endswith(suffix) for suffix in _PERSISTENT_UI_SUFFIXES)

def sanitize_ui_state(ui_state: dict | None) -> dict:
    return {str(k): v for k, v in (ui_state or {}).items() if is_persistable_ui_key(k)}


def merge_persisted_ui_state(previous: dict | None, live: dict | None) -> dict:
    """Overlay currently visible widget state without deleting hidden-page settings.

    Streamlit removes widget keys when their page is not rendered. Missing live keys are
    therefore not deletion requests; they retain the last durable value. An explicit
    empty/False/zero live value still overwrites the previous value normally.
    """
    out=copy.deepcopy(sanitize_ui_state(previous))
    for k,v in sanitize_ui_state(live).items():
        out[str(k)]=copy.deepcopy(v)
    return out

def _sanitize_payload_ui_state(payload: dict | None) -> tuple[dict | None, bool]:
    if not isinstance(payload, dict):
        return payload, False
    raw = payload.get("ui_state")
    if not isinstance(raw, dict):
        raw = {}
    clean = sanitize_ui_state(raw)
    changed = clean != raw
    if changed:
        payload = copy.deepcopy(payload)
        payload["ui_state"] = clean
    return payload, changed


def _deep_merge(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for k, v in overlay.items():
            out[k] = _deep_merge(out.get(k), v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(overlay)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    if not data:
        return _DATA_BLOB(0, None), None
    buf = ctypes.create_string_buffer(data)
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI hanya tersedia di Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    inp, keep = _blob(data)
    out = _DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not crypt32.CryptProtectData(ctypes.byref(inp), "CPMF LLM API key", None, None, None, 0x1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI hanya tersedia di Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    inp, keep = _blob(data)
    out = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _atomic_write(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        last=None
        for attempt in range(24):
            try:
                os.replace(tmp_name, path)
                return
            except PermissionError as exc:
                last=exc
            except OSError as exc:
                if getattr(exc,"winerror",None) not in (5,32):
                    raise
                last=exc
            time.sleep(min(0.025*(attempt+1),0.30))
        if last is not None:
            raise last
        raise RuntimeError(f"atomic replace failed: {path}")
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def _encode_ui(v):
    if v is None or isinstance(v,(str,int,float,bool)):
        return v
    if isinstance(v,datetime): return {"__type__":"datetime","value":v.isoformat()}
    if isinstance(v,date): return {"__type__":"date","value":v.isoformat()}
    if isinstance(v,tuple): return {"__type__":"tuple","items":[_encode_ui(x) for x in v]}
    if isinstance(v,list): return [_encode_ui(x) for x in v]
    if isinstance(v,dict): return {str(k):_encode_ui(x) for k,x in v.items()}
    raise TypeError(type(v).__name__)

def _decode_ui(v):
    if isinstance(v,list): return [_decode_ui(x) for x in v]
    if isinstance(v,dict):
        typ=v.get("__type__")
        if typ=="date": return date.fromisoformat(v["value"])
        if typ=="datetime": return datetime.fromisoformat(v["value"])
        if typ=="tuple": return tuple(_decode_ui(x) for x in v.get("items",[]))
        return {k:_decode_ui(x) for k,x in v.items()}
    return v


class UserSettingsStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.settings_path = self.root / "settings.json"
        self.backup_path = self.root / "settings.backup.json"
        self.secret_path = self.root / "llm_api_key.dpapi"

    def load(self, base_cfg: dict) -> tuple[dict, str, dict, dict]:
        cfg = copy.deepcopy(base_cfg)
        meta = {"source": "base", "recovered_from_backup": False, "secret_loaded": False}
        payload = None
        for candidate, is_backup in ((self.settings_path, False), (self.backup_path, True)):
            if not candidate.exists():
                continue
            try:
                obj = json.loads(candidate.read_text(encoding="utf-8"))
                if obj.get("schema") != SCHEMA or not isinstance(obj.get("config"), dict):
                    raise ValueError("unsupported settings schema")
                payload = obj
                meta["source"] = str(candidate)
                meta["recovered_from_backup"] = is_backup
                break
            except Exception:
                continue
        payload, payload_scrubbed = _sanitize_payload_ui_state(payload)
        ui_state = _decode_ui(payload.get("ui_state", {})) if payload else {}
        ui_state = sanitize_ui_state(ui_state)
        if payload:
            cfg = _deep_merge(cfg, payload["config"])
            # Self-heal legacy settings on disk. This removes stale button values and
            # any accidentally persisted secret-like UI fields from previous releases.
            if payload_scrubbed and meta.get("source") == str(self.settings_path):
                try:
                    _atomic_write(self.settings_path, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
                    meta["ui_state_scrubbed"] = True
                except Exception:
                    meta["ui_state_scrubbed"] = False
        secret = ""
        if self.secret_path.exists() and os.name == "nt":
            try:
                secret = _dpapi_unprotect(self.secret_path.read_bytes()).decode("utf-8")
                meta["secret_loaded"] = bool(secret)
            except Exception:
                secret = ""
        return cfg, secret, meta, ui_state

    def save(self, cfg: dict, api_key: str = "", ui_state: dict | None = None) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                shutil.copy2(self.settings_path, self.backup_path)
            except Exception:
                pass
        clean_ui={}
        for k,v in sanitize_ui_state(ui_state).items():
            try: clean_ui[str(k)] = _encode_ui(v)
            except Exception: pass
        obj = {"schema": SCHEMA, "config": copy.deepcopy(cfg), "ui_state": clean_ui}
        # Secrets are never written to JSON.
        llm = obj["config"].setdefault("agent", {}).setdefault("llm", {})
        for key in ("api_key", "secret", "token"):
            llm.pop(key, None)
        _atomic_write(self.settings_path, json.dumps(obj, indent=2, sort_keys=True).encode("utf-8"))
        secret_status = "UNCHANGED"
        if api_key:
            if os.name == "nt":
                _atomic_write(self.secret_path, _dpapi_protect(api_key.encode("utf-8")))
                secret_status = "DPAPI_SAVED"
            else:
                secret_status = "NOT_SAVED_NON_WINDOWS"
        return {"settings": str(self.settings_path), "backup": str(self.backup_path), "secret": secret_status}

    def clear_secret(self):
        try:
            self.secret_path.unlink(missing_ok=True)
        except TypeError:
            if self.secret_path.exists():
                self.secret_path.unlink()
