from __future__ import annotations
import json
import re
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

from factory.challenger_registry import release_human_challenger_artifacts, register_eligible_challenger, load_challenger_registry, publish_challenger_to_terminal
from strategy.strategy_optimizer import ABSOLUTE_BOUNDS, read_ea_optimizer_defaults


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)


def main():
    # Imported Strategy Optimizer Champion must be the packaged EA defaults while
    # v0.9.1 risk/audit runtime remains present.
    auth=json.loads((PKG/'EA_v1_06'/'CHAMPION_IMPORTED_PARAMETERS.json').read_text(encoding='utf-8'))
    defaults=read_ea_optimizer_defaults(PKG/'EA_v1_06'/'Max.mq5')
    expected=auth.get('optimizer_params') or {}
    req(set(expected)==set(ABSOLUTE_BOUNDS),'imported Champion must carry the complete optimizer-owned parameter vector')
    for name in ABSOLUTE_BOUNDS:
        req(abs(float(defaults[name])-float(expected[name])) <= 1e-10*max(1.0,abs(float(expected[name]))),f'EA Champion default mismatch: {name}')
    ea=(PKG/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    req('OrderCalcProfit' in ea and 'RISK_MIN_VOLUME_EXCEEDS_CAP' in ea,'risk-cap repair must survive Champion merge')
    req('Max_Champion_Trades.csv' in ea and 'Max_Shadow_Trades.csv' in ea,'v0.9.1 isolated Champion/Shadow audit must survive Champion merge')

    with tempfile.TemporaryDirectory() as td:
        base=Path(td); app=base/'ModelLab'; app.mkdir(); (app/'governance').mkdir()
        # Standalone Challenger release: human readable, unique by family+UTC run time, no SHA filename.
        run=base/'runs'/'AGENT_20260916_223501_UTC'; run.mkdir(parents=True)
        (run/'challenger.onnx').write_bytes(b'onnx-standalone')
        manifest={
            'run_id':run.name,'status':'ELIGIBLE_CHALLENGER','model_family':'lstm','model_name':'LSTM_Trial_7',
            'generated_utc':'2026-09-16T22:35:01+00:00','locked_test_trading':{'trades':88,'profit_factor':1.71,'expectancy_r':0.12,'max_drawdown_r':6.2,'recovery_factor':3.1}
        }
        art=release_human_challenger_artifacts(run,manifest)
        fname=art['files']['standalone']
        req(fname=='Challenger_LSTM_20260916_223501.onnx',f'unexpected human Challenger name: {fname}')
        req(not re.search(r'[0-9a-fA-F]{32,}',fname),'Challenger filename must not expose hash identity')
        req((run/fname).read_bytes()==b'onnx-standalone','human Challenger artifact bytes mismatch')
        req((run/'challenger.onnx').exists(),'compatibility challenger.onnx alias must remain for existing research consumers')
        manifest['challenger_artifact']=art
        register_eligible_challenger(run,manifest,app)
        reg=load_challenger_registry(app)
        req(len(reg['entries'])==1 and reg['entries'][0]['challenger_id']==art['challenger_id'],'eligible Challenger must register once')
        req(reg['entries'][0]['locked_test_kpi']['profit_factor']==1.71,'registry must carry Challenger KPI')
        terminal=base/'TerminalFiles'; terminal.mkdir()
        pub=publish_challenger_to_terminal(run,terminal,manifest)
        req(pub['ea_mutated'] is False,'Shadow publish must never mutate EA inputs')
        req((terminal/'models'/fname).exists(),'Shadow publish must preserve human-readable filename')
        req(pub['manual_ea_parameters']['InpChallengerModel'].endswith(fname),'EA manual parameter must reference human-readable Challenger filename')

        # Same human timestamp with different bytes must receive a readable collision suffix
        # and a distinct Challenger ID rather than silently overwriting the first identity.
        (run/'challenger.onnx').write_bytes(b'onnx-standalone-v2')
        art2=release_human_challenger_artifacts(run,manifest)
        req(art2['files']['standalone']=='Challenger_LSTM_20260916_223501_02.onnx','collision must use human _02 suffix')
        req(art2['challenger_id'].endswith('-02') and art2['challenger_id']!=art['challenger_id'],'collision must produce unique human Challenger ID')

        # Hybrid produces a readable pair rather than an opaque hash or generic shared filename.
        hrun=base/'runs'/'FRESH_20260916_224002_UTC'; hrun.mkdir(parents=True)
        (hrun/'challenger_temporal.onnx').write_bytes(b'temporal')
        (hrun/'challenger_policy_model.onnx').write_bytes(b'policy')
        hm={'run_id':hrun.name,'status':'ELIGIBLE_CHALLENGER','model_family':'hybrid::gru::lightgbm','model_name':'GRU_LGBM','generated_utc':'2026-09-16T22:40:02+00:00'}
        ha=release_human_challenger_artifacts(hrun,hm)
        req(ha['topology']=='TEMPORAL_TO_TREE_HYBRID','hybrid topology identity')
        req(ha['files']['temporal']=='Challenger_GRU-LightGBM_20260916_224002_Temporal.onnx','human hybrid temporal filename')
        req(ha['files']['policy_model']=='Challenger_GRU-LightGBM_20260916_224002_Policy.onnx','human hybrid policy filename')
        req(ha['manual_ea_parameters']['InpChallengerHybrid']=='true','hybrid manual EA identity')

    app_src=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    gov=(ROOT/'factory/governance.py').read_text(encoding='utf-8')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('PROMOTE SELECTED CHALLENGER' in app_src and 'Model Challengers' in app_src,'Model Challengers page must centralize model Challenger list and explicit promotion button')
    req('PUBLISH FOR SHADOW' in app_src and 'EA unchanged' in app_src,'Shadow publishing must be explicit and non-mutating')
    req('register_eligible_challenger' in sup,'Research must register eligible Challengers automatically')
    req('source_challenger_id' in gov and 'champion_temporal.onnx' in gov and 'champion_policy_model.onnx' in gov,'promotion must preserve Challenger lineage and support hybrid Champion pair')
    req('mark_challenger_promoted' in gov,'promotion must update Challenger registry status')
    print('V010_CHALLENGER_LIFECYCLE_SELFTEST PASS')


if __name__=='__main__':
    main()
