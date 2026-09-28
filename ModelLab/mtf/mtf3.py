from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


CONTRACT_ID = "MAX_MTF3_TIME_DEPENDENCY_PURGE_V1"
SCHEMA = "MAX_MTF3_TIME_PURGE_V1"

_REQUIRED_COLUMNS = (
    "decision_id",
    "dependency_start_time_utc",
    "decision_time_utc",
    "label_end_time_utc",
)


class MTF3Error(ValueError):
    pass


def _utc_series(frame: pd.DataFrame, column: str, *, allow_null: bool = False) -> pd.Series:
    values = frame[column]
    if not allow_null and bool(values.isna().any()):
        raise MTF3Error(f"{column} contains null timestamps")
    for value in values.dropna():
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            raise MTF3Error(f"{column} contains timezone-naive timestamp")
    parsed = pd.to_datetime(values, utc=True, errors="raise")
    return parsed


def _ids_sha256(values: Iterable[str]) -> str:
    payload = "\n".join(str(value) for value in values) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_fingerprint(
    *,
    kind: str,
    ordinal: int,
    train_ids: Iterable[str],
    protected_ids: Iterable[str],
    purged_ids: Iterable[str],
    extra: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "contract_id": CONTRACT_ID,
        "kind": str(kind),
        "ordinal": int(ordinal),
        "train_decision_ids": [str(value) for value in train_ids],
        "protected_decision_ids": [str(value) for value in protected_ids],
        "purged_decision_ids": [str(value) for value in purged_ids],
        "extra": dict(extra or {}),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_comparison_intervals(
    comparison_rows: pd.DataFrame,
    *,
    execution_label_active: bool = False,
) -> pd.DataFrame:
    missing = [column for column in _REQUIRED_COLUMNS if column not in comparison_rows.columns]
    if missing:
        raise MTF3Error("MTF3 interval columns missing: " + ", ".join(missing))
    if comparison_rows.empty:
        raise MTF3Error("MTF3 comparison rows are empty")

    out = comparison_rows.copy().reset_index(drop=True)
    out["decision_id"] = out["decision_id"].astype(str)
    if bool(out["decision_id"].eq("").any()) or bool(out["decision_id"].duplicated().any()):
        raise MTF3Error("MTF3 decision_id must be non-empty and unique")

    dependency = _utc_series(out, "dependency_start_time_utc")
    decision = _utc_series(out, "decision_time_utc")
    label_end = _utc_series(out, "label_end_time_utc")
    if "label_start_time_utc" in out.columns:
        label_start = _utc_series(out, "label_start_time_utc")
        if not bool((label_start == decision).all()):
            raise MTF3Error("MTF3 label_start_time_utc must equal decision_time_utc")

    if not bool(decision.is_monotonic_increasing) or bool(decision.duplicated().any()):
        raise MTF3Error("MTF3 decision_time_utc must be strictly increasing")
    if bool((dependency > decision).any()):
        raise MTF3Error("MTF3 dependency_start_time_utc is after decision_time_utc")
    if bool((label_end <= decision).any()):
        raise MTF3Error("MTF3 label_end_time_utc must be after decision_time_utc")

    if "execution_end_time_utc" in out.columns:
        execution = _utc_series(out, "execution_end_time_utc", allow_null=True)
        missing_execution = execution.isna()
        if execution_label_active and bool(missing_execution.any()):
            raise MTF3Error("MTF3 active execution layer requires explicit execution_end_time_utc")
        execution = execution.where(~missing_execution, label_end)
    else:
        if execution_label_active:
            raise MTF3Error("MTF3 active execution layer requires execution_end_time_utc")
        execution = label_end.copy()

    if bool((execution < decision).any()):
        raise MTF3Error("MTF3 execution_end_time_utc is before decision_time_utc")

    sample_end = pd.concat([label_end, execution], axis=1).max(axis=1)
    if bool((sample_end <= decision).any()):
        raise MTF3Error("MTF3 sample outcome end must be after decision_time_utc")

    out["dependency_start_time_utc"] = dependency
    out["decision_time_utc"] = decision
    out["label_end_time_utc"] = label_end
    out["execution_end_time_utc"] = execution
    out["sample_end_time_utc"] = sample_end
    out["mtf3_row_index"] = np.arange(len(out), dtype=np.int64)
    return out


def _protected_arrays(
    intervals: pd.DataFrame,
    protected_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    protected = intervals.iloc[protected_idx]
    starts = protected["decision_time_utc"].astype("int64").to_numpy(dtype=np.int64)
    ends = protected["sample_end_time_utc"].astype("int64").to_numpy(dtype=np.int64)
    ids = protected["decision_id"].astype(str).to_numpy()
    rows = protected["mtf3_row_index"].to_numpy(dtype=np.int64)
    order = np.argsort(starts, kind="stable")
    return starts[order], ends[order], ids[order], rows[order]


def _overlap_witness(
    train_start_ns: int,
    train_end_ns: int,
    protected_starts: np.ndarray,
    protected_ends: np.ndarray,
) -> int | None:
    if len(protected_starts) == 0:
        return None
    right = int(np.searchsorted(protected_starts, train_end_ns, side="right") - 1)
    if right < 0:
        return None
    eligible_ends = protected_ends[: right + 1]
    candidates = np.flatnonzero(eligible_ends >= train_start_ns)
    return int(candidates[0]) if len(candidates) else None


def audit_time_purge_split(
    intervals: pd.DataFrame,
    train_idx: Iterable[int],
    protected_idx: Iterable[int],
) -> dict[str, Any]:
    train = np.asarray(list(train_idx) if not isinstance(train_idx, np.ndarray) else train_idx, dtype=np.int64)
    protected = np.asarray(
        list(protected_idx) if not isinstance(protected_idx, np.ndarray) else protected_idx,
        dtype=np.int64,
    )
    if len(np.unique(train)) != len(train) or len(np.unique(protected)) != len(protected):
        raise MTF3Error("MTF3 split indices must be unique")
    if np.intersect1d(train, protected).size:
        raise MTF3Error("MTF3 train/protected decision sets intersect")
    if len(train) and (int(train.min()) < 0 or int(train.max()) >= len(intervals)):
        raise MTF3Error("MTF3 train index out of range")
    if len(protected) and (int(protected.min()) < 0 or int(protected.max()) >= len(intervals)):
        raise MTF3Error("MTF3 protected index out of range")

    protected_starts, protected_ends, protected_ids, protected_rows = _protected_arrays(intervals, protected)
    violations: list[dict[str, Any]] = []
    for row_index in train:
        row = intervals.iloc[int(row_index)]
        start_ns = int(pd.Timestamp(row["dependency_start_time_utc"]).value)
        end_ns = int(pd.Timestamp(row["sample_end_time_utc"]).value)
        witness = _overlap_witness(start_ns, end_ns, protected_starts, protected_ends)
        if witness is None:
            continue
        overlap_start_ns = max(start_ns, int(protected_starts[witness]))
        overlap_end_ns = min(end_ns, int(protected_ends[witness]))
        violations.append(
            {
                "train_decision_id": str(row["decision_id"]),
                "train_row_index": int(row_index),
                "protected_decision_id": str(protected_ids[witness]),
                "protected_row_index": int(protected_rows[witness]),
                "train_interval_start_utc": pd.Timestamp(start_ns, tz="UTC").isoformat(),
                "train_interval_end_utc": pd.Timestamp(end_ns, tz="UTC").isoformat(),
                "protected_interval_start_utc": pd.Timestamp(int(protected_starts[witness]), tz="UTC").isoformat(),
                "protected_interval_end_utc": pd.Timestamp(int(protected_ends[witness]), tz="UTC").isoformat(),
                "overlap_start_utc": pd.Timestamp(overlap_start_ns, tz="UTC").isoformat(),
                "overlap_end_utc": pd.Timestamp(overlap_end_ns, tz="UTC").isoformat(),
            }
        )

    return {
        "schema": "MAX_MTF3_SPLIT_OVERLAP_AUDIT_V1",
        "status": "PASS" if not violations else "FAIL",
        "train_rows": int(len(train)),
        "protected_rows": int(len(protected)),
        "violation_count": int(len(violations)),
        "violations": violations,
        "boundary_semantics": "FAIL_SAFE_CLOSED_TOUCH_COUNTS_AS_OVERLAP",
    }


def purge_train_against_protected(
    intervals: pd.DataFrame,
    candidate_train_idx: Iterable[int],
    protected_idx: Iterable[int],
) -> tuple[np.ndarray, dict[str, Any]]:
    candidate = np.asarray(
        list(candidate_train_idx) if not isinstance(candidate_train_idx, np.ndarray) else candidate_train_idx,
        dtype=np.int64,
    )
    protected = np.asarray(
        list(protected_idx) if not isinstance(protected_idx, np.ndarray) else protected_idx,
        dtype=np.int64,
    )
    candidate = np.unique(candidate)
    protected = np.unique(protected)
    if np.intersect1d(candidate, protected).size:
        raise MTF3Error("MTF3 candidate train includes protected decision rows")
    if len(candidate) and (int(candidate.min()) < 0 or int(candidate.max()) >= len(intervals)):
        raise MTF3Error("MTF3 candidate train index out of range")
    if len(protected) and (int(protected.min()) < 0 or int(protected.max()) >= len(intervals)):
        raise MTF3Error("MTF3 protected index out of range")

    protected_starts, protected_ends, protected_ids, protected_rows = _protected_arrays(intervals, protected)
    kept: list[int] = []
    purged_rows: list[dict[str, Any]] = []

    for row_index in candidate:
        row = intervals.iloc[int(row_index)]
        train_start = pd.Timestamp(row["dependency_start_time_utc"])
        train_decision = pd.Timestamp(row["decision_time_utc"])
        train_end = pd.Timestamp(row["sample_end_time_utc"])
        start_ns = int(train_start.value)
        end_ns = int(train_end.value)
        witness = _overlap_witness(start_ns, end_ns, protected_starts, protected_ends)
        if witness is None:
            kept.append(int(row_index))
            continue

        protected_start = pd.Timestamp(int(protected_starts[witness]), tz="UTC")
        protected_end = pd.Timestamp(int(protected_ends[witness]), tz="UTC")
        overlap_start = max(train_start, protected_start)
        overlap_end = min(train_end, protected_end)
        if train_decision < protected_start:
            reason = "PRE_BOUNDARY_OUTCOME_REACHES_PROTECTED"
        else:
            reason = "POST_BOUNDARY_DEPENDENCY_REACHES_PROTECTED"
        if overlap_start == overlap_end:
            reason += "_TOUCH"

        purged_rows.append(
            {
                "train_decision_id": str(row["decision_id"]),
                "train_row_index": int(row_index),
                "reason": reason,
                "train_interval_start_utc": train_start.isoformat(),
                "train_interval_end_utc": train_end.isoformat(),
                "protected_decision_id": str(protected_ids[witness]),
                "protected_row_index": int(protected_rows[witness]),
                "protected_interval_start_utc": protected_start.isoformat(),
                "protected_interval_end_utc": protected_end.isoformat(),
                "overlap_start_utc": overlap_start.isoformat(),
                "overlap_end_utc": overlap_end.isoformat(),
            }
        )

    kept_idx = np.asarray(kept, dtype=np.int64)
    audit = audit_time_purge_split(intervals, kept_idx, protected)
    if audit["status"] != "PASS":
        raise RuntimeError("MTF3 post-purge overlap audit failed")

    evidence = {
        "schema": "MAX_MTF3_EXACT_TIME_PURGE_EVIDENCE_V1",
        "status": "PASS",
        "candidate_train_rows": int(len(candidate)),
        "kept_train_rows": int(len(kept_idx)),
        "purged_train_rows": int(len(purged_rows)),
        "protected_rows": int(len(protected)),
        "kept_decision_ids": intervals.iloc[kept_idx]["decision_id"].astype(str).tolist(),
        "protected_decision_ids": intervals.iloc[protected]["decision_id"].astype(str).tolist(),
        "purged": purged_rows,
        "post_purge_audit": audit,
        "boundary_semantics": "FAIL_SAFE_CLOSED_TOUCH_COUNTS_AS_OVERLAP",
        "bar_count_fallback": False,
    }
    return kept_idx, evidence


def mtf3_expanding_folds(
    intervals: pd.DataFrame,
    *,
    folds: int = 3,
    first_train_fraction: float = 0.50,
) -> list[dict[str, Any]]:
    n = int(len(intervals))
    folds = max(1, int(folds))
    if not (0.0 < float(first_train_fraction) < 1.0):
        raise MTF3Error("MTF3 first_train_fraction must be between 0 and 1")
    first_train = max(1, int(n * float(first_train_fraction)))
    remaining = n - first_train
    if remaining < folds:
        raise MTF3Error("MTF3 insufficient rows for expanding folds")
    span = max(1, remaining // folds)
    out: list[dict[str, Any]] = []

    for fold_no in range(1, folds + 1):
        train_end = first_train + (fold_no - 1) * span
        validation_start = train_end
        validation_end = n if fold_no == folds else min(n, validation_start + span)
        if validation_start >= validation_end:
            raise MTF3Error("MTF3 empty validation fold")
        candidate = np.arange(0, train_end, dtype=np.int64)
        protected = np.arange(validation_start, validation_end, dtype=np.int64)
        kept, evidence = purge_train_against_protected(intervals, candidate, protected)
        if len(kept) == 0:
            raise MTF3Error(f"MTF3 WFA fold {fold_no} has no legal train rows after exact purge")
        train_ids = intervals.iloc[kept]["decision_id"].astype(str).tolist()
        protected_ids = intervals.iloc[protected]["decision_id"].astype(str).tolist()
        purged_ids = [row["train_decision_id"] for row in evidence["purged"]]
        fingerprint = _split_fingerprint(
            kind="WFA",
            ordinal=fold_no,
            train_ids=train_ids,
            protected_ids=protected_ids,
            purged_ids=purged_ids,
            extra={"folds": folds},
        )
        out.append(
            {
                "schema": "MAX_MTF3_WFA_SPLIT_V1",
                "status": "PASS",
                "fold": fold_no,
                "train_idx": kept,
                "protected_idx": protected,
                "candidate_train_count": int(len(candidate)),
                "kept_train_count": int(len(kept)),
                "protected_count": int(len(protected)),
                "purge_evidence": evidence,
                "split_fingerprint": fingerprint,
                "protected_decision_start_utc": pd.Timestamp(
                    intervals.iloc[int(protected[0])]["decision_time_utc"]
                ).isoformat(),
                "protected_decision_end_utc": pd.Timestamp(
                    intervals.iloc[int(protected[-1])]["decision_time_utc"]
                ).isoformat(),
            }
        )
    return out


def mtf3_cpcv_splits(
    intervals: pd.DataFrame,
    *,
    n_groups: int = 6,
    test_groups: int = 2,
) -> list[dict[str, Any]]:
    n = int(len(intervals))
    n_groups = int(n_groups)
    test_groups = int(test_groups)
    if n_groups != 6 or test_groups != 2:
        raise MTF3Error("MTF3 CPCV methodology requires exactly N=6,k=2")
    if n < n_groups:
        raise MTF3Error("MTF3 insufficient rows for CPCV groups")

    groups = [np.asarray(part, dtype=np.int64) for part in np.array_split(np.arange(n, dtype=np.int64), n_groups)]
    if any(len(group) == 0 for group in groups):
        raise MTF3Error("MTF3 CPCV contains empty group")

    all_idx = np.arange(n, dtype=np.int64)
    out: list[dict[str, Any]] = []
    combos = list(combinations(range(n_groups), test_groups))
    if len(combos) != 15:
        raise RuntimeError("MTF3 CPCV expected exactly 15 combinations")

    for split_no, combo in enumerate(combos, 1):
        protected = np.unique(np.concatenate([groups[group] for group in combo]))
        candidate = np.setdiff1d(all_idx, protected, assume_unique=True)
        kept, evidence = purge_train_against_protected(intervals, candidate, protected)
        train_ids = intervals.iloc[kept]["decision_id"].astype(str).tolist()
        protected_ids = intervals.iloc[protected]["decision_id"].astype(str).tolist()
        purged_ids = [row["train_decision_id"] for row in evidence["purged"]]
        fingerprint = _split_fingerprint(
            kind="CPCV",
            ordinal=split_no,
            train_ids=train_ids,
            protected_ids=protected_ids,
            purged_ids=purged_ids,
            extra={"combo": list(combo), "n_groups": n_groups, "test_groups": test_groups},
        )
        out.append(
            {
                "schema": "MAX_MTF3_CPCV_SPLIT_V1",
                "status": "PASS",
                "split": split_no,
                "test_groups": list(combo),
                "train_idx": kept,
                "protected_idx": protected,
                "candidate_train_count": int(len(candidate)),
                "kept_train_count": int(len(kept)),
                "protected_count": int(len(protected)),
                "purge_evidence": evidence,
                "split_fingerprint": fingerprint,
            }
        )

    if len(out) != 15:
        raise RuntimeError("MTF3 CPCV did not emit all 15 deterministic splits")
    return out


def build_mtf3_split_authority(
    comparison_rows: pd.DataFrame,
    *,
    execution_label_active: bool = False,
    wfa_folds: int = 3,
) -> dict[str, Any]:
    intervals = build_comparison_intervals(
        comparison_rows,
        execution_label_active=execution_label_active,
    )
    wfa = mtf3_expanding_folds(intervals, folds=wfa_folds)
    cpcv = mtf3_cpcv_splits(intervals, n_groups=6, test_groups=2)

    decision_ids = intervals["decision_id"].astype(str).tolist()
    authority_payload = {
        "contract_id": CONTRACT_ID,
        "decision_ids_sha256": _ids_sha256(decision_ids),
        "wfa_fingerprints": [split["split_fingerprint"] for split in wfa],
        "cpcv_fingerprints": [split["split_fingerprint"] for split in cpcv],
    }
    authority_fingerprint = hashlib.sha256(
        json.dumps(authority_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "comparison_rows": int(len(intervals)),
        "comparison_decision_ids_sha256": authority_payload["decision_ids_sha256"],
        "intervals": intervals,
        "wfa": wfa,
        "cpcv": cpcv,
        "authority_fingerprint": authority_fingerprint,
        "cpcv_combinations": int(len(cpcv)),
        "bar_count_fallback": False,
        "model_training_started": False,
    }
