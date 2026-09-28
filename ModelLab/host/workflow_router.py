from __future__ import annotations


def route_for_manifest(m: dict) -> dict:
    """Single authority for UI routing. No page decides its own next action."""
    status = str(m.get("status") or "UNKNOWN")
    rt = str(m.get("run_type") or "")
    cv_pass = bool((m.get("cv_acceptance") or {}).get("passed"))
    locked_open = bool((m.get("agent") or {}).get("locked_test_opened_once"))
    has_locked = bool(m.get("locked_test_trading") or m.get("kpi_report"))

    if status == "POLICY_CV_REJECTED":
        return {"stage":"POLICY", "page":"Pipeline", "action":"RUN_FEATURE_LABEL_AUDIT", "label":"RUN FEATURE + LABEL AUDIT", "terminal":False}
    if status == "FEATURE_LABEL_AUDIT_READY":
        return {"stage":"AUDIT", "page":"Guided Research", "action":"OPEN_GUIDED_RESEARCH", "label":"OPEN GUIDED RESEARCH", "terminal":False}
    if status == "GUIDED_RESEARCH_READY":
        return {"stage":"GUIDED", "page":"Guided Research", "action":"START_NEW_GENERATION", "label":"START NEW GENERATION RESEARCH", "terminal":False}
    if status == "GUIDED_RESEARCH_REJECTED":
        return {"stage":"GUIDED", "page":"Guided Research", "action":"STOP_NEW_HYPOTHESIS", "label":"REVIEW AUDIT · NEW HYPOTHESIS REQUIRED", "terminal":True}
    if status == "NEEDS_FRESH_HOLDOUT":
        return {"stage":"CV", "page":"Pipeline", "action":"VALIDATE_FROZEN_MODEL_FRESH", "label":"VALIDATE FROZEN MODEL · FRESH DATA", "terminal":False}
    if status == "POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT":
        return {"stage":"POLICY", "page":"Pipeline", "action":"VALIDATE_FROZEN_POLICY_FRESH", "label":"VALIDATE POLICY · FRESH DATA", "terminal":False}
    if status == "ELIGIBLE_CHALLENGER":
        return {"stage":"HOLDOUT", "page":"Champion", "action":"MT5_VALIDATION", "label":"CONTINUE TO MT5 VALIDATION", "terminal":False}
    if status == "RESEARCH_REJECTED":
        return {"stage":"CV", "page":"Pipeline", "action":"RUN_FEATURE_LABEL_AUDIT", "label":"RUN FEATURE + LABEL AUDIT", "terminal":False}
    if status == "REJECTED" and cv_pass and locked_open and has_locked and rt not in {"FRESH_HOLDOUT_VALIDATION","FRESH_MODEL_VALIDATION"}:
        return {"stage":"LOCKED", "page":"Pipeline", "action":"RUN_OOF_POLICY", "label":"RUN OOF POLICY DISCOVERY", "terminal":False}
    if status == "REJECTED":
        return {"stage":"HOLDOUT", "page":"Pipeline", "action":"RUN_FEATURE_LABEL_AUDIT", "label":"RUN FEATURE + LABEL AUDIT", "terminal":False}
    return {"stage":"RESEARCH", "page":"Research", "action":"NONE", "label":"NO AUTOMATIC ACTION", "terminal":False}


def route_steps(m: dict) -> list[tuple[str,str]]:
    r = route_for_manifest(m)
    status = str(m.get("status") or "")
    if status == "FEATURE_LABEL_AUDIT_READY":
        return [("Research","done"),("CV","done"),("Holdout/Policy","done"),("Feature+Label Audit","done"),("Guided Research","active"),("Fresh Holdout","todo"),("MT5","todo"),("Shadow","todo"),("Promotion","todo")]
    if status in {"GUIDED_RESEARCH_READY","GUIDED_RESEARCH_REJECTED"}:
        return [("Research","done"),("CV","done"),("Holdout/Policy","done"),("Feature+Label Audit","done"),("Guided Research","done" if status=="GUIDED_RESEARCH_READY" else "fail"),("New Generation","active" if status=="GUIDED_RESEARCH_READY" else "todo"),("Fresh Holdout","todo"),("MT5","todo"),("Shadow","todo"),("Promotion","todo")]
    if status == "POLICY_CV_REJECTED":
        return [("Research","done"),("CV","done"),("Retired Holdout","done"),("OOF Policy","fail"),("Feature+Label Audit","active"),("Guided Research","todo")]
    if status == "NEEDS_FRESH_HOLDOUT":
        return [("Research","done"),("CV","done"),("Fresh Holdout","active"),("MT5","todo"),("Shadow","todo"),("Promotion","todo")]
    if status == "POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT":
        return [("Research","done"),("CV","done"),("Retired Holdout","done"),("OOF Policy","done"),("Fresh Holdout","active"),("MT5","todo"),("Shadow","todo"),("Promotion","todo")]
    if status == "ELIGIBLE_CHALLENGER":
        return [("Research","done"),("CV","done"),("Holdout","done"),("MT5","active"),("Shadow","todo"),("Promotion","todo")]
    if status == "RESEARCH_REJECTED":
        return [("Research","done"),("CV","fail"),("Feature+Label Audit","active"),("Guided Research","todo")]
    if status == "REJECTED":
        if r["action"] == "RUN_OOF_POLICY":
            return [("Research","done"),("CV","done"),("Locked Holdout","fail"),("OOF Policy","active"),("Feature+Label Audit","todo")]
        return [("Research","done"),("CV","done"),("Holdout","fail"),("Feature+Label Audit","active")]
    return [("Research","active"),("CV","todo"),("Holdout","todo")]
