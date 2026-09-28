from __future__ import annotations
import json
import tempfile
from pathlib import Path

import strategy.strategy_optimizer_worker as worker
import strategy.strategy_optimizer_jobs as jobs_mod
import factory.factory_jobs as factory_jobs
from strategy.strategy_optimizer import EA_SOURCE, DEFAULT_SPACE, OptimizationPass, validate_scientist_ranges, select_champion, discover_bootstrap_optimization_reports, parse_optimization_xml


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


def row(*, passed: bool, round_no: int = 1, pass_no: int = 1) -> OptimizationPass:
    params={k:v['start'] for k,v in DEFAULT_SPACE.items()}
    return OptimizationPass(
        round_no=round_no, pass_no=pass_no,
        profit_factor=1.20 if passed else 0.80,
        recovery_factor=0.50 if passed else -0.10,
        expectancy_r=0.10 if passed else -0.10,
        profit=10.0, trades=5000, params=params, raw={},
        minimum_trades_required=20,
        min_profit_factor_required=1.0,
        min_recovery_factor_required=0.0,
        min_expectancy_r_required=0.0,
    )


def frozen(scientist: bool, max_rounds: int = 3) -> dict:
    return {
        'installation': {'terminal':'terminal64.exe','metaeditor':'metaeditor64.exe','data_dir':'DATA'},
        'symbol':'EURUSD.m','confirm_symbol':'XAUUSD.m','period':'H1',
        'from_date':'2021.01.01','to_date':'2026.09.09','deposit':10000.0,'leverage':100,
        'model':1,'optimization':2,'max_rounds':max_rounds,
        'scientist_assist':scientist,
        'scientist_llm': {'enabled':True,'provider':'test','model':'test-model'} if scientist else {},
        'search_space':DEFAULT_SPACE,
        'optimize_params':['InpSL_ATR','InpTP_ATR'],
        'optimizer_kpi': {'min_profit_factor':1.0,'min_recovery_factor':0.0,'min_expectancy_r':0.0,'base_h1_trades_per_month':20},
        'optimizer_trade_sample': {'minimum_trades':20,'kpi_profile':{'min_profit_factor':1.0,'min_recovery_factor':0.0,'min_expectancy_r':0.0,'base_h1_trades_per_month':20}},
        'fixed_param_values':{}, 'ea_source':{'sha256':'frozen'},
    }


def setup_job(root: Path, jid: str, request: dict, status: str, round_no: int) -> tuple[Path,Path]:
    job=root/jid; job.mkdir(parents=True)
    (job/'request.json').write_text(json.dumps(request),encoding='utf-8')
    st={'job_id':jid,'status':status,'request':request,'frozen_config':request,'round':round_no,'first_failed_gate':None,'state_transitions':[]}
    (job/'status.json').write_text(json.dumps(st),encoding='utf-8')
    return job,job/'status.json'



