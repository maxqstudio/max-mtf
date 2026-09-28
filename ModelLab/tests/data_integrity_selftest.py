from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from core.contract import FEATURES, REQUIRED_COLUMNS, CONTRACT_ID
from data.dataset_integrity import (
    integrity_summary,
    repair_legacy_duplicates,
    build_research_window_snapshot,
    research_window_preview,
    fresh_readiness,
)
from models.model_lab import load_cfg, load_training_csv
import strategy.strategy_geometry as strategy_geometry
ROOT = Path(__file__).resolve().parents[1]
CFG = load_cfg(ROOT / "config/config.json")
EVIDENCE = ROOT / "evidence/history/DATA_INTEGRITY_ACCEPTANCE_v0_6_6.json"


def require(cond, name, checks):
    if not cond:
        raise AssertionError(name)
    checks.append(name)
    print("PASS ", name)


def make_df(n=96, start="2026-09-01 00:00", symbol="EURUSD.m", period=16385):
    ts = pd.date_range(start, periods=n, freq="h")
    base = 1.1000 + np.arange(n) * 0.00005
    d = {
        "contract": [CONTRACT_ID] * n,
        "signal_time": ts.strftime("%Y.%m.%d %H:%M"),
        "decision_bar_time": ts.strftime("%Y.%m.%d %H:%M"),
        "symbol": [symbol] * n,
        "period": [period] * n,
        "open": base,
        "high": base + 0.00010,
        "low": base - 0.00010,
        "close": base + 0.00002,
        "atr": [0.0010] * n,
        "decision_bid": base,
        "decision_ask": base + 0.00010,
        "spread_points": [10.0] * n,
        "sl_atr": [1.8] * n,
        "tp_atr": [2.7] * n,
        "max_hold_bars": [24] * n,
        "consensus": np.linspace(-0.2, 0.2, n),
    }
    for i, f in enumerate(FEATURES):
        d[f] = np.sin(np.arange(n) / (5.0 + (i % 7))) * 0.1
    return pd.DataFrame(d, columns=REQUIRED_COLUMNS)


def write_csv(df, path):
    df.to_csv(path, sep=";", index=False, lineterminator="\n")


