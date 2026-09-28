from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from strategy.strategy_optimizer import EA_SOURCE,build_set_text,DEFAULT_SPACE,TESTER_SET,OPTIMIZER_METRICS_CSV
from mtf.mtf_names import OPTIMIZER_REPORT_XML,EXPERT_SUBDIR

def req(x,msg):
    if not x: raise AssertionError(msg)
req(EA_SOURCE.name=='Max_MTF.mq5','optimizer active EA stem')
t=build_set_text(DEFAULT_SPACE,confirm_symbol='XAGUSD')
req(f'InpOptimizerMetricsFile={OPTIMIZER_METRICS_CSV}' in t,'optimizer sidecar namespace')
worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
req('set_name=TESTER_SET' in worker and 'report_name=OPTIMIZER_REPORT_XML' in worker,'worker uses namespace constants')
req('EXPERT_SUBDIR' in worker,'worker uses MaxMTF expert namespace')
req(TESTER_SET=='Max_MTF.set' and OPTIMIZER_REPORT_XML=='Max_MTF.xml' and EXPERT_SUBDIR=='MaxMTF','canonical optimizer namespace')
print('V200_OPTIMIZER_NAMESPACE PASS')