def mini_report_xml(title: str, *, pass_no: int = 9182, expected_payoff: float = 0.935825, custom: float = -0.0009863807119168486, pf: float = 1.032246, rf: float = 0.506509, trades: int = 1569) -> str:
    params=''.join(f'<Cell><Data ss:Type="String">{k}</Data></Cell>' for k in DEFAULT_SPACE)
    vals=''.join(f'<Cell><Data ss:Type="Number">{v["start"]}</Data></Cell>' for v in DEFAULT_SPACE.values())
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<DocumentProperties xmlns="urn:schemas-microsoft-com:office:office"><Title>{title}</Title><Created>2099-01-01T00:00:00Z</Created></DocumentProperties>
<Worksheet ss:Name="Tester Optimizator Results"><Table>
<Row><Cell><Data ss:Type="String">Pass</Data></Cell><Cell><Data ss:Type="String">Result</Data></Cell><Cell><Data ss:Type="String">Profit</Data></Cell><Cell><Data ss:Type="String">Expected Payoff</Data></Cell><Cell><Data ss:Type="String">Profit Factor</Data></Cell><Cell><Data ss:Type="String">Recovery Factor</Data></Cell><Cell><Data ss:Type="String">Custom</Data></Cell><Cell><Data ss:Type="String">Trades</Data></Cell>{params}</Row>
<Row><Cell><Data ss:Type="Number">{pass_no}</Data></Cell><Cell><Data ss:Type="Number">{rf}</Data></Cell><Cell><Data ss:Type="Number">1468.31</Data></Cell><Cell><Data ss:Type="Number">{expected_payoff}</Data></Cell><Cell><Data ss:Type="Number">{pf}</Data></Cell><Cell><Data ss:Type="Number">{rf}</Data></Cell><Cell><Data ss:Type="Number">{custom}</Data></Cell><Cell><Data ss:Type="Number">{trades}</Data></Cell>{vals}</Row>
</Table></Worksheet></Workbook>'''

def main():
    original={name:getattr(worker,name) for name in (
        'RUNS_ROOT','EVIDENCE_ROOT','validate_request','optimization_report_identity','run_round',
        'scientist_propose_ranges','compile_ea','_apply_winner'
    )}
    try:
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); runs=base/'runs'; ev=base/'evidence'; runs.mkdir(); ev.mkdir()
            worker.RUNS_ROOT=runs; worker.EVIDENCE_ROOT=ev
            worker.validate_request=lambda x:x
            worker.optimization_report_identity=lambda p:{'expert':'Max','symbol':'EURUSD.m','period':'H1','from':'2021.01.01','to':'2026.09.09'}
            report=base/'ReportOptimizer.xml'; report.write_text('<xml/>',encoding='utf-8')
            compile_calls=[]; llm_calls=[]; winner_calls=[]
            worker.compile_ea=lambda *a,**k:(compile_calls.append(1) or (base/'fake.ex5','MaxResearch\\Max'))

            def fake_apply(req0,job0,status_path,st0,round_no,ch,records):
                winner_calls.append(round_no)
                worker.update(status_path,st0,'CHAMPION_FOUND','winner applied; stop',round=round_no,rounds=records,first_failed_gate=None,frozen_config=req0,report_identity=records[-1]['report_identity'])
                return 0
            worker._apply_winner=fake_apply

            # 1: RESUME never reruns the checkpointed round, but a no-winner result auto-continues later rounds.
            calls=[]; r=frozen(False,max_rounds=3); job,sp=setup_job(runs,'resume_no_winner',r,'WAITING_FOR_REPORT',1)
            def rr_no_winner(*a,**k):
                rn=a[3]
                calls.append((rn,k.get('launch_mt5')))
                return [row(passed=False,round_no=rn)],report
            worker.run_round=rr_no_winner
            rc=worker.main('resume_no_winner',resume=True)
            st=json.loads(sp.read_text())
            req(rc==2 and st['status']=='NO_CHAMPION_MAX_ROUNDS','No-winner run must stop only after frozen max_rounds is exhausted')
            req(calls==[(1,False),(2,True),(3,True)],f'Resume must parse current evidence then auto-run later rounds: {calls}')
            req(st['round']==3 and st['first_failed_gate']=='OPTIMIZER_KPI_ELIGIBILITY','terminal no-Champion evidence must retain round and failed gate')
            req(st.get('report_identity',{}).get('symbol')=='EURUSD.m','machine evidence must retain report identity')

            # 2+6: recovered eligible winner is a hard stop; no Scientist and no later MT5 round.
            calls.clear(); llm_calls.clear(); winner_calls.clear(); compile_calls.clear()
            r=frozen(True); job,sp=setup_job(runs,'resume_winner',r,'WAITING_FOR_REPORT',1)
            worker.run_round=lambda *a,**k:(calls.append((a[3],k.get('launch_mt5'))) or ([row(passed=True,round_no=a[3])],report))
            worker.scientist_propose_ranges=lambda *a,**k:(llm_calls.append(1) or ({},{}))
            rc=worker.main('resume_winner',resume=True)
            st=json.loads(sp.read_text())
            req(rc==0 and st['status']=='CHAMPION_FOUND' and winner_calls==[1],'Recovered winner must apply then stop')
            req(calls==[(1,False)] and not llm_calls and not compile_calls,'Winner evidence must forbid Scientist, compile-for-next-round, and later MT5 launch')

            # 3+4: Scientist OFF => deterministic refinement and automatic next round.
            calls.clear(); compile_calls.clear(); winner_calls.clear()
            r=frozen(False,max_rounds=2); job,sp=setup_job(runs,'auto_off',r,'WAITING_FOR_REPORT',1)
            def rr_off(*a,**k):
                rn=a[3]; calls.append((rn,k.get('launch_mt5')))
                return [row(passed=(rn==2),round_no=rn)],report
            worker.run_round=rr_off
            rc=worker.main('auto_off',resume=True)
            st=json.loads(sp.read_text()); prop=json.loads((job/'round_1_next_range_proposal.json').read_text())
            req(rc==0 and calls==[(1,False),(2,True)] and winner_calls==[2],'Scientist OFF must auto-refine and run exactly the needed next round')
            req(prop['mode']=='DETERMINISTIC_ONLY' and prop['actual_llm_call'] is False and prop['accepted'] is True,'Scientist OFF path must be deterministic-only')

            # 5: Scientist ON => actual LLM proposal, persisted validation, then automatic next round.
            calls.clear(); compile_calls.clear(); llm_calls.clear(); winner_calls.clear()
            r=frozen(True,max_rounds=2); job,sp=setup_job(runs,'auto_on',r,'WAITING_FOR_REPORT',1)
            selected={k:dict(DEFAULT_SPACE[k]) for k in r['optimize_params']}
            def fake_scientist(*a,**k):
                llm_calls.append(k.get('round_no'))
                return {'ranges':selected,'reason':'bounded evidence refinement'}, {'reason':'bounded evidence refinement','llm_provenance':{'provider':'test','model':'test-model'}}
            worker.scientist_propose_ranges=fake_scientist
            def rr_on(*a,**k):
                rn=a[3]; calls.append((rn,k.get('launch_mt5')))
                return [row(passed=(rn==2),round_no=rn)],report
            worker.run_round=rr_on
            rc=worker.main('auto_on',resume=True)
            st=json.loads(sp.read_text()); prop=json.loads((job/'round_1_next_range_proposal.json').read_text())
            req(rc==0 and llm_calls==[2] and calls==[(1,False),(2,True)] and winner_calls==[2],'Scientist ON must call once for the needed next range and stop immediately when round 2 wins')
            req(prop['mode']=='SCIENTIST_PROPOSAL' and prop['actual_llm_call'] is True and prop['accepted'] is True,'Actual Scientist proposal must persist accepted validation evidence')
            req(prop['validation']['status']=='ACCEPTED' and prop['llm_provenance']['model']=='test-model','proposal validation + provenance must be machine-readable')

            # Deterministic validator must reject parameter-universe escalation.
            try:
                validate_scientist_ranges(DEFAULT_SPACE,{'ranges':{'InpSL_ATR':dict(DEFAULT_SPACE['InpSL_ATR']),'InpTP_ATR':dict(DEFAULT_SPACE['InpTP_ATR']),'InpMaxHoldBars':dict(DEFAULT_SPACE['InpMaxHoldBars'])}},['InpSL_ATR','InpTP_ATR'])
                raise AssertionError('validator accepted Scientist activation of a frozen parameter')
            except ValueError:
                pass

            # 8: durable terminal state survives fresh file read.
            persisted=json.loads((runs/'resume_no_winner'/'status.json').read_text())
            req(persisted['status']=='NO_CHAMPION_MAX_ROUNDS' and persisted['round']==3 and persisted['frozen_config']['max_rounds']==3,'durable atomic run state must survive restart/readback')

            # Owner runtime regression: with frozen ExpR >= -0.01, the real-report-like
            # pass 9182 values are eligible and must hard-stop as Champion rather than refine.
            params={k:v['start'] for k,v in DEFAULT_SPACE.items()}
            p9182=OptimizationPass(round_no=1,pass_no=9182,profit_factor=1.032246,recovery_factor=0.506509,expectancy_r=-0.0009863807119168486,profit=1468.31,trades=1569,params=params,raw={},minimum_trades_required=1365,min_profit_factor_required=1.0,min_recovery_factor_required=0.0,min_expectancy_r_required=-0.01)
            lower=OptimizationPass(round_no=1,pass_no=9099,profit_factor=1.038260,recovery_factor=0.627585,expectancy_r=-0.006457708531911132,profit=1717.45,trades=1527,params=params,raw={},minimum_trades_required=1365,min_profit_factor_required=1.0,min_recovery_factor_required=0.0,min_expectancy_r_required=-0.01)
            req(p9182.passed and lower.passed,'Owner -0.01 Expectancy R threshold must make report-like candidates eligible')
            req(select_champion([lower,p9182]).pass_no==9182,'ranking must choose highest Expectancy R first, matching real report pass 9182')


            # Parser regression from the Owner screenshot/report shape: Expected Payoff is
            # informational; Custom is the independent Expectancy-R authority. -0.000986 >= -0.01.
            xml=base/'ReportOptimizer-owner-like.xml'
            xml.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09'),encoding='utf-8')
            parsed=parse_optimization_xml(xml,round_no=1)
            req(len(parsed)==1 and abs(parsed[0].expectancy_r-(-0.0009863807119168486))<1e-15,'parser must map Custom, not Expected Payoff, to Expectancy R')
            parsed[0].minimum_trades_required=1365; parsed[0].min_profit_factor_required=1.0; parsed[0].min_recovery_factor_required=0.0; parsed[0].min_expectancy_r_required=-0.01
            req(parsed[0].passed and select_champion(parsed).pass_no==9182,'Owner report-like pass 9182 must be eligible at frozen ExpR >= -0.01')

            # Freshness regression: a stale compatible report with a future internal Created
            # timestamp must never be reused as the next MT5 round. New/changed fingerprint wins.
            data=base/'freshness_data'; prof=data/'MQL5'/'Profiles'/'Tester'; prof.mkdir(parents=True)
            freshness_req={**r,'installation':{'terminal':str(base/'terminal64.exe'),'metaeditor':str(base/'metaeditor64.exe'),'data_dir':str(data)}}
            stale=prof/'ReportOptimizer-stale.xml'; stale.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09',pass_no=7,custom=-0.2,pf=0.8,rf=-0.1),encoding='utf-8')
            baseline=worker._report_snapshot(freshness_req)
            fresh_name='Max.xml'; fresh=prof/fresh_name
            fresh.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09'),encoding='utf-8')
            original_sleep=worker.time.sleep; worker.time.sleep=lambda _x: None
            try:
                picked,mode=worker._wait_for_fresh_report(freshness_req,report_name=fresh_name,prelaunch_snapshot=baseline,timeout_sec=2)
            finally:
                worker.time.sleep=original_sleep
            req(picked is not None and picked.name==fresh_name and mode=='EXPECTED_CANONICAL_REPORT','next round must select fresh canonical report, never stale compatible XML by timestamp')

            # Owner runtime evidence regression 20260915_201225_bd7103a6:
            # a newer stale MAX-generated prior-job R2 must never outrank an older manual
            # ReportOptimizer XML when a brand-new job bootstraps existing evidence.
            bootstrap_data=base/'bootstrap_data'; bootstrap_prof=bootstrap_data/'MQL5'/'Profiles'/'Tester'; bootstrap_prof.mkdir(parents=True)
            bootstrap_terminal=base/'bootstrap_terminal'; bootstrap_terminal.mkdir()
            bootstrap_req={**r,'installation':{'terminal':str(bootstrap_terminal/'terminal64.exe'),'metaeditor':str(bootstrap_terminal/'metaeditor64.exe'),'data_dir':str(bootstrap_data)}}
            manual=bootstrap_prof/'ReportOptimizer-1007105508.xml'; manual.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09'),encoding='utf-8'); manual.with_name(manual.stem+'.metrics.csv').write_text('pass,mean_expectancy_r,weighted_r,mt5_trades,r_accounted_trades,sum_net,sum_initial_risk,accounting_errors,run_nonce\n9182,-0.000986,0.01,1569,1569,10,1000,0,123\n',encoding='utf-8')
            stale_max=bootstrap_data/'Max.xml'; stale_max.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09',pass_no=7,custom=-0.2,pf=0.8,rf=-0.1),encoding='utf-8')
            stale_legacy=bootstrap_data/'MAX_StrategyOptimizer_20260915_174420_recover_24e285ee_R2.xml'; stale_legacy.write_text(mini_report_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09',pass_no=8,custom=-0.2,pf=0.8,rf=-0.1),encoding='utf-8')
            import os as _os, time as _time
            now_ns=_time.time_ns(); _os.utime(manual,ns=(now_ns-10_000_000_000,now_ns-10_000_000_000)); _os.utime(stale_max,ns=(now_ns,now_ns)); _os.utime(stale_legacy,ns=(now_ns,now_ns))
            boot=discover_bootstrap_optimization_reports(bootstrap_req)
            req(boot and boot[0].name==manual.name and all(not (p.name.startswith('MAX_StrategyOptimizer_') or p.name in {'Max.xml','Max_R1.xml','Max_R2.xml','Max_R3.xml'}) for p in boot),'new START must bootstrap only Owner/manual XML with paired Weighted-R evidence and exclude stale current/legacy MAX-generated round XML regardless of newer mtime')

            # Windows regression: hardened atomic writer must retry transient PermissionError
            # instead of failing fixed status.json.tmp -> status.json replacement.
            target=base/'atomic'/'status.json'; original_replace=factory_jobs.os.replace; attempts={'n':0}
            def flaky_replace(src,dst):
                attempts['n']+=1
                if attempts['n']<=3:
                    raise PermissionError(13,'Access is denied')
                return original_replace(src,dst)
            factory_jobs.os.replace=flaky_replace
            try:
                jobs_mod._atomic(target,{'status':'PASS'})
            finally:
                factory_jobs.os.replace=original_replace
            req(json.loads(target.read_text())['status']=='PASS' and attempts['n']==4,'Windows-safe atomic writer must retry transient access-denied replacement')

        # 9+10+11 source contract: separate research lifecycle, frozen request, transitions/evidence.
        app=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')
        jobs=(Path(__file__).resolve().parents[1]/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8')
        worker_src=(Path(__file__).resolve().parents[1]/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
        req('START AUTO OPTIMIZER' in app and 'RESUME AUTO OPTIMIZER' in app and 'STOP OPTIMIZER' in app,'contextual Optimizer lifecycle controls missing')
        req('CONTINUE NEXT ROUND' not in app,'manual Continue action must not exist; no-winner rounds auto-continue')
        req('RECOVER LATEST MT5 RESULT' not in app and 'RESUME FROM MT5 REPORT' not in app,'ambiguous legacy recovery controls must remain removed')
        req('continue_next_round_job' not in jobs and 'CONTINUABLE' not in jobs,'backend must not expose manual next-round authorization')
        req('frozen_config' in jobs and 'state_transitions' in jobs,'job authority must persist frozen config and state transitions')
        req('research_active' in app and 'Research is active · Optimizer start is locked.' in app,'Research/Optimizer lifecycle interlock must remain explicit')
        req('while True:' in worker_src and 'Automatically refining and continuing' in worker_src,'worker must auto-loop only while no Champion and round budget remains')
        req('Hard stop contract: once an eligible winner exists' in worker_src,'winner hard-stop guard missing')
        req('MAX_STRATEGY_OPTIMIZER_PROCESS_OWNER_V1' in jobs and 'worker_process.json' in jobs,'launcher PID must live outside worker-owned status.json')
        req('atomic_write_json' in jobs and 'atomic_write_json' in worker_src,'Optimizer status writers must reuse hardened Windows-safe atomic authority')
        req('status.json.tmp' not in jobs and 'status.json.tmp' not in worker_src,'fixed status.json.tmp race must not return')
        req('prelaunch_report_snapshot' in worker_src and 'EXPECTED_CANONICAL_REPORT' in worker_src and 'FRESH_FINGERPRINT' in worker_src,'round report freshness must use pre-launch fingerprint authority, not MT5 Created timestamp')
        req('eligibility_audit' in worker_src and 'report_sha256' in worker_src and 'report_selection_mode' in worker_src,'round evidence must expose exact report provenance and eligibility audit')
        req('Report provenance:' in app and 'Evidence report' in app and 'Eligible' in app,'Optimizer UI must surface the exact evidence report and eligible count')
        req('"WAITING_FOR_REPORT","FAILED"' in jobs and 'winerror 5' in jobs.lower(),'v0.8.2 access-denied failure must be resumable as existing evidence')
        req(EA_SOURCE.name=='Max.mq5','canonical EA runtime filename must be Max.mq5')
        req('set_name="Max.set"' in worker_src and 'report_name="Max.xml"' in worker_src,'new Optimizer runtime artifacts must use the exact Max EA stem')
        req('EA_v1_06/Max.mq5' in app and 'EA_v1_06/ComplexPolicy_ONNXReady_EA.mq5' not in app,'Optimizer UI must expose Max canonical EA name only')

        print('V084_STRATEGY_OPTIMIZER_AUTO_CONTINUE_STOP_ON_CHAMPION_WINDOWS_IO_PASS')
    finally:
        for name,value in original.items():
            setattr(worker,name,value)

if __name__=='__main__':
    main()
