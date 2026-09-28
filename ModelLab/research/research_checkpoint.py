from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory.factory_jobs import atomic_write_json

SCHEMA = "CP_RESEARCH_CHECKPOINT_V1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _envelope(payload: dict, sequence: int) -> dict:
    body = deepcopy(payload)
    return {
        "schema": SCHEMA,
        "sequence": int(sequence),
        "committed_utc": _utcnow(),
        "payload_sha256": _hash_payload(body),
        "payload": body,
    }


def _valid(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("schema") == SCHEMA
        and isinstance(obj.get("payload"), dict)
        and str(obj.get("payload_sha256") or "") == _hash_payload(obj["payload"])
    )


def _read(path: Path) -> dict | None:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        return obj if _valid(obj) else None
    except Exception:
        return None


def load_checkpoint(path: str | Path) -> dict | None:
    """Load newest valid committed checkpoint, falling back to the previous commit."""
    p = Path(path)
    candidates = [x for x in (_read(p), _read(p.with_suffix(p.suffix + ".bak"))) if x]
    if not candidates:
        return None
    best = max(candidates, key=lambda x: int(x.get("sequence", 0) or 0))
    payload = deepcopy(best["payload"])
    payload["_checkpoint_sequence"] = int(best.get("sequence", 0) or 0)
    payload["_checkpoint_committed_utc"] = best.get("committed_utc")
    return payload


def commit_checkpoint(path: str | Path, payload: dict) -> dict:
    """Atomically commit payload and retain one previously valid checkpoint as backup."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    current = _read(p)
    prior = load_checkpoint(p)
    seq = int((prior or {}).get("_checkpoint_sequence", 0) or 0) + 1
    if current is not None:
        atomic_write_json(p.with_suffix(p.suffix + ".bak"), current)
    env = _envelope(payload, seq)
    atomic_write_json(p, env)
    return env


def clean_partial_temps(root: str | Path) -> list[str]:
    """Remove only uncommitted temp files left by our atomic writers under a Factory root."""
    root = Path(root)
    removed: list[str] = []
    if not root.exists():
        return removed
    for p in root.rglob("*.tmp"):
        try:
            p.unlink()
            removed.append(str(p))
        except OSError:
            pass
    return removed
