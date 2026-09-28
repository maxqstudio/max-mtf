from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from mtf.mtf_data import build_alignment_index, build_canonical_views
from mtf.mtf2 import build_mtf2_dataset
from mtf.mtf3 import (
    CONTRACT_ID,
    MTF3Error,
    audit_time_purge_split,
    build_comparison_intervals,
    build_mtf3_split_authority,
    mtf3_cpcv_splits,
    purge_train_against_protected,
)
from mtf_test_utils import synthetic_native_frames


def req(value, message):
    if not value:
        raise AssertionError(message)


contracts = json.loads((PKG / ".workflow" / "contracts.json").read_text(encoding="utf-8"))
contract = next(row for row in contracts["data_contracts"] if row.get("contract_id") == CONTRACT_ID)
req(contract["cpcv"]["n_groups"] == 6 and contract["cpcv"]["test_groups"] == 2, "governed CPCV 6x2")
req(contract["cpcv"]["combinations"] == 15, "governed CPCV 15 combinations")
req(contract["overlap_rule"]["bar_count_fallback"] is False, "bar-count fallback forbidden")

# Exact legacy single-TF files must not move during isolated MTF-3 source acceptance.
legacy_expected = {
    "core/temporal_index.py": "f4ad023eed88f8212fce3c31ff9dec23b8f89c2d",
    "research/cpcv.py": "9c587abdfa0f7b629a1c9c0e45214a9f2b345bc5",
}
# Git blob SHA-1 = sha1("blob <len>\0" + bytes), matching GitHub's immutable blob identity.
for rel, expected in legacy_expected.items():
    raw = (ROOT / rel).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    req(blob == expected, rel + " legacy blob identity changed")

# Build the MTF-2 D-common sample authority first; MTF-3 must consume exact decision IDs.
frames = synthetic_native_frames(periods=5200)
views, parity = build_canonical_views(frames, price_atol=1e-9)
req(parity["status"] == "PASS", "canonical M5-derived views")
alignment, alignment_meta = build_alignment_index(views)
req(alignment_meta["status"] == "PASS", "causal MTF alignment")
geometry = {
    "geometry_id": "SELFTEST-MTF3-GEOM",
    "sl_atr": 3.2,
    "tp_atr": 4.8,
    "horizon_minutes": 60,
    "min_edge_r": 0.20,
    "min_margin_r": 0.10,
}
mtf2 = build_mtf2_dataset(views, alignment, geometry)
d_common = mtf2["ablations"]["D"].copy()
req(len(d_common) > 360, "enough D-common rows for 6x2 CPCV")
authority = build_mtf3_split_authority(d_common, wfa_folds=3)
req(authority["status"] == "PASS", "MTF3 authority status")
req(authority["cpcv_combinations"] == 15 and len(authority["cpcv"]) == 15, "all 15 CPCV splits")
req(len(authority["wfa"]) == 3, "three expanding WFA folds")
req(authority["bar_count_fallback"] is False, "no bar-count fallback")
req(authority["model_training_started"] is False, "MTF3 source acceptance cannot train")

d_ids = d_common["decision_id"].astype(str).tolist()
for ablation_name in ("A", "B", "C"):
    req(
        mtf2["ablations"][ablation_name]["decision_id"].astype(str).tolist() == d_ids,
        ablation_name + " must reuse exact D-common decision IDs",
    )
req(
    authority["comparison_decision_ids_sha256"]
    == hashlib.sha256(("\n".join(d_ids) + "\n").encode("utf-8")).hexdigest(),
    "D-common decision identity",
)
for split in authority["wfa"] + authority["cpcv"]:
    req(split["purge_evidence"]["post_purge_audit"]["status"] == "PASS", "post-purge audit")
    req(split["purge_evidence"]["post_purge_audit"]["violation_count"] == 0, "zero kept overlap")
    req(len(split["split_fingerprint"]) == 64, "split fingerprint")

