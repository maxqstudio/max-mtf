from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path

from models.capacity_governor import (
    build_dataset_capacity_profile,
    candidate_scientific_capacity,
    summarize_capacity_evidence,
)
from models.model_registry import family_spec, temporal_families, effective_bounds
from models.models import (
    CandidateSpec,
    candidate_capacity_contract,
    estimate_candidate_parameter_count,
    generate_initial_population,
    random_candidate,
    strict_scientist_candidate_admission,
)
from research.research_architect import (
    apply_research_plan,
    compile_research_plan,
    recommended_parameter_envelopes,
)
from research.research_control import bind_manual_capacity_authority, compile_manual_runtime

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "config/config.json").read_text(encoding="utf-8"))


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("PASS ", msg)


def profile(*, ram=32.0, available=24.0, cuda=False, vram=0.0, vram_free=0.0, cores=12):
    return {
        "profile_hash": f"CAP_{ram}_{vram}_{cores}",
        "cpu": {"name":"fixture","physical_cores":cores,"logical_threads":cores*2,"planning_cores":cores},
        "memory": {"total_gib":ram,"available_gib":available,"source":"fixture"},
        "nvidia": {"detected":bool(cuda),"devices":([{"name":"fixture GPU","memory_total_gib":vram,"memory_free_gib":vram_free}] if cuda else [])},
        "torch": {"installed":True,"cuda_available":bool(cuda)},
    }


def planned_cfg(*, rows=70_000, years=10, hardware=None, priority=0.50, max_minutes=120, family="transformer"):
    cfg=deepcopy(BASE)
    ra=cfg.setdefault("research_architecture",{})
    ra["family_selection_mode"]="MANUAL"
    ra["allowed_families"]=[family]
    ra["topology_selection_mode"]="OWNER_FIXED"
    ra["hybrid_priority"]=0.0
    ra["require_baseline"]=False
    ra["max_single_experiment_minutes"]=int(max_minutes)
    if family in (ra.get("family_size_priorities") or {}):
        ra["family_size_priorities"][family]=float(priority)
    cfg.setdefault("split",{})["purge_bars"]=54
    cfg["split"]["embargo_bars"]=54
    cfg.setdefault("label",{})["max_hold_bars"]=54
    cfg.setdefault("agent",{})["max_experiments"]=8
    cfg["agent"]["round_size"]=8
    ident={"rows":int(rows),"start":"2016-01-01","end":f"{2016+int(years)}-01-01","symbol":"XAUUSD","period":"M5"}
    cap=build_dataset_capacity_profile(ident,cfg)
    hw=hardware or profile()
    plan=compile_research_plan({"active_families":[family]},hw,cfg,cap)
    return apply_research_plan(cfg,plan), cap, plan, hw


def transformer_params(**overrides):
    p={
        "sequence_length":64,
        "d_model":128,
        "num_layers":3,
        "attention_heads":4,
        "ffn_mult":4,
        "dropout":0.10,
        "learning_rate":0.001,
        "batch_size":16,
        "epochs":8,
        "weight_decay":0.001,
        "training_memory_months":48,
    }
    p.update(overrides)
    return p


