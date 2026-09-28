from __future__ import annotations

"""Single authority for chronological research indices.

This module contains no estimator logic.  It only defines which rows are legal for
training/validation and how discontinuous index sets are represented.  WFA, CPCV,
policy discovery and temporal stacking are expected to consume these helpers rather
than rebuilding chronology rules independently.
"""

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from strategy.strategy_geometry import resolved_strategy_horizon_bars


SCHEMA = "CP_TEMPORAL_INDEX_CONTRACT_V2"


@dataclass(frozen=True)
class TemporalIndexContract:
    purge_bars: int
    embargo_bars: int
    label_horizon_bars: int
    schema: str = SCHEMA


@dataclass(frozen=True)
class InternalEarlyStopSplit:
    """Chronological supervised train/early-stop validation split with target purge.

    Positions index the caller's already-filtered supervised rows.  Original row ids
    remain authoritative so discontinuous CPCV complements cannot be compressed into
    fake adjacency.  Feature/context rows are not removed here; only supervised target
    eligibility is purged.
    """
    train_positions: np.ndarray
    validation_positions: np.ndarray
    evidence: dict


def purged_internal_earlystop_split(
    supervised_row_ids: Iterable[int],
    *,
    validation_rows: int,
    purge_bars: int,
    label_horizon_bars: int,
    min_train_rows: int,
    min_validation_rows: int = 1,
) -> InternalEarlyStopSplit:
    """Build the internal checkpoint-selection split without label overlap.

    The validation boundary is chosen chronologically on supervised decision rows.
    Training targets within ``effective_purge`` bars before that boundary are excluded,
    but their historical feature rows remain available to causal validation sequences.
    """
    rows=np.asarray(list(supervised_row_ids) if not isinstance(supervised_row_ids,np.ndarray) else supervised_row_ids,dtype=int).reshape(-1)
    if len(rows)<2:
        raise ValueError('DL_INTERNAL_EARLYSTOP_PURGE_INSUFFICIENT: fewer than two supervised rows')
    if np.any(np.diff(rows)<=0):
        raise ValueError('DL_INTERNAL_EARLYSTOP_ROW_IDS_NOT_STRICTLY_INCREASING')
    horizon=max(0,int(label_horizon_bars)); requested=max(0,int(purge_bars)); effective=max(horizon,requested)
    if horizon<=0 or effective<=0:
        raise ValueError('DL_INTERNAL_EARLYSTOP_HORIZON_AUTHORITY_MISSING')
    val_n=max(int(min_validation_rows),int(validation_rows)); val_n=min(val_n,max(1,len(rows)-1))
    cut=len(rows)-val_n
    if cut<=0:
        raise ValueError('DL_INTERNAL_EARLYSTOP_PURGE_INSUFFICIENT: no pre-validation rows')
    first_val=int(rows[cut])
    pre=np.arange(cut,dtype=int)
    # Integer-bar contract: keep t only when t < first_val - purge.  Therefore for
    # purge==horizon, t+horizon <= first_val-1 and the target cannot touch validation.
    keep=rows[:cut] < (first_val-effective)
    tr=pre[keep]; va=np.arange(cut,len(rows),dtype=int)
    if len(tr)<int(min_train_rows) or len(va)<int(min_validation_rows):
        raise ValueError(
            f'DL_INTERNAL_EARLYSTOP_PURGE_INSUFFICIENT: train={len(tr)}, val={len(va)}, '
            f'purge={effective}, horizon={horizon}, rows={len(rows)}'
        )
    last_train=int(rows[tr[-1]]); latest_target_end=last_train+horizon
    overlap_ok=bool(latest_target_end < first_val)
    if not overlap_ok:
        raise RuntimeError(
            f'DL_INTERNAL_EARLYSTOP_OVERLAP: last_train={last_train}, horizon={horizon}, first_val={first_val}'
        )
    evidence={
        'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1',
        'effective_horizon_bars':horizon,
        'requested_purge_bars':requested,
        'applied_purge_bars':effective,
        'internal_train_last_supervised_row':last_train,
        'internal_train_latest_target_end_row':latest_target_end,
        'first_internal_validation_row':first_val,
        'decision_gap_bars':int(first_val-last_train),
        'purged_supervised_rows':int(cut-len(tr)),
        'train_supervised_rows':int(len(tr)),
        'validation_supervised_rows':int(len(va)),
        'authorized_row_gaps':int(np.sum(np.diff(rows)>1)),
        'validation_context_preserved':True,
        'overlap_check':'PASS',
    }
    return InternalEarlyStopSplit(tr,va,evidence)


def contract_from_cfg(cfg: dict) -> TemporalIndexContract:
    split = cfg.get("split") or {}
    horizon = max(0, int(resolved_strategy_horizon_bars(cfg)))
    purge = max(horizon, int(split.get("purge_bars", horizon) or 0))
    embargo = max(horizon, int(split.get("embargo_bars", purge) or 0))
    return TemporalIndexContract(purge_bars=purge, embargo_bars=embargo, label_horizon_bars=horizon)


def sorted_unique_indices(indices: Iterable[int]) -> np.ndarray:
    x = np.asarray(list(indices) if not isinstance(indices, np.ndarray) else indices, dtype=int).reshape(-1)
    if len(x) == 0:
        return np.empty(0, dtype=int)
    return np.unique(x)


def contiguous_chunks(indices: Iterable[int]) -> list[np.ndarray]:
    """Split original row ids into truly contiguous chronological chunks."""
    idx = sorted_unique_indices(indices)
    if len(idx) == 0:
        return []
    cuts = np.where(np.diff(idx) > 1)[0] + 1
    return [part for part in np.split(idx, cuts) if len(part)]


