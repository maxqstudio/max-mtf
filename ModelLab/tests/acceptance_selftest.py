from __future__ import annotations

import json
import tempfile
import numpy as np
import pandas as pd
from copy import deepcopy
from pathlib import Path

from factory.governance import assess_promotion, save_evidence
from research.kpi import locked_test_acceptance, shadow_acceptance, walk_forward_acceptance, walk_forward_composite_score
from research.policy_discovery import policy_actions, write_policy_csv, discover_policy, POLICY_SCHEMA
from host.preflight import list_runs, period_label
from host.workflow_router import route_for_manifest, route_steps
from models.models import CandidateSpec
from factory.supervisor_agent import run_post_locked_policy_discovery, validate_frozen_policy_on_fresh_data, validate_frozen_model_on_fresh_data, _holdout_key

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text(encoding="utf-8"))


def require(cond: bool, name: str):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def good_cv():
    return {
        "total_validation_trades": 450,
        "total_validation_r": 126.0,
        "overall_expectancy_r": 0.28,
        "median_profit_factor": 1.55,
        "median_expectancy_r": 0.28,
        "worst_expectancy_r": 0.12,
        "positive_fold_ratio": 1.0,
        "median_max_drawdown_r": 8.0,
        "worst_fold_max_drawdown_r": 11.0,
        "median_recovery_factor": 3.4,
        "worst_fold_recovery_factor": 1.6,
        "median_positive_month_ratio": 0.70,
        "median_positive_quarter_ratio": 0.75,
        "median_regime_concentration": 0.60,
        "median_top10_win_profit_share": 0.35,
        "median_stress_x1_25_expectancy_r": 0.22,
        "median_stress_x1_50_expectancy_r": 0.16,
        "median_threshold_plateau": 1.0,
        "median_sharpe_ratio": 0.40,
        "median_sortino_ratio": 0.55,
        "median_calmar_mar_ratio": 1.50,
        "median_probabilistic_sharpe_ratio": 0.98,
        "median_deflated_sharpe_ratio": 0.97,
        "median_ulcer_index_r": 3.0,
        "median_daily_cvar95_r": -1.5,
        "selection_score": 1.0,
        "name": "synthetic_good",
        "family": "xgboost",
        "take_threshold": 0.55,
    }

def good_report():
    return {
        "schema": "KPI_V5_HIERARCHICAL",
        "profile": "SURVIVAL_H1_V1",
        "locked_test": {
            "trades": 180,
            "profit_factor": 1.65,
            "expectancy_r": 0.62,
            "max_drawdown_r": 10.0,
            "total_r": 42.0,
            "recovery_factor": 4.2,
            "win_rate": 0.57,
            "payoff_ratio": 1.40,
            "median_trade_r": 0.20,
            "max_losing_streak": 5,
            "max_underwater_trades": 28,
            "cvar95_r": -1.0,
            "daily_cvar95_r": -1.5,
            "sharpe_ratio": 0.40,
            "sortino_ratio": 0.55,
            "calmar_mar_ratio": 1.50,
            "probabilistic_sharpe_ratio": 0.98,
            "deflated_sharpe_ratio": 0.97,
            "ulcer_index_r": 3.0,
            "top10_win_profit_share": 0.40,
            "active_trade_days": 80,
            "daily_tail_sample_count": 4,
            "sample_years": 1.0,
        },
        "temporal_stability": {"positive_month_ratio": 0.65, "positive_quarter_ratio": 0.75},
        "regime": {"dominant_positive_regime_share": 0.60},
        "classification": {"brier_score": 0.45, "expected_calibration_error": 0.08},
        "stress": {
            "spread": {
                "spread_x1.25": {"expectancy_r": 0.30},
                "spread_x1.50": {"expectancy_r": 0.16},
            },
            "profitable_threshold_variant_ratio": 1.0,
        },
        "onnx_parity": {"max_abs_error": 1e-6},
    }


