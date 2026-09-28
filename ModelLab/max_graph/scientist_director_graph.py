from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from max_graph.evidence_tools import ALLOWED_TOOLS, attribute_previous_proposals, inspect_request
from max_graph.runtime import sqlite_checkpointer
from max_graph.state import ScientistDirectorState
from models.models import strict_scientist_candidate_admission
from scientist.core.scientist import _extract_json

SCHEMA="MAX_AGENTIC_SCIENTIST_DIRECTOR_GRAPH_V1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw="|".join(json.dumps(x,sort_keys=True,separators=(",",":"),default=str) for x in parts)
    return prefix+"_"+hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _jsonable_proposal(spec: Any) -> dict:
    return {"family":str(spec.family),"name":str(spec.name),"params":deepcopy(spec.params)}


def _inspection_plan(scientist, context: dict, cfg: dict, hypothesis_memory: list[dict]) -> dict:
    """Ask Scientist what evidence it needs before designing the next experiments.

    This is a bounded read-only tool-selection step. It cannot alter config, gates,
    candidate eligibility, strategy geometry, chronology, seeds or promotion authority.
    """
    allowed=sorted(ALLOWED_TOOLS)
    compact={
        "round":context.get("round"),
        "budget_remaining":context.get("budget_remaining"),
        "first_failed_gate_counts":context.get("first_failed_gate_counts") or {},
        "failure_topology":context.get("failure_topology") or {},
        "fidelity_ladder":context.get("fidelity_ladder") or {},
        "top_results":deepcopy((context.get("top_results") or [])[:5]),
        "prior_hypotheses":deepcopy((hypothesis_memory or [])[-8:]),
        "allowed_tools":allowed,
        "request":"Choose 0-4 read-only evidence inspections needed before the next experiment design. Return JSON only.",
    }
    system=(
        "You are the evidence-inspection phase of an autonomous quantitative Research Director. "
        "You may only request the listed read-only deterministic evidence tools. You cannot change KPI, "
        "strategy geometry, seeds, chronology, locked/fresh holdouts, live risk, execution or promotion. "
        "Prefer targeted inspection over broad context. Return JSON keys: observation, diagnosis, focus_candidate, evidence_requests. "
        "evidence_requests is an array of {tool,candidate,reason}; tool must be from allowed_tools."
    )
    txt=scientist._call_with_phase(
        [{"role":"system","content":system},{"role":"user","content":json.dumps(compact,separators=(",",":"),default=str)}],
        temperature=0.12,
        phase="AGENTIC_EVIDENCE_INSPECTION",
    )
    obj=_extract_json(txt)
    reqs=[]
    for raw in obj.get("evidence_requests") or []:
        if len(reqs)>=4 or not isinstance(raw,dict): break
        tool=str(raw.get("tool") or "").upper().strip()
        if tool not in ALLOWED_TOOLS: continue
        reqs.append({"tool":tool,"candidate":str(raw.get("candidate") or "")[:160],"reason":str(raw.get("reason") or "")[:400]})
    return {
        "observation":str(obj.get("observation") or "")[:900],
        "diagnosis":str(obj.get("diagnosis") or "")[:900],
        "focus_candidate":str(obj.get("focus_candidate") or "")[:160],
        "evidence_requests":reqs,
        "llm_provenance":deepcopy(getattr(scientist,"last_call_provenance",{}) or {}),
    }


