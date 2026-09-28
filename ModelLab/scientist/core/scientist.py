from __future__ import annotations
import json
import os
import re
import inspect
import ast
from copy import deepcopy
from typing import Any

from models.models import CandidateSpec, spec_fingerprint, validate_candidate, strict_scientist_candidate_admission
from models.model_registry import enabled_families, get_bounds, registry_for_scientist, family_spec, effective_bounds, configured_family_size_priorities
from host.provider_catalog import chat_completion, extract_chat_text, extract_token_usage, estimate_api_cost_usd, normalize_base_url, fallback_error_category
from research.scientific_hypotheses import validate_hypothesis, strict_scientist_hypothesis_admission, merge_strategy_from_hypotheses, seed_stability_hypothesis_from_topology
from research.creativity_governor import adaptive_creativity_profile, phase_temperature
from scientist.core.llm_health import model_health, record_failure, record_success, health_snapshot
from core.training_method_contract import training_method_context
from scientist.python.scientist_python_runtime import (
    analysis_capability_instruction,
    authorized_analysis_inputs_from_messages,
    parse_python_analysis_request,
    python_analysis_evidence_for_llm,
    run_scientist_python_analysis,
    scientist_python_health,
)

# The Scientist is advisory. Search bounds come from model_registry.json and remain Supervisor-owned.
BOUNDS = get_bounds()


def _coerce(v: Any, lo: float, hi: float, typ):
    if typ is int:
        v = int(round(float(v)))
    else:
        v = float(v)
    v = max(lo, min(hi, v))
    return int(v) if typ is int else float(v)


def _strip_trailing_commas_json(text: str) -> str:
    """Remove commas directly before ]/} while preserving quoted string content.

    This is deliberately narrow: it repairs a common LLM serialization defect without
    accepting comments, unquoted identifiers, or executing arbitrary content.
    """
    out=[]
    i=0
    in_string=False
    escape=False
    while i < len(text):
        ch=text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape=False
            elif ch=='\\':
                escape=True
            elif ch=='"':
                in_string=False
            i+=1
            continue
        if ch=='"':
            in_string=True; out.append(ch); i+=1; continue
        if ch==',':
            j=i+1
            while j < len(text) and text[j].isspace():
                j+=1
            if j < len(text) and text[j] in ']}':
                i+=1
                continue
        out.append(ch); i+=1
    return ''.join(out)


def _json_error_context(text: str, exc: BaseException) -> str:
    pos=getattr(exc,'pos',None)
    if not isinstance(pos,int):
        return str(exc)[:300]
    lo=max(0,pos-90); hi=min(len(text),pos+90)
    frag=text[lo:hi].replace('\r',' ').replace('\n',' \n ')
    return f"{exc}; near={frag!r}"[:500]


def _parse_json_object_candidate(candidate: str) -> dict:
    errors=[]
    for label, payload in (("strict",candidate),("trailing_comma_recovery",_strip_trailing_commas_json(candidate))):
        try:
            obj=json.loads(payload)
            if isinstance(obj,dict):
                return obj
            errors.append(f"{label}: top-level is {type(obj).__name__}, expected object")
        except Exception as exc:
            errors.append(f"{label}: {_json_error_context(payload,exc)}")
    # Safe stdlib fallback for Python-literal style dicts occasionally emitted by LLMs
    # (single-quoted keys/strings, True/False/None, trailing commas). literal_eval never
    # executes calls or arbitrary code. The resulting object still passes schema cleaning.
    try:
        obj=ast.literal_eval(candidate)
        if isinstance(obj,dict):
            return obj
        errors.append(f"python_literal: top-level is {type(obj).__name__}, expected object")
    except Exception as exc:
        errors.append(f"python_literal: {str(exc)[:300]}")
    raise ValueError("LLM Scientist malformed JSON object; " + " | ".join(errors[-3:]))


def _extract_json(text: str) -> dict:
    text = str(text or '').strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    candidates=[text]
    start=text.find('{'); end=text.rfind('}')
    if start >= 0 and end > start:
        sliced=text[start:end+1]
        if sliced != text:
            candidates.append(sliced)
    last=None
    for candidate in candidates:
        try:
            return _parse_json_object_candidate(candidate)
        except Exception as exc:
            last=exc
    raise ValueError(str(last or "LLM Scientist did not return a JSON object"))


_FORMAT_ONLY_JSON_REPAIR_SYSTEM = (
    "You are a strict JSON serializer. Convert the supplied malformed response into exactly one valid JSON object. "
    "Preserve every scientific claim, value, array, object, key intent, and decision exactly in meaning. "
    "Do not add, remove, reinterpret, summarize, optimize, correct scientific content, or invent missing values. "
    "Repair JSON serialization syntax only. Use double-quoted JSON property names and strings, JSON true/false/null, "
    "no comments, no markdown fences, and no text before or after the object."
)


def _extract_json_with_bounded_format_repair(self, text: str, *, phase: str) -> tuple[dict, dict]:
    """Parse one Scientist response with at most one format-only LLM repair.

    This helper never guesses scientific content locally. The initial response is parsed by
    the existing JSON authority. On serialization failure only, one retry is allowed at
    temperature 0 under a serializer-only system prompt. The repaired response is parsed
    by the same authority and then flows through the same downstream schema/bounds
    validation as an initially valid response. A second malformed response fails closed.
    """
    try:
        return _extract_json(text), {"used": False}
    except Exception as initial_exc:
        initial_provenance = json.loads(json.dumps(getattr(self, "last_call_provenance", {}) or {}, default=str))
        try:
            repaired = _invoke_call_with_phase_compat(
                self,
                [
                    {"role": "system", "content": _FORMAT_ONLY_JSON_REPAIR_SYSTEM},
                    {"role": "user", "content": str(text or "")},
                ],
                temperature=0.0,
                phase=str(phase) + "_JSON_REPAIR",
            )
            obj = _extract_json(repaired)
        except Exception as repair_exc:
            raise ValueError(
                "LLM Scientist malformed JSON and bounded format-only retry failed; "
                f"phase={phase}; initial={str(initial_exc)[:700]}; repair={str(repair_exc)[:700]}"
            ) from repair_exc
        return obj, {
            "used": True,
            "phase": str(phase),
            "repair_phase": str(phase) + "_JSON_REPAIR",
            "temperature": 0.0,
            "initial_error": str(initial_exc)[:700],
            "initial_call_provenance": initial_provenance,
            "repair_call_provenance": json.loads(json.dumps(getattr(self, "last_call_provenance", {}) or {}, default=str)),
            "authority": "FORMAT_ONLY_ONE_RETRY_NO_SEMANTIC_CHANGE",
        }


