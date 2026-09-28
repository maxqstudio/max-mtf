from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from typing import Any

_LOCK = threading.Lock()
SCHEMA = "CP_LLM_MODEL_HEALTH_V1"


def _default_path() -> Path:
    return MODELLAB_ROOT / "runtime" / "llm_model_health.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"schema": SCHEMA, "models": {}}


def _write(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _key(provider: str, model: str, endpoint: str | None = None, api_key_env: str | None = None) -> str:
    # Route identity, not merely model identity.  Two accounts/endpoints using the same
    # provider/model must not poison each other's cooldown state.  We persist only the
    # environment variable *name*, never the secret value.
    ep=str(endpoint or "").strip().rstrip("/").lower()
    env=str(api_key_env or "").strip()
    return f"{str(provider).strip().lower()}|{str(model).strip()}|{ep}|{env}"


@contextmanager
def _cross_process_lock(path: Path):
    lock_path=Path(str(path)+".lock")
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    with open(lock_path,"a+b") as f:
        f.seek(0,2)
        if f.tell()==0:
            f.write(b"\0"); f.flush()
        f.seek(0)
        try:
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
            except Exception:
                pass


def _parse_iso(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def model_health(provider: str, model: str, path: str | Path | None = None, *, endpoint: str | None = None, api_key_env: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _default_path()
    with _LOCK, _cross_process_lock(p):
        obj = _read(p)
        row = dict((obj.get("models") or {}).get(_key(provider, model, endpoint, api_key_env)) or {})
    until = _parse_iso(row.get("cooldown_until_utc"))
    active = bool(until and until > datetime.now(timezone.utc))
    row["cooldown_active"] = active
    if until:
        row["cooldown_until_utc"] = until.isoformat()
    return row


def record_success(provider: str, model: str, path: str | Path | None = None, *, endpoint: str | None = None, api_key_env: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _default_path()
    now = datetime.now(timezone.utc)
    with _LOCK, _cross_process_lock(p):
        obj = _read(p); models = obj.setdefault("models", {})
        route_key=_key(provider, model, endpoint, api_key_env)
        row = dict(models.get(route_key) or {})
        row.update({
            "provider": provider, "model": model, "status": "READY",
            "last_success_utc": now.isoformat(), "cooldown_until_utc": None,
            "last_error_category": None, "last_error": None,
        })
        row["endpoint"]=str(endpoint or ""); row["api_key_env"]=str(api_key_env or "")
        models[route_key] = row; obj["updated_utc"] = now.isoformat(); _write(p, obj)
    return row


def record_failure(provider: str, model: str, category: str, error: str, *, path: str | Path | None = None,
                   transient_cooldown_sec: int = 300, endpoint: str | None = None, api_key_env: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _default_path()
    now = datetime.now(timezone.utc); text = str(error or "").lower(); category = str(category or "ERROR")
    if category in {"QUOTA_OR_RATE_LIMIT", "QUOTA_EXHAUSTED", "RATE_LIMIT"}:
        daily = any(x in text for x in ("perday", "per day", "requestsperday", "rpd", "daily", "generate_requests_per_day"))
        if daily:
            tomorrow = (now + timedelta(days=1)).date()
            until = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc) + timedelta(minutes=5)
            status = "DAILY_QUOTA_EXHAUSTED"
        else:
            until = now + timedelta(seconds=max(60, int(transient_cooldown_sec)))
            status = "RATE_LIMITED"
    elif category in {"MODEL_UNAVAILABLE", "PROVIDER_5XX", "TIMEOUT", "PROVIDER_UNREACHABLE"}:
        until = now + timedelta(seconds=max(60, int(transient_cooldown_sec)))
        status = category
    else:
        until = None; status = category
    with _LOCK, _cross_process_lock(p):
        obj = _read(p); models = obj.setdefault("models", {})
        route_key=_key(provider, model, endpoint, api_key_env)
        row = dict(models.get(route_key) or {})
        row.update({
            "provider": provider, "model": model, "status": status,
            "last_failure_utc": now.isoformat(), "last_error_category": category,
            "last_error": str(error)[:1000], "cooldown_until_utc": until.isoformat() if until else None,
        })
        row["failure_count"] = int(row.get("failure_count", 0) or 0) + 1
        row["endpoint"]=str(endpoint or ""); row["api_key_env"]=str(api_key_env or "")
        models[route_key] = row; obj["updated_utc"] = now.isoformat(); _write(p, obj)
    return row


def health_snapshot(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _default_path()
    with _LOCK, _cross_process_lock(p):
        obj = _read(p)
    out = {"schema": SCHEMA, "updated_utc": obj.get("updated_utc"), "models": {}}
    for k, row in (obj.get("models") or {}).items():
        r = dict(row or {}); until = _parse_iso(r.get("cooldown_until_utc"))
        r["cooldown_active"] = bool(until and until > datetime.now(timezone.utc))
        out["models"][k] = r
    return out