def _build_graph(scientist, cfg: dict, max_n: int):
    from langgraph.graph import END, START, StateGraph

    def guard(state: ScientistDirectorState):
        req=str(state.get("request_id") or "")
        if req and req==str(state.get("last_request_id") or "") and isinstance(state.get("last_response"),dict):
            return {"status":"CACHED","response":deepcopy(state["last_response"])}
        return {"status":"RUNNING","error":None}

    def guard_route(state: ScientistDirectorState):
        return "cached" if state.get("status")=="CACHED" else "attribute"

    def attribute(state: ScientistDirectorState):
        context=deepcopy(state.get("context") or {})
        lineage=attribute_previous_proposals(context,list(state.get("proposal_lineage") or []))
        memory=deepcopy(state.get("hypothesis_memory") or [])
        # Import pre-existing deterministic lifecycle evidence as Scientist memory,
        # but never overwrite its statuses.
        existing=context.get("hypothesis_lifecycle") or context.get("scientific_agenda") or []
        known={str(x.get("memory_id") or x.get("hypothesis_id") or "") for x in memory if isinstance(x,dict)}
        for raw in existing:
            if not isinstance(raw,dict): continue
            ident=str(raw.get("hypothesis_id") or _stable_id("HYP",raw.get("kind"),raw.get("title"),raw.get("payload")))
            if ident in known: continue
            rr=deepcopy(raw); rr.setdefault("memory_id",ident); rr.setdefault("source","DETERMINISTIC_LIFECYCLE_IMPORT")
            memory.append(rr); known.add(ident)
        return {"prior_attribution":lineage,"proposal_lineage":lineage,"hypothesis_memory":memory}

    def inspect_plan(state: ScientistDirectorState):
        context=deepcopy(state.get("context") or {})
        plan=_inspection_plan(scientist,context,cfg,list(state.get("hypothesis_memory") or []))
        return {"inspection_plan":plan,"evidence_requests":deepcopy(plan.get("evidence_requests") or [])}

    def inspect_evidence(state: ScientistDirectorState):
        context=deepcopy(state.get("context") or {})
        memory=list(state.get("hypothesis_memory") or [])
        rows=[inspect_request(context,r,memory) for r in (state.get("evidence_requests") or [])]
        return {"inspected_evidence":rows}

    def design(state: ScientistDirectorState):
        context=deepcopy(state.get("context") or {})
        context["agentic_scientist"]={
            "inspection_plan":deepcopy(state.get("inspection_plan") or {}),
            "inspected_evidence":deepcopy(state.get("inspected_evidence") or []),
            "prior_proposal_attribution":deepcopy(state.get("prior_attribution") or [])[-12:],
            "persistent_hypothesis_memory":deepcopy(state.get("hypothesis_memory") or [])[-16:],
            "authority":"ADVISORY_RESEARCH_DIRECTION_ONLY",
        }
        resp=scientist.propose(context,cfg,max_n=max_n)
        proposals=[_jsonable_proposal(x) for x in (resp.get("proposals") or [])]
        clean=deepcopy(resp); clean["proposals"]=proposals
        clean["agentic_inspection"]=deepcopy(state.get("inspection_plan") or {})
        clean["agentic_evidence"]=deepcopy(state.get("inspected_evidence") or [])
        return {"response":clean}

    def validate_and_remember(state: ScientistDirectorState):
        response=deepcopy(state.get("response") or {})
        validated=[]
        lineage=list(state.get("proposal_lineage") or [])
        round_no=int(state.get("round_no") or 0)
        req=str(state.get("request_id") or "")
        graph_admission=[]
        for i,raw in enumerate(response.get("proposals") or [],1):
            spec, admission = strict_scientist_candidate_admission(raw,cfg,i)
            graph_admission.append(admission)
            if spec is None: continue
            row=_jsonable_proposal(spec); validated.append(row)
            pid=_stable_id("PROP",req,round_no,i,row)
            if not any(str(x.get("proposal_id"))==pid for x in lineage if isinstance(x,dict)):
                lineage.append({
                    "proposal_id":pid,"request_id":req,"round":round_no,"candidate_name":row["name"],
                    "family":row["family"],"params":deepcopy(row["params"]),"fate":"PROPOSED_VALIDATED",
                    "created_utc":_utc(),"authority":"SCIENTIST_PROPOSAL_VALIDATED_DETERMINISTICALLY",
                })
        response["proposals"]=validated
        response["graph_candidate_admission"]=graph_admission
        memory=list(state.get("hypothesis_memory") or [])
        for i,h in enumerate(response.get("hypotheses") or [],1):
            if not isinstance(h,dict): continue
            mid=_stable_id("HYP",h.get("kind"),h.get("title"),h.get("payload"))
            if any(str(x.get("memory_id"))==mid for x in memory if isinstance(x,dict)): continue
            hh=deepcopy(h); hh["memory_id"]=mid; hh["source"]="SCIENTIST_GRAPH"; hh["first_seen_round"]=round_no; hh.setdefault("status","PROPOSED")
            memory.append(hh)
        response["agentic_metadata"]={
            "schema":SCHEMA,"thread_id":state.get("thread_id"),"request_id":req,
            "hypothesis_memory_count":len(memory),"proposal_lineage_count":len(lineage),
            "inspection_tool_count":len(state.get("inspected_evidence") or []),
        }
        return {
            "response":response,"last_request_id":req,"last_response":deepcopy(response),
            "proposal_lineage":lineage[-256:],"hypothesis_memory":memory[-128:],"status":"COMPLETED",
        }

    g=StateGraph(ScientistDirectorState)
    g.add_node("guard",guard)
    g.add_node("attribute_previous",attribute)
    g.add_node("plan_inspection",inspect_plan)
    g.add_node("inspect_evidence",inspect_evidence)
    g.add_node("design_experiments",design)
    g.add_node("validate_and_remember",validate_and_remember)
    g.add_edge(START,"guard")
    g.add_conditional_edges("guard",guard_route,{"cached":END,"attribute":"attribute_previous"})
    g.add_edge("attribute_previous","plan_inspection")
    g.add_edge("plan_inspection","inspect_evidence")
    g.add_edge("inspect_evidence","design_experiments")
    g.add_edge("design_experiments","validate_and_remember")
    g.add_edge("validate_and_remember",END)
    return g


def run_agentic_scientist_round(*, scientist, context: dict, cfg: dict, out_dir: str | Path, thread_id: str, request_id: str, max_n: int=5) -> dict:
    """Execute one persistent Scientist Research Director round via LangGraph."""
    out=Path(out_dir); db=out/"langgraph"/"scientist_director.sqlite"
    initial: ScientistDirectorState={
        "schema":SCHEMA,"thread_id":str(thread_id),"request_id":str(request_id),
        "round_no":int(context.get("round") or 0),"context":deepcopy(context),"status":"STARTED",
    }
    with sqlite_checkpointer(db) as saver:
        graph=_build_graph(scientist,cfg,max(0,int(max_n))).compile(checkpointer=saver)
        final=graph.invoke(initial,config={"configurable":{"thread_id":str(thread_id)}})
    response=deepcopy(final.get("response") or final.get("last_response") or {})
    # Runtime callers still use CandidateSpec objects. Keep checkpoints JSON-safe and
    # reconstruct only after the graph has committed its state.
    rebuilt=[]
    rebuild_admission=[]
    for i,raw in enumerate(response.get("proposals") or [],1):
        spec, admission = strict_scientist_candidate_admission(raw,cfg,i)
        rebuild_admission.append(admission)
        if spec is not None: rebuilt.append(spec)
    response["proposals"]=rebuilt
    response["graph_rebuild_candidate_admission"]=rebuild_admission
    response["langgraph_thread_id"]=str(thread_id)
    response["langgraph_request_id"]=str(request_id)
    response["langgraph_checkpoint_db"]=str(db)
    return response