class LLMScientist:
    def __init__(self, cfg: dict, api_key: str | None = None):
        self.cfg = cfg
        self.timeout = int(cfg.get("timeout_sec", 60))
        self.temperature = float(cfg.get("temperature", 0.15))
        self.default_env = str(cfg.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY")
        self.api_key = (api_key or os.environ.get(self.default_env) or "").strip()
        self.last_call_provenance: dict = {"attempts": []}
        self.health_enabled = bool(cfg.get("model_health_enabled", False))
        self.health_path = cfg.get("model_health_path") or None
        self.transient_cooldown_sec = int(cfg.get("transient_cooldown_sec", 300) or 300)
        raw_stack=cfg.get("stack") if isinstance(cfg.get("stack"),list) else []
        stack=[]
        for raw in raw_stack:
            if not isinstance(raw,dict) or not bool(raw.get("enabled",True)):
                continue
            base=normalize_base_url(str(raw.get("base_url") or cfg.get("base_url") or cfg.get("endpoint") or ""))
            model=str(raw.get("model") or "").strip()
            if not base or not model:
                continue
            provider=str(raw.get("provider") or cfg.get("provider") or "custom")
            price_key=f"{provider}|{model}"
            pricing_map=cfg.get("pricing_usd_per_1m") if isinstance(cfg.get("pricing_usd_per_1m"),dict) else {}
            stack.append({"provider":provider,"base_url":base,"model":model,"api_key_env":str(raw.get("api_key_env") or self.default_env),"pricing":pricing_map.get(price_key) if isinstance(pricing_map.get(price_key),dict) else {}})
        if not stack:
            base=normalize_base_url(str(cfg.get("base_url") or cfg.get("endpoint") or "")); model=str(cfg.get("model") or "").strip()
            if base and model:
                provider=str(cfg.get("provider") or "custom")
                price_key=f"{provider}|{model}"
                pricing_map=cfg.get("pricing_usd_per_1m") if isinstance(cfg.get("pricing_usd_per_1m"),dict) else {}
                stack=[{"provider":provider,"base_url":base,"model":model,"api_key_env":self.default_env,"pricing":pricing_map.get(price_key) if isinstance(pricing_map.get(price_key),dict) else {}}]
        self.stack=stack
        first=stack[0] if stack else {}
        self.base_url=str(first.get("base_url") or "")
        self.provider=str(first.get("provider") or cfg.get("provider") or "custom")
        self.model=str(first.get("model") or "")

    @property
    def ready(self) -> bool:
        return bool(self.stack)

    def _key_for(self, entry: dict, index: int) -> str:
        env_name=str(entry.get("api_key_env") or self.default_env)
        if index == 0 and self.api_key:
            return self.api_key
        if env_name != self.default_env:
            return (os.environ.get(env_name) or "").strip()
        return (os.environ.get(env_name) or self.api_key or "").strip()

    def _call(self, messages: list[dict], *, temperature: float | None = None, phase: str = "GENERAL") -> str:
        if not self.ready:
            raise RuntimeError("LLM Scientist provider/model stack belum dikonfigurasi")
        attempts=[]
        last_exc=None
        for i,entry in enumerate(self.stack):
            provider=str(entry["provider"]); model=str(entry["model"])
            if self.health_enabled:
                health=model_health(provider,model,self.health_path,endpoint=entry.get("base_url"),api_key_env=entry.get("api_key_env"))
                if health.get("cooldown_active"):
                    attempts.append({
                        "priority":i+1,"provider":provider,"model":model,"status":"SKIP",
                        "category":str(health.get("status") or "COOLDOWN"),
                        "cooldown_until_utc":health.get("cooldown_until_utc"),
                        "reason":"MODEL_HEALTH_COOLDOWN",
                    })
                    continue
            try:
                call_temperature=self.temperature if temperature is None else max(0.0,min(1.0,float(temperature)))
                body=chat_completion(entry["base_url"],model,self._key_for(entry,i),messages,temperature=call_temperature,timeout=self.timeout)
                text=extract_chat_text(body)
                usage=extract_token_usage(body,messages=messages,output_text=text)
                cost=estimate_api_cost_usd(usage,entry.get("pricing"))
                attempt={"priority":i+1,"provider":provider,"model":model,"status":"PASS","usage":usage,"cost":cost,"temperature":call_temperature,"phase":str(phase)}
                attempts.append(attempt)
                if self.health_enabled:
                    record_success(provider,model,self.health_path,endpoint=entry.get("base_url"),api_key_env=entry.get("api_key_env"))
                self.last_call_provenance={
                    "selected_priority":i+1,"selected_provider":provider,"selected_model":model,
                    "fallback_used":i>0 or any(a.get("status")=="SKIP" for a in attempts[:-1]),
                    "attempts":attempts,"usage":usage,"cost":cost,"temperature":call_temperature,"phase":str(phase),
                    "model_health":health_snapshot(self.health_path) if self.health_enabled else {},
                }
                return text
            except Exception as exc:
                last_exc=exc; category=fallback_error_category(exc)
                attempts.append({"priority":i+1,"provider":provider,"model":model,"status":"FAIL","category":category or "NON_FALLBACK_ERROR","error":str(exc)[:500]})
                if self.health_enabled and category is not None:
                    record_failure(provider,model,category,str(exc),path=self.health_path,transient_cooldown_sec=self.transient_cooldown_sec,endpoint=entry.get("base_url"),api_key_env=entry.get("api_key_env"))
                if category is None:
                    self.last_call_provenance={"selected_priority":None,"fallback_used":i>0,"attempts":attempts,"model_health":health_snapshot(self.health_path) if self.health_enabled else {}}
                    raise
        self.last_call_provenance={"selected_priority":None,"fallback_used":len(attempts)>1,"attempts":attempts,"model_health":health_snapshot(self.health_path) if self.health_enabled else {}}
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LLM stack exhausted or all configured models are in cooldown")

    def _call_with_phase(self, messages: list[dict], *, temperature: float, phase: str) -> str:
        """Invoke one Scientist phase with at most one optional guarded Python attempt.

        Python remains analytical support only.  The model may request one bounded analysis
        from host-authorized in-memory evidence; deterministic host code chooses the
        interpreter and validates/executes the request.  Any non-EXECUTED result is returned
        to the same Scientist as REASONING_ONLY evidence.  JSON-format repair and connection
        tests never start Python analysis, preventing hidden retries.
        """
        call=self._call
        try:
            sig=inspect.signature(call)
            params=sig.parameters
            accepts_kwargs=any(x.kind is inspect.Parameter.VAR_KEYWORD for x in params.values())
            phase_aware=accepts_kwargs or ("temperature" in params and "phase" in params)
        except (TypeError,ValueError):
            phase_aware=True

        def invoke_once(call_messages: list[dict], call_phase: str) -> str:
            if phase_aware:
                return call(call_messages, temperature=temperature, phase=call_phase)
            return call(call_messages)

        phase_u=str(phase or "GENERAL").upper()
        capability_enabled=(phase_u != "CONNECTION_TEST" and not phase_u.endswith("_JSON_REPAIR") and "PYTHON_INTERPRETATION" not in phase_u)
        if not capability_enabled:
            return invoke_once(messages, str(phase))

        self.last_python_analysis=None
        authorized=authorized_analysis_inputs_from_messages(messages)
        health=scientist_python_health()
        capability=analysis_capability_instruction(authorized,health)
        call_messages=list(messages)
        insert_at=1 if call_messages and str(call_messages[0].get("role") or "")=="system" else 0
        call_messages.insert(insert_at,{"role":"system","content":capability})
        initial=invoke_once(call_messages,str(phase))
        request=parse_python_analysis_request(initial)
        if request is None:
            return initial

        initial_prov=json.loads(json.dumps(self.last_call_provenance,default=str))
        analysis=run_scientist_python_analysis(request,authorized)
        self.last_python_analysis=analysis
        evidence=python_analysis_evidence_for_llm(analysis)
        followup=list(call_messages)+[
            {"role":"assistant","content":initial},
            {"role":"system","content":
                "HOST SCIENTIST PYTHON RESULT. Treat this only as ANALYTICAL_EVIDENCE_ONLY; it cannot set Factory PASS/FAIL, admission, promotion, training, or acceptance. "
                "If execution_status is not EXECUTED, continue REASONING_ONLY and do not claim Python-derived numbers. No second Python request is allowed in this turn.\n"
                + json.dumps(evidence,ensure_ascii=False,separators=(",",":"),default=str)},
            {"role":"user","content":"Return the FINAL response now using the original required schema. Do not return python_analysis again."},
        ]
        final=invoke_once(followup,str(phase)+"_PYTHON_INTERPRETATION")
        final_prov=json.loads(json.dumps(self.last_call_provenance,default=str))
        merged=dict(final_prov)
        merged["python_analysis_request_call"]=initial_prov
        merged["python_analysis"]={
            "analysis_id":analysis.get("analysis_id"),
            "analysis_mode":analysis.get("analysis_mode"),
            "execution_status":analysis.get("execution_status"),
            "code_sha256":analysis.get("code_sha256"),
            "input_hashes":deepcopy(analysis.get("input_hashes") or {}),
            "evidence_class":analysis.get("evidence_class"),
        }
        self.last_call_provenance=merged
        return final

    def _with_provenance(self, payload: dict) -> dict:
        out=dict(payload)
        out["llm_provenance"]=json.loads(json.dumps(self.last_call_provenance,default=str))
        analysis=getattr(self,"last_python_analysis",None)
        out["analysis_mode"]=str((analysis or {}).get("analysis_mode") or "REASONING_ONLY")
        if isinstance(analysis,dict):
            out["python_analysis"]=python_analysis_evidence_for_llm(analysis)
        return out

    def test(self) -> dict:
        txt = self._call_with_phase([
            {"role": "system", "content": "Return only JSON."},
            {"role": "user", "content": "Return {\"ok\":true,\"role\":\"research_scientist\"}."},
        ], temperature=0.0, phase="CONNECTION_TEST")
        obj = _extract_json(txt)
        return self._with_provenance({"ok": bool(obj.get("ok")), "raw": obj})


    def propose(self, context: dict, cfg: dict, max_n: int = 5) -> dict:
        # The context deliberately excludes locked-test results. The Scientist is
        # not allowed to optimize against the final holdout.
        active_now=set(enabled_families(cfg))
        bounds_obj = {f: {k: [lo, hi] for k, (lo, hi, _) in ps.items()} for f, ps in BOUNDS.items() if f in active_now}
        system = (
            "You are a quantitative research scientist advising a deterministic Supervisor. You are NOT merely a hyperparameter mutator. "
            "Reason from the accumulated OOF evidence and Research Memory. You may formulate bounded scientific hypotheses about label geometry, "
            "feature ablation, temporal training memory, selectivity/abstention policy, regime policy, model-family architecture, hybrid ablations, "
            "and even objective ideas that the current engine cannot yet execute. Unsupported ideas must be marked as research backlog, never silently forced. "
            "You may also propose concrete model candidates. effective_parameter_bounds define the legal/current search envelope, while the deterministic dynamic capacity contract separately enforces actual-parameter-count LEGAL/RESOURCE/SCIENTIFIC ceilings using each candidate's memory and sequence. A proposal outside either authority is REJECTED, never clamped into a different experiment. You have NO authority to inspect or optimize against locked/fresh holdouts, "
            "change acceptance gates, promote a Champion, set live risk, or trade. Never request locked/fresh evidence. Optimize survival and repeatability across OOF folds. "
            "Return only compact JSON. Operator-facing text must be Indonesian. Keys: summary, report, stop_research, strategy, proposals, hypotheses. In SCIENTIST_DIRECTED topology mode, strategy may include hybrid_priority in [0,1]. "
            "report={condition,interpretation,next_action,confidence}. strategy may contain exploration_ratio [0.15..0.85], family_priorities weights [0.35..3.0], focus. "
            "proposals is an array of concrete {family,name,params}. hypotheses is an array of scientific hypotheses with keys kind,title,rationale,expected_observation,payload. "
            "Allowed kinds: LABEL_GEOMETRY, FEATURE_ABLATION, TRAINING_MEMORY, SELECTIVITY_POLICY, REGIME_POLICY, MODEL_ARCHITECTURE, HYBRID_ABLATION, SEED_STABILITY, OBJECTIVE_RESEARCH. "
            "Prefer hypotheses that explain WHY an edge works or fails, not parameter shopping. "
            "Use supplied MAX Data Scientist skill doctrines AND selected methodology sections (decision procedure, failure patterns, allowed/forbidden actions, output schema, regression fixtures) as methodological constraints. Do not reduce them to the one-line doctrine when methods are present. Use the structured Learning Policy only as an empirical prior for which experiment type to consider next; neither skills nor policy may override deterministic evidence. "
            "If deterministic_wfa_state is NO_WFA_SURVIVOR, you MUST NOT describe any family as optimal, converged, robust, successful, or production-ready; diagnose failure gates instead. "
            "Do not reveal chain-of-thought; provide concise conclusions/evidence only."
        )
        wfa_pass_count=int(context.get("wfa_pass_count",0) or 0)
        wfa_total_count=int(context.get("wfa_total_count",0) or 0)
        deterministic_wfa_state=("NO_WFA_SURVIVOR" if wfa_total_count>0 and wfa_pass_count==0 else ("WFA_SURVIVORS_PRESENT" if wfa_pass_count>0 else "NO_COMPLETED_WFA"))
        user = {
            "deterministic_wfa_state": deterministic_wfa_state,
            "wfa_pass_count": wfa_pass_count,
            "wfa_total_count": wfa_total_count,
            "first_failed_gate_counts": context.get("first_failed_gate_counts") or {},
            "enabled_families": sorted(enabled_families(cfg)),
            "parameter_bounds": bounds_obj,
            "effective_parameter_bounds": context.get("effective_parameter_bounds") or {f:{k:[v[0],v[1]] for k,v in effective_bounds(cfg,f).items()} for f in enabled_families(cfg)},
            "model_training_method_contract": training_method_context(),
            "dynamic_capacity_authority": deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_authority")) or {})),
            "capacity_evidence": deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence")) or {})),
            "capacity_evidence_by_family": deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence_by_family")) or {})),
            "recommended_starting_parameter_envelopes": deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("recommended_starting_parameter_envelopes")) or {})),
            "executable_parameter_envelopes": deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("executable_parameter_envelopes")) or {})),
            "owner_family_size_priorities": context.get("family_size_priorities") or configured_family_size_priorities(cfg),
            "experiment_budget_remaining": context.get("budget_remaining"),
            "round": context.get("round"),
            "dataset": context.get("dataset"),
            "top_walk_forward_results": context.get("top_results", [])[:10],
            "family_statistics": context.get("family_stats", {}),
            "fold_forensics": context.get("fold_forensics", [])[:8],
            "research_memory": context.get("research_memory", {}),
            "structured_learning_policy": context.get("learning_policy", {}),
            "max_data_scientist_skills": context.get("scientist_skills", {}),
            "future_learning_foundation": context.get("future_learning_foundation", {}),
            "prior_scientific_agenda": context.get("scientific_agenda", [])[-12:],
            "supervisor_plan": context.get("supervisor_plan", {}),
            "creativity_profile": context.get("creativity_profile") or adaptive_creativity_profile(cfg,board=context.get("top_results") or [],failure_topology=context.get("failure_topology") or {}),
            "factory_context": context.get("factory_context") or {},
            "topology_allocation": context.get("topology_allocation") or {},
            "compute_allocation": context.get("compute_allocation") or {},
            "cpcv_seed_policy": context.get("seed_policy") or {},
            "request": f"Propose at most {max_n} concrete experiments plus at most 6 scientific hypotheses. Learn from prior generations; do not repeat an experiment unless the research contract changed or the repetition is an explicit ablation/recheck."
        }
        _cp=user.get("creativity_profile") if isinstance(user.get("creativity_profile"),dict) else adaptive_creativity_profile(cfg)
        txt = self._call_with_phase([
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"), default=str)},
        ], temperature=phase_temperature(cfg,"DISCOVERY_HYPOTHESIS",_cp), phase="DISCOVERY_HYPOTHESIS")
        obj, _format_recovery = _extract_json_with_bounded_format_repair(self, txt, phase="DISCOVERY_HYPOTHESIS")
        proposals = []
        proposal_admission = []
        for i, raw in enumerate(obj.get("proposals") or [], 1):
            if len(proposals) >= max_n:
                break
            spec, admission = strict_scientist_candidate_admission(raw, cfg, i)
            proposal_admission.append(admission)
            if spec is not None:
                proposals.append(spec)
        hypotheses=[]
        hypothesis_admission=[]
        for i, raw_h in enumerate(obj.get("hypotheses") or [], 1):
            if len(hypotheses) >= 6:
                break
            h, h_admission=strict_scientist_hypothesis_admission(raw_h,cfg,i)
            hypothesis_admission.append(h_admission)
            if h is not None:
                hypotheses.append(h)
        strategy_raw = obj.get("strategy") if isinstance(obj.get("strategy"), dict) else {}
        strategy = {}
        if "exploration_ratio" in strategy_raw:
            try: strategy["exploration_ratio"] = max(0.15, min(0.85, float(strategy_raw["exploration_ratio"])))
            except Exception: pass
        pri = strategy_raw.get("family_priorities") if isinstance(strategy_raw.get("family_priorities"), dict) else {}
        allowed = set(enabled_families(cfg))
        clean_pri = {}
        for family, value in pri.items():
            if family in allowed:
                try: clean_pri[family] = max(0.35, min(3.0, float(value)))
                except Exception: pass
        if clean_pri: strategy["family_priorities"] = clean_pri
        _topology_mode=str(((cfg.get("agent") or {}).get("research_plan") or {}).get("topology_priority",{}).get("mode") or (cfg.get("research_architecture") or {}).get("topology_selection_mode") or "OWNER_FIXED").upper()
        if _topology_mode=="SCIENTIST_DIRECTED" and "hybrid_priority" in strategy_raw:
            try: strategy["hybrid_priority"] = max(0.0,min(1.0,float(strategy_raw["hybrid_priority"])))
            except Exception: pass
        if strategy_raw.get("focus"):
            strategy["focus"] = str(strategy_raw.get("focus"))[:240]
        strategy = merge_strategy_from_hypotheses(strategy, hypotheses)
        report_raw = obj.get("report") if isinstance(obj.get("report"), dict) else {}
        report = {
            "condition": str(report_raw.get("condition") or obj.get("summary") or "")[:700],
            "interpretation": str(report_raw.get("interpretation") or "")[:700],
            "next_action": str(report_raw.get("next_action") or strategy.get("focus") or "")[:500],
        }
        try:
            report["confidence"] = max(0.0, min(1.0, float(report_raw.get("confidence", 0.5))))
        except Exception:
            report["confidence"] = 0.5
        summary_text=str(obj.get("summary") or report.get("condition") or "")[:500]
        if deterministic_wfa_state=="NO_WFA_SURVIVOR":
            report["condition"]="NO_WFA_SURVIVOR"
            if not summary_text.startswith("NO_WFA_SURVIVOR"):
                summary_text=("NO_WFA_SURVIVOR · "+summary_text)[:500]
        return self._with_provenance({
            "summary": summary_text,
            "report": report,
            "stop_research": bool(obj.get("stop_research", False)),
            "stop_research_advisory": bool(obj.get("stop_research", False)),
            "response_format_recovery": _format_recovery,
            "strategy": strategy,
            "proposals": proposals,
            "proposal_admission": proposal_admission,
            "hypothesis_admission": hypothesis_admission,
            "model_training_method_contract": training_method_context(),
            "hypotheses": hypotheses,
            "deterministic_state": deterministic_wfa_state,
        })

