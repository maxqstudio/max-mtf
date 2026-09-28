from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=MODELLAB_ROOT
SKILL_ROOT=ROOT/"skills"/"max_scientist"
MANIFEST=SKILL_ROOT/"manifest.json"
SCHEMA="MAX_DATA_SCIENTIST_SKILL_PACK_V1"
REQUIRED_SECTIONS=(
    "## PURPOSE","## INPUT EVIDENCE","## DECISION PROCEDURE","## FAILURE PATTERNS",
    "## ALLOWED ACTIONS","## FORBIDDEN ACTIONS","## OUTPUT SCHEMA","## TEST / REGRESSION FIXTURES","## REFERENCES",
)
METHOD_SECTIONS=(
    "PURPOSE","INPUT EVIDENCE","DECISION PROCEDURE","FAILURE PATTERNS",
    "ALLOWED ACTIONS","FORBIDDEN ACTIONS","OUTPUT SCHEMA","TEST / REGRESSION FIXTURES",
)

_RUNTIME_DOCTRINE={
    "max-research-data-scientist":"Observe deterministic evidence; form falsifiable hypotheses; run bounded attributable experiments; learn from lineage; never change gates, execution authority, protected OOS, promotion or risk.",
    "scientific-method":"State mechanism, prediction and falsification before execution; preserve negative results; avoid parameter shopping and post-hoc stories.",
    "data-quality-point-in-time":"Every feature must be available at decision time; learned transforms fit train-only; preserve source lineage and temporal gaps.",
    "feature-label-research":"Audit feature causality, context-vs-supervised rows, execution eligibility, label/KPI utility alignment and temporal continuity before tuning models.",
    "experiment-design":"Choose the smallest bounded intervention that tests one mechanism; use controls/ablations and explicit escalation rules.",
    "time-series-validation":"Chronology, purge/embargo, held-fold isolation and protected Fresh boundaries are immutable scientific constraints.",
    "model-research":"Select family/capacity from data and failure mechanism; demand controlled incremental evidence for hybrids/complex architectures.",
    "robustness-overfitting":"Inspect worst folds, trial multiplicity, sensitivity, seeds and tails; canonical MAX DSR/PBO remain deterministic authority.",
    "research-diagnosis":"Diagnose blocker class from margins/coverage/folds; prioritize blocker removal over composite-score chasing; treat learning-policy ranking as advisory prior.",
}
_TAGS={
    "max-research-data-scientist":["core"],"scientific-method":["core","hypothesis"],
    "data-quality-point-in-time":["data","leakage","point_in_time"],"feature-label-research":["feature","label","coverage"],
    "experiment-design":["experiment","budget"],"time-series-validation":["fold","wfa","cpcv","validation"],
    "model-research":["model","family","capacity","seed"],"robustness-overfitting":["robustness","pbo","dsr","stress","seed"],
    "research-diagnosis":["failure","diagnosis","learning_policy"],
}


