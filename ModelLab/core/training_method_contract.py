from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = MODELLAB_ROOT
CONTRACT_PATH = ROOT / "governance" / "MODEL_TRAINING_METHOD_CONTRACT_V1.json"
SCHEMA = "MODEL_TRAINING_METHOD_CONTRACT_V1"
AUTHORITY = "SINGLE_CANONICAL_TRAINING_METHOD_AUTHORITY"


def load_training_method_contract() -> dict[str, Any]:
    try:
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"MODEL_TRAINING_METHOD_CONTRACT_UNREADABLE: {exc}") from exc
    if payload.get("schema") != SCHEMA:
        raise RuntimeError(f"MODEL_TRAINING_METHOD_CONTRACT_SCHEMA: {payload.get('schema')!r}")
    if payload.get("authority") != AUTHORITY:
        raise RuntimeError(f"MODEL_TRAINING_METHOD_CONTRACT_AUTHORITY: {payload.get('authority')!r}")
    required = {
        "candidate_admission", "label_horizon_authority", "temporal_early_stop",
        "moe_routing", "moe_balance", "moe_diagnostics", "hybrid_stacking", "tree_models",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"MODEL_TRAINING_METHOD_CONTRACT_MISSING: {missing}")
    return payload


def training_method_contract_hash() -> str:
    return hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()


def training_method_context() -> dict[str, Any]:
    payload = load_training_method_contract()
    return {
        "schema": payload["schema"],
        "authority": payload["authority"],
        "contract_sha256": training_method_contract_hash(),
        "candidate_admission": deepcopy(payload["candidate_admission"]),
        "label_horizon_authority": deepcopy(payload["label_horizon_authority"]),
        "temporal_early_stop": deepcopy(payload["temporal_early_stop"]),
        "moe_routing": deepcopy(payload["moe_routing"]),
        "moe_balance": deepcopy(payload["moe_balance"]),
        "moe_diagnostics": deepcopy(payload["moe_diagnostics"]),
        "hybrid_stacking": deepcopy(payload["hybrid_stacking"]),
        "tree_models": deepcopy(payload["tree_models"]),
    }
