from __future__ import annotations
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

import data.data_quality as dq
from core.contract import FEATURES, CONTRACT_ID
from host.mt5_gap_repair import build_gap_fill_plan, matching_mt5_gap_fill_targets
from data.labels import build_labels


def req(x,msg):
    if not x: raise AssertionError(msg)


def synth(path: Path, n=128):
    t=pd.date_range('2025-01-01',periods=n,freq='h')
    base=np.linspace(1.1,1.2,n)
    data={
        'contract':[CONTRACT_ID]*n,'signal_time':t,'decision_bar_time':t,'symbol':['EURUSD.m']*n,'period':[16385]*n,
        'open':base,'high':base+0.002,'low':base-0.002,'close':base+0.0002,'atr':[0.005]*n,
        'decision_bid':base+0.0001,'decision_ask':base+0.0003,'spread_points':[2.0]*n,
        'sl_atr':[1.8]*n,'tp_atr':[2.7]*n,'max_hold_bars':[24]*n,'consensus':[0.1]*n,
    }
    for i,f in enumerate(FEATURES):
        data[f]=np.linspace(-0.2,0.2,n)+(i*1e-4)
    pd.DataFrame(data).to_csv(path,sep=';',index=False)


def main():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'Max_Training.csv'; synth(p)
        original=dq._broker_reconcile
        try:
            dq._broker_reconcile=lambda df:{'status':'VERIFIED','verified':True,'source_backed_missing_count':2,'dataset_only_count':0,'missing_timestamps':['2025-01-02T05:00:00','2025-01-02T06:00:00'],'dataset_only_timestamps':[],'server':'Demo','login':1,'match_ratio':1.0,'time_shift_minutes':0}
            r=dq.audit_dataset(p,broker_reconcile=True)
            req(r['status']=='INCOMPLETE','source-backed gaps must mark dataset INCOMPLETE')
            ok,reasons=dq.research_readiness(r)
            req(not ok and any('SOURCE_BACKED_MISSING_BARS' in x for x in reasons),'START gate must block source-backed gaps')
            plan=build_gap_fill_plan(r,p)
            req(plan['status']=='READY' and plan['missing_count']==2,'gap repair plan missing')
            req(plan['repair_authority']=='EA_STRATEGY_TESTER_FIRST_WRITE_WINS_CP32' and plan['synthetic_fill_allowed'] is False,'repair must use EA first-write-wins, never synthetic fill')
            rr=dict(r); rr['broker_reconciliation']=dict(rr['broker_reconciliation'],terminal_path='C:/MT5A',terminal_data_path='C:/DataA')
            targets=[{'terminal_exe':'C:/MT5A/terminal64.exe','data_dir':'C:/DataA'},{'terminal_exe':'C:/MT5B/terminal64.exe','data_dir':'C:/DataB'}]
            matched=matching_mt5_gap_fill_targets(targets,rr)
            req(len(matched)==1 and 'MT5A' in matched[0]['terminal_exe'],'gap repair must be constrained to verified MT5 terminal/feed')

            dq._broker_reconcile=lambda df:{'status':'VERIFIED','verified':True,'source_backed_missing_count':0,'dataset_only_count':0,'missing_timestamps':[],'dataset_only_timestamps':[],'server':'Demo','login':1,'match_ratio':1.0,'time_shift_minutes':0}
            r2=dq.audit_dataset(p,broker_reconcile=True)
            ok2,reasons2=dq.research_readiness(r2)
            req(ok2 and not reasons2,'clean broker-reconciled dataset must be research ready')

            # Broker-sourced zero-spread observations are unusual but not corrupt.
            # They must remain visible as warnings and must not block research or
            # be silently dropped by label construction.
            zero=pd.read_csv(p,sep=';')
            zero.loc[5,'decision_ask']=zero.loc[5,'decision_bid']
            zero.to_csv(p,sep=';',index=False)
            rz=dq.audit_dataset(p,broker_reconcile=True)
            okz,reasonsz=dq.research_readiness(rz)
            req(rz['market_sanity']['zero_spread_decision_quote_rows']==1,'zero-spread row must be counted explicitly')
            req(rz['market_sanity']['invalid_decision_quote_rows']==0,'zero-spread row must not be classified as structurally invalid')
            req(okz and not reasonsz,'zero-spread warning must not block START RESEARCH')
            req(any('ZERO_SPREAD_DECISION_QUOTE_ROWS:1' in x for x in rz['warnings']),'zero-spread row must remain observable as warning')
            lcfg={'label':{'horizon_bars':24,'sl_atr':1.8,'tp_atr':2.7,'min_edge_r':-1.0,'min_margin_r':0.0,'ambiguous_policy':'keep'}}
            lab=build_labels(pd.read_csv(p,sep=';'),lcfg)
            req(len(lab)>0,'zero-spread dataset must remain labelable')

            # Truly inverted quotes remain a hard deterministic failure.
            inv=pd.read_csv(p,sep=';')
            inv.loc[6,'decision_ask']=float(inv.loc[6,'decision_bid'])-0.0001
            inv.to_csv(p,sep=';',index=False)
            ri=dq.audit_dataset(p,broker_reconcile=True)
            req(ri['status']=='INVALID' and ri['market_sanity']['quote_inverted_rows']>=1,'inverted quote must fail closed')
            req(any('INVALID_DECISION_QUOTE_ROWS' in x for x in ri['hard_reasons']),'inverted quote hard reason missing')

            synth(p)
            bad=pd.read_csv(p,sep=';'); bad.loc[3,'high']=bad.loc[3,'low']-1; bad.to_csv(p,sep=';',index=False)
            r3=dq.audit_dataset(p,broker_reconcile=True)
            req(r3['status']=='INVALID' and any('INVALID_OHLC_ROWS' in x for x in r3['hard_reasons']),'invalid OHLC must fail closed')
        finally:
            dq._broker_reconcile=original
    print('DATA_QUALITY_AUTHORITY PASS')

if __name__=='__main__': main()
