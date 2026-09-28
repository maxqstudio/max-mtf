from __future__ import annotations

import hashlib, json, shutil, tempfile
from pathlib import Path

import strategy.strategy_optimizer as so
import strategy.strategy_optimizer_worker as worker
import strategy.strategy_geometry as sg
import strategy.strategy_challenger_registry as scr
from strategy.strategy_optimizer import OptimizationPass, read_ea_optimizer_defaults

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent


def req(cond,msg):
    if not cond: raise AssertionError(msg)


def main():
    with tempfile.TemporaryDirectory() as td:
        t=Path(td); app=t/'ModelLab'; app.mkdir(); (app/'runtime').mkdir()
        ea=t/'Max.mq5'; shutil.copy2(PKG/'EA_v1_06'/'Max.mq5',ea)
        art=t/'challengers'; runtime_auth=app/'runtime'/'strategy_authority.json'
        old=(scr.EA_SOURCE,scr.ARTIFACT_ROOT,scr.RUNTIME_AUTHORITY,so.EA_SOURCE,worker.EA_SOURCE,sg.RUNTIME_AUTHORITY,worker.compile_ea)
        scr.EA_SOURCE=ea; scr.ARTIFACT_ROOT=art; scr.RUNTIME_AUTHORITY=runtime_auth
        so.EA_SOURCE=ea; worker.EA_SOURCE=ea; sg.RUNTIME_AUTHORITY=runtime_auth
        worker.compile_ea=lambda req0,job0:(job0/'Max.ex5','MaxResearch\\Max')
        try:
            base=read_ea_optimizer_defaults(ea)
            sg.persist_optimizer_champion_authority(params=base,ea_sha256=hashlib.sha256(ea.read_bytes()).hexdigest(),job_id='BASE',champion_pass=1,path=runtime_auth)
            reg=scr.ensure_strategy_registry(app)
            req(reg.get('current_champion',{}).get('status')=='CHAMPION','canonical Max must bootstrap as current Strategy Champion')
            before=hashlib.sha256(ea.read_bytes()).hexdigest()
            params=dict(base); params['InpSL_ATR']=2.8; params['InpTP_ATR']=4.2; params['InpMaxHoldBars']=48
            ch=OptimizationPass(round_no=2,pass_no=321,profit_factor=1.42,recovery_factor=2.7,expectancy_r=.041,profit=123.0,trades=800,params=params,raw={},weighted_r=.035,r_accounted_trades=800,total_initial_risk=3500,r_sum_net=123)
            ch.minimum_trades_required=100; ch.min_profit_factor_required=1.0; ch.min_recovery_factor_required=0.0; ch.min_expectancy_r_required=0.0; ch.min_weighted_r_required=0.0
            term=t/'terminal'; (term/'MQL5'/'Profiles'/'Tester').mkdir(parents=True)
            request={'installation':{'terminal':str(t/'terminal64.exe'),'metaeditor':str(t/'metaeditor64.exe'),'data_dir':str(term)},'symbol':'XAUUSD','confirm_symbol':'DXY','period':'H1','from_date':'2021.01.01','to_date':'2024.12.31','deposit':10000,'leverage':100,'model':1,'optimization':2,'optimizer_kpi':{'min_profit_factor':1.0,'min_recovery_factor':0.0,'min_expectancy_r':0.0,'min_weighted_r':0.0},'optimizer_trade_sample':{'minimum_trades':100,'kpi_profile':{'min_profit_factor':1.0,'min_recovery_factor':0.0,'min_expectancy_r':0.0,'min_weighted_r':0.0}}}
            job=t/'20260916_230000_test'; job.mkdir()
            entry=scr.register_optimizer_challenger(app,request,job,ch,[{'round':2,'report_sha256':'a','optimizer_metrics_sha256':'b'}])
            req(hashlib.sha256(ea.read_bytes()).hexdigest()==before,'Optimizer Challenger registration must not mutate Max.mq5 Champion')
            req(entry['challenger_id'].startswith('STRAT-20260916-230000-R02-P321'),'human Strategy Challenger code')
            req(Path(entry['ea_file']).name.startswith('Max_Challenger_STRAT-'),'human EA filename')
            req(Path(entry['set_file']).suffix=='.set' and Path(entry['ea_file']).is_file() and Path(entry['set_file']).is_file(),'EA + setup bundle required')
            req(entry['kpi']['mean_r']==.041 and entry['kpi']['weighted_r']==.035 and entry['kpi']['profit_factor']==1.42,'Strategy Challenger KPI preserved')
            res=scr.promote_strategy_challenger(app,entry['challenger_id'],installation=request['installation'])
            promoted=read_ea_optimizer_defaults(ea)
            req(float(promoted['InpSL_ATR'])==2.8 and float(promoted['InpTP_ATR'])==4.2 and int(promoted['InpMaxHoldBars'])==48,'promotion must replace Max defaults with selected Challenger')
            reg2=scr.load_strategy_registry(app)
            req(reg2['current_champion']['strategy_id']==entry['challenger_id'],'selected Challenger becomes current Champion')
            req(reg2['current_champion']['kpi']['weighted_r']==.035,'Champion must retain Challenger KPI')
            dem=res['demoted_champion']; req(dem['role_origin']=='DEMOTED_CHAMPION' and Path(dem['ea_file']).is_file(),'old Champion must become a new Challenger')
            deleted=scr.delete_strategy_challenger(app,dem['challenger_id'])
            req(deleted['status']=='DELETED' and not Path(dem['ea_file']).exists(),'delete removes active Challenger artifact')
            reg3=scr.load_strategy_registry(app); req(any(x['challenger_id']==dem['challenger_id'] for x in reg3['tombstones']),'delete must retain audit tombstone')
            try:
                scr.delete_strategy_challenger(app,entry['challenger_id']); raise AssertionError('current Champion delete should fail')
            except RuntimeError: pass
        finally:
            scr.EA_SOURCE,scr.ARTIFACT_ROOT,scr.RUNTIME_AUTHORITY,so.EA_SOURCE,worker.EA_SOURCE,sg.RUNTIME_AUTHORITY,worker.compile_ea=old
    # Static workflow boundary: optimizer winner is Challenger, not auto-promotion.
    w=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
    a=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('STRATEGY_CHALLENGER_FOUND' in w and 'register_optimizer_challenger' in w,'worker must register Strategy Challenger terminal state')
    req('PROMOTE TO STRATEGY CHAMPION' in a and 'DELETE CHALLENGER' in a,'UI must expose explicit promotion/delete')
    print('V0.11.0 STRATEGY CHALLENGER LIFECYCLE PASS')

if __name__=='__main__': main()
