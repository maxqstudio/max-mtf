from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from mtf.mtf_data import build_alignment_index, build_canonical_views
from mtf.mtf2 import (
    ABLATION_ROLES,
    CONTRACT_ID,
    FEATURE_PRIMITIVES,
    ROLE_FEATURES,
    MTF2Error,
    build_directional_labels,
    build_mtf2_dataset,
    build_role_feature_matrix,
    feature_schema_payload,
    feature_schema_sha256,
)
from mtf_test_utils import synthetic_native_frames


def req(value, message):
    if not value:
        raise AssertionError(message)


# Governance contract and executable source must remain identical.
contracts = json.loads((PKG / ".workflow" / "contracts.json").read_text(encoding="utf-8"))
governed = next(row for row in contracts["data_contracts"] if row.get("contract_id") == CONTRACT_ID)
expected_schema = {
    "contract_id": governed["contract_id"],
    "schema_version": governed["schema_version"],
    "primitive_registry": governed["primitive_registry"],
    "role_features": governed["role_features"],
}
req(feature_schema_payload() == expected_schema, "source/governance feature schema drift")
req(len(feature_schema_sha256()) == 64, "feature schema hash")

frames = synthetic_native_frames(periods=3600)
views, parity = build_canonical_views(frames, price_atol=1e-9)
req(parity["status"] == "PASS", "MTF-1 canonical parity")
alignment, alignment_meta = build_alignment_index(views)
req(alignment_meta["status"] == "PASS", "MTF-1 alignment")

geometry = {
    "geometry_id": "SELFTEST-MTF2-GEOM",
    "sl_atr": 3.2,
    "tp_atr": 4.8,
    "horizon_minutes": 60,
    "min_edge_r": 0.20,
    "min_margin_r": 0.10,
}
dataset = build_mtf2_dataset(views, alignment, geometry)
req(dataset["status"] == "PASS", "dataset status")
req(dataset["meta"]["causality"]["status"] == "PASS", "feature causality")
req(dataset["meta"]["ablations"]["common_rows"] > 0, "common ablation rows")
req(dataset["meta"]["ablations"]["feature_counts"] == {"A": 14, "B": 23, "C": 29, "D": 37}, "compact feature counts")
redundancy = dataset["meta"]["feature"]["redundancy_audit"]
req(redundancy["status"] == "PASS", "redundancy audit status")
req(redundancy["exact_duplicate_pairs"] == [], "exact duplicate features are forbidden")
req("m5__hour_sin" not in dataset["meta"]["feature"]["all_feature_columns"], "V2 removes duplicate M5 hour_sin")
req("m5__hour_cos" not in dataset["meta"]["feature"]["all_feature_columns"], "V2 removes duplicate M5 hour_cos")
req(redundancy["automatic_drop_authority"] is False, "correlation audit cannot auto-drop features")
req("h1__signed_body_atr" not in dataset["meta"]["feature"]["all_feature_columns"], "V3 removes H1 body/ret1 duplicate")
req("m15__signed_body_atr" not in dataset["meta"]["feature"]["all_feature_columns"], "V3 removes M15 body/ret1 duplicate")
req("m5__signed_body_atr" not in dataset["meta"]["feature"]["all_feature_columns"], "V3 removes M5 body/ret1 duplicate")

ids = None
for name in ("A", "B", "C", "D"):
    frame = dataset["ablations"][name]
    current = frame["decision_id"].tolist()
    ids = current if ids is None else ids
    req(current == ids, name + " must use identical decision IDs")
    decision = pd.to_datetime(frame["decision_time_utc"], utc=True)
    dep = pd.to_datetime(frame["dependency_start_time_utc"], utc=True)
    label_end = pd.to_datetime(frame["label_end_time_utc"], utc=True)
    req(bool((dep <= decision).all()), name + " dependency must be causal")
    req(bool((label_end > decision).all()), name + " labels must be future outcomes")

# A future M5 mutation beginning exactly at decision time may affect labels, never features at t.
feature_matrix, _ = build_role_feature_matrix(views, alignment)
ready = feature_matrix.loc[feature_matrix["feature_ready_d"]].reset_index(drop=True)
req(len(ready) > 0, "feature-ready row")
probe = ready.iloc[len(ready) // 2]
probe_time = pd.Timestamp(probe["decision_time_utc"])
all_feature_cols = [f"{ROLE_FEATURES[role]['timeframe'].lower()}__{name}" for role in ABLATION_ROLES["D"] for name in ROLE_FEATURES[role]["features"]]

mutated = {key: value.copy() for key, value in views.items()}
future_mask = pd.to_datetime(mutated["M5"]["open_time_utc"], utc=True) >= probe_time
mutated["M5"].loc[future_mask, "high"] = mutated["M5"].loc[future_mask, "high"] + 5000.0
mutated["M5"].loc[future_mask, "low"] = np.maximum(0.01, mutated["M5"].loc[future_mask, "low"] - 1000.0)
mut_feature_matrix, _ = build_role_feature_matrix(mutated, alignment)
orig_row = feature_matrix.loc[feature_matrix["decision_id"] == probe["decision_id"], all_feature_cols].iloc[0].to_numpy(float)
mut_row = mut_feature_matrix.loc[mut_feature_matrix["decision_id"] == probe["decision_id"], all_feature_cols].iloc[0].to_numpy(float)
req(np.allclose(orig_row, mut_row, rtol=0.0, atol=0.0, equal_nan=True), "future M5 changed directional features")

# The same future mutation is consumed by the label path and must fail closed on ambiguity.
mut_labels, _ = build_directional_labels(mutated, feature_matrix, geometry)
mut_probe = mut_labels.loc[mut_labels["decision_id"] == probe["decision_id"]].iloc[0]
req(mut_probe["label_reason"] == "AMBIGUOUS_BARRIER" and not bool(mut_probe["label_valid"]), "future M5 label ambiguity must drop")

# Legacy bar count without typed timeframe/minutes can never silently become the MTF horizon.
failed = False
try:
    build_directional_labels(
        views,
        feature_matrix,
        {
            "geometry_id": "UNTYPED-LEGACY",
            "sl_atr": 3.2,
            "tp_atr": 4.8,
            "max_hold_bars": 54,
            "min_edge_r": 0.20,
            "min_margin_r": 0.10,
        },
    )
except MTF2Error as exc:
    failed = "untyped max_hold_bars" in str(exc)
req(failed, "untyped max_hold_bars must fail closed")

# End-of-data labels with incomplete wall-clock horizon remain invalid.
long_geometry = dict(geometry)
long_geometry["geometry_id"] = "SELFTEST-INCOMPLETE"
long_geometry["horizon_minutes"] = 24 * 60
labels, _ = build_directional_labels(views, feature_matrix.tail(1), long_geometry)
req(len(labels) == 1 and labels.iloc[0]["label_reason"] == "INCOMPLETE_HORIZON", "incomplete horizon must be invalid")

print("V202_MTF2_FEATURE_LABEL_CONTRACT PASS")