# v0.6.0: optional operator-facing review after deterministic Policy Discovery.

def _invoke_call_with_phase_compat(self, messages: list[dict], *, temperature: float, phase: str) -> str:
    """Module-level compatibility bridge for legacy/test Scientist doubles.

    R5 phase-aware production calls carry temperature/phase provenance, while historical
    custom Scientist implementations may only implement `_call(messages)`.  Stage and
    Director helper functions are intentionally usable with both without weakening the
    production Scientist path.
    """
    fn=getattr(self,"_call_with_phase",None)
    if callable(fn):
        return fn(messages,temperature=temperature,phase=phase)
    call=getattr(self,"_call")
    try:
        sig=inspect.signature(call)
        params=sig.parameters
        accepts_kwargs=any(x.kind is inspect.Parameter.VAR_KEYWORD for x in params.values())
        phase_aware=accepts_kwargs or ("temperature" in params and "phase" in params)
    except (TypeError,ValueError):
        phase_aware=True
    if phase_aware:
        return call(messages,temperature=temperature,phase=phase)
    return call(messages)


def _policy_review(self, context: dict) -> dict:
    system = (
        "You are the same quantitative research scientist. The deterministic Supervisor has finished model "
        "hyperparameter search and then a bounded OOF Policy Discovery phase. You have no authority to change "
        "gates or open the locked test. Return only compact JSON with report={condition,interpretation,next_action,confidence} "
        "and summary. Write operator-facing text in Indonesian. Do not reveal chain-of-thought."
    )
    user = {"model_frontier": context.get("model_frontier"), "policy_frontier": context.get("policy_frontier"),
            "policy_passed": bool(context.get("policy_passed")), "next_required": context.get("next_required")}
    txt = _invoke_call_with_phase_compat(self,[{"role":"system","content":system},{"role":"user","content":json.dumps(user,separators=(",",":"),default=str)}], temperature=phase_temperature(self.cfg if isinstance(self.cfg,dict) else {},"POLICY_REVIEW"), phase="POLICY_REVIEW")
    obj, _format_recovery = _extract_json_with_bounded_format_repair(self, txt, phase="POLICY_REVIEW"); rr = obj.get("report") if isinstance(obj.get("report"),dict) else {}
    report={"condition":str(rr.get("condition") or obj.get("summary") or "")[:700],"interpretation":str(rr.get("interpretation") or "")[:700],"next_action":str(rr.get("next_action") or "")[:500]}
    try: report["confidence"]=max(0.0,min(1.0,float(rr.get("confidence",0.5))))
    except Exception: report["confidence"]=0.5
    return self._with_provenance({"summary":str(obj.get("summary") or report["condition"])[:500],"report":report,"response_format_recovery":_format_recovery})

