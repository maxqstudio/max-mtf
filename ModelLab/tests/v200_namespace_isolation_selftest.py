from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
from mtf.mtf_names import *
from strategy.strategy_optimizer import EA_SOURCE

def req(x,msg):
    if not x: raise AssertionError(msg)
ea=EA_SOURCE.read_text(encoding='utf-8')
for name in (TRAINING_CSV,TELEMETRY_CSV,CHAMPION_TRADES_CSV,SHADOW_TRADES_CSV,OPTIMIZER_METRICS_CSV):
    req(name in ea,'EA missing isolated runtime name '+name)
for old in ('Max_Training.csv','Max_Telemetry.csv','Max_Champion_Trades.csv','Max_Shadow_Trades.csv','Max_metrics.csv'):
    req(old not in ea,'active EA must not write legacy single-TF runtime name '+old)
req(TESTER_SET=='Max_MTF.set' and OPTIMIZER_REPORT_XML=='Max_MTF.xml' and GAP_REPAIR_SET=='Max_MTF_GapRepair.set','isolated tester/report names')
req((PKG/'EA_v1_06/LEGACY_SINGLE_TF_REFERENCE_ONLY.txt').is_file(),'legacy source explicitly marked reference-only')
print('V200_NAMESPACE_ISOLATION PASS')
