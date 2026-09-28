from __future__ import annotations
import json, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.research_e2e import _factory_to_challenger

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('"Model Challengers","Model Champion"' in app,'Dedicated Model Challenger and Model Champion pages are present')
    req('elif page=="Model Challengers": _render_model_challengers_stage(cfg)' in app,'Model Challengers navigation renders dedicated page')
    chall=app.split('def _render_model_challengers_stage',1)[1].split('def _render_model_champion_stage',1)[0]
    req('_render_model_challenger_registry(cfg)' in chall and '_render_strategy_challenger_registry(cfg)' not in chall,'Model Challenger page owns only Model registry')
    champ=app.split('def _render_model_champion_stage',1)[1].split('def _render_strategy_challengers_stage',1)[0]
    req('_render_model_champion_summary()' in champ and '_render_strategy_champion_summary()' not in champ,'Model Champion page owns only Model Champion authority')
    req('_render_model_challenger_registry(cfg)' not in champ,'Model Champion page no longer embeds Challenger registry')

    with tempfile.TemporaryDirectory() as td:
        td=Path(td); fd=td/'factory'; (fd/'champion_runtime').mkdir(parents=True)
        (fd/'factory_manifest.json').write_text(json.dumps({'status':'CHAMPION'}),encoding='utf-8')
        metrics={'trades':473,'profit_factor':4.973265985275098,'expectancy_r':0.8907494844856699,'max_drawdown_r':14.761702859647244,'recovery_factor':28.541727886520416,'win_rate':0.7674418604651163,'payoff_ratio':1.5070502985682113,'cvar95_r':-1.0,'daily_cvar95_r':-8.0,'total_r':421.3245061617219}
        (fd/'champion.json').write_text(json.dumps({'family':'RandomForest','metrics':metrics,'take_threshold':0.45}),encoding='utf-8')
        (fd/'champion_runtime'/'champion.onnx').write_bytes(b'dummy')
        run=td/'challenger'; m=_factory_to_challenger(fd,run); locked=m['locked_test_trading']
        for k in ('trades','profit_factor','expectancy_r','max_drawdown_r','recovery_factor','win_rate','payoff_ratio','cvar95_r','daily_cvar95_r','total_r'):
            req(locked.get(k)==metrics.get(k),f'E2E Challenger preserves actual Forward KPI 1:1: {k}')
        req(locked.get('evidence_source')=='GOLDEN_FORWARD_EVIDENCE','Propagated KPI evidence source is explicit')
        kpi=json.loads((run/'kpi_report.json').read_text(encoding='utf-8'))
        req(kpi.get('evidence_source')=='GOLDEN_FORWARD_EVIDENCE','KPI report marks Golden Forward evidence source')
        req((kpi.get('onnx_parity') or {}).get('evidence_source')=='SYNTHETIC_E2E','Synthetic E2E-only ONNX promotion proof is explicitly labelled')
    print('V0123_CHALLENGER_PAGE_EVIDENCE_PARITY_SELFTEST PASS')
if __name__=='__main__': main()