LLMScientist.policy_review = _policy_review


# v0.7.2 R3: Factory-level Research Director. This is advisory and consumes only
# Discovery-side evidence. Tournament / Monte Carlo / Fresh Forward are deliberately
# excluded while their evaluation windows remain sealed.
def _clean_director_response(obj: dict, cfg: dict) -> dict:
    strategy_raw = obj.get("strategy") if isinstance(obj.get("strategy"), dict) else {}
    strategy = {}
    if "exploration_ratio" in strategy_raw:
        try:
            strategy["exploration_ratio"] = max(0.15, min(0.85, float(strategy_raw["exploration_ratio"])))
        except Exception:
            pass
    pri = strategy_raw.get("family_priorities") if isinstance(strategy_raw.get("family_priorities"), dict) else {}
    allowed = {f for f in pri if family_spec(str(f).strip().lower()) is not None}
    clean_pri = {}
    for family, value in pri.items():
        if family in allowed:
            try:
                clean_pri[family] = max(0.35, min(3.0, float(value)))
            except Exception:
                pass
    if clean_pri:
        strategy["family_priorities"] = clean_pri
    if strategy_raw.get("focus"):
        strategy["focus"] = str(strategy_raw.get("focus"))[:320]
    if isinstance(strategy_raw.get("active_families"), list):
        strategy["active_families"] = [str(x).strip().lower() for x in strategy_raw.get("active_families")[:24] if str(x).strip()]
    if isinstance(strategy_raw.get("hybrid_compositions"), list):
        comps=[]
        for raw in strategy_raw.get("hybrid_compositions")[:24]:
            if not isinstance(raw,dict): continue
            comps.append({
                "temporal":str(raw.get("temporal") or raw.get("encoder") or "").strip().lower(),
                "policy":str(raw.get("policy") or raw.get("head") or "").strip().lower(),
                "rationale":str(raw.get("rationale") or "")[:300],
            })
        strategy["hybrid_compositions"]=comps
    pref = strategy_raw.get("preferred_training_memory_months")
    if isinstance(pref, list):
        vals=[]
        for v in pref[:8]:
            try:
                iv=max(1,min(120,int(v)))
                if iv not in vals: vals.append(iv)
            except Exception:
                pass
        if vals: strategy["preferred_training_memory_months"] = vals

    penv = strategy_raw.get("parameter_envelopes") if isinstance(strategy_raw.get("parameter_envelopes"),dict) else {}
    clean_env={}
    for family, raw_params in list(penv.items())[:24]:
        fam=str(family).strip().lower()
        spec=family_spec(fam)
        if not spec or not isinstance(raw_params,dict):
            continue
        legal=spec.get("search") or {}; row={}
        for key, raw_range in list(raw_params.items())[:32]:
            if key not in legal or not (isinstance(raw_range,(list,tuple)) and len(raw_range)>=2):
                continue
            try:
                lo=float(raw_range[0]); hi=float(raw_range[1])
                if lo>hi: lo,hi=hi,lo
                meta=legal[key]; lo=max(float(meta.get("min")),lo); hi=min(float(meta.get("max")),hi)
                if lo<=hi:
                    if str(meta.get("type"))=="int": row[key]=[int(round(lo)),int(round(hi))]
                    else: row[key]=[lo,hi]
            except Exception:
                pass
        if row: clean_env[fam]=row
    if clean_env: strategy["parameter_envelopes"]=clean_env
    cint=strategy_raw.get("capacity_intent") if isinstance(strategy_raw.get("capacity_intent"),dict) else {}
    if cint:
        strategy["capacity_intent"]={
            "reference_training_memory_months": int(max(1,min(120,int(cint.get("reference_training_memory_months",18) or 18)))),
            "target_total_params": cint.get("target_total_params"),
            "rationale": str(cint.get("rationale") or "")[:500],
        }

    hypotheses=[]
    hypothesis_admission=[]
    for i, raw_h in enumerate(obj.get("hypotheses") or [], 1):
        if len(hypotheses) >= 6:
            break
        h,h_admission=strict_scientist_hypothesis_admission(raw_h,cfg,i)
        hypothesis_admission.append(h_admission)
        if h is not None:
            hypotheses.append(h)
    strategy = merge_strategy_from_hypotheses(strategy, hypotheses)

    rr = obj.get("report") if isinstance(obj.get("report"),dict) else {}
    report={
        "condition":str(rr.get("condition") or obj.get("summary") or "")[:900],
        "interpretation":str(rr.get("interpretation") or "")[:900],
        "next_action":str(rr.get("next_action") or strategy.get("focus") or "")[:700],
    }
    try:
        report["confidence"]=max(0.0,min(1.0,float(rr.get("confidence",0.5))))
    except Exception:
        report["confidence"]=0.5
    return {
        "summary":str(obj.get("summary") or report["condition"])[:700],
        "report":report,
        "strategy":strategy,
        "hypotheses":hypotheses,
        "hypothesis_admission":hypothesis_admission,
        "stop_research":bool(obj.get("stop_research",False)),
        "stop_research_advisory":bool(obj.get("stop_research",False)),
    }


