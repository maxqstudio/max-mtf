from __future__ import annotations
import tempfile
from pathlib import Path
import pandas as pd

import host.mt5_gap_repair as gr
def req(x,msg):
    if not x:
        raise AssertionError(msg)


def _fake_cp32(path: Path):
    rows=[]
    for i,t in enumerate(pd.date_range('2022-01-01',periods=6,freq='h')):
        rows.append({
            'contract':'CP32_V1','signal_time':t.strftime('%Y.%m.%d %H:%M'),'decision_bar_time':t.strftime('%Y.%m.%d %H:%M'),
            'symbol':'EURUSD.m','period':16385,'open':1.0,'high':1.1,'low':0.9,'close':1.0,'atr':0.1,
            'decision_bid':1.0,'decision_ask':1.01,'spread_points':1.0,'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54,
            'consensus':0.5,
        })
    # mt5_gap_repair only reads geometry from the CSV in this regression.
    pd.DataFrame(rows).to_csv(path,sep=';',index=False)


def _fake_champion_set(path: Path):
    text='''; canonical Champion Max.set\nInpSL_ATR=3.2||3.2||0||3.2||N\nInpTP_ATR=4.8||4.8||0||4.8||N\nInpMaxHoldBars=54||54||0||54||N\nInpEntryThreshold=0.2||0.2||0||0.2||N\nInpAllowLiveTrading=true\nInpWriteTelemetry=false\nInpWriteTrainingData=false\nInpUseOnnxChampion=false\nInpUseOnnxChallenger=false\nInpOptimizerRunNonce=0\n'''
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        master=root/'Max_Training.csv'; _fake_cp32(master)
        report={
            'sha256':'abc',
            'identity':{'symbol':'EURUSD.m','period':16385,'timeframe':'H1'},
            'broker_reconciliation':{
                'verified':True,'server':'Demo','terminal_path':str(root/'Terminal'),
                'terminal_data_path':str(root/'Data'),
                'missing_timestamps':['2022-01-01T02:00:00','2022-01-01T03:00:00'],
            },
        }
        plan=gr.build_gap_fill_plan(report,master)
        req(plan['strategy_geometry']=={'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54},'dataset geometry authority missing')
        data_dir=root/'Data'
        source_set=data_dir/'MQL5'/'Profiles'/'Tester'/'Max.set'; _fake_champion_set(source_set)
        target={'data_dir':str(data_dir),'expert_relative':'MaxResearch\\Max','terminal_exe':str(root/'Terminal'/'terminal64.exe')}
        repair_set=gr._write_gap_repair_set(plan,target)
        text=repair_set.read_text(encoding='utf-8')
        req('InpWriteTrainingData=true' in text,'repair preset must force training writer ON')
        req('InpTrainingFile=Max_Training.csv' in text,'repair preset must force canonical training filename')
        req('InpAllowLiveTrading=false' in text,'repair preset must disable trading')
        req('InpSL_ATR=3.2||3.2||0||3.2||N' in text,'SL geometry must stay exact')
        req('InpTP_ATR=4.8||4.8||0||4.8||N' in text,'TP geometry must stay exact')
        req('InpMaxHoldBars=54||54||0||54||N' in text,'MaxHold geometry must stay exact')
        ini,repair_set2,report_path=gr._write_ini(plan,target)
        ini_text=ini.read_text(encoding='ascii')
        req(repair_set2==repair_set,'INI must use dedicated repair preset')
        req('ExpertParameters=Max_GapRepair.set' in ini_text,'Tester must explicitly load repair preset')
        req('Optimization=0' in ini_text,'gap repair must be single test')
        req('FromDate=2021.12.22' in ini_text and 'ToDate=2022.01.03' in ini_text,'bounded repair envelope mismatch')
        req('ShutdownTerminal=1' in ini_text,'tester must auto-close after repair')
        req(report_path.parent==data_dir/'reports','repair report must belong to verified terminal data dir')

        # Real MT5 commonly writes .set files as UTF-16 LE with FF FE BOM.
        # Repair must auto-detect and preserve that encoding instead of crashing
        # with a UTF-8 codec error.
        utf16_set=data_dir/'MQL5'/'Profiles'/'Tester'/'Max.set'
        original_text=utf16_set.read_text(encoding='utf-8')
        utf16_set.write_text(original_text,encoding='utf-16')
        raw=utf16_set.read_bytes(); req(raw.startswith(b'\xff\xfe'),'fixture must reproduce MT5 UTF-16 BOM')
        repaired_utf16=gr._write_gap_repair_set(plan,target)
        req(repaired_utf16.read_bytes().startswith(b'\xff\xfe'),'repair preset must preserve UTF-16 MT5 encoding')
        text16=repaired_utf16.read_text(encoding='utf-16')
        req('InpWriteTrainingData=true' in text16 and 'InpSL_ATR=3.2||3.2||0||3.2||N' in text16,'UTF-16 repair preset content mismatch')

        # Mixed/stale dataset geometry must fail closed before any tester launch.
        bad=pd.read_csv(master,sep=';'); bad.loc[0,'sl_atr']=9.9; bad.to_csv(master,sep=';',index=False)
        try:
            gr.build_gap_fill_plan(report,master)
        except ValueError as exc:
            req('mixed/stale strategy geometry' in str(exc),'wrong mixed geometry failure')
        else:
            raise AssertionError('mixed strategy geometry must fail closed')
    print('V091_GAP_REPAIR_TESTER PASS')


if __name__=='__main__':
    main()
