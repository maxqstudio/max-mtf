from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from models.models import CandidateSpec, validate_candidate
from research.structured_research_memory import refresh_structured_memory

SCHEMA = "CP_RESEARCH_MEMORY_V1"


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _contract_fingerprint(cfg: dict, source_hash: str) -> str:
    obj = {
        "source_hash": str(source_hash or ""),
        "label": cfg.get("label", {}),
        "feature_research": cfg.get("feature_research", {}),
        "split": cfg.get("split", {}),
    }
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _parents(manifest: dict):
    keys = ("source_run_id", "model_source_run_id", "audit_run_id", "policy_run_id")
    return [str(manifest.get(k)) for k in keys if manifest.get(k)]


def lineage_runs(start: Path, runs_dir: Path, limit=24) -> list[Path]:
    out=[]; queue=[start]; seen=set()
    while queue and len(out)<limit:
        cur=queue.pop(0)
        if cur.name in seen: continue
        seen.add(cur.name); out.append(cur)
        m=_load(cur/"model_manifest.json")
        for p in _parents(m):
            pp=runs_dir/p
            if pp.exists() and pp.name not in seen: queue.append(pp)
    return out


def build_research_memory(guided_run_dir: str|Path, runs_dir: str|Path, recommended_cfg: dict) -> dict:
    guided=Path(guided_run_dir); runs=Path(runs_dir)
    lineage=lineage_runs(guided,runs)
    experiments=[]; scientist=[]; guided_evidence=[]; source_hash=""; parent_cfg={}
    for rd in lineage:
        m=_load(rd/"model_manifest.json")
        if not source_hash:
            source_hash=str(m.get("research_source_csv_sha256") or m.get("source_csv_sha256") or "")
        lb=rd/"cv_leaderboard.json"
        if lb.exists():
            for row in _load(lb,[]):
                if isinstance(row,dict):
                    r=deepcopy(row); r["run_id"]=rd.name; experiments.append(r)
        sj=rd/"scientist_journal.json"
        if sj.exists():
            scientist.extend([x for x in _load(sj,[]) if isinstance(x,dict)])
        sa=rd/"scientific_agenda.json"
        if sa.exists():
            scientist.append({"hypotheses":[x for x in _load(sa,[]) if isinstance(x,dict)]})
        gl=rd/"guided_leaderboard.json"
        if gl.exists():
            guided_evidence.extend([x for x in _load(gl,[]) if isinstance(x,dict)])
        rc=rd/"run_config.json"
        if rc.exists() and not parent_cfg:
            parent_cfg=_load(rc,{})
    experiments.sort(key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True)
    elites=[]
    for r in experiments:
        if not r.get("family") or not isinstance(r.get("params"),dict): continue
        elites.append({
            "run_id":r.get("run_id"),"name":r.get("name"),"family":r.get("family"),"params":r.get("params"),
            "cv_gate_pass":bool(r.get("cv_gate_pass")),"selection_score":float(r.get("selection_score",-1e99)),
            "first_failed_gate":r.get("cv_first_failed_gate"),"trades":int(r.get("total_validation_trades",0) or 0),
            "pf":float(r.get("median_profit_factor",0) or 0),"expectancy_r":float(r.get("median_expectancy_r",0) or 0),
            "worst_expectancy_r":float(r.get("worst_expectancy_r",0) or 0),"worst_dd_r":float(r.get("worst_fold_max_drawdown_r",0) or 0),
            "training_memory_months":int((r.get("params") or {}).get("training_memory_months",0) or 0),
        })
        if len(elites)>=8: break
    fail_counts={}
    for r in experiments:
        g=str(r.get("cv_first_failed_gate") or "PASS")
        fail_counts[g]=fail_counts.get(g,0)+1
    agenda=[]
    for s in scientist:
        for h in (s.get("hypotheses") or []):
            if isinstance(h,dict): agenda.append(h)
    # Keep unique agenda by kind/title/payload.
    seen=set(); clean_agenda=[]
    for h in agenda:
        key=json.dumps({"kind":h.get("kind"),"title":h.get("title"),"payload":h.get("payload")},sort_keys=True,default=str)
        if key in seen: continue
        seen.add(key); clean_agenda.append(h)
    parent_contract=_contract_fingerprint(parent_cfg or recommended_cfg,source_hash)
    next_contract=_contract_fingerprint(recommended_cfg,source_hash)
    winner = guided_evidence[0] if guided_evidence else {}
    memory={
        "schema":SCHEMA,
        "source_hash":source_hash,
        "parent_contract_fingerprint":parent_contract,
        "next_contract_fingerprint":next_contract,
        "contract_changed":parent_contract!=next_contract,
        "lineage_runs":[x.name for x in lineage],
        "elites":elites,
        "failure_gate_counts":fail_counts,
        "guided_winner":{k:winner.get(k) for k in ("name","reason","label","zero_features","selection_score","cv_gate_pass","cv_first_failed_gate")},
        "scientist_agenda":clean_agenda[-24:],
        "experiment_count":len(experiments),
        "learning_summary":{
            "best_family":elites[0]["family"] if elites else None,
            "best_model":elites[0]["name"] if elites else None,
            "best_failed_gate":elites[0].get("first_failed_gate") if elites else None,
            "dominant_failure_gate":max(fail_counts,key=fail_counts.get) if fail_counts else None,
        },
    }
    memory=refresh_structured_memory(memory,clean_agenda)
    (guided/"research_memory.json").write_text(json.dumps(memory,indent=2,default=str),encoding="utf-8")
    return memory