def _sanitize_director_parameter_claims(text: Any) -> str:
    """Remove numeric architecture-bound claims from Director prose.

    Numeric parameter authority belongs to the deterministic compiled research plan.
    The LLM may propose ranges in strategy.parameter_envelopes, but operator prose must
    not present uncompiled numbers as if they were executable bounds.
    """
    out=str(text or "")
    keys=set()
    for fam,row in BOUNDS.items():
        keys.update(str(k) for k in (row or {}).keys())
    # Also catch common component aliases used in natural-language reports.
    keys.update({"hidden_size","sequence_length","num_layers","max_depth","n_estimators","num_leaves","batch_size","epochs","d_model","ffn_mult","expert_ffn","num_experts"})
    for key in sorted(keys,key=len,reverse=True):
        pat=rf"(?i)\b{re.escape(key)}\b\s*(?:=|:)?\s*\d+(?:\.\d+)?\s*(?:[-–—]|to|s/d)\s*\d+(?:\.\d+)?"
        out=re.sub(pat, f"{key} sesuai compiled bounds", out)
        pat_single=rf"(?i)\b{re.escape(key)}\b\s*(?:=|:)\s*\d+(?:\.\d+)?"
        out=re.sub(pat_single, f"{key}=compiled authority", out)
    return out


def _factory_director_call(self, phase: str, context: dict, cfg: dict) -> dict:
    phase=str(phase).upper()
    if phase not in {"PREFLIGHT","GENERATION_REVIEW"}:
        raise ValueError(f"Unsupported Research Director phase: {phase}")
    phase_instruction = (
        "This is PRE-FLIGHT before Generation 1. Analyze the legal Discovery research memory, source identity, prior failure patterns, "
        "family coverage and compute budget BEFORE any new candidate is created. Baseline is only a control anchor; produce a directed research thesis."
        if phase=="PREFLIGHT" else
        "A Discovery generation has just committed. Diagnose what was learned from WFA/OOF and Guided Research in that generation; CPCV is a later finalist stage, "
        "then direct the NEXT generation. Do not simply repeat the previous agenda."
    )
    system=(
        "You are the Factory-level quantitative Research Director for CPMF. " + phase_instruction + " "
        "You are advisory: the deterministic kernel owns bounds, chronology, KPI gates and execution. "
        "You may direct exploration ratio, model-family priorities, preferred training-memory windows and scientific hypotheses. "
        "You MUST NOT inspect, request, or optimize against CURRENT-CYCLE Tournament, Monte Carlo, Fresh Forward, locked holdout or live evidence while it is sealed. "
        "You MAY use prior-cycle committed stage-feedback summaries already present inside research_memory when their exact research-contract hash matches; treat them as bounded scientific lessons, never as permission to change KPI thresholds. "
        "Prefer falsifiable hypotheses and explain the current bottleneck. Use MAX Data Scientist skill doctrines plus their selected methodology sections as methodology; apply decision procedure/failure patterns rather than merely quoting the doctrine. Use the structured Learning Policy only as an empirical prior; neither may override deterministic evidence or the current research contract. Return only compact JSON in Indonesian for operator-facing text. "
        "Keys: summary, report, strategy, hypotheses, stop_research. "
        "report={condition,interpretation,next_action,confidence}. strategy may contain exploration_ratio [0.15..0.85], "
        "family_priorities weights [0.35..3.0], preferred_training_memory_months, focus, active_families, hybrid_compositions, parameter_envelopes, capacity_intent. "
        "At PREFLIGHT, choose an executable research portfolio from the deterministic model_registry and hardware_capabilities. "
        "Use dataset_capacity_profile to size temporal models from realistic per-fold/per-memory training rows rather than total history. "
        "Transformer-family choices have different inductive biases: vanilla Encoder is the control, PatchTST compresses chronological patches, iTransformer attends across feature tokens, TFT is an observed-covariate variable-selection/recurrent/attention model, and Transformer MoE is experimental specialization. Do not assume a more complex family is better; allocate experiments to falsify that claim against TCN/GRU/tree baselines. "
        "parameter_envelopes maps family -> parameter -> [low,high] and must remain inside model_registry legal bounds. "
        "Do NOT state numeric architecture/search bounds in summary/report/interpretation/next_action; numeric ranges belong only in strategy.parameter_envelopes and become authoritative only after deterministic compilation. Refer to them as compiled/effective bounds in prose. "
        "capacity_intent={reference_training_memory_months,target_total_params,rationale}. Prefer the smallest capacity likely to learn; larger models require evidence of under-capacity. "
        "During GENERATION_REVIEW compare committed parameter_count, effective train rows, fit cost and WFA generalization before widening capacity; shrink or regularize when added capacity improves fit but not OOS robustness. "
        "legacy_fallback_families is compatibility context only and MUST NOT constrain the new portfolio. "
        "You may choose pure ML, pure temporal DL, or compatible temporal->policy hybrids, but the Owner's topology_priority is immutable allocation authority: you select candidates inside its SINGLE/HYBRID shares and may only recommend a future change, never override it. Per-family owner_family_size_priorities are immutable search preferences: 0=Small, 0.50=balanced, 1=Large toward the upper currently justified region. effective_parameter_bounds define legal/current generation ranges, while dynamic_capacity_authority separately admits each actual candidate by min(LEGAL, RESOURCE, SCIENTIFIC) capacity using executable parameter count and candidate memory/sequence. Never bypass those hard ceilings. Do not assume bigger is better; justify movement with evidence. "
        "hypotheses uses the same allowed hypothesis kinds as the Scientist. stop_research is advisory only. "
        "Do not reveal chain-of-thought; provide concise conclusions and evidence references only."
    )
    user={
        "phase":phase,
        "factory_id":context.get("factory_id"),
        "factory_generation":context.get("factory_generation"),
        "dataset":context.get("dataset"),
        "data_quality_profile":context.get("data_quality_profile") or {},
        "research_memory":context.get("research_memory") or {},
        "structured_learning_policy":context.get("learning_policy") or {},
        "max_data_scientist_skills":context.get("scientist_skills") or {},
        "future_learning_foundation":context.get("future_learning_foundation") or {},
        "generation_summary":context.get("generation_summary") or {},
        "guided_summary":context.get("guided_summary") or {},
        "scientific_agenda":context.get("scientific_agenda") or [],
        "remaining_budget":context.get("remaining_budget"),
        "legacy_fallback_families":sorted(enabled_families(cfg)),
        "model_registry":context.get("model_registry") or registry_for_scientist(),
        "hardware_profile":context.get("hardware_profile") or {},
        "hardware_capabilities":context.get("hardware_capabilities") or {},
        "recommended_parameter_envelopes":context.get("recommended_parameter_envelopes") or {},
        "dataset_capacity_profile":context.get("dataset_capacity_profile") or {},
        "capacity_guidance":context.get("capacity_guidance") or {},
        "dynamic_capacity_authority":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_authority")) or {})),
        "capacity_evidence":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence")) or {})),
        "capacity_evidence_by_family":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence_by_family")) or {})),
        "recommended_starting_parameter_envelopes":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("recommended_starting_parameter_envelopes")) or {})),
        "executable_parameter_envelopes":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("executable_parameter_envelopes")) or {})),
        "effective_parameter_bounds":{f:{k:[v[0],v[1]] for k,v in effective_bounds(cfg,f).items()} for f in enabled_families(cfg)},
        "model_training_method_contract":training_method_context(),
        "dynamic_capacity_authority":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_authority")) or {})),
        "capacity_evidence":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence")) or {})),
        "capacity_evidence_by_family":deepcopy(((((cfg.get("agent") or {}).get("research_plan") or {}).get("capacity_evidence_by_family")) or {})),
        "owner_family_size_priorities":configured_family_size_priorities(cfg),
        "creativity_profile":context.get("creativity_profile") or adaptive_creativity_profile(cfg,failure_topology=((context.get("generation_summary") or {}).get("failure_topology") or {})),
        "cpcv_seed_policy":((((cfg.get("champion_factory") or {}).get("cpcv_stage") or {}).get("seed_confirmation") or {})),
        "owner_topology_priority": {
            "hybrid": max(0.0,min(1.0,float(((cfg.get("research_architecture") or {}).get("hybrid_priority",0.50))))),
            "single": 1.0-max(0.0,min(1.0,float(((cfg.get("research_architecture") or {}).get("hybrid_priority",0.50))))),
            "authority":"OWNER_SLIDER_0_TO_1",
            "meaning":"candidate allocation; not prediction blending",
        },
        "evaluation_feedback":"CURRENT_CYCLE_SEALED; PRIOR_COMMITTED_EXACT_CONTRACT_FEEDBACK_MAY_EXIST_IN_RESEARCH_MEMORY",
    }
    _profile=context.get("creativity_profile") if isinstance(context.get("creativity_profile"),dict) else adaptive_creativity_profile(cfg,failure_topology=((context.get("generation_summary") or {}).get("failure_topology") or {}))
    _phase="DIRECTOR_PREFLIGHT" if phase=="PREFLIGHT" else "DIRECTOR_GENERATION_REVIEW"
    txt=_invoke_call_with_phase_compat(self,[
        {"role":"system","content":system},
        {"role":"user","content":json.dumps(user,separators=(",",":"),default=str)},
    ], temperature=phase_temperature(cfg,_phase,_profile), phase=_phase)
    _director_obj, _format_recovery = _extract_json_with_bounded_format_repair(self, txt, phase=_phase)
    out=_clean_director_response(_director_obj,cfg)
    out["response_format_recovery"]=_format_recovery
    out["summary"]=_sanitize_director_parameter_claims(out.get("summary"))
    rr=dict(out.get("report") or {})
    for _k in ("condition","interpretation","next_action"):
        rr[_k]=_sanitize_director_parameter_claims(rr.get(_k))
    rr["parameter_authority"]="DETERMINISTIC_COMPILED_EFFECTIVE_BOUNDS"
    out["report"]=rr
    if phase=="GENERATION_REVIEW":
        gs=context.get("generation_summary") or {}
        try: wfa_passed=int(gs.get("wfa_passed",0) or 0)
        except Exception: wfa_passed=0
        try: experiments=int(gs.get("experiments",0) or 0)
        except Exception: experiments=0
        if experiments>0 and wfa_passed==0:
            out["deterministic_state"]="NO_WFA_SURVIVOR"
            rr=dict(out.get("report") or {}); rr["condition"]="NO_WFA_SURVIVOR"; out["report"]=rr
            if not str(out.get("summary") or "").startswith("NO_WFA_SURVIVOR"):
                out["summary"]=("NO_WFA_SURVIVOR · "+str(out.get("summary") or ""))[:700]
    return self._with_provenance(out)


