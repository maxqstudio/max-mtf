from __future__ import annotations

from typing import Any, Mapping
import pandas as pd

from mtf.mtf_data import (
    NATIVE_FRAME_ORDER,
    ROLE_TO_TIMEFRAME,
    MTFDataError,
    audit_alignment,
    audit_native_frame,
)

SCHEMA = "MAX_MTF_DATA_QUALITY_V1"


def audit_canonical_bundle(views: Mapping[str, pd.DataFrame], alignment: pd.DataFrame, parity: Mapping[str, Any]) -> dict[str, Any]:
    missing = [tf for tf in NATIVE_FRAME_ORDER if tf not in views]
    if missing:
        return {"schema": SCHEMA, "status": "FAIL", "reason": "MISSING_FRAME", "missing": missing}
    frames = {tf: audit_native_frame(views[tf], tf).as_dict() for tf in NATIVE_FRAME_ORDER}
    alignment_audit = audit_alignment(alignment)
    parity_status = str(parity.get("status") or "").upper()
    ok = all(x["status"] == "PASS" for x in frames.values()) and alignment_audit.get("status") == "PASS" and parity_status == "PASS"
    return {
        "schema": SCHEMA,
        "status": "PASS" if ok else "FAIL",
        "roles": dict(ROLE_TO_TIMEFRAME),
        "frames": frames,
        "alignment": alignment_audit,
        "resampling_parity_status": parity_status,
        "no_forward_fill": True,
        "closed_bar_only": True,
    }