# Deterministic all-15 authority: rebuilding must produce identical split fingerprints.
repeat = mtf3_cpcv_splits(authority["intervals"], n_groups=6, test_groups=2)
req(
    [x["split_fingerprint"] for x in repeat]
    == [x["split_fingerprint"] for x in authority["cpcv"]],
    "CPCV fingerprints deterministic",
)

# Adversarial closed-boundary contract. Touch is deliberately illegal.
base_time = pd.Timestamp("2026-01-01T00:00:00Z")
rows = pd.DataFrame(
    [
        {
            "decision_id": "EARLY_TOUCH",
            "dependency_start_time_utc": base_time,
            "decision_time_utc": base_time + pd.Timedelta(hours=1),
            "label_start_time_utc": base_time + pd.Timedelta(hours=1),
            "label_end_time_utc": base_time + pd.Timedelta(hours=2),
        },
        {
            "decision_id": "LEGAL_GAP",
            "dependency_start_time_utc": base_time,
            "decision_time_utc": base_time + pd.Timedelta(hours=1, minutes=10),
            "label_start_time_utc": base_time + pd.Timedelta(hours=1, minutes=10),
            "label_end_time_utc": base_time + pd.Timedelta(hours=1, minutes=59, seconds=59),
        },
        {
            "decision_id": "PROTECTED",
            "dependency_start_time_utc": base_time + pd.Timedelta(minutes=30),
            "decision_time_utc": base_time + pd.Timedelta(hours=2),
            "label_start_time_utc": base_time + pd.Timedelta(hours=2),
            "label_end_time_utc": base_time + pd.Timedelta(hours=3),
        },
        {
            "decision_id": "LATE_LOOKBACK",
            "dependency_start_time_utc": base_time + pd.Timedelta(hours=2, minutes=30),
            "decision_time_utc": base_time + pd.Timedelta(hours=4),
            "label_start_time_utc": base_time + pd.Timedelta(hours=4),
            "label_end_time_utc": base_time + pd.Timedelta(hours=5),
        },
    ]
)
intervals = build_comparison_intervals(rows)
kept, evidence = purge_train_against_protected(intervals, np.array([0, 1, 3]), np.array([2]))
req(kept.tolist() == [1], "only exact-gap sample remains legal")
reasons = {item["train_decision_id"]: item["reason"] for item in evidence["purged"]}
req(reasons["EARLY_TOUCH"] == "PRE_BOUNDARY_OUTCOME_REACHES_PROTECTED_TOUCH", "pre-boundary touch purged")
req(reasons["LATE_LOOKBACK"] == "POST_BOUNDARY_DEPENDENCY_REACHES_PROTECTED", "post-boundary lookback purged")
req(evidence["post_purge_audit"]["status"] == "PASS", "adversarial post-purge audit")
req(audit_time_purge_split(intervals, np.array([0]), np.array([2]))["status"] == "FAIL", "unpurged touch detected")

# Malformed / ambiguous time authority must fail closed.
bad = rows.copy()
bad.loc[0, "dependency_start_time_utc"] = bad.loc[0, "decision_time_utc"] + pd.Timedelta(minutes=1)
failed = False
try:
    build_comparison_intervals(bad)
except MTF3Error:
    failed = True
req(failed, "dependency after decision must fail")

naive = rows.copy().astype(object)
naive["decision_time_utc"] = naive["decision_time_utc"].map(lambda value: pd.Timestamp(value).isoformat())
naive.loc[0, "decision_time_utc"] = "2026-01-01 01:00:00"
failed = False
try:
    build_comparison_intervals(naive)
except MTF3Error:
    failed = True
req(failed, "timezone-naive decision must fail")

active_execution = rows.copy()
failed = False
try:
    build_comparison_intervals(active_execution, execution_label_active=True)
except MTF3Error:
    failed = True
req(failed, "active execution layer requires explicit execution_end_time")

print("V203_MTF3_TIMESTAMP_OVERLAP_PURGE PASS")
