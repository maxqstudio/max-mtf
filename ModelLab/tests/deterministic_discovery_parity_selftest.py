from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import effective_bounds, family_spec, is_hybrid_family
from models.models import CandidateSpec, spec_fingerprint, validate_candidate, candidate_capacity_contract
from research.research_architect import capability_catalog, compile_research_plan
from research.research_engine_v3 import select_full_wfa_promotions
from research.research_planner import family_stats, adaptive_family_weights, plan_next_candidates
from research.risk_kpi import dsr_trial_count
from research.kpi import walk_forward_composite_score
from models.topology_allocation import enforce_item_allocation

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def fake_profile():
    return {
        'profile_hash':'R4_FAKE_RTX8',
        'cpu':{'name':'test','physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'detected':True,'devices':[{'name':'RTX','memory_total_gib':8.0,'memory_free_gib':7.0}]},
        'torch':{'installed':True,'cuda_available':True},
    }


def main():
    cfg=deepcopy(BASE)
    plan=compile_research_plan({},fake_profile(),cfg)
    catalog=capability_catalog(fake_profile(),cfg)
    eligible={f for f,r in catalog['families'].items() if r.get('eligible')}
    active=set(plan['active_families'])
    req(eligible.issubset({f for f in active if not is_hybrid_family(f)}),'deterministic fallback exposes every eligible base family, not a hard-coded shortlist')
    req({'patchtst','itransformer','tft','transformer_moe'}.intersection(active),'modern Transformer families remain reachable without LLM Scientist')

    cfg2=deepcopy(BASE)
    cfg2.setdefault('agent',{})['research_plan']={
        'active_families':['lightgbm','xgboost','tcn','patchtst','itransformer','tft','hybrid::tcn::lightgbm','hybrid::patchtst::lightgbm','hybrid::itransformer::xgboost','hybrid::tft::xgboost'],
        'topology_priority':{'single':0.5,'hybrid':0.5},
    }
    specs,meta=plan_next_candidates([],{},cfg2,1,12,{})
    req(meta.get('phase')=='STRATIFIED_INITIAL_DISCOVERY','round-1 Discovery uses stratified/space-filling path by default')
    req(len(specs)==12,'stratified initial Discovery preserves requested budget')

    screen=[]
    fams=['lightgbm','xgboost','tcn','patchtst','hybrid::tcn::lightgbm','hybrid::patchtst::lightgbm','hybrid::itransformer::xgboost','hybrid::tft::xgboost']
    for i,f in enumerate(fams):
        screen.append({'family':f,'name':f's{i}','original_name':f's{i}','cv_gate_pass':True,'selection_score':100-i})
    pcfg=deepcopy(cfg2)
    pcfg['agent']['fidelity_ladder']['min_promote_per_round']=4
    pcfg['agent']['fidelity_ladder']['max_promote_per_round']=4
    pcfg['agent']['fidelity_ladder']['promote_fraction']=0.5
    promoted=select_full_wfa_promotions(screen,pcfg)
    rows=[r for r in screen if r['original_name'] in promoted]
    hy=sum(is_hybrid_family(r['family']) for r in rows)
    req(len(rows)==4 and hy==2,'cheap-screen promotion preserves 50/50 Single↔Hybrid authority into Full-WFA opportunity')
    req(len({r['family'] for r in rows})==4,'cheap-screen promotion prefers family coverage before duplicate-family promotion')

    only_hy=[CandidateSpec('hybrid::tcn::lightgbm',f'h{i}',{}) for i in range(5)]
    admitted,adm=enforce_item_allocation(only_hy,0.5,target_total=5,available_families=['tcn','lightgbm','hybrid::tcn::lightgbm'])
    req(len(admitted)==3 and adm['missing_slots']==2,'LLM proposal batch cannot redefine 50/50 authority by omitting Single proposals')

    # Effective-parameter identity: shadow knobs must not create fake novelty.
    a=CandidateSpec('transformer','a',{'d_model':64,'hidden_size':32,'attention_heads':4})
    b=CandidateSpec('transformer','b',{'d_model':64,'hidden_size':256,'attention_heads':4})
    req(spec_fingerprint(a)==spec_fingerprint(b),'Transformer hidden_size shadow knob is removed from effective experiment identity')
    ta=CandidateSpec('tcn','ta',{'tcn_channels':64,'hidden_size':16})
    tb=CandidateSpec('tcn','tb',{'tcn_channels':64,'hidden_size':256})
    req(spec_fingerprint(ta)==spec_fingerprint(tb),'TCN hidden_size shadow knob is removed when tcn_channels is authoritative')

    wb=effective_bounds(BASE,'lightgbm')['training_memory_months']
    req(int(wb[0])>=int(BASE['agent']['window_discovery']['min_months']) and int(wb[1])<=int(BASE['agent']['window_discovery']['max_months']),'window_discovery config now executes as training-memory bound authority')

    # Hard capacity compiler: a deliberately tiny extended ceiling must reject a legal-but-oversized Transformer.
    capcfg=deepcopy(BASE)
    capcfg.setdefault('agent',{})['research_plan']={
        'active_families':['transformer'],
        'capacity_guidance':{'preferred_total_params':[100,500],'extended_total_params':[100,1000]},
    }
    raw={'family':'transformer','name':'oversize','params':{
        'sequence_length':64,'d_model':64,'num_layers':2,'attention_heads':4,'ffn_mult':4,'dropout':0.1,
        'learning_rate':0.001,'batch_size':32,'epochs':10,'weight_decay':0.001,'training_memory_months':18,
    }}
    req(validate_candidate(raw,capcfg,1) is None,'actual neural parameter count above extended capacity is rejected before training')

    # Family allocation must prefer repeatability over a single lucky outlier.
    statcfg=deepcopy(BASE)
    statcfg.setdefault('agent',{})['research_plan']={'active_families':['lightgbm','xgboost']}
    board=[]
    for i,score in enumerate([20,-8,-7,-6]):
        board.append({'family':'lightgbm','name':f'a{i}','selection_score':score,'cv_gate_pass':False,'median_profit_factor':1.0,'median_expectancy_r':0.0,'median_recovery_factor':1.0,'positive_fold_ratio':0.3,'expectancy_std_r':1.0,'total_fit_seconds':1.0})
    for i,score in enumerate([6,6,5,6]):
        board.append({'family':'xgboost','name':f'b{i}','selection_score':score,'cv_gate_pass':True,'median_profit_factor':1.4,'median_expectancy_r':0.2,'median_recovery_factor':2.0,'positive_fold_ratio':0.8,'expectancy_std_r':0.1,'total_fit_seconds':1.0})
    w=adaptive_family_weights(board,statcfg,{})
    req(w['xgboost']>w['lightgbm'],'family allocation rewards robust median/P25/PASS-rate evidence over one lucky best run')

    sample={
        'median_max_drawdown_r':5,'worst_fold_max_drawdown_r':8,'median_recovery_factor':2,'worst_fold_recovery_factor':1.5,
        'median_profit_factor':1.5,'median_expectancy_r':0.2,'worst_expectancy_r':0.05,'total_validation_trades':200,
        'positive_fold_ratio':0.8,'expectancy_std_r':0.05,'profit_factor_std':0.1,
        'median_stress_x1_25_expectancy_r':0.15,'median_stress_x1_50_expectancy_r':0.1,'median_threshold_plateau':0.8,
        'median_positive_month_ratio':0.7,'median_positive_quarter_ratio':0.7,'median_regime_concentration':0.5,
        'median_win_rate':0.55,'median_payoff_ratio':1.2,'median_trade_r':0.05,'median_top10_win_profit_share':0.4,
        'mean_balanced_accuracy':0.4,'mean_macro_f1':0.4,'mean_log_loss':1.0,'mean_brier_score':0.5,'mean_expected_calibration_error':0.08,
        'median_sharpe_ratio':0.5,'median_sortino_ratio':0.7,'median_calmar_mar_ratio':1.5,'median_probabilistic_sharpe_ratio':0.97,
        'median_deflated_sharpe_ratio':0.96,'median_ulcer_index_r':3.0,'median_daily_cvar95_r':-1.0,
        'auto_min_validation_trades':90,
    }
    score=walk_forward_composite_score(sample,deepcopy(BASE))
    names={x['name'] for x in score['components']}
    req({'CV_SHARPE','CV_SORTINO','CV_CALMAR','CV_PSR','CV_DSR','CV_ULCER','CV_CVAR'}.issubset(names),'deterministic ranking now sees all seven active advanced risk KPI')
    req(dsr_trial_count(deepcopy(BASE))>int(BASE['champion_factory']['max_total_experiments']),'DSR trial budget includes threshold/policy selection multiplicity, not model count only')

    src=(ROOT/'models/model_lab.py').read_text(encoding='utf-8')
    req('NESTED_LEAVE_ONE_WFA_FOLD_OUT_V1' in src,'WFA threshold selection uses nested held-fold grading instead of grading the threshold on the same folds used to select it')

    print('DETERMINISTIC_DISCOVERY_PARITY_SELFTEST PASS')

if __name__=='__main__':
    main()
