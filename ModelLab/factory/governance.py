from __future__ import annotations
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from factory.challenger_registry import release_human_challenger_artifacts, mark_challenger_promoted

from research.kpi import (
    champion_relative_assessment,
    locked_test_acceptance,
    shadow_acceptance,
    shadow_recovery_factor,
    walk_forward_acceptance,
)


def _read_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def load_registry(app_dir: str | Path) -> dict:
    return _read_json(Path(app_dir) / "governance" / "champion_registry.json", {"current": None, "history": []})


def load_evidence(run_dir: str | Path) -> dict:
    return _read_json(Path(run_dir) / "promotion_evidence.json", {})


def save_evidence(run_dir: str | Path, evidence: dict):
    evidence = dict(evidence)
    evidence["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(Path(run_dir) / "promotion_evidence.json", evidence)
    return evidence


def _promotion_kpi_snapshot(manifest: dict, run: Path, cfg: dict, evidence: dict, current: dict | None) -> dict:
    """Re-evaluate every historical KPI against the policy active *now*.

    This closes a subtle governance hole in v0.5.7: a run that was ELIGIBLE under an
    old/looser policy could otherwise remain promotable after the operator tightened
    the Research Policy UI. Promotion authority must never trust a stale PASS label.
    """
    cv_row = manifest.get("cv_selection") or {}
    kpi_report = _read_json(run / "kpi_report.json", manifest.get("kpi_report") or {})
    cv_current = walk_forward_acceptance(cv_row, cfg) if cv_row else {
        "stage": "WALK_FORWARD", "passed": False, "reasons": ["MISSING_CV_SELECTION"], "gates": []
    }
    locked_current = locked_test_acceptance(kpi_report, cfg) if kpi_report else {
        "stage": "LOCKED_TEST", "passed": False, "reasons": ["MISSING_KPI_REPORT"], "gates": []
    }

    shadow = dict(evidence.get("shadow_forward") or {})
    shadow["recovery_factor"] = float(shadow.get("recovery_factor", shadow_recovery_factor(shadow.get("total_r", 0.0), shadow.get("max_drawdown_r", 999999.0))))
    shadow_current = shadow_acceptance(shadow, cfg)

    compare = None
    compare_pass = True
    if current:
        champion = shadow.get("champion") or {}
        if champion:
            champion = dict(champion)
            champion["recovery_factor"] = float(champion.get("recovery_factor", shadow_recovery_factor(champion.get("total_r", 0.0), champion.get("max_drawdown_r", 999999.0))))
            compare = champion_relative_assessment(shadow, champion, cfg.get("agent", {}).get("promotion", {}))
            compare_pass = bool(compare.get("passed"))
        else:
            compare_pass = False
            compare = {"passed": False, "reason": "CURRENT_CHAMPION_EXISTS_BUT_SAME_WINDOW_EVIDENCE_MISSING"}

    return {
        "schema": "PROMOTION_KPI_V5",
        "acceptance_profile": str(cfg.get("acceptance", {}).get("profile", "SURVIVAL_STRICT_V1")),
        "historical_walk_forward_current_policy": cv_current,
        "historical_locked_test_current_policy": locked_current,
        "shadow_forward_current_policy": shadow_current,
        "champion_relative_same_window": compare,
        "historical_current_policy_pass": bool(cv_current.get("passed") and locked_current.get("passed")),
        "shadow_current_policy_pass": bool(shadow_current.get("passed")),
        "champion_relative_pass": bool(compare_pass),
        "policy_revalidated_utc": datetime.now(timezone.utc).isoformat(),
    }


def assess_promotion(run_dir: str | Path, cfg: dict, app_dir: str | Path) -> dict:
    run = Path(run_dir)
    manifest = _read_json(run / "model_manifest.json", {})
    evidence = load_evidence(run)
    registry = load_registry(app_dir)
    pc = cfg.get("agent", {}).get("promotion", {})
    gates = []

    def gate(name, passed, detail):
        gates.append({"name": name, "passed": bool(passed), "detail": str(detail)})

    current = registry.get("current")
    snap = _promotion_kpi_snapshot(manifest, run, cfg, evidence, current)
    _write_json(run / "promotion_kpi_assessment.json", snap)

    manifest_eligible = manifest.get("status") == "ELIGIBLE_CHALLENGER"
    gate("HISTORICAL_ELIGIBLE_MANIFEST", manifest_eligible, manifest.get("status", "MISSING"))

    # Mandatory current-policy revalidation. A stale historical PASS cannot leapfrog
    # a policy tightened after the research run.
    cv_now = snap["historical_walk_forward_current_policy"]
    locked_now = snap["historical_locked_test_current_policy"]
    gate("HISTORICAL_CV_KPI_CURRENT_POLICY", bool(cv_now.get("passed")), ", ".join(cv_now.get("reasons") or []) or "PASS")
    gate("HISTORICAL_LOCKED_KPI_CURRENT_POLICY", bool(locked_now.get("passed")), ", ".join(locked_now.get("reasons") or []) or "PASS")

    policy_required = str(manifest.get("policy_schema") or "").upper() == "CP_POLICY_V1"
    policy_path = run / "challenger_policy.csv"
    policy_ok = (not policy_required) or policy_path.exists()
    gate("DECISION_POLICY_ARTIFACT", policy_ok, "CP_POLICY_V1 present" if policy_ok and policy_required else ("not required" if not policy_required else "challenger_policy.csv missing"))

    mt = evidence.get("mt5_parity") or {}
    mt_ok = (
        str(mt.get("status", "")).upper() == "PASS"
        and int(mt.get("rows", 0)) >= int(pc.get("min_mt5_parity_rows", 100))
        and float(mt.get("max_abs_error", 999)) <= float(pc.get("max_mt5_parity_abs_error", 1e-4))
    )
    gate("MT5_PARITY", mt_ok, f"status={mt.get('status')} rows={mt.get('rows')} err={mt.get('max_abs_error')}")

    st = evidence.get("strategy_tester") or {}
    st_ok = (str(st.get("status", "")).upper() == "PASS") if pc.get("require_strategy_tester_pass", True) else True
    gate("STRATEGY_TESTER_INTEGRATION", st_ok, str(st.get("status", "MISSING")))

    sh = dict(evidence.get("shadow_forward") or {})
    sh_total = float(sh.get("total_r", 0.0))
    sh_dd = float(sh.get("max_drawdown_r", 999999.0))
    sh_rec = float(sh.get("recovery_factor", shadow_recovery_factor(sh_total, sh_dd)))
    sh["recovery_factor"] = sh_rec
    shadow_now = snap["shadow_forward_current_policy"]
    # Evidence status remains fail-closed, but actual KPI calculations are authority.
    sh_ok = str(sh.get("status", "")).upper() == "PASS" and bool(shadow_now.get("passed"))
    shadow_fail = ", ".join(shadow_now.get("reasons") or [])
    gate(
        "SHADOW_FORWARD_KPI",
        sh_ok,
        f"status={sh.get('status')} trades={sh.get('trades')} PF={sh.get('profit_factor')} Exp={sh.get('expectancy_r')} DD={sh_dd} Recovery={sh_rec:.3f}" + (f" · fail={shadow_fail}" if shadow_fail else ""),
    )

    compare_ok = True
    compare_detail = "bootstrap: no current Champion"
    compare_assessment = snap.get("champion_relative_same_window")
    if current:
        if not compare_assessment or not bool(compare_assessment.get("passed")):
            compare_ok = False
            if compare_assessment and "deltas" in compare_assessment:
                d = compare_assessment["deltas"]
                compare_detail = (
                    f"improved {compare_assessment['improvement_count']}/{compare_assessment['min_improvements_required']} · "
                    f"PF Δ={d['profit_factor']:+.4f}, Exp Δ={d['expectancy_r']:+.4f}R, "
                    f"DD Δ={d['max_drawdown_r']:+.2f}R, Recovery Δ={d['recovery_factor']:+.3f}"
                )
            else:
                compare_detail = str((compare_assessment or {}).get("reason", "same-window Champion comparison missing"))
        else:
            d = compare_assessment["deltas"]
            compare_detail = (
                f"improved {compare_assessment['improvement_count']}/{compare_assessment['min_improvements_required']} · "
                f"PF Δ={d['profit_factor']:+.4f}, Exp Δ={d['expectancy_r']:+.4f}R, "
                f"DD Δ={d['max_drawdown_r']:+.2f}R, Recovery Δ={d['recovery_factor']:+.3f}"
            )
    gate("CHAMPION_RELATIVE", compare_ok, compare_detail)

    ready = all(g["passed"] for g in gates)
    hist_now = bool(cv_now.get("passed") and locked_now.get("passed"))
    if not manifest_eligible or not hist_now:
        stage = "RESEARCH_REJECTED_CURRENT_POLICY"
    elif not policy_ok:
        stage = "WAITING_POLICY_ARTIFACT"
    elif not mt_ok:
        stage = "WAITING_MT5_PARITY"
    elif not st_ok:
        stage = "WAITING_STRATEGY_TESTER"
    elif not sh_ok or not compare_ok:
        stage = "WAITING_SHADOW_FORWARD"
    else:
        stage = "PROMOTION_READY"

    state = {
        "stage": stage,
        "promotion_ready": ready,
        "gates": gates,
        "current_champion": current,
        "run_id": manifest.get("run_id"),
        "candidate": manifest.get("model_name"),
        "champion_relative": compare_assessment,
        "promotion_kpi_schema": "PROMOTION_KPI_V5",
        "acceptance_profile": snap["acceptance_profile"],
        "promotion_kpi_assessment_file": "promotion_kpi_assessment.json",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run / "supervisor_state.json", state)
    return state


def promote(run_dir: str | Path, terminal_files_dir: str | Path, cfg: dict, app_dir: str | Path) -> dict:
    run = Path(run_dir); app = Path(app_dir); terminal = Path(terminal_files_dir)
    state = assess_promotion(run, cfg, app)
    if not state["promotion_ready"]:
        raise RuntimeError("Supervisor promotion gates are not all PASS under current KPI policy")
    manifest = _read_json(run / "model_manifest.json", {})
    if str(manifest.get("status") or "") != "ELIGIBLE_CHALLENGER":
        raise RuntimeError("Only ELIGIBLE_CHALLENGER may be promoted")
    art = manifest.get("challenger_artifact")
    if not isinstance(art, dict):
        art = release_human_challenger_artifacts(run, manifest)
        manifest["challenger_artifact"] = art
        _write_json(run / "model_manifest.json", manifest)
    files = dict(art.get("files") or {})
    topology = str(art.get("topology") or "STANDALONE")
    challenger_id = str(art.get("challenger_id") or manifest.get("run_id") or run.name)

    source_files: dict[str, Path] = {}
    if topology == "TEMPORAL_TO_TREE_HYBRID":
        tname = files.get("temporal"); pname = files.get("policy_model")
        if not tname or not pname:
            raise RuntimeError("Hybrid Challenger artifact pair is incomplete")
        source_files["temporal"] = run / str(tname)
        source_files["policy_model"] = run / str(pname)
    else:
        sname = files.get("standalone")
        src = run / str(sname) if sname else run / "challenger.onnx"
        source_files["standalone"] = src
    for src in source_files.values():
        if not src.exists():
            raise FileNotFoundError(src)

    evidence = load_evidence(run)
    promo_kpi = _read_json(run / "promotion_kpi_assessment.json", {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    champ_id = f"CHAMPION_{stamp}"
    archive = app / "governance" / "champions" / champ_id
    archive.mkdir(parents=True, exist_ok=True)

    archived_models: dict[str, str] = {}
    if "standalone" in source_files:
        dst = archive / "champion.onnx"
        shutil.copy2(source_files["standalone"], dst); archived_models["standalone"] = str(dst)
    else:
        td = archive / "champion_temporal.onnx"; pd = archive / "champion_policy_model.onnx"
        shutil.copy2(source_files["temporal"], td); shutil.copy2(source_files["policy_model"], pd)
        archived_models.update({"temporal":str(td),"policy_model":str(pd)})

    policy_src = run / str(files.get("decision_policy")) if files.get("decision_policy") else run / "challenger_policy.csv"
    policy_required = str(manifest.get("policy_schema") or "").upper() == "CP_POLICY_V1"
    if policy_required and not policy_src.exists():
        raise FileNotFoundError(policy_src)
    if policy_src.exists():
        shutil.copy2(policy_src, archive / "champion_policy.csv")

    shutil.copy2(run / "model_manifest.json", archive / "source_model_manifest.json")
    _write_json(archive / "promotion_evidence.json", evidence)
    _write_json(archive / "promotion_kpi_assessment.json", promo_kpi)
    _write_json(archive / "promotion_policy_snapshot.json", {"acceptance": cfg.get("acceptance", {}), "promotion": cfg.get("agent", {}).get("promotion", {})})
    for name in ("kpi_report.json", "kpi_acceptance.json", "cv_acceptance.json", "onnx_preflight.json"):
        p = run / name
        if p.exists():
            shutil.copy2(p, archive / name)

    models_dir = terminal / "models"; models_dir.mkdir(parents=True, exist_ok=True)
    targets: dict[str, str] = {}; backups: dict[str, str] = {}
    deploy_map = ({"standalone":"champion.onnx"} if "standalone" in source_files else {"temporal":"champion_temporal.onnx","policy_model":"champion_policy_model.onnx"})
    for key, filename in deploy_map.items():
        target = models_dir / filename
        if target.exists():
            backup = models_dir / f"{filename}.bak_{stamp}"
            shutil.copy2(target, backup); backups[key] = str(backup)
        shutil.copy2(source_files[key], target); targets[key] = str(target)
    policy_target = None
    if policy_src.exists():
        policy_target = models_dir / "champion_policy.csv"
        shutil.copy2(policy_src, policy_target)

    locked = (manifest.get("kpi_report") or {}).get("locked_test") or manifest.get("locked_test_trading") or {}
    shadow = evidence.get("shadow_forward") or {}
    registry = load_registry(app)
    entry = {
        "champion_id": champ_id,
        "source_challenger_id": challenger_id,
        "promoted_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run),
        "model_name": manifest.get("model_name"),
        "model_family": manifest.get("model_family"),
        "topology": topology,
        "take_threshold": manifest.get("take_threshold"),
        "policy_schema": manifest.get("policy_schema"),
        "decision_policy": manifest.get("decision_policy"),
        "policy_target": str(policy_target) if policy_target else None,
        "model_targets": targets,
        "acceptance_profile": state.get("acceptance_profile"),
        "promotion_kpi_schema": state.get("promotion_kpi_schema"),
        "locked_test_kpi": {
            k: locked.get(k) for k in ("trades", "profit_factor", "expectancy_r", "max_drawdown_r", "recovery_factor", "win_rate", "payoff_ratio", "cvar95_r")
        },
        "shadow_forward_kpi": {
            k: shadow.get(k) for k in ("trades", "profit_factor", "expectancy_r", "max_drawdown_r", "total_r", "recovery_factor")
        },
        "archive": str(archive),
        "terminal_target": (targets.get("standalone") or targets.get("temporal")),
    }
    history = list(registry.get("history") or [])
    if registry.get("current"):
        history.append(registry["current"])
    registry = {"current": entry, "history": history}
    _write_json(app / "governance" / "champion_registry.json", registry)
    mark_challenger_promoted(app, challenger_id, champ_id)

    state["stage"] = "CHAMPION"; state["promotion_ready"] = False; state["champion_id"] = champ_id; state["current_champion"] = entry; state["promoted_utc"] = entry["promoted_utc"]
    _write_json(run / "supervisor_state.json", state)
    _write_json(archive / "promotion_record.json", entry)
    return {
        "champion_id": champ_id,
        "challenger_id": challenger_id,
        "target": entry["terminal_target"],
        "targets": targets,
        "backups": backups,
        "archive": str(archive),
    }