def _params_exact(source: dict, executable: dict) -> tuple[bool,list[dict]]:
    """Executable-semantic equality for memory rechecks.

    Historical candidates may predate explicit neutral regularization keys. Inserting
    those estimator defaults is semantic identity, not a transformed descendant.
    Any clamp or non-neutral key/value change remains non-exact.
    """
    source=dict(source or {}); executable=dict(executable or {})
    canonicalization=[]
    if set(source) - set(executable):
        return False,canonicalization
    neutral_defaults={"reg_alpha":0.0,"reg_lambda":1.0,"policy_reg_alpha":0.0,"policy_reg_lambda":1.0}
    for key in set(executable)-set(source):
        if key not in neutral_defaults:
            return False,canonicalization
        try:
            if abs(float(executable[key])-float(neutral_defaults[key]))>1e-12:
                return False,canonicalization
        except Exception:
            return False,canonicalization
        canonicalization.append({"parameter":key,"requested":None,"executable":executable[key],"kind":"NEUTRAL_OPTIONAL_DEFAULT_INSERTION"})
    for key,value in source.items():
        other=executable.get(key)
        try:
            if abs(float(value)-float(other)) > 1e-12:
                return False,canonicalization
        except (TypeError,ValueError):
            if value != other:
                return False,canonicalization
    return True,canonicalization


def seed_candidates_from_memory(memory: dict, cfg: dict, count: int, *, return_evidence: bool = False):
    """Seed only exact rechecks under the *current* executable contract.

    Historical elites that require clamping/canonical transformation are not rechecks.
    They are rejected here so fresh deterministic discovery can fill the slot, while
    provenance records the old scientific intent instead of silently rewriting it.
    """
    out=[]; evidence=[]
    for i,e in enumerate(memory.get("elites") or [],1):
        if len(out)>=count: break
        source_params=deepcopy(e.get("params") or {})
        raw={"family":e.get("family"),"name":f"learn_recheck_{i:02d}_{e.get('family','model')}","params":source_params}
        s=validate_candidate(raw,cfg,i)
        row={
            "schema":"MAX_MEMORY_RECHECK_ADMISSION_V1",
            "source_family":str(e.get("family") or ""),
            "source_name":str(e.get("name") or ""),
            "source_params":source_params,
            "requested_recheck_name":raw["name"],
            "exact_recheck":False,
        }
        if s is None:
            row.update({"admission_status":"REJECTED","rejection_reason":"NOT_EXECUTABLE_UNDER_CURRENT_CONTRACT","executable_params":None})
            evidence.append(row); continue
        row["executable_params"]=deepcopy(s.params)
        exact_semantics, semantic_canonicalization = _params_exact(source_params,s.params)
        row["semantic_canonicalization"]=semantic_canonicalization
        if not exact_semantics:
            row.update({
                "admission_status":"REJECTED",
                "rejection_reason":"CURRENT_CONTRACT_REQUIRES_TRANSFORMATION",
                "scientific_attribution":"SOURCE_ELITE_NOT_EXACTLY_RECHECKABLE",
            })
            evidence.append(row); continue
        row.update({
            "admission_status":"ACCEPTED",
            "rejection_reason":None,
            "exact_recheck":True,
            "scientific_attribution":"EXACT_MEMORY_ELITE_RECHECK",
        })
        setattr(s,"memory_recheck_provenance",deepcopy(row))
        evidence.append(row); out.append(s)
    return (out,evidence) if return_evidence else out