def expanding_folds(n: int, folds: int, purge_bars: int, min_train_rows: int = 200,
                    min_validation_rows: int = 50) -> list[tuple[np.ndarray, np.ndarray]]:
    """Canonical expanding WFA split.

    The purge is applied on both sides of the train/validation boundary: the last
    training targets are removed and validation starts after the same boundary gap.
    """
    n = int(n); folds = max(1, int(folds)); purge = max(0, int(purge_bars))
    first_train = int(n * 0.50)
    val_span = max(1, int((n - first_train) / folds))
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(folds):
        train_end = first_train + i * val_span
        val_start = train_end + purge
        val_end = n if i == folds - 1 else min(n, val_start + val_span)
        tr_end_purged = max(0, train_end - purge)
        if tr_end_purged < int(min_train_rows) or val_end - val_start < int(min_validation_rows):
            continue
        out.append((np.arange(0, tr_end_purged, dtype=int), np.arange(val_start, val_end, dtype=int)))
    if not out:
        raise ValueError("Could not construct legal walk-forward folds; need more rows.")
    return out


def apply_training_memory(df: pd.DataFrame, train_idx: Iterable[int], spec, cfg: dict) -> tuple[np.ndarray, dict]:
    """Apply candidate memory only to TRAIN rows; evaluation rows never shrink."""
    tr = sorted_unique_indices(train_idx)
    requested = int((getattr(spec, "params", {}) or {}).get("training_memory_months", 0) or 0)
    if requested <= 0 or len(tr) == 0:
        return tr, {
            "schema": SCHEMA, "requested_months": requested, "applied": False,
            "fallback": "FULL_FOLD_TRAIN", "rows": int(len(tr)),
            "validation_window_preserved": True,
        }
    ts = pd.to_datetime(df.iloc[tr]["signal_time"], errors="coerce")
    end = ts.max(); start = end - pd.DateOffset(months=requested)
    sub = tr[np.asarray(ts >= start)]
    min_rows = max(200, min(1000, int((cfg.get("split") or {}).get("min_train_rows", 1000))))
    if len(sub) < min_rows:
        return tr, {
            "schema": SCHEMA, "requested_months": requested, "applied": False,
            "fallback": "TOO_FEW_FOLD_TRAIN_ROWS", "rows": int(len(tr)),
            "candidate_rows": int(len(sub)), "start": str(start), "end": str(end),
            "validation_window_preserved": True,
        }
    return sub, {
        "schema": SCHEMA, "requested_months": requested, "applied": True,
        "fallback": None, "rows": int(len(sub)),
        "start": str(pd.to_datetime(df.iloc[sub]["signal_time"], errors="coerce").min()),
        "end": str(pd.to_datetime(df.iloc[sub]["signal_time"], errors="coerce").max()),
        "validation_window_preserved": True,
    }


def purge_train_before_validation(train_idx: Iterable[int], validation_idx: Iterable[int], purge_bars: int) -> np.ndarray:
    """Remove train targets whose label horizon can touch any validation chunk.

    Only original row identities are used; discontinuous train sets remain discontinuous.
    """
    tr = sorted_unique_indices(train_idx)
    va = sorted_unique_indices(validation_idx)
    purge = max(0, int(purge_bars))
    if purge == 0 or len(tr) == 0 or len(va) == 0:
        return tr
    keep = np.ones(len(tr), dtype=bool)
    for chunk in contiguous_chunks(va):
        lo = int(chunk[0]) - purge
        hi = int(chunk[0])
        keep &= ~((tr >= lo) & (tr < hi))
    return tr[keep]


def inner_oof_folds(authorized_idx: Iterable[int], folds: int, purge_bars: int,
                    min_train_rows: int = 100, min_validation_rows: int = 20) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding OOF splits over an arbitrary authorized chronology.

    Indices retain original row ids. Validation slices may contain multiple contiguous
    chunks when the outer authority is discontinuous (for example CPCV complement).
    Temporal estimators must therefore build sequences from original ids, never from a
    compressed X[train_idx] array.
    """
    idx = sorted_unique_indices(authorized_idx)
    n = len(idx)
    if n < 2 * int(min_validation_rows):
        return []
    folds = 2 if n < 240 else max(2, min(3, int(folds)))
    first = max(120, int(n * 0.45))
    first = min(first, max(1, n - int(min_validation_rows)))
    remaining = n - first
    span = max(int(min_validation_rows), remaining // folds)
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(folds):
        tr_end_pos = first + i * span
        va_start_pos = tr_end_pos
        va_end_pos = n if i == folds - 1 else min(n, va_start_pos + span)
        if va_start_pos >= n:
            continue
        tr = idx[:tr_end_pos]
        va = idx[va_start_pos:va_end_pos]
        tr = purge_train_before_validation(tr, va, purge_bars)
        if len(tr) < int(min_train_rows) or len(va) < int(min_validation_rows):
            continue
        out.append((tr, va))
    return out


def describe_indices(indices: Iterable[int]) -> dict:
    idx = sorted_unique_indices(indices)
    chunks = contiguous_chunks(idx)
    return {
        "rows": int(len(idx)),
        "chunks": int(len(chunks)),
        "first_index": int(idx[0]) if len(idx) else None,
        "last_index": int(idx[-1]) if len(idx) else None,
        "contiguous": bool(len(chunks) <= 1),
    }