def main():
    a = CFG["acceptance"]
    require(a["min_profit_factor"] == 1.35, "H1 locked PF = 1.35")
    require(a["min_expectancy_r"] == 0.15, "H1 locked expectancy = 0.15R")
    require(a["max_drawdown_r"] == 12.0, "H1 locked max DD = 12R")
    require(a["min_recovery_factor"] == 2.0, "H1 locked recovery = 2.00")
    require(a["cv_min_median_profit_factor"] == 1.25, "H1 CV PF = 1.25")
    require(a["stress_min_expectancy_r"]["spread_x1.50"] == 0.05, "H1 spread x1.50 stress expectancy = 0.05R")
    require(CFG["models"]["xgboost"] is False and CFG["models"]["lightgbm"] is False and CFG["models"]["random_forest"] is False and CFG["models"].get("gru") is False and CFG["models"].get("hybrid_xgboost") is True and CFG["models"].get("hybrid_lightgbm") is True and CFG["models"].get("hybrid_random_forest") is False, "default research activates only GRU→XGBoost / GRU→LightGBM while standalone and RF families remain dormant")
    require(CFG["agent"]["policy_discovery"]["enabled"] is True, "bounded OOF Policy Discovery enabled")
    require(CFG["agent"]["policy_discovery"]["max_policies"] == 72, "default policy budget = 72")
    require("TRANSITION" in CFG["agent"]["policy_discovery"]["regime_modes"], "Policy Discovery includes TRANSITION regime")

    scored_cv = {
        **good_cv(),
        "folds": 3, "total_validation_r": 95.0,
        "expectancy_std_r": 0.08, "profit_factor_std": 0.12,
        "median_win_rate": 0.56, "median_payoff_ratio": 1.35, "median_trade_r": 0.18,
        "median_cvar95_r": -0.8, "median_max_losing_streak": 5, "median_max_underwater_trades": 24,
        "mean_balanced_accuracy": 0.45, "mean_macro_f1": 0.44, "mean_log_loss": 0.95,
        "mean_brier_score": 0.55, "mean_expected_calibration_error": 0.07,
    }
    score = walk_forward_composite_score(scored_cv, CFG)
    require(score["schema"] == "CV_SCORE_V5_FIXED_100", "survival-first walk-forward score schema active")
    require(abs(sum(float(x["weight"]) for x in score["components"]) - 100.0) < 1e-9, "score component weights sum to 100")
    weights={x["name"]:float(x["weight"]) for x in score["components"]}
    require(weights["CV_MEDIAN_MAX_DD"] + weights["CV_WORST_FOLD_MAX_DD"] > weights["CV_MEDIAN_RECOVERY"] + weights["CV_WORST_FOLD_RECOVERY"] > weights["CV_MEDIAN_PF"], "score priority is DD > Recovery > PF")
    require(walk_forward_acceptance(scored_cv, CFG)["passed"], "comprehensive good CV passes every mandatory group")

    unsafe=deepcopy(scored_cv); unsafe.update({"median_profit_factor":3.0,"median_expectancy_r":0.8,"worst_expectancy_r":0.5,"median_max_drawdown_r":25.0,"worst_fold_max_drawdown_r":35.0,"median_recovery_factor":0.6,"worst_fold_recovery_factor":0.2})
    unsafe_acc=walk_forward_acceptance(unsafe,CFG)
    require(not unsafe_acc["passed"] and unsafe_acc.get("first_failed_gate")=="CV_MEDIAN_MAX_DD", "huge PF cannot compensate failed DD/Recovery authority")
    worstfold=deepcopy(scored_cv); worstfold["worst_fold_max_drawdown_r"]=19.0
    require(not walk_forward_acceptance(worstfold,CFG)["passed"], "bad worst-fold DD fails even when median DD is good")
    stressbad=deepcopy(scored_cv); stressbad["median_stress_x1_50_expectancy_r"]=-0.01
    require(not walk_forward_acceptance(stressbad,CFG)["passed"], "stress robustness is mandatory, not a score decoration")
    timebad=deepcopy(scored_cv); timebad["median_positive_month_ratio"]=0.40
    require(not walk_forward_acceptance(timebad,CFG)["passed"], "time/regime robustness is mandatory")
    overallbad=deepcopy(scored_cv); overallbad["overall_expectancy_r"]=0.05
    oa=walk_forward_acceptance(overallbad,CFG)
    require(not oa["passed"] and "CV_OVERALL_EXPECTANCY" in oa["reasons"], "Overall OOF Mean R is an independent mandatory gate")

    app_src=(ROOT/"ui/app.py").read_text(encoding="utf-8")
    require("st.json(" not in app_src, "operator UI renders no raw JSON widgets")
    require(".block-container{max-width:none!important;width:100%!important" in app_src and "margin-left:{main_left}" in app_src and "margin-right:{main_right}" in app_src, "workspace expands within the single-authority left/right shell margins")
    require("KPI & Evaluation" in app_src and "Each gate owns one independent profile." in app_src and "advanced_gate_kpi_selected" not in app_src, "per-gate KPI UI is one coherent vertical authority")
    require('pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]' in app_src and 'if page=="Research": _render_research_stage(cfg)' in app_src and 'elif page=="Monte Carlo": _render_monte_carlo_stage(cfg)' in app_src and 'elif page=="Forward Championship": _render_forward_stage(cfg)' in app_src, "Research Control Room wires Tournament survivors → Monte Carlo → Forward Championship while stage pages remain inspectors")
    require("Kembali ke source run" not in app_src, "ghost source-run redirect removed from operator route")
    require("Install Challenger shadow" in app_src and 'if status=="ELIGIBLE_CHALLENGER"' in app_src, "shadow install is hidden unless candidate is eligible")

    cv = good_cv()
    require(walk_forward_acceptance(cv, CFG)["passed"], "good CV passes current policy")
    report = good_report()
    require(locked_test_acceptance(report, CFG)["passed"], "rich locked-test KPI passes")
    bad = deepcopy(report); bad["temporal_stability"]["positive_month_ratio"] = 0.25
    acc_bad = locked_test_acceptance(bad, CFG)
    require(not acc_bad["passed"] and "TEST_POSITIVE_MONTH_RATIO" in acc_bad["reasons"], "rich temporal KPI fails closed")

    shadow = {"trades": 150, "profit_factor": 1.6, "expectancy_r": 0.6, "max_drawdown_r": 10.0, "total_r": 35.0, "recovery_factor": 3.5,
              "sharpe_ratio":0.40,"sortino_ratio":0.55,"calmar_mar_ratio":1.50,"probabilistic_sharpe_ratio":0.98,"deflated_sharpe_ratio":0.97,"ulcer_index_r":3.0,"daily_cvar95_r":-1.5,
              "active_trade_days":80,"daily_tail_sample_count":4,"sample_years":1.0}
    require(shadow_acceptance(shadow, CFG)["passed"], "strict shadow KPI passes")

    # CP_POLICY_V1 must be a bounded selectivity layer, not an alternate risk engine.
    n=1200; rng=np.random.default_rng(42)
    synth=pd.DataFrame({f:rng.normal(size=n) for f in __import__('contract').FEATURES})
    synth['consensus']=0.8; synth['spread_points']=10.0; synth['range_atr']=1.2; synth['atr']=1.0; synth['decision_bid']=100.0; synth['decision_ask']=100.1
    synth['long_r']=np.where(synth['ret1_atr']>0,1.5,-1.0); synth['short_r']=np.where(synth['ret1_atr']<0,1.5,-1.0)
    synth['signal_time']=pd.date_range('2020-01-01',periods=n,freq='h')
    synth['label']=np.where(synth['ret1_atr']>0.35,2,np.where(synth['ret1_atr']<-0.35,0,1))
    probs=np.full((n,3),0.1,dtype=float); probs[:,1]=0.2; probs[:,2]=np.where(synth['ret1_atr']>0,0.7,0.1); probs[:,0]=np.where(synth['ret1_atr']<0,0.7,0.1); probs=probs/probs.sum(axis=1,keepdims=True)
    pol={'schema':POLICY_SCHEMA,'take_threshold':0.65,'buy_threshold':0.55,'sell_threshold':0.55,'directional_margin':0.2,'max_entropy':1.0,'regime_mode':'NON_SHOCK'}
    act=policy_actions(probs,synth,CFG,pol)
    require(np.any(act!=0) and np.all(np.isin(act,[-1,0,1])), "CP_POLICY_V1 produces bounded SELL/SKIP/BUY actions")
    pol_transition=dict(pol); pol_transition["regime_mode"]="TRANSITION"
    act_transition=policy_actions(probs,synth,CFG,pol_transition)
    require(np.all(np.isin(act_transition,[-1,0,1])), "TRANSITION regime policy is executable")
    with tempfile.TemporaryDirectory() as ptd:
        pp=write_policy_csv(Path(ptd)/'challenger_policy.csv',pol)
        require(pp.exists() and 'CP_POLICY_V1' in pp.read_text(), "decision policy CSV artifact is machine-readable")

    # Real tiny XGBoost OOF run: proves Policy Discovery trains only on upstream folds and produces scored policies.
    pd_cfg=deepcopy(CFG); pd_cfg['cpu_threads']=2; pd_cfg['agent']['policy_discovery']['max_policies']=12; pd_cfg['split']['min_train_rows']=200; pd_cfg['strategy_geometry']={'sl_atr':1.8,'tp_atr':2.7,'max_hold_bars':24}
    spec=CandidateSpec('xgboost','policy_smoke',{'n_estimators':60,'max_depth':2,'learning_rate':0.05,'min_child_weight':5.0,'subsample':0.8,'colsample_bytree':0.8})
    pd_result=discover_policy(spec,synth,pd_cfg,0.65)
    require(pd_result['oof_folds']==pd_cfg['split']['walk_forward_folds'], "Policy Discovery uses walk-forward OOF folds")
    require(len(pd_result['board'])==12 and pd_result['winner'] is not None, "bounded policy search returns ranked frontier")
    require(len(pd_result['winner']['score_breakdown'])>=24 and pd_result['winner'].get('score_schema')=='CV_SCORE_V5_FIXED_100', "Policy Discovery uses comprehensive survival-first KPI score")

    # New guided recovery paths must fail closed before touching data when authority is invalid.
    with tempfile.TemporaryDirectory() as td_recovery:
        base=Path(td_recovery); bad_source=base/'bad_source'; bad_source.mkdir()
        (bad_source/'model_manifest.json').write_text(json.dumps({'run_id':'BAD','status':'REJECTED','cv_acceptance':{'passed':False}}),encoding='utf-8')
        try:
            run_post_locked_policy_discovery(bad_source, base/'missing.csv', ROOT/'config/config.json', base/'runs')
            raise AssertionError('post-locked recovery accepted CV-failed source')
        except ValueError as e:
            require('CV-nya PASS' in str(e), 'post-locked Policy Discovery rejects invalid source before data access')
        bad_policy=base/'bad_policy'; bad_policy.mkdir()
        (bad_policy/'model_manifest.json').write_text(json.dumps({'run_id':'BADP','status':'POLICY_CV_REJECTED'}),encoding='utf-8')
        try:
            validate_frozen_policy_on_fresh_data(bad_policy, base/'missing.csv', ROOT/'config/config.json', base/'runs')
            raise AssertionError('fresh validation accepted non-passing policy run')
        except ValueError as e:
            require('belum memiliki frozen policy' in str(e), 'fresh-holdout validation rejects non-passing policy run before data access')

    # Legacy workflow router remains internal audit authority; v0.7.0 no longer exposes it as parallel top-level navigation.
    require(period_label(16385)=="H1", "MT5 enum PERIOD_H1=16385 renders as H1")
    r=route_for_manifest({"status":"POLICY_CV_REJECTED"})
    require(r["action"]=="RUN_FEATURE_LABEL_AUDIT", "Policy CV rejection routes to executable Feature+Label Audit")
    r=route_for_manifest({"status":"FEATURE_LABEL_AUDIT_READY"})
    require(r["action"]=="OPEN_GUIDED_RESEARCH", "Audit-ready lineage retains internal Guided Research action")
    r=route_for_manifest({"status":"GUIDED_RESEARCH_READY"})
    require(r["action"]=="START_NEW_GENERATION", "Guided PASS routes to new-generation research")
    app_text=(ROOT/"ui/app.py").read_text(encoding="utf-8")
    require('pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]' in app_text, "top-level navigation exposes Research Control Room and current Champion Factory stage inspectors")
    require('Legacy diagnostics' in app_text and 'Guided Research' in app_text, "Guided/legacy authority remains available under Advanced diagnostics")
    require('research_tab, runs_tab' not in app_text, "legacy tab navigation removed")
    require('RUN FEATURE + LABEL AUDIT' in app_text and 'RUN BOUNDED GUIDED RESEARCH' in app_text and 'START NEW GENERATION RESEARCH' in app_text, "audit → guided → new-generation actions are executable in UI")

    # Run discovery must include every lineage type; no hidden POLICY/FRESH descendants.
    with tempfile.TemporaryDirectory() as td_runs:
        rr=Path(td_runs)
        for name in ["AGENT_20260909_000001_UTC","POLICY_20260909_000002_UTC","AUDIT_20260909_000003_UTC","GUIDED_20260909_000004_UTC","FRESH_20260909_000005_UTC"]:
            d=rr/name; d.mkdir(); (d/"model_manifest.json").write_text(json.dumps({"run_id":name,"status":"X"}),encoding="utf-8")
        found={x.name for x in list_runs(rr)}
        require(found=={"AGENT_20260909_000001_UTC","POLICY_20260909_000002_UTC","AUDIT_20260909_000003_UTC","GUIDED_20260909_000004_UTC","FRESH_20260909_000005_UTC"}, "pipeline discovers AGENT + POLICY + AUDIT + GUIDED + FRESH lineages")

    # Same file hash must never collapse M15 and H1 identities in the new holdout key.
    key_m15=_holdout_key("abc",CFG,{"symbol":"EURUSD.m","period":15,"source_start":"2020-01-01","source_end":"2024-01-01"})
    key_h1=_holdout_key("abc",CFG,{"symbol":"EURUSD.m","period":60,"source_start":"2020-01-01","source_end":"2024-01-01"})
    require(key_m15!=key_h1, "holdout identity separates M15 and H1 even with same legacy hash")

    # NEEDS_FRESH_HOLDOUT route must fail closed before data access when source status is wrong.
    with tempfile.TemporaryDirectory() as td_model:
        base=Path(td_model); bad=base/'bad'; bad.mkdir(); (bad/'model_manifest.json').write_text(json.dumps({'run_id':'BAD','status':'REJECTED','cv_acceptance':{'passed':True}}),encoding='utf-8')
        try:
            validate_frozen_model_on_fresh_data(bad,base/'missing.csv',ROOT/'config/config.json',base/'runs')
            raise AssertionError('fresh model validation accepted wrong source state')
        except ValueError as e:
            require('NEEDS_FRESH_HOLDOUT' in str(e), 'fresh-model validation requires exact legal source state')

    with tempfile.TemporaryDirectory() as td:
        base = Path(td); run = base / "run"; app = base / "app"; run.mkdir(); (app / "governance").mkdir(parents=True)
        manifest = {
            "run_id": "TEST_RUN",
            "status": "ELIGIBLE_CHALLENGER",
            "model_name": "synthetic_good",
            "model_family": "xgboost",
            "take_threshold": 0.55,
            "cv_selection": cv,
            "kpi_report": report,
            "locked_test_trading": report["locked_test"],
        }
        (run / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (run / "kpi_report.json").write_text(json.dumps(report), encoding="utf-8")
        (run / "challenger.onnx").write_bytes(b"selftest")
        save_evidence(run, {
            "mt5_parity": {"status": "PASS", "rows": 1000, "max_abs_error": 1e-6},
            "strategy_tester": {"status": "PASS"},
            "shadow_forward": {"status": "PASS", **shadow},
        })
        state = assess_promotion(run, CFG, app)
        require(state["promotion_ready"], "promotion uses rich/current KPI and reaches READY")
        snap = json.loads((run / "promotion_kpi_assessment.json").read_text())
        require(snap["historical_current_policy_pass"], "promotion snapshot revalidates historical KPI")
        require(snap["shadow_current_policy_pass"], "promotion snapshot calculates shadow KPI")

        # Policy-aware Challenger must carry its exact deployable policy artifact into promotion.
        manifest_policy=deepcopy(manifest); manifest_policy['policy_schema']='CP_POLICY_V1'; manifest_policy['decision_policy']=pol
        (run / 'model_manifest.json').write_text(json.dumps(manifest_policy),encoding='utf-8')
        missing_policy_state=assess_promotion(run,CFG,app)
        require(not missing_policy_state['promotion_ready'] and any(g['name']=='DECISION_POLICY_ARTIFACT' and not g['passed'] for g in missing_policy_state['gates']), "promotion fails closed when CP_POLICY_V1 artifact is missing")
        write_policy_csv(run/'challenger_policy.csv',pol)
        require(assess_promotion(run,CFG,app)['promotion_ready'], "promotion accepts exact CP_POLICY_V1 artifact when all other gates pass")
        (run / 'model_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')

        stricter = deepcopy(CFG); stricter["acceptance"]["min_profit_factor"] = 2.0
        state2 = assess_promotion(run, stricter, app)
        require(not state2["promotion_ready"], "policy tightened after run invalidates stale historical PASS")
        require(any(g["name"] == "HISTORICAL_LOCKED_KPI_CURRENT_POLICY" and not g["passed"] for g in state2["gates"]), "first-class current-policy historical gate present")

        # Same-window Champion-relative authority: promotion must calculate it, not
        # merely display the values in UI.
        champ = {"champion_id":"OLD","model_name":"old","model_family":"xgboost"}
        (app / "governance" / "champion_registry.json").write_text(json.dumps({"current":champ,"history":[]}), encoding="utf-8")
        ev = {
            "mt5_parity": {"status": "PASS", "rows": 1000, "max_abs_error": 1e-6},
            "strategy_tester": {"status": "PASS"},
            "shadow_forward": {"status": "PASS", **shadow, "champion": {"profit_factor":1.55,"expectancy_r":0.55,"max_drawdown_r":12.0,"total_r":33.0,"recovery_factor":2.75}},
        }
        save_evidence(run, ev)
        state3 = assess_promotion(run, CFG, app)
        require(state3["promotion_ready"], "Champion-relative KPI is calculated in promotion authority")
        require(bool(state3.get("champion_relative",{}).get("passed")), "same-window Champion relative gate passes")
        ev["shadow_forward"]["champion"] = {"profit_factor":2.2,"expectancy_r":0.9,"max_drawdown_r":5.0,"total_r":40.0,"recovery_factor":8.0}
        save_evidence(run, ev)
        state4 = assess_promotion(run, CFG, app)
        require(not state4["promotion_ready"], "materially inferior Challenger fails Champion-relative gate")

    print("\nALL ACCEPTANCE SELF-TESTS PASS")


if __name__ == "__main__":
    evidence_path = ROOT / "evidence/history/CUMULATIVE_ACCEPTANCE_v0_7_1.json"
    try:
        main()
        evidence_path.write_text(json.dumps({
            "version":"0.7.1",
            "overall_status":"PASS",
            "first_failed_gate":None,
            "scope":[
                "hierarchical survival-first KPI authority", "DD > Recovery > PF ranking", "all mandatory robustness/stress gates",
                "grouped compact UI", "simplified Champion Factory navigation", "legacy workflow internal-only", "MT5 H1 enum provenance",
                "Feature+Label Audit", "bounded Guided Research", "new-generation skip-retired-holdout route", "cross-timeframe holdout identity",
                "post-locked OOF Policy Discovery", "fresh-model/fresh-policy holdout routes", "CP_POLICY_V1 deployment artifact", "promotion governance regression"
            ]
        }, indent=2), encoding="utf-8")
    except Exception as exc:
        evidence_path.write_text(json.dumps({
            "version":"0.7.1",
            "overall_status":"FAIL",
            "first_failed_gate":str(exc),
        }, indent=2), encoding="utf-8")
        raise