def _factory_preflight(self, context: dict, cfg: dict) -> dict:
    return _factory_director_call(self,"PREFLIGHT",context,cfg)


def _factory_generation_review(self, context: dict, cfg: dict) -> dict:
    return _factory_director_call(self,"GENERATION_REVIEW",context,cfg)


LLMScientist.factory_preflight = _factory_preflight
LLMScientist.factory_generation_review = _factory_generation_review


# v0.7.3 R5: committed stage Scientist review. CPCV/Tournament/Monte Carlo failures
# may become exact-dataset research lessons only at a cycle boundary. Fresh Forward is
# reported but remains sealed from same-snapshot tuning.
def _stage_review(self, stage: str, context: dict, cfg: dict, learning_allowed: bool = True) -> dict:
    stage=str(stage or "").upper()
    if stage not in {"DATA","POOL","CPCV_CANDIDATE","CPCV","TOURNAMENT","MONTE_CARLO","FORWARD","CHAMPION"}:
        raise ValueError(f"Unsupported Scientist stage: {stage}")
    status=str(context.get("status") or "UNKNOWN")
    failed=("NO_SURVIVOR" in status or "FAIL" in status or status in {"INSUFFICIENT_QUALIFIED_POOL"})
    system=(
        "You are the CPMF quantitative LLM Scientist reviewing one COMMITTED deterministic research stage. "
        "The deterministic engine owns PASS/FAIL, chronology, KPI gates, candidate identity and execution. You may never override a gate. "
        "The dataset object contains header/schema information only; never request raw rows, prices, full CSV, or hidden holdout data. "
        "Use the supplied aggregate evidence, failure topology, candidate summaries and prior lineage. Return only compact JSON in Indonesian. "
        "Keys: summary, report, scientific_method, strategy, hypotheses, next_discovery_plan, stop_research. "
        "report={condition,interpretation,next_action,confidence}. scientific_method MUST contain {observation,hypothesis,experiment,falsification,conclusion}. "
        "OBSERVATION may state only deterministic supplied evidence; causal explanations belong only in HYPOTHESIS. EXPERIMENT states the bounded intervention, FALSIFICATION states what committed result rejects it, and CONCLUSION must be PENDING_DECISIVE_EXPERIMENT until decisive evidence exists. "
        "strategy may use the same bounded fields as Research Director. "
        "hypotheses must use legal Scientist hypothesis kinds and should explain failure mechanisms rather than chase one exact split metric. "
        "For executable MODEL_ARCHITECTURE hypotheses, payload may contain family_priorities, variable_keys_by_family, and parameter_ranges_by_family. "
        "HYBRID_ABLATION is executable and must name concrete dynamic hybrid families; the deterministic compiler supplies their standalone temporal controls without weakening Owner topology allocation. "
        "When CPCV seed evidence shows instability, prefer SEED_STABILITY rather than seed shopping; the fixed seed set is immutable. "
        "parameter_ranges_by_family must map family -> parameter -> [low,high], stay inside supplied effective_parameter_bounds (the executable authority), and should be used whenever the diagnosis says stronger/weaker regularization, depth, child/leaf constraints, sampling, learning rate, or estimator count. "
        "A vague architecture hypothesis without executable knobs/ranges is not sufficient for failure learning. Prefer a small interpretable variable set tied to the diagnosed mechanism. "
        "next_discovery_plan={objective,freeze,change,falsification,do_not_do}. "
        + ("This stage failure is allowed to inform the NEXT Discovery cycle only under the exact research-contract hash. Produce a falsifiable next-Discovery plan AND at least one executable bounded hypothesis that implements the plan using executable effective_parameter_bounds. Prefer MODEL_ARCHITECTURE, TRAINING_MEMORY, or SELECTIVITY_POLICY when appropriate; do not return only prose/backlog hypotheses. " if learning_allowed and failed else
           "This stage is REPORT-ONLY for research feedback. Do not prescribe same-snapshot tuning from this evidence. ")
        + "Do not reveal chain-of-thought; provide concise conclusions and evidence references only."
    )
    user={
        "stage":stage,"status":status,"dataset":context.get("dataset") or {},
        "stage_evidence":context.get("stage_evidence") or {},"failure_topology":context.get("failure_topology") or {},
        "candidate_summaries":context.get("candidate_summaries") or [],"prior_research_memory":context.get("research_memory") or {},
        "enabled_families":sorted(enabled_families(cfg)),
        "parameter_bounds":{f:{k:[v[0],v[1]] for k,v in ps.items()} for f,ps in BOUNDS.items() if f in set(enabled_families(cfg))},
        "effective_parameter_bounds":{f:{k:[v[0],v[1]] for k,v in effective_bounds(cfg,f).items()} for f in enabled_families(cfg)},
        "model_training_method_contract":training_method_context(),
        "owner_family_size_priorities":configured_family_size_priorities(cfg),
        "creativity_profile":context.get("creativity_profile") or adaptive_creativity_profile(cfg,failure_topology=context.get("failure_topology") or {}),
        "factory_context":context.get("factory_context") or {},
        "cpcv_seed_policy":context.get("seed_policy") or {},
        "feedback_exposure":int(context.get("feedback_exposure",0) or 0),
        "feedback_learning_allowed":bool(learning_allowed and failed),
        "request":"Explain what the committed evidence means using OBSERVATION -> HYPOTHESIS -> EXPERIMENT -> FALSIFICATION -> CONCLUSION. If learning is allowed and the stage failed, create a bounded next-Discovery thesis without changing KPI thresholds. Never state a causal hypothesis as an observation."
    }
    _phase="FAILURE_LEARNING" if (learning_allowed and failed) else "STAGE_FORENSIC"
    txt=_invoke_call_with_phase_compat(self,[{"role":"system","content":system},{"role":"user","content":json.dumps(user,separators=(",",":"),default=str)}], temperature=phase_temperature(cfg,_phase,user.get("creativity_profile")), phase=_phase)
    obj, _format_recovery = _extract_json_with_bounded_format_repair(self, txt, phase=_phase)
    out=_clean_director_response(obj,cfg)
    out["response_format_recovery"]=_format_recovery
    if learning_allowed and failed:
        seed_h=seed_stability_hypothesis_from_topology(context.get("failure_topology") or {},cfg)
        if seed_h is not None and not any(str((h or {}).get("kind") or "").upper()=="SEED_STABILITY" for h in (out.get("hypotheses") or [])):
            out.setdefault("hypotheses",[]).append(seed_h)
    plan=obj.get("next_discovery_plan") if isinstance(obj.get("next_discovery_plan"),dict) else {}
    topo=context.get("failure_topology") if isinstance(context.get("failure_topology"),dict) else {}
    evidence=context.get("stage_evidence") if isinstance(context.get("stage_evidence"),dict) else {}
    det_bits=[f"{stage} status={status}"]
    if evidence.get("evaluated") is not None: det_bits.append(f"evaluated={int(evidence.get('evaluated') or 0)}")
    if topo.get("dominant_first_failed_gate"): det_bits.append(f"dominant_first_failed_gate={topo.get('dominant_first_failed_gate')}")
    wc=topo.get("worst_split_combination") if isinstance(topo.get("worst_split_combination"),dict) else {}
    if wc.get("test_groups") is not None: det_bits.append(f"worst_split={wc.get('test_groups')}")
    sm_raw=obj.get("scientific_method") if isinstance(obj.get("scientific_method"),dict) else {}
    scientific_method={
        "observation":"; ".join(det_bits)[:1200],
        "hypothesis":str(sm_raw.get("hypothesis") or (out.get("report") or {}).get("interpretation") or "Belum ada hipotesis kausal yang sah.")[:1200],
        "experiment":str(sm_raw.get("experiment") or plan.get("objective") or "REPORT_ONLY")[:1200],
        "falsification":str(sm_raw.get("falsification") or plan.get("falsification") or "Belum didefinisikan")[:1200],
        "conclusion":("PENDING_DECISIVE_EXPERIMENT" if (learning_allowed and failed) else str(sm_raw.get("conclusion") or "REPORT_ONLY_NO_CAUSAL_CLAIM")[:1200]),
        "observation_authority":"DETERMINISTIC_ENGINE",
        "hypothesis_authority":"ADVISORY_LLM",
    }
    out["scientific_method"]=scientific_method
    clean_plan={}
    for key,limit in (("objective",500),("falsification",500),("do_not_do",500)):
        if plan.get(key): clean_plan[key]=str(plan.get(key))[:limit]
    for key in ("freeze","change"):
        vals=plan.get(key) or []
        if isinstance(vals,str): vals=[vals]
        clean_plan[key]=[str(x)[:240] for x in vals[:12]] if isinstance(vals,list) else []
    out["next_discovery_plan"]=clean_plan
    out["stage"]=stage; out["status"]=status; out["research_feedback_allowed"]=bool(learning_allowed and failed)
    if not (learning_allowed and failed):
        out["hypotheses"]=[]
        out["strategy"]={}
    return self._with_provenance(out)

LLMScientist.stage_review = _stage_review