def main():
    checks=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        # This legacy data-integrity fixture intentionally exercises its own 1.8/2.7/24
        # geometry. v1.2.6 requires runtime Strategy authority even for fresh-readiness,
        # so the fixture provides a matching isolated authority instead of relying on
        # the removed dataset-only fail-open behavior.
        strategy_geometry.RUNTIME_AUTHORITY=td/"strategy_authority.json"
        strategy_geometry.RUNTIME_AUTHORITY.write_text(json.dumps({
            "schema":"MAX_STRATEGY_EXECUTION_AUTHORITY_V1",
            "geometry":{"sl_atr":1.8,"tp_atr":2.7,"max_hold_bars":24},
            # v1.3.2 requires the complete promoted execution policy as part of
            # Strategy authority. This isolated fixture keeps its historical
            # geometry while providing a valid policy so the test continues to
            # exercise data-integrity/fresh-readiness rather than authority parsing.
            "execution_policy":{
                "entry_threshold":0.18,
                "exit_reverse_threshold":0.25,
                "min_consensus":0.70,
                "shock_halt_range_atr":3.5,
                "max_spread_points":35.0,
                "onnx_blend":0.70
            }
        }),encoding="utf-8")
        master=td/"Max_Training.csv"
        base=make_df(96)
        write_csv(base, master)
        info=integrity_summary(master)
        require(info["duplicate_extra_rows"]==0 and info["physical_rows"]==96, "clean master starts with 96 unique identity keys", checks)

        # Legacy duplicate: same identity key but different payload. Cleanup must preserve first row.
        dup=base.iloc[[10]].copy()
        dup["consensus"]=0.987654
        dirty=pd.concat([base,dup],ignore_index=True)
        write_csv(dirty,master)
        dirty_info=integrity_summary(master)
        require(dirty_info["duplicate_extra_rows"]==1, "legacy physical duplicate is detected", checks)
        try:
            load_training_csv(master)
            raise AssertionError("research accepted dirty CSV")
        except ValueError as e:
            require("duplicate identity rows" in str(e), "research fails closed instead of silently drop_duplicates", checks)
        rep=repair_legacy_duplicates(master)
        require(rep["status"]=="REPAIRED" and rep["removed"]==1 and Path(rep["backup"]).exists(), "legacy cleanup makes backup and removes exact duplicate", checks)
        clean=load_training_csv(master)
        preserved=float(clean.loc[clean["signal_time"]==pd.Timestamp("2026-09-01 10:00"),"consensus"].iloc[0])
        require(abs(preserved-float(base.iloc[10]["consensus"]))<1e-12, "legacy cleanup is first-write-wins", checks)

        # Live + backtest overlap semantics: existing live keys remain, tester fills only gaps.
        live=base.iloc[[0,1,3,4]].copy(); live["consensus"]=[0.11,0.12,0.13,0.14]
        tester=base.iloc[:6].copy(); tester["consensus"]=[0.91,0.92,0.93,0.94,0.95,0.96]
        key=["contract","symbol","period","signal_time"]
        merged=pd.concat([live,tester],ignore_index=True).drop_duplicates(key,keep="first").sort_values("signal_time")
        require(len(merged)==6 and not merged.duplicated(key).any(), "live + overlapping backtest yields exactly six unique keys", checks)
        overlap=merged[merged["signal_time"].isin(live["signal_time"])]
        require(set(np.round(overlap["consensus"],2))=={0.11,0.12,0.13,0.14}, "first-write-wins preserves existing live rows", checks)
        require(set(merged["signal_time"])-set(live["signal_time"])==set(tester.iloc[[2,5]]["signal_time"]), "backtest fills only missing H1 gaps", checks)

        # Research range 1-2 Sep is immutable and reserves 3-4 Sep for fresh validation.
        start=pd.Timestamp("2026-09-01").date(); end=pd.Timestamp("2026-09-02").date()
        preview=research_window_preview(master,start,end)
        require(preview["selected_rows"]==48 and preview["reserve_raw_rows"]==48, "research range separates 48 research rows from 48 later raw rows", checks)
        snap=td/"research_window.csv"
        lineage=build_research_window_snapshot(master,start,end,snap)
        # Regression v0.7.0 R2: persisted settings/manifests use ISO strings,
        # while pandas dt.date yields datetime.date. Both boundary functions must
        # normalize before comparisons.
        preview_str=research_window_preview(master,start.isoformat(),end.isoformat())
        require(preview_str["selected_rows"]==preview["selected_rows"],"persisted ISO-string dates are normalized in research preview",checks)
        snap_str=td/"source_window_from_strings.csv"
        lineage_str=build_research_window_snapshot(master,start.isoformat(),end.isoformat(),snap_str)
        require(lineage_str["snapshot_rows"]==lineage["snapshot_rows"],"persisted ISO-string dates are normalized in snapshot builder",checks)
        snap_df=load_training_csv(snap)
        require(len(snap_df)==48 and snap_df["signal_time"].max()==pd.Timestamp("2026-09-02 23:00"), "research snapshot excludes every row after selected cutoff", checks)
        require(lineage["snapshot_rows"]==48 and lineage["source_raw_end"].startswith("2026-09-02 23:00"), "research lineage records exact selected cutoff", checks)

        ready=fresh_readiness(master,lineage["source_raw_end"],CFG)
        require(ready["status"]=="READY" and ready["raw_new_rows"]==48 and ready["mature_raw_rows"]==24 and ready["labeled_fresh_rows"]==24, "fresh readiness becomes READY only from mature label-valid rows", checks)
        short=td/"short.csv"; write_csv(base.iloc[:60],short)
        waiting=fresh_readiness(short,lineage["source_raw_end"],CFG)
        require(waiting["status"]=="WAITING_LABEL_HORIZON" and waiting["raw_new_rows"]==12, "fresh readiness explains WAITING_LABEL_HORIZON instead of generic no-label error", checks)

    ea=(ROOT.parent/"EA_v1_06"/"Max.mq5").read_text(encoding="utf-8")
    writer=ea[ea.index("int OpenTrainingCsvExclusiveWriter()"):ea.index("void OpenTelemetry()")]
    require('#property version   "1.06"' in ea, "EA data writer version is 1.06", checks)
    require("AcquireTrainingWriterLock" in writer and "TrainingTimeExists(s.bar_time)" in writer, "EA writer serializes and checks existing timestamp before append", checks)
    open_line=next(line for line in writer.splitlines() if "return FileOpen(InpTrainingFile" in line)
    require("FILE_SHARE_WRITE" not in open_line and "FILE_SHARE_READ" in open_line, "training writer does not allow uncoordinated concurrent writers", checks)
    require("First-write-wins" in writer and "missing H1 gaps" in writer, "EA source explicitly documents live-preserving gap-fill invariant", checks)

    app=(ROOT/"ui/app.py").read_text(encoding="utf-8")
    require("Research date range" in app and "build_research_window_snapshot" in app, "Research UI exposes available-date range and creates authority snapshot", checks)
    require("authority_source_csv" in app and "source_window.csv authority" in app, "downstream research stages are pinned to immutable source window", checks)
    require("WAITING_LABEL_HORIZON" in app and "render_fresh_readiness" in app, "Fresh Validation UI reports label maturity state", checks)

    EVIDENCE.write_text(json.dumps({
        "version":"0.6.6",
        "schema":"DATA_INTEGRITY_ACCEPTANCE_V1",
        "overall_status":"PASS",
        "first_failed_gate":None,
        "checks":checks,
    },indent=2),encoding="utf-8")
    print("\nDATA INTEGRITY ACCEPTANCE PASS")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        EVIDENCE.write_text(json.dumps({
            "version":"0.6.6","schema":"DATA_INTEGRITY_ACCEPTANCE_V1",
            "overall_status":"FAIL","first_failed_gate":str(exc)
        },indent=2),encoding="utf-8")
        raise
