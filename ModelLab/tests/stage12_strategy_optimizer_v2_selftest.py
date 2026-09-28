from __future__ import annotations
import json, tempfile
from pathlib import Path
import scientist.core.scientist as scientist
from strategy.strategy_optimizer_worker import _compile_summary
from strategy.strategy_optimizer import (
    EA_SOURCE, ABSOLUTE_BOUNDS, DEFAULT_SPACE, FAMILY_WEIGHT_PARAMS, OptimizationPass,
    OPTIMIZER_PF_MIN, OPTIMIZER_RF_MIN, OPTIMIZER_EXPECTANCY_R_MIN, OPTIMIZER_H1_TRADES_PER_MONTH, optimizer_trade_sample, build_set_text, build_tester_ini,
    validate_search_space, parse_optimization_xml, select_champion, deterministic_refine,
    scientist_refine, validate_request,
)

ROOT=Path(__file__).resolve().parent.parent; PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def xml_report(path:Path):
    headers=['Pass','Result','Profit','Expected Payoff','Profit Factor','Recovery Factor','Sharpe Ratio','Custom','Trades']+list(ABSOLUTE_BOUNDS)
    rows=[]
    for pass_no,pf,rf,er in [(1,0.95,1.3,0.20),(2,1.2,1.4,0.15),(3,1.3,0.8,0.40)]:
        vals=[pass_no,er,100,10,pf,rf,0.5,er,25]
        for name,(lo,hi,step,typ) in ABSOLUTE_BOUNDS.items():
            v=(lo+hi)/2
            vals.append(int(round(v)) if typ=='int' else v)
        rows.append(vals)
    def row(vals):
        return '<Row>'+''.join(f'<Cell><Data ss:Type="String">{v}</Data></Cell>' for v in vals)+'</Row>'
    body='<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet><Table>'+row(headers)+''.join(row(r) for r in rows)+'</Table></Worksheet></Workbook>'
    path.write_text(body,encoding='utf-8')

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    ea=(PKG/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
    req('Strategy Optimizer' in app and 'render_strategy_optimizer_page' in app,'V2 optimizer is exposed in UI')
    req('pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]' in app,'Strategy Optimizer remains a separate upstream tool after Advanced; dedicated Strategy Challenger/Champion pages follow it')
    req('label:nth-of-type(12)::before' in app and 'never between Strategy Optimizer / Challengers / Champion' in app and 'label:nth-of-type(13)' in app and 'label:nth-of-type(14)' in app,'sidebar renders one separator before the Strategy section and keeps Optimizer/Challengers/Champion grouped')
    req('START AUTO OPTIMIZER' in app and 'global_optimizer_start' in app and '_render_global_optimizer_controls_body' in app,'Optimizer page owns a dedicated footer lifecycle CTA')
    req('_render_contextual_lifecycle_controls' in app and '_is_strategy_nav_page(nav_page)' in app and '_render_global_optimizer_controls_body(cfg)' in app and '_render_global_research_controls_body(cfg)' in app and 'left_footer_research_controls' not in app and 'left_footer_optimizer_controls' not in app,'single contextual footer authority prevents Research/Optimizer cross-wiring')
    req('_is_strategy_nav_page(nav_page)' in app and 'OPTIMIZER IDLE' in app and 'MT5 round' in app,'workspace status bar reports Optimizer state instead of Research state on the Optimizer page')
    req('START MT5 OPTIMIZATION' not in app,'duplicate in-page optimizer START control is removed')
    req('research_active=latest_factory_job(FACTORY_DIR,active_only=True)' in app and 'optimizer_active=bool(optimizer_job' in app,'Research and Optimizer lifecycle starts are mutually interlocked')
    req('Optimization=2' not in worker and 'run_round' in worker,'worker delegates optimization mode to native MT5 config builder')
    ini=build_tester_ini(expert='MaxResearch\\EA',set_name='x.set',symbol='XAUUSD',period='H1',from_date='2021.01.01',to_date='2024.12.31',deposit=10000,leverage=100,model=0,report_path='x',optimization=2)
    req('Optimization=2' in ini and 'OptimizationCriterion=6' in ini and 'ForwardMode=0' in ini,'native MT5 genetic + Custom max Expectancy-R fitness + no forward')
    txt=build_set_text(DEFAULT_SPACE,confirm_symbol='XAGUSD')
    req(all(f'{n}=' in txt and txt.split(f'{n}=',1)[1].splitlines()[0].endswith('||Y') for n in FAMILY_WEIGHT_PARAMS),'all seven family weights stay active and optimized')
    req('InpAllowLiveTrading=true' in txt and 'InpUseOnnxChampion=false' in txt and 'InpWriteTrainingData=false' in txt,'optimization set trades in tester with ONNX/training disabled')
    req('StrategyOptimizerSevenFamilyContract' in ea and 'double OnTester()' in ea and 'g_optimizerSumR' in ea,'EA enforces seven-family optimizer contract and realized R OnTester')
    req('InpWeightRelative<=0.0' in ea and 'StringLen(InpConfirmSymbol)==0' in ea,'EA fails closed when seventh family cannot be active')
    req(EA_SOURCE.resolve()==(PKG/'EA_v1_06'/'Max.mq5').resolve(),'Strategy Optimizer source authority is exactly the existing package EA_v1_06 file')

    boundary=OptimizationPass(round_no=1,pass_no=99,profit_factor=1.0,recovery_factor=0.0,expectancy_r=0.0,profit=0.0,trades=20,params={k:v[0] for k,v in ABSOLUTE_BOUNDS.items()},raw={},minimum_trades_required=20)
    req(boundary.passed,'Owner KPI boundaries are inclusive: PF>=1 RF>=0 ExpectancyR>=0 and trades meet frozen AUTO minimum')
    zero_trade=OptimizationPass(round_no=1,pass_no=100,profit_factor=1.0,recovery_factor=0.0,expectancy_r=0.0,profit=0.0,trades=19,params=boundary.params,raw={},minimum_trades_required=20)
    req(not zero_trade.passed,'pass below frozen AUTO minimum trades is fail-closed even at inclusive KPI boundaries')
    req((OPTIMIZER_PF_MIN,OPTIMIZER_RF_MIN,OPTIMIZER_EXPECTANCY_R_MIN,OPTIMIZER_H1_TRADES_PER_MONTH)==(1.0,0.0,0.0,20),'optimizer KPI constants match Owner lock')
    req('OptimizationCriterion=6' in ini and 'OptimizationCriterion=4' not in ini,'Recovery Factor max is not used as genetic fitness')
    req(optimizer_trade_sample('H1','2026.01.01','2026.02.01')['scaled_trades_per_month']==20 and optimizer_trade_sample('H4','2026.01.01','2026.02.01')['scaled_trades_per_month']==10 and optimizer_trade_sample('M5','2026.01.01','2026.02.01')['scaled_trades_per_month']==70,'Optimizer AUTO sample scales from H1=20 and rounds monthly rate up to integer')
    try:
        bad=dict(DEFAULT_SPACE); bad['HACK']={'start':1,'step':1,'stop':2}; validate_search_space(bad); raise AssertionError('unknown param accepted')
    except ValueError: pass
    req(True,'deterministic compiler rejects parameter injection')
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'r.xml'; xml_report(p); rows=parse_optimization_xml(p,round_no=1); ch=select_champion(rows)
        req(len(rows)==3 and ch is not None and ch.pass_no==3,'XML parser + inclusive PF/RF/Expectancy-R filter selects deterministic champion')
        ref=deterministic_refine(DEFAULT_SPACE,rows); req(set(ref)==set(DEFAULT_SPACE),'deterministic fallback preserves exact parameter universe')
    old=scientist.LLMScientist._call_with_phase
    try:
        def fake(self,messages,*,temperature,phase):
            return json.dumps({'ranges':DEFAULT_SPACE,'reason':'keep broad evidence-driven ranges'})
        scientist.LLMScientist._call_with_phase=fake
        space,meta=scientist_refine(DEFAULT_SPACE,[],{'stack':[{'provider':'x','base_url':'https://example.invalid/v1','model':'m'}]},round_no=2)
        req(space==validate_search_space(DEFAULT_SPACE) and 'llm_provenance' in meta,'Scientist proposal is advisory and deterministically compiled')
    finally: scientist.LLMScientist._call_with_phase=old
    req('walk_forward' not in worker.lower() and 'cpcv' not in worker.lower() and 'monte_carlo' not in worker.lower(),'optimizer V2 contains no ModelLab validation stages')
    req('register_optimizer_challenger' in worker and 'STRATEGY_CHALLENGER_FOUND' in worker and 'apply_champion_to_canonical_ea(ch.params)' not in worker,'eligible winner is saved as Strategy Challenger and current Max Champion remains unchanged')
    req('EVIDENCE_ROOT' in (ROOT/'strategy/strategy_optimizer.py').read_text(encoding='utf-8') and 'write_diagnostic' in worker,'runtime failures are automatically captured into a stable evidence directory')
    req('worker_stdout.log' in (ROOT/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8') and 'worker_stderr.log' in (ROOT/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8'),'worker stdout/stderr are preserved instead of discarded')
    req('Automatic diagnostic' in app and 'OPEN EVIDENCE FOLDER' in app and 'DOWNLOAD DIAGNOSTIC ZIP' in app,'failed runs surface diagnostic details, evidence folder, and one-file diagnostic bundle directly in UI')
    req('Existing EA_v1_06 · current Strategy Champion protected · optimizer winners become Challengers' in app and 'EA_v1_06/Max.mq5' in app and 'Relative reference symbol' in app,'UI exposes protected Strategy Champion and Challenger handoff semantics')
    req('Optimizer KPI' in app and 'H1 min trades / month' in app and 'Scientist Optimizer Report' in app,'Optimizer KPI and Scientist report are first-class UI sections')
    req('EA_SOURCE' in worker and 'canonical_ea_source.mq5' in worker and 'BYTE_IDENTICAL_COPY_OF_PACKAGE_EA_V1_06; NEVER_GENERATED' in worker and 'register_optimizer_challenger' in worker and 'req["ea_path"]' not in worker,'worker starts from canonical Max Champion, never accepts unrelated EA, and registers winner as Challenger')
    req('returncode_authority' in worker and 'compile summary + EX5 own PASS/FAIL' in worker,'MetaEditor process return code is diagnostic-only; compiler summary plus EX5 own compile authority')
    summary=_compile_summary("Result: 0 errors, 0 warnings, 1907 ms elapsed, cpu='X64 Regular'")
    req(summary.get('found') and summary.get('errors')==0 and summary.get('warnings')==0,'MetaEditor zero-error summary is parsed as compile success independent of CLI return code')
    req((ROOT/'strategy/strategy_optimizer_runtime_acceptance.py').exists() and (PKG/'owner_acceptance'/'runtime'/'RUN_MT5_STRATEGY_OPTIMIZER_V2_ACCEPTANCE.ps1').exists(),'one-click Owner MT5 runtime acceptance is included')
    runtime_accept=(ROOT/'strategy/strategy_optimizer_runtime_acceptance.py').read_text(encoding='utf-8')
    req("trades >= min_trades" in runtime_accept and "pf >= min_pf" in runtime_accept and "rf >= min_rf" in runtime_accept and "er >= min_er" in runtime_accept,'Owner runtime acceptance replays the frozen Optimizer KPI and AUTO minimum trades')
    print('STAGE12_STRATEGY_OPTIMIZER_V2 PASS')
if __name__=='__main__': main()