def main():
    # CASE A — old recommendation is guidance, not executable max.
    cfg, cap, plan, hw = planned_cfg()
    old=plan["recommended_parameter_envelopes"]["transformer"]
    exe=plan["executable_parameter_envelopes"]["transformer"]
    req(int(old["d_model"][1]) <= 96 and int(old["num_layers"][1]) <= 2, "fixture preserves old conservative Transformer recommendation")
    req(int(exe["d_model"][1]) > int(old["d_model"][1]) and int(exe["num_layers"][1]) > int(old["num_layers"][1]), "recommended starting envelope no longer hard-blocks legal temporal capacity")
    larger=CandidateSpec("transformer","larger_than_old_static",transformer_params())
    cc=candidate_capacity_contract(larger,cfg)
    req(cc["passed"] and larger.params["d_model"] > old["d_model"][1] and larger.params["num_layers"] > old["num_layers"][1], "CASE A larger-than-old-static Transformer is admitted when justified")
    req(cc["actual_parameter_count"] == estimate_candidate_parameter_count(larger), "actual executable parameter count is measured")

    # Observability contract.
    required_fields={"family","actual_parameter_count","legal_ceiling","resource_ceiling","scientific_ceiling","effective_ceiling","preferred_range","extended_ceiling","training_memory_months","sequence_length","minimum_fold_train_rows","effective_sample_estimate","size_priority","capacity_band","capacity_admission_status","capacity_reason"}
    req(required_fields.issubset(cc), "DL capacity evidence exposes required admission observability")

    # CASE B — scientific ceiling blocks hardware-fit model on small information set.
    strong=profile(ram=64,available=50,cuda=True,vram=24,vram_free=20,cores=16)
    small_cfg,_,_,_=planned_cfg(rows=4_000,years=5,hardware=strong,max_minutes=10_000)
    small_cc=candidate_capacity_contract(larger,small_cfg)
    req((not small_cc["passed"]) and small_cc["rejecting_authority"]=="SCIENTIFIC", "CASE B dataset-too-small rejects by SCIENTIFIC ceiling")

    # CASE C — resource ceiling/resource estimator blocks otherwise scientifically justified model.
    weak=profile(ram=8,available=1,cuda=False,cores=4)
    resource_cfg,_,_,_=planned_cfg(rows=200_000,years=10,hardware=weak,max_minutes=10_000)
    resource_spec=CandidateSpec("transformer","resource_pressure",transformer_params(d_model=192,num_layers=2,sequence_length=128,batch_size=128,epochs=80))
    resource_cc=candidate_capacity_contract(resource_spec,resource_cfg)
    req((not resource_cc["passed"]) and resource_cc["rejecting_authority"]=="RESOURCE", "CASE C hardware-too-small rejects by RESOURCE authority")

    # CASE D — legal max remains hard even if data/resources justify more.
    huge_cfg,_,_,_=planned_cfg(rows=2_000_000,years=10,hardware=strong,max_minutes=10_000)
    legal_probe=CandidateSpec("transformer","legal_probe",transformer_params(sequence_length=16,num_layers=2,training_memory_months=120))
    legal_cc=candidate_capacity_contract(legal_probe,huge_cfg)
    req(legal_cc["scientific_ceiling"] > legal_cc["legal_ceiling"] and legal_cc["resource_ceiling"] > legal_cc["legal_ceiling"], "CASE D fixture data/resources exceed legal implementation ceiling")
    req(legal_cc["effective_ceiling"] == legal_cc["legal_ceiling"], "CASE D LEGAL ceiling remains effective authority")

    # CASE E — same data, different sequence length => different scientific capacity.
    sci32=candidate_scientific_capacity(huge_cfg,"transformer",transformer_params(sequence_length=32))
    sci512=candidate_scientific_capacity(huge_cfg,"transformer",transformer_params(sequence_length=512))
    req(sci32["scientific_parameter_ceiling"] != sci512["scientific_parameter_ceiling"] and sci32["scientific_parameter_ceiling"] > sci512["scientific_parameter_ceiling"], "CASE E scientific capacity is candidate sequence-aware")

    # CASE F — training memory changes actual fold information budget.
    sci6=candidate_scientific_capacity(huge_cfg,"transformer",transformer_params(sequence_length=64,training_memory_months=6))
    sci48=candidate_scientific_capacity(huge_cfg,"transformer",transformer_params(sequence_length=64,training_memory_months=48))
    req(sci48["minimum_temporal_train_rows"] > sci6["minimum_temporal_train_rows"] and sci48["scientific_parameter_ceiling"] > sci6["scientific_parameter_ceiling"], "CASE F scientific capacity is training-memory aware")

    # CASE G/H — LARGE reaches extended justified region but never means registry max.
    large_cfg,_,large_plan,_=planned_cfg(priority=1.0)
    generated=[random_candidate(large_cfg,"transformer",random.Random(100+i),f"large_{i}") for i in range(4)]
    generated_cc=[candidate_capacity_contract(s,large_cfg) for s in generated]
    req(all(x["passed"] for x in generated_cc), "CASE G/H Large generator emits only dynamically admitted candidates")
    req(any(s.params["d_model"] > old["d_model"][1] or s.params["num_layers"] > old["num_layers"][1] for s in generated), "CASE G Large can reach above old conservative static envelope")
    req(all(x["actual_parameter_count"] <= x["effective_ceiling"] < x["legal_ceiling"] for x in generated_cc), "CASE H Large remains below current justified ceiling instead of jumping to registry max")

    # Evidence-aware movement is search preference only, never a hard-ceiling override.
    expand=summarize_capacity_evidence([
        {"family":"transformer","parameter_count":100_000,"selection_score":0.10,"cv_gate_pass":True},
        {"family":"transformer","parameter_count":150_000,"selection_score":0.12,"cv_gate_pass":True},
        {"family":"transformer","parameter_count":600_000,"selection_score":0.20,"cv_gate_pass":True},
        {"family":"transformer","parameter_count":800_000,"selection_score":0.22,"cv_gate_pass":True},
    ],family="transformer")
    contract=summarize_capacity_evidence([
        {"family":"transformer","parameter_count":100_000,"selection_score":0.20,"cv_gate_pass":True},
        {"family":"transformer","parameter_count":150_000,"selection_score":0.22,"cv_gate_pass":True},
        {"family":"transformer","parameter_count":600_000,"selection_score":0.08,"cv_gate_pass":False},
        {"family":"transformer","parameter_count":800_000,"selection_score":0.06,"cv_gate_pass":False},
    ],family="transformer")
    req(expand["status"]=="EXPAND" and contract["status"]=="CONTRACT" and float(contract["expansion_factor"])<1.0, "capacity movement is evidence-aware and conservative")

    # CASE I — common capacity concept across old/new temporal families and hybrid temporal leg.
    rec=recommended_parameter_envelopes(hw,cap,{})
    old_temporal={"gru","lstm","tcn","transformer"}
    all_temporal=set(temporal_families())
    req({"patchtst","itransformer","tft","transformer_moe"}.issubset(all_temporal), "CASE I modern temporal families present in common universe")
    for fam in sorted(all_temporal):
        row=candidate_scientific_capacity(cfg,fam,{"sequence_length":64,"training_memory_months":48})
        req(row.get("available") is True and row.get("scientific_parameter_ceiling",0)>0, f"CASE I {fam} uses common candidate-aware scientific capacity")
    for fam in sorted(old_temporal):
        spec=family_spec(fam) or {}; size_keys=list(spec.get("size_parameters") or [])
        req(bool(size_keys),f"CASE I {fam} declares size dimensions")
    hybrid_sci=candidate_scientific_capacity(cfg,"hybrid::gru::lightgbm",{"temporal_sequence_length":64,"training_memory_months":48})
    req(hybrid_sci.get("available") is True and hybrid_sci.get("hybrid_temporal_oof") is True, "CASE I hybrid temporal leg inherits scientific capacity authority")

    # CASE J — MANUAL exact candidate above old recommendation is legal if dynamically admitted.
    manual_cfg=deepcopy(BASE)
    manual_cfg.setdefault("champion_factory",{})["research_mode"]="MANUAL"
    manual_cfg["champion_factory"]["manual_research"]={"enabled":True,"take_threshold":0.60,"minimum_wfa_survivors":1,"candidates":[{"family":"transformer","name":"manual_dynamic","params":deepcopy(larger.params)}]}
    manual_runtime, manual_rows=compile_manual_runtime(manual_cfg)
    bound_runtime, manual_evidence=bind_manual_capacity_authority(manual_runtime,manual_rows,hw,cap)
    req(manual_rows[0]["params"]==larger.params and manual_evidence[0]["capacity_contract"]["passed"], "CASE J Manual accepts exact candidate above old recommendation when inside dynamic capacity")

    # CASE K — Scientist shares same dynamic capacity authority.
    spec,admission=strict_scientist_candidate_admission({"family":"transformer","name":"scientist_dynamic","params":deepcopy(larger.params)},cfg,1)
    req(spec is not None and spec.params==larger.params and admission["admission_status"]=="ACCEPTED", "CASE K Scientist may propose above old static recommendation inside dynamic ceiling")
    too_large=transformer_params(sequence_length=512,d_model=512,num_layers=6,attention_heads=4,ffn_mult=6,batch_size=16,epochs=8,training_memory_months=48)
    spec2,admission2=strict_scientist_candidate_admission({"family":"transformer","name":"scientist_too_large","params":too_large},cfg,2)
    req(spec2 is None and admission2["admission_status"]=="REJECTED" and admission2["rejection_reason"]=="CANDIDATE_CAPACITY_CONTRACT_REJECTED", "CASE K Scientist cannot bypass effective dynamic capacity")

    # CASE L — AUTO emitted identity is already inside capacity authority.
    auto_cfg,_,_,_=planned_cfg(priority=1.0)
    auto=generate_initial_population(auto_cfg,count=4,round_no=1)
    req(len(auto)==4 and all(candidate_capacity_contract(s,auto_cfg)["passed"] for s in auto), "CASE L AUTO never emits candidate outside current capacity authority")

    print("V201_DYNAMIC_MODEL_CAPACITY_AUTHORITY PASS")


if __name__ == "__main__":
    main()
