from __future__ import annotations
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from data.labels import build_labels
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from models.model_lab import load_cfg, load_training_csv, research_region, expanding_folds, feature_matrix, sha256_file, apply_fold_training_memory
from models.models import CandidateSpec, make_model, fit_model_indexed, predict_model_proba
from models.model_registry import is_hybrid_family
from host.preflight import period_label


def _write_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _label_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows":0,"supervised_rows":0,"context_only_rows":0,"supervised_ratio":0.0,"sell":0,"skip":0,"buy":0,"sell_ratio":0.0,"skip_ratio":0.0,"buy_ratio":0.0,"directional_ratio":0.0}
    if "supervised_weight" in df.columns:
        mask=pd.to_numeric(df["supervised_weight"],errors="coerce").fillna(0.0).to_numpy(float)>0
    else:
        mask=np.ones(len(df),dtype=bool)
    supervised=df.loc[mask]
    counts=supervised["label"].value_counts().to_dict() if not supervised.empty else {}
    n=max(1,len(supervised))
    return {
        "rows":int(len(df)),"supervised_rows":int(len(supervised)),"context_only_rows":int(len(df)-len(supervised)),
        "supervised_ratio":float(len(supervised)/max(1,len(df))),
        "sell":int(counts.get(0,0)),"skip":int(counts.get(1,0)),"buy":int(counts.get(2,0)),
        "sell_ratio":float(counts.get(0,0)/n),"skip_ratio":float(counts.get(1,0)/n),"buy_ratio":float(counts.get(2,0)/n),
        "directional_ratio":float((counts.get(0,0)+counts.get(2,0))/n),
    }


