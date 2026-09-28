from pathlib import Path
import json, re, sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent
sys.path.insert(0,str(ROOT))
from core.project_paths import PROJECT_NAME,PROJECT_VERSION,EA_VERSION,EA_SOURCE,LEGACY_SINGLE_TF_REFERENCE
from strategy.strategy_optimizer import canonical_ea_identity,read_ea_optimizer_defaults

def req(x,msg):
    if not x: raise AssertionError(msg)
ident=json.loads((PKG/'governance/PROJECT_IDENTITY.json').read_text(encoding='utf-8'))
req(PROJECT_NAME=='Max MTF' and PROJECT_VERSION=='2.0.1' and EA_VERSION=='2.00','project identity constants')
req(ident['project']=='Max MTF' and ident['project_version']=='2.0.1' and ident['ea_version']=='2.00','identity json')
req(ident['initial_state']['strategy_champion'] is None and ident['initial_state']['model_champion'] is None,'zero champion state')
req(ident['baseline_is_champion'] is False,'baseline is not Champion')
req(EA_SOURCE.resolve()==(PKG/'EA_v2_00/baseline/Max_MTF.mq5').resolve(),'active EA path')
ea=EA_SOURCE.read_text(encoding='utf-8')
req('#property version   "2.00"' in ea,'EA version 2.00')
req('MAX_MTF_FOUNDATION_PHASE 0' in ea,'foundation phase marker')
ci=canonical_ea_identity(); req(ci['package_relative_path']=='EA_v2_00/baseline/Max_MTF.mq5','canonical identity path')
req((LEGACY_SINGLE_TF_REFERENCE/'Max.mq5').is_file(),'legacy v1.4.5 EA reference retained')
old=read_ea_optimizer_defaults(LEGACY_SINGLE_TF_REFERENCE/'Max.mq5'); new=read_ea_optimizer_defaults(EA_SOURCE)
req(old==new,'seed strategy optimizer defaults are exactly inherited from v1.4.5')
print('V200_MTF_FOUNDATION_IDENTITY PASS')
