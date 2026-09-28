from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'ModelLab'
EA=ROOT/'EA_v1_06'/'Max.mq5'

def req(cond,msg):
    if not cond: raise AssertionError(msg)

ea=EA.read_text(encoding='utf-8',errors='ignore')
app=(APP/'ui/app.py').read_text(encoding='utf-8')
opt=(APP/'strategy/strategy_optimizer.py').read_text(encoding='utf-8')
gap=(APP/'host/mt5_gap_repair.py').read_text(encoding='utf-8')
registry=json.loads((APP/'config/models/model_registry.json').read_text(encoding='utf-8'))

# Current deployable standalone temporal/tree family universe must be representable
# explicitly in EA settings; hybrid is topology, not a separate model-family enum.
expected={
    'lightgbm':'MODEL_FAMILY_LIGHTGBM',
    'xgboost':'MODEL_FAMILY_XGBOOST',
    'random_forest':'MODEL_FAMILY_RANDOM_FOREST',
    'gru':'MODEL_FAMILY_GRU',
    'lstm':'MODEL_FAMILY_LSTM',
    'tcn':'MODEL_FAMILY_TCN',
    'transformer':'MODEL_FAMILY_TRANSFORMER_ENCODER',
    'patchtst':'MODEL_FAMILY_PATCHTST',
    'itransformer':'MODEL_FAMILY_ITRANSFORMER',
    'tft':'MODEL_FAMILY_TFT',
    'transformer_moe':'MODEL_FAMILY_TRANSFORMER_MOE',
}
for family,token in expected.items():
    req(family in registry['families'] and registry['families'][family].get('deployable') is True,f'{family} must remain deployable in registry')
    req(token in ea,f'EA ONNX family selector missing {family}')
req('InpChampionModelFamily' in ea and 'InpChallengerModelFamily' in ea,'Champion/Shadow model-family selectors required')
req('InpChampionHybridPolicyFamily' in ea and 'InpChallengerHybridPolicyFamily' in ea,'hybrid tree-policy family selectors required')
req('generic temporal model -> classical tree policy' in ea,'hybrid setting wording must be family-generic')
req('GRU direction -> classical policy' not in ea and 'shadow hybrid GRU direction -> classical policy' not in ea,'stale GRU-only runtime labels forbidden')
req('ValidateOnnxTopologyIdentity' in ea and 'IsTemporalModelFamily' in ea,'family/topology identity must be validated fail-closed')

# Champion audit is actual MT5 deal evidence; optimizer fitness remains history-rebuilt.
for token in ('Max_Champion_Trades.csv','InpWriteChampionTrades','OpenTradeAuditCsv','LogChampionDealAudit','TRADE_TRANSACTION_DEAL_ADD','DEAL_POSITION_ID','DEAL_COMMISSION','DEAL_SWAP','DEAL_FEE'):
    req(token in ea,f'Champion trade audit missing {token}')
req('optimizer R fitness is still reconstructed only from complete history' in ea,'OnTradeTransaction audit must not regain optimizer fitness authority')

# Shadow is explicitly non-executing and logs only candidate plans, not fake live fills.
for token in ('Max_Shadow_Trades.csv','InpWriteShadowTrades','LogShadowTradeAudit','SHADOW_ENTRY_CANDIDATE','SHADOW_RISK_REJECT','"executed"'):
    req(token in ea,f'Shadow audit missing {token}')
req('"0");' in ea,'Shadow audit rows must explicitly mark executed=0')
req('CalculateVolume(direction,entry,sl,risk_reason,planned_risk)' in ea,'Shadow audit must expose deterministic planned volume/risk without placing an order')

# Optimizer/gap-repair are not audit CSV writers: no parallel FILE_COMMON contention.
req('"InpWriteChampionTrades": False' in opt and '"InpWriteShadowTrades": False' in opt,'optimizer preset must disable trade-audit CSV writers')
req('"InpWriteChampionTrades":"false"' in gap and '"InpWriteShadowTrades":"false"' in gap,'gap-repair preset must disable unrelated trade-audit writers')

# Latest MAX Matrix UI retained; terminal optimizer state refreshes the lifecycle button promptly.
req('def _render_optimizer_max_matrix' in app and 'MAX Matrix' in app and 'Max_metrics.csv' in app,'latest MAX Matrix UI must be retained')
req('@st.fragment(run_every="2s", key="contextual_lifecycle")' in app,'historical contextual lifecycle heartbeat remains 2s')
req('terminal_statuses={"STRATEGY_CHALLENGER_FOUND","CHAMPION_FOUND","NO_CHAMPION_MAX_ROUNDS","FAILED","STOPPED"}' in app and 'st.rerun(["contextual_lifecycle"])' in app,'terminal optimizer transition must actively wake the lifecycle footer instead of waiting for heartbeat')
req('status in STRATEGY_OPTIMIZER_ACTIVE' in app,'lifecycle active state must use worker authority')
req('START AUTO OPTIMIZER' in app and 'STOP OPTIMIZER' in app,'terminal state must fall back to START while active state alone shows STOP')
req('STRATEGY_CHALLENGER_FOUND' in app and 'NO_CHAMPION_MAX_ROUNDS' in app,'terminal optimizer states must remain explicit in UI')

print('V091_ONNX_AUDIT_UI_SELFTEST PASS')
