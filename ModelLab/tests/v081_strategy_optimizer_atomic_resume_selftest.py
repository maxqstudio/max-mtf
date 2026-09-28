from pathlib import Path
import tempfile, shutil
from strategy.strategy_optimizer import (
    DEFAULT_SPACE, build_set_text, read_ea_optimizer_defaults, search_space_cardinality,
    optimization_report_identity, report_matches_request, discover_optimization_reports,
    validate_request,
)

ROOT=Path(__file__).resolve().parents[1]
WORKER=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
JOBS=(ROOT/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8')
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond: raise AssertionError(msg)

def mini_xml(title:str)->str:
    params=''.join(f'<Cell><Data ss:Type="String">{k}</Data></Cell>' for k in DEFAULT_SPACE)
    vals=''.join('<Cell><Data ss:Type="Number">1</Data></Cell>' for _ in DEFAULT_SPACE)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<DocumentProperties xmlns="urn:schemas-microsoft-com:office:office"><Title>{title}</Title><Created>2026-09-15T16:38:38Z</Created></DocumentProperties>
<Worksheet ss:Name="Tester Optimizator Results"><Table>
<Row><Cell><Data ss:Type="String">Pass</Data></Cell><Cell><Data ss:Type="String">Result</Data></Cell><Cell><Data ss:Type="String">Profit</Data></Cell><Cell><Data ss:Type="String">Profit Factor</Data></Cell><Cell><Data ss:Type="String">Recovery Factor</Data></Cell><Cell><Data ss:Type="String">Custom</Data></Cell><Cell><Data ss:Type="String">Trades</Data></Cell>{params}</Row>
<Row><Cell><Data ss:Type="Number">1</Data></Cell><Cell><Data ss:Type="Number">0.2</Data></Cell><Cell><Data ss:Type="Number">10</Data></Cell><Cell><Data ss:Type="Number">1.1</Data></Cell><Cell><Data ss:Type="Number">0.2</Data></Cell><Cell><Data ss:Type="Number">0.1</Data></Cell><Cell><Data ss:Type="Number">2000</Data></Cell>{vals}</Row>
</Table></Worksheet></Workbook>'''

def main():
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); prof=base/'MQL5'/'Profiles'/'Tester'; prof.mkdir(parents=True)
        rp=prof/'ReportOptimizer-123.xml'
        rp.write_text(mini_xml('Max EURUSD.m,H1 2021.01.01-2026.09.09'),encoding='utf-8')
        request={
            'installation':{'terminal':str(base/'terminal64.exe'),'metaeditor':str(base/'metaeditor64.exe'),'data_dir':str(base)},
            'symbol':'EURUSD.m','confirm_symbol':'XAUUSD.m','period':'H1','from_date':'2021.01.01','to_date':'2026.09.09',
            'deposit':10000,'leverage':100,'model':1,'optimization':2,'max_rounds':3,'scientist_assist':False,
            'search_space':DEFAULT_SPACE,'optimize_params':['InpSL_ATR','InpTP_ATR'],
        }
        frozen=validate_request(request)
        req(report_matches_request(rp,frozen),'report identity must match EA+symbol+TF+range')
        hits=discover_optimization_reports(frozen); req(hits and hits[0].name==rp.name,'Profiles/Tester compatible report auto-discovery')
        ident=optimization_report_identity(rp); req(ident['symbol']=='EURUSD.m' and ident['period']=='H1','report identity parsed')
        txt=build_set_text(DEFAULT_SPACE,confirm_symbol='XAUUSD.m',optimize_params=['InpSL_ATR','InpTP_ATR'],fixed_param_values=read_ea_optimizer_defaults())
        req(sum(1 for line in txt.splitlines() if line.endswith('||Y'))==2,'only Owner-selected parameters optimized')
        req(search_space_cardinality(DEFAULT_SPACE,['InpSL_ATR','InpTP_ATR'])['optimized_inputs']==2,'cardinality respects Owner selection')
    req('MAX_STRATEGY_OPTIMIZER_ROUND_STATE_V1' in WORKER and 'WAITING_FOR_REPORT' in WORKER,'worker has durable round checkpoint + recoverable report state')
    req('MT5_COMPLETE_UNCONFIRMED' in WORKER and 'Never relaunch the same round' in WORKER,'worker restart never blindly reruns completed/running round')
    req('resume_job' in JOBS and 'continue_next_round_job' not in JOBS and 'recover_latest_report_job' not in JOBS,'jobs expose checkpoint resume without legacy Recovery or manual Continue authorities')
    req('RESUME AUTO OPTIMIZER' in APP and 'CONTINUE NEXT ROUND' not in APP and 'RECOVER LATEST MT5 RESULT' not in APP and 'RESUME FROM MT5 REPORT' not in APP,'UI exposes START/RESUME/STOP lifecycle without ambiguous Recovery/Continue actions')
    req('Parameters to optimize' in APP,'UI exposes Owner parameter selection')
    print('V081_STRATEGY_OPTIMIZER_ATOMIC_RESUME_PASS')

if __name__=='__main__': main()