def _feature_drift(pre: pd.DataFrame) -> list[dict]:
    n=len(pre); cut=max(1,n//2); a=pre.iloc[:cut]; b=pre.iloc[cut:]
    rows=[]
    for f in FEATURES:
        av=a[f].to_numpy(float); bv=b[f].to_numpy(float)
        ma=float(np.mean(av)); mb=float(np.mean(bv)); sa=float(np.std(av)); sb=float(np.std(bv))
        pooled=max(1e-9, (sa+sb)/2.0)
        smd=abs(mb-ma)/pooled
        rows.append({"feature":f,"early_mean":ma,"late_mean":mb,"standardized_shift":float(smd)})
    return sorted(rows,key=lambda x:x["standardized_shift"],reverse=True)


def _redundancy(pre: pd.DataFrame) -> list[dict]:
    corr=pre[FEATURES].corr().abs()
    out=[]
    for i,a in enumerate(FEATURES):
        for j in range(i+1,len(FEATURES)):
            b=FEATURES[j]; c=float(corr.iloc[i,j])
            if np.isfinite(c) and c>=0.95:
                out.append({"feature_a":a,"feature_b":b,"abs_correlation":c})
    return sorted(out,key=lambda x:x["abs_correlation"],reverse=True)[:40]


def _importance_stability(pre: pd.DataFrame, spec: CandidateSpec, cfg: dict) -> list[dict]:
    """OOF feature-importance stability for both tree and temporal families.

    Tree estimators use native feature_importances_. Families without that attribute
    (notably GRU) use bounded permutation log-loss degradation on the validation tail.
    This keeps Feature/Label Audit useful without making a diagnostic stage unbounded.
    """
    from sklearn.metrics import log_loss

    folds=expanding_folds(pre,cfg); vals=[]
    X=feature_matrix(pre,cfg); y=pre["label"].to_numpy(np.int64)
    for fold_no,(tr,va) in enumerate(folds,1):
        fit_tr,_mem=apply_fold_training_memory(pre,tr,spec,cfg)
        model=make_model(spec,cfg); model=fit_model_indexed(model,spec.family,X,y,fit_tr,cfg,sample_weight=(pre["supervised_weight"].to_numpy(float) if "supervised_weight" in pre.columns else None))
        native=getattr(model,"feature_importances_",None)
        if is_hybrid_family(spec.family):
            native=None  # hybrid policy importance includes four temporal meta-features; audit original CP32 by permutation instead
        if native is not None:
            imp=np.asarray(native,float)
            if imp.shape[0] != len(FEATURES): imp=np.zeros(len(FEATURES),float)
        else:
            # Audit-only bounded permutation importance. Use a deterministic validation
            # tail so sequence models retain chronological order and runtime is capped.
            va=np.asarray(va,dtype=int)
            if "supervised_weight" in pre.columns:
                vw=pre["supervised_weight"].to_numpy(float); va=va[vw[va]>0]
            take=min(128,len(va)); idx=np.asarray(va[-take:],dtype=int)
            Xv=X[idx].copy(); yv=y[idx]
            if take<8 or len(np.unique(yv))<2:
                imp=np.zeros(len(FEATURES),float)
            else:
                base_p=np.asarray(predict_model_proba(model,spec.family,X[:int(idx[0])],Xv),float)
                base_p=np.clip(base_p,1e-9,1.0); base_p/=base_p.sum(axis=1,keepdims=True)
                base=float(log_loss(yv,base_p,labels=[0,1,2]))
                rng=np.random.default_rng(20260909+fold_no)
                imp=np.zeros(len(FEATURES),float)
                for j in range(len(FEATURES)):
                    Xp=Xv.copy(); perm=rng.permutation(take); Xp[:,j]=Xp[perm,j]
                    pp=np.asarray(predict_model_proba(model,spec.family,X[:int(idx[0])],Xp),float)
                    pp=np.clip(pp,1e-9,1.0); pp/=pp.sum(axis=1,keepdims=True)
                    imp[j]=max(0.0,float(log_loss(yv,pp,labels=[0,1,2]))-base)
        total=float(imp.sum())
        vals.append(imp/total if total>0 else imp)
    M=np.vstack(vals) if vals else np.zeros((1,len(FEATURES)))
    out=[]
    for i,f in enumerate(FEATURES):
        mean=float(np.mean(M[:,i])); std=float(np.std(M[:,i])); cv=float(std/max(mean,1e-9)) if mean>0 else 999.0
        out.append({"feature":f,"mean_importance":mean,"std_importance":std,"importance_cv":cv})
    return sorted(out,key=lambda x:x["mean_importance"],reverse=True)


def _variant(base: dict, field: str, value) -> dict:
    x=deepcopy(base); x[field]=value; return x


def _label_sensitivity(raw_pre: pd.DataFrame, cfg: dict) -> list[dict]:
    base=dict(cfg["label"]); cur={k:float(base[k]) for k in ("min_edge_r","min_margin_r")}
    candidates=[]
    # v0.8.5: SL/TP/hold are deployment geometry, not model-label search knobs.
    # Only classification separation thresholds may vary inside Model Research.
    for fld,delta,lo in [("min_edge_r",0.05,0.0),("min_margin_r",0.05,0.0)]:
        c=float(cur[fld])
        for v in sorted(set([max(lo,c-delta),c,c+delta])):
            candidates.append((f"{fld}_{v:.2f}",_variant(base,fld,round(v,6))))
    seen=set(); out=[]
    for name,label_cfg in candidates:
        key=json.dumps(label_cfg,sort_keys=True)
        if key in seen: continue
        seen.add(key)
        cc=deepcopy(cfg); cc["label"]=label_cfg
        try:
            lab=build_labels(raw_pre,cc); st=_label_stats(lab)
            st.update({"name":name,"label":label_cfg,"retention_ratio":float(st.get("supervised_rows",0)/max(1,len(raw_pre)))})
            out.append(st)
        except Exception as e:
            out.append({"name":name,"label":label_cfg,"error":str(e),"rows":0,"retention_ratio":0.0})
    return out


def _guided_hypotheses(cfg: dict, label_rows: list[dict], feature_rows: list[dict], drift_rows: list[dict]) -> list[dict]:
    base=deepcopy(cfg["label"]); hy=[]
    # Feature audit is diagnostic in v0.6.3. Automatic feature-contract mutation is forbidden
    # because MT5/Python parity would otherwise be silently broken. Guided executable hypotheses
    # therefore mutate labels only while keeping exact CP32 input semantics.
    valid=[r for r in label_rows if not r.get("error") and r.get("rows",0)>=500]
    def label_rank(r):
        bal=abs(float(r.get("directional_ratio",0.0))-0.55)+abs(float(r.get("skip_ratio",0.0))-0.45)
        return (bal,-float(r.get("retention_ratio",0.0)))
    hy.append({"name":"BASELINE FROZEN","label":base,"zero_features":[],"reason":"control; exact CP32"})
    # v1.3.2 FEAT-01: rule_meta_score is both an input feature and a post-model
    # deployment blend signal. Do not silently remove it from production semantics;
    # require a deterministic zero-mask ablation so Research can measure whether the
    # double exposure adds independent edge or merely duplicates the rule engine.
    hy.append({"name":"ABLATION · RULE_META_SCORE","label":deepcopy(base),"zero_features":["rule_meta_score"],"reason":"FEAT-01 diagnostic ablation; CP32/runtime tensor contract preserved via zero-mask"})
    for r in sorted(valid,key=label_rank):
        if r["label"] == base: continue
        hy.append({"name":"LABEL · "+r["name"],"label":r["label"],"zero_features":[],"reason":"bounded label sensitivity; OOF only; CP32 unchanged"})
        if len(hy)>=9: break
    return hy


def _merge_scientist_guided_hypotheses(model_run: Path, cfg: dict, hypotheses: list[dict], max_total: int = 14) -> tuple[list[dict], list[dict]]:
    agenda_path=model_run/"scientific_agenda.json"
    if not agenda_path.exists(): return hypotheses, []
    try: agenda=_load_json(agenda_path)
    except Exception: return hypotheses, []
    out=list(hypotheses); accepted=[]; seen=set(json.dumps({"label":h.get("label"),"zero_features":h.get("zero_features")},sort_keys=True) for h in out)
    for h in agenda if isinstance(agenda,list) else []:
        if len(out)>=max_total: break
        if not isinstance(h,dict) or not h.get("executable",True): continue
        kind=str(h.get("kind") or ""); payload=h.get("payload") if isinstance(h.get("payload"),dict) else {}
        if kind=="LABEL_GEOMETRY":
            label=deepcopy(cfg["label"])
            for key in ("min_edge_r","min_margin_r"):
                if key in payload: label[key]=payload[key]
            candidate={"name":"SCIENTIST LABEL · "+str(h.get("title") or "hypothesis"),"label":label,"zero_features":[],"reason":"LLM label-separation agenda; execution geometry remains frozen to Strategy Optimizer/CP32 · "+str(h.get("rationale") or "")[:300]}
        elif kind=="FEATURE_ABLATION":
            candidate={"name":"SCIENTIST FEATURE · "+str(h.get("title") or "ablation"),"label":deepcopy(cfg["label"]),"zero_features":list(payload.get("zero_features") or []),"reason":"LLM feature ablation hypothesis; CP32 zero-mask preserves runtime contract · "+str(h.get("rationale") or "")[:300]}
        else:
            continue
        key=json.dumps({"label":candidate["label"],"zero_features":candidate["zero_features"]},sort_keys=True)
        if key in seen: continue
        seen.add(key); out.append(candidate); accepted.append(h)
    return out, accepted


def _expected_research_hash(source_run: Path, sm: dict, out_dir: str | Path) -> str:
    """Resolve immutable research hash, including legacy v0.6.6 fresh manifests.

    v0.6.6 fresh validation reused source_csv_sha256 for the mutable master CSV.
    For those manifests, walk to policy/source ancestry and recover the immutable hash.
    """
    direct=str(sm.get("research_source_csv_sha256") or "")
    if direct:
        return direct
    run_type=str(sm.get("run_type") or "")
    if run_type in {"FRESH_HOLDOUT_VALIDATION","FRESH_MODEL_VALIDATION"}:
        ids=[]
        if sm.get("policy_run_id"): ids.append(str(sm.get("policy_run_id")))
        if sm.get("source_run_id"): ids.append(str(sm.get("source_run_id")))
        for rid in ids:
            mp=Path(out_dir)/rid/"model_manifest.json"
            if not mp.exists():
                continue
            pm=_load_json(mp)
            h=str(pm.get("research_source_csv_sha256") or (pm.get("research_window") or {}).get("authority_snapshot_sha256") or pm.get("source_csv_sha256") or "")
            if h:
                return h
    return str((sm.get("research_window") or {}).get("authority_snapshot_sha256") or sm.get("source_csv_sha256") or "")


def run_feature_label_audit(source_run_dir, csv_path, config_path="config.json", out_dir="runs", progress=None):
    source_run=Path(source_run_dir); mp=source_run/"model_manifest.json"
    if not mp.exists(): raise ValueError("Source run tidak memiliki model_manifest.json")
    sm=_load_json(mp); csv_path=str(csv_path); actual=sha256_file(csv_path); expected=_expected_research_hash(source_run,sm,out_dir)
    if expected and actual!=expected:
        raise ValueError(f"Immutable research source hash mismatch. expected={expected[:12]} actual={actual[:12]}")
    # Policy runs point back to the original model run; otherwise source is the run itself.
    model_run_id=str(sm.get("source_run_id") or sm.get("run_id")); model_run=Path(out_dir)/model_run_id
    mm=_load_json(model_run/"model_manifest.json") if (model_run/"model_manifest.json").exists() else sm
    source_cfg_path=model_run/"run_config.json"; cfg=load_cfg(source_cfg_path if source_cfg_path.exists() else config_path)
    current=load_cfg(config_path); cfg["acceptance"]=deepcopy(current.get("acceptance",cfg.get("acceptance",{})))
    raw=load_training_csv(csv_path); labeled=build_labels(raw,cfg); pre,_retired,region_meta=research_region(labeled,cfg)
    cutoff=pd.Timestamp(pre["signal_time"].max())
    raw_pre=raw[pd.to_datetime(raw["signal_time"],errors="coerce")<=cutoff].copy().reset_index(drop=True)
    if progress: progress({"stage":"audit","current":1,"total":4,"message":"Audit label distribution + sensitivity pada upstream pre-holdout…"})
    label_base=_label_stats(pre); label_rows=_label_sensitivity(raw_pre,cfg)
    if progress: progress({"stage":"audit","current":2,"total":4,"message":"Audit feature drift + redundancy…"})
    drift=_feature_drift(pre); redundant=_redundancy(pre)
    spec=CandidateSpec(str(mm.get("model_family")),str(mm.get("model_name")),dict(mm.get("hyperparameters") or {}))
    if progress: progress({"stage":"audit","current":3,"total":4,"message":"Re-fit frozen model per OOF fold untuk feature-importance stability…"})
    importance=_importance_stability(pre,spec,cfg)
    source_cv=sm.get("cv_selection") or {}
    overselection={
        "policy_total_validation_trades":int(source_cv.get("total_validation_trades",0) or 0),
        "policy_regime_concentration":float(source_cv.get("median_regime_concentration",0.0) or 0.0),
        "policy_pf_std":float(source_cv.get("profit_factor_std",0.0) or 0.0),
        "suspected_overselection":bool(int(source_cv.get("total_validation_trades",0) or 0)<int(cfg.get("acceptance",{}).get("cv_min_validation_trades",90)) or float(source_cv.get("median_regime_concentration",0.0) or 0.0)>float(cfg.get("acceptance",{}).get("max_dominant_positive_regime_share",0.75)))
    }
    hypotheses=_guided_hypotheses(cfg,label_rows,importance,drift)
    hypotheses, scientist_guided=_merge_scientist_guided_hypotheses(model_run,cfg,hypotheses)
    run_id=datetime.now(timezone.utc).strftime("AUDIT_%Y%m%d_%H%M%S_UTC"); out=Path(out_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    report={
        "schema":"FEATURE_LABEL_AUDIT_V1","run_id":run_id,"source_run_id":sm.get("run_id"),"model_source_run_id":model_run_id,
        "retired_locked_test_accessed":False,"research_cutoff":str(cutoff),"dataset_sha256":actual,"research_region":region_meta,
        "dataset":{"symbol":str(raw["symbol"].iloc[0]),"period":int(raw["period"].iloc[0]),"timeframe":period_label(raw["period"].iloc[0]),"raw_rows":int(len(raw)),"pre_rows":int(len(pre))},
        "policy_overselection":overselection,"label_base":label_base,"label_sensitivity":label_rows,"feature_drift":drift,"feature_redundancy":redundant,"feature_importance_stability":importance,
        "guided_hypotheses":hypotheses,"scientist_guided_hypotheses":scientist_guided,
    }
    _write_json(out/"feature_label_audit.json",report); _write_json(out/"guided_hypotheses.json",hypotheses); _write_json(out/"run_config.json",cfg)
    manifest={
        "run_id":run_id,"run_type":"FEATURE_LABEL_AUDIT","status":"FEATURE_LABEL_AUDIT_READY","supervisor_stage":"WAITING_GUIDED_RESEARCH","reject_reasons":[],
        "source_run_id":sm.get("run_id"),"model_source_run_id":model_run_id,"source_csv_sha256":actual,"research_source_csv_sha256":actual,"dataset_provenance":{"symbol":str(raw["symbol"].iloc[0]),"period":int(raw["period"].iloc[0]),"timeframe":period_label(raw["period"].iloc[0]),"source_start":str(raw["signal_time"].min()),"source_end":str(raw["signal_time"].max())},
        "symbol":str(raw["symbol"].iloc[0]),"period":int(raw["period"].iloc[0]),"timeframe":period_label(raw["period"].iloc[0]),"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),
        "model_family":spec.family,"model_name":spec.name,"hyperparameters":spec.params,"label_policy":cfg["label"],"research_cutoff":str(cutoff),"research_region":region_meta,"audit_report_file":"feature_label_audit.json",
        "generated_utc":datetime.now(timezone.utc).isoformat(),"agent":{"locked_test_opened_once":False,"retired_locked_test_accessed":False,"planner":"feature_label_audit_v1"},
    }
    _write_json(out/"model_manifest.json",manifest); _write_json(out/"supervisor_state.json",{"stage":"WAITING_GUIDED_RESEARCH","run_id":run_id,"next_required":"GUIDED_RESEARCH","updated_utc":datetime.now(timezone.utc).isoformat()})
    with (out/"REPORT.md").open("w",encoding="utf-8") as f:
        f.write(f"# Feature + Label Audit {run_id}\n\n**Source run:** {sm.get('run_id')}\n\n**Status:** FEATURE_LABEL_AUDIT_READY\n\n")
        f.write(f"Retired locked test accessed: **FALSE**. Research cutoff: `{cutoff}`.\n\n")
        f.write(f"Policy overselection risk: **{'YES' if overselection['suspected_overselection'] else 'NO'}** · OOF trades {overselection['policy_total_validation_trades']} · regime concentration {overselection['policy_regime_concentration']:.3f}.\n\n")
        f.write(f"Generated {len(hypotheses)} bounded OOF hypotheses.\n\n**Next required:** GUIDED_RESEARCH\n")
    if progress: progress({"stage":"done","current":4,"total":4,"message":"FEATURE_LABEL_AUDIT_READY · lanjut Guided Research"})
    return {"run":str(out),"status":"FEATURE_LABEL_AUDIT_READY","manifest":manifest,"report":report}