def _sha(path: Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest()->dict:
    rows=[]
    for sid in _RUNTIME_DOCTRINE:
        p=SKILL_ROOT/sid/"SKILL.md"; txt=p.read_text(encoding="utf-8")
        missing=[s for s in REQUIRED_SECTIONS if s not in txt]
        if missing: raise RuntimeError(f"SKILL_QUALITY_CONTRACT: {sid} missing {missing}")
        rows.append({
            "skill_id":sid,"file":str(p.relative_to(ROOT)).replace("\\","/"),"sha256":_sha(p),
            "tags":_TAGS[sid],"runtime_doctrine":_RUNTIME_DOCTRINE[sid],
            "max_authority":"ADVISORY","may_compute_authoritative_metrics":False,"may_emit_pass_fail":False,
            "may_rank_challengers":False,"may_promote":False,"may_trade":False,"may_mutate_frozen_contract":False,
        })
    return {"schema":SCHEMA,"skills":rows,"skill_count":len(rows),"authority":"ADVISORY_METHOD_ONLY"}


def write_manifest()->dict:
    m=build_manifest(); MANIFEST.write_text(json.dumps(m,indent=2),encoding="utf-8"); return m


def load_manifest(*, verify: bool=True)->dict:
    if not MANIFEST.exists(): return write_manifest()
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if m.get("schema")!=SCHEMA: raise RuntimeError("SCIENTIST_SKILL_MANIFEST_SCHEMA")
    if verify:
        for row in m.get("skills") or []:
            p=ROOT/str(row.get("file"));
            if not p.exists() or _sha(p)!=str(row.get("sha256")): raise RuntimeError(f"SCIENTIST_SKILL_HASH_DRIFT: {row.get('skill_id')}")
            txt=p.read_text(encoding="utf-8")
            missing=[s for s in REQUIRED_SECTIONS if s not in txt]
            if missing: raise RuntimeError(f"SKILL_QUALITY_CONTRACT: {row.get('skill_id')} missing {missing}")
            if any(bool(row.get(k)) for k in ("may_compute_authoritative_metrics","may_emit_pass_fail","may_rank_challengers","may_promote","may_trade","may_mutate_frozen_contract")):
                raise RuntimeError(f"SCIENTIST_SKILL_AUTHORITY_VIOLATION: {row.get('skill_id')}")
    return m




def _section_map(txt: str)->dict[str,str]:
    out: dict[str,str]={}
    current=None
    buf=[]
    def flush():
        nonlocal current,buf
        if current is not None:
            out[current]="\n".join(buf).strip()
        buf=[]
    for line in str(txt or "").splitlines():
        if line.startswith("## "):
            flush(); current=line[3:].strip(); continue
        if current is not None:
            buf.append(line)
    flush()
    return out


def _runtime_methodology(skill_id: str, row: dict)->dict:
    p=ROOT/str(row.get("file")); txt=p.read_text(encoding="utf-8")
    sections=_section_map(txt)
    selected={k:sections.get(k,"") for k in METHOD_SECTIONS}
    if any(not v.strip() for v in selected.values()):
        missing=[k for k,v in selected.items() if not v.strip()]
        raise RuntimeError(f"SKILL_RUNTIME_CONTEXT_INCOMPLETE: {skill_id} missing {missing}")
    return {
        "skill_id":skill_id,
        "sha256":str(row.get("sha256") or _sha(p)),
        "runtime_doctrine":str(row.get("runtime_doctrine") or ""),
        "methodology":selected,
        "authority":"ADVISORY_METHOD_ONLY",
    }


def _wanted_ids(context: dict)->list[str]:
    ids=["max-research-data-scientist","scientific-method","experiment-design","research-diagnosis"]
    gate=str(((context.get("failure_topology") or {}).get("dominant_first_failed_gate") or "")).upper()
    if any(x in gate for x in ("DATA","NAN","SCHEMA","LEAK","GAP")): ids.append("data-quality-point-in-time")
    if any(x in gate for x in ("TRADE","COVERAGE","EXPECTANCY","LABEL")): ids.append("feature-label-research")
    if any(x in gate for x in ("FOLD","CPCV","PBO","WFA","SAMPLE")): ids.append("time-series-validation")
    if any(x in gate for x in ("SEED","MODEL","CAPACITY","PF","EXPECTANCY")): ids.append("model-research")
    if any(x in gate for x in ("DD","CVAR","SHARPE","SORTINO","PBO","DSR","STRESS","SEED","WORST")): ids.append("robustness-overfitting")
    # Validation and robustness are relevant defaults for any completed WFA evidence.
    if context.get("top_results"): ids.extend(["time-series-validation","model-research","robustness-overfitting"])
    return list(dict.fromkeys(ids))


def skill_guidance(context: dict, *, max_skills:int=9)->dict:
    m=load_manifest(verify=True); by={r["skill_id"]:r for r in m.get("skills") or []}
    ids=[x for x in _wanted_ids(context or {}) if x in by][:max(1,int(max_skills))]
    methods=[_runtime_methodology(x,by[x]) for x in ids]
    return {
        "schema":SCHEMA,"skill_ids":ids,"doctrines":[by[x]["runtime_doctrine"] for x in ids],
        "methods":methods,"method_context_mode":"SELECTED_SKILL_PROCEDURES_NOT_SUMMARY_ONLY",
        "authority":"ADVISORY_METHOD_ONLY","may_emit_pass_fail":False,"may_promote":False,"may_trade":False,
    }

# Ensure a reproducible manifest exists for packaged builds.
if __name__=="__main__":
    print(json.dumps(write_manifest(),indent=2))
