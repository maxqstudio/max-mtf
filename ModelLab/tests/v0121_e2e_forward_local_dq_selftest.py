from __future__ import annotations
import tempfile
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from research.research_e2e import golden_cp32, e2e_config
from factory.champion_factory import _e2e_forward_local_data_quality


def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        ds=td/'CP32_E2E_GOLDEN.csv'
        golden_cp32(ds,3600)
        cp=td/'config_e2e.json'
        cfg=e2e_config(ROOT/'config/config.json',ds,cp)
        report=_e2e_forward_local_data_quality(ds,cfg)
        req(isinstance(report,dict),'Golden E2E Forward receives local DQ report')
        req((report.get('e2e_workflow_local_proof') or {}).get('status')=='PASS','Golden E2E local proof passes without broker authority')
        req((report.get('broker_reconciliation') or {}).get('verified') is False,'E2E local proof never forges broker verification')
        req((report.get('e2e_workflow_local_proof') or {}).get('production_evidence') is False,'E2E local proof is explicitly non-production')

        prod=dict(cfg)
        prod['champion_factory']=dict(cfg['champion_factory'])
        prod['champion_factory']['e2e_workflow_test']={'enabled':False}
        req(_e2e_forward_local_data_quality(ds,prod) is None,'Production config cannot enter E2E broker-bypass path')

        bad=dict(cfg)
        bad['champion_factory']=dict(cfg['champion_factory'])
        bad['champion_factory']['e2e_workflow_test']=dict(cfg['champion_factory']['e2e_workflow_test'])
        bad['champion_factory']['e2e_workflow_test']['profile']='WRONG'
        try:
            _e2e_forward_local_data_quality(ds,bad)
        except RuntimeError as exc:
            req('E2E_FORWARD_DQ_CONTRACT_INVALID' in str(exc),'Wrong E2E profile fails closed')
        else:
            raise AssertionError('Wrong E2E profile did not fail closed')
    print('V0121_E2E_FORWARD_LOCAL_DQ_SELFTEST PASS')

if __name__=='__main__': main()
