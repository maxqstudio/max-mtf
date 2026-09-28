from __future__ import annotations
import json, tempfile, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.research_e2e import golden_cp32, e2e_config, _factory_to_challenger, _finalize_diagnostics
from factory.challenger_registry import register_eligible_challenger
from factory.governance import save_evidence, assess_promotion, promote

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        ds=td/'CP32_E2E_GOLDEN.csv'; golden_cp32(ds,3600)
        cfg=e2e_config(ROOT/'config/config.json',ds,td/'config_e2e.json')
        stress=cfg['acceptance']['stress_min_expectancy_r']
        req(stress.get('spread_x1.25')==-0.05 and stress.get('spread_x1.50')==-0.05,'E2E promotion current-policy stress thresholds are sandbox-low only')

        fd=td/'factory'; (fd/'champion_runtime').mkdir(parents=True)
        (fd/'champion_runtime'/'champion.onnx').write_bytes(b'E2E_DUMMY_ONNX_FOR_GOVERNANCE_TRANSACTION_TEST')
        (fd/'factory_manifest.json').write_text(json.dumps({'status':'CHAMPION'}),encoding='utf-8')
        (fd/'champion.json').write_text(json.dumps({'family':'RandomForest','metrics':{'trades':20,'profit_factor':1.10,'expectancy_r':0.02,'max_drawdown_r':1.0,'recovery_factor':1.0},'take_threshold':0.45}),encoding='utf-8')
        run=td/'model_challenger'; manifest=_factory_to_challenger(fd,run)
        register_eligible_challenger(run,manifest,td/'sandbox_app')
        save_evidence(run,{
            'mt5_parity':{'status':'PASS','rows':100,'max_abs_error':0.0,'authority':'SYNTHETIC_E2E_TRANSACTION_TEST'},
            'strategy_tester':{'status':'PASS','authority':'SYNTHETIC_E2E_TRANSACTION_TEST'},
            'shadow_forward':{'status':'PASS','trades':20,'profit_factor':1.20,'expectancy_r':0.05,'max_drawdown_r':1.0,'total_r':1.0,'recovery_factor':1.0},
        })
        state=assess_promotion(run,cfg,td/'sandbox_app')
        req(state.get('promotion_ready') is True,'E2E-only complete KPI evidence reaches sandbox promotion-ready state')
        req(all(g.get('passed') for g in state.get('gates',[])),'Every sandbox promotion gate passes under E2E policy')
        promo=promote(run,td/'sandbox_terminal',cfg,td/'sandbox_app')
        req(bool(promo.get('champion_id')) and any((td/'sandbox_terminal'/'models').glob('champion*.onnx')),'Sandbox promotion transaction reaches Champion artifact')

        pass_diag=td/'diagnostic_evidence'/'E2E_PASS'; pass_root=td/'pass_run'; pass_root.mkdir(); (pass_root/'research_e2e_evidence.json').write_text(json.dumps({'status':'PASS'}),encoding='utf-8')
        _finalize_diagnostics(pass_diag,pass_root,status='PASS',first_failed_gate=None)
        pass_summary=json.loads((pass_diag/'diagnostic_summary.json').read_text(encoding='utf-8'))
        req(pass_summary.get('status')=='PASS' and pass_summary.get('first_failed_gate') is None,'PASS diagnostics always capture machine-readable success summary')

        diag=td/'diagnostic_evidence'/'E2E_TEST'; root=td/'run'; root.mkdir(); (root/'research_e2e_evidence.json').write_text('{}',encoding='utf-8')
        try:
            raise RuntimeError('diagnostic sentinel')
        except RuntimeError as exc:
            _finalize_diagnostics(diag,root,status='FAIL',first_failed_gate='SENTINEL',error=exc)
        req((diag/'diagnostic_summary.json').exists() and (diag/'traceback.txt').exists(),'FAIL diagnostics always capture summary + traceback')
        summary=json.loads((diag/'diagnostic_summary.json').read_text(encoding='utf-8'))
        req(summary.get('first_failed_gate')=='SENTINEL' and summary.get('status')=='FAIL','Diagnostic first-failed-gate is machine readable')

    cmd=(ROOT/'tools/research/RUN_RESEARCH_E2E.cmd').read_text(encoding='utf-8')
    ps=(ROOT/'tools/research/RUN_RESEARCH_E2E.ps1').read_text(encoding='utf-8')
    req('ExecutionPolicy Bypass' in cmd and 'diagnostic_evidence' in cmd,'CMD is one-click and surfaces diagnostic folder')
    req('diagnostic_evidence' in ps,'PowerShell runner surfaces diagnostic evidence root')
    print('V0122_E2E_PROMOTION_DIAGNOSTICS_SELFTEST PASS')

if __name__=='__main__': main()
