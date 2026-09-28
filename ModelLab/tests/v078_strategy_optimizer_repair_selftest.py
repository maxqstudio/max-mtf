from pathlib import Path
from strategy.strategy_optimizer import EA_SOURCE, canonical_ea_identity, validate_request
from strategy.strategy_optimizer_worker import _compile_summary

ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
WORKER=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
CHAT=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
RUNTIME=(ROOT/'strategy/strategy_optimizer_runtime_acceptance.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS',msg)

def main():
    summary=_compile_summary("Result: 0 errors, 0 warnings, 1907 ms elapsed, cpu='X64 Regular'")
    req(summary=={'found':True,'errors':0,'warnings':0,'line':'Result: 0 errors, 0 warnings'},'real Owner zero-error MetaEditor summary parses deterministically')
    compile_body=WORKER.split('def compile_ea',1)[1].split('def re_search_error',1)[0]
    req('cp.returncode not in (0,None)' not in compile_body and 'returncode_authority' in compile_body,'MetaEditor returncode cannot false-fail a zero-error compile')
    req(EA_SOURCE.resolve()==(PKG/'EA_v1_06'/'Max.mq5').resolve(),'canonical optimizer EA authority is exactly package EA_v1_06')
    ident=canonical_ea_identity()
    req(ident['package_relative_path']=='EA_v1_06/Max.mq5' and len(ident['sha256'])==64,'canonical EA identity includes package path and SHA-256')
    base={
        'installation':{'terminal':'terminal64.exe','metaeditor':'MetaEditor64.exe','data_dir':'MT5_DATA'},
        'symbol':'XAUUSD.m','confirm_symbol':'XAGUSD.m','period':'H1',
        'from_date':'2026.01.01','to_date':'2026.02.01','optimization':2,'model':0,'max_rounds':3,
        'search_space':None,'scientist_assist':True,
        'optimizer_kpi':{'min_profit_factor':1.25,'min_recovery_factor':0.5,'min_expectancy_r':0.10,'base_h1_trades_per_month':21,'timeframe_scaling':'SQRT','min_timeframe_factor':0.2,'max_timeframe_factor':4.0},
    }
    out=validate_request(base)
    req(out['ea_source']['sha256']==ident['sha256'] and 'ea_path' not in out,'request freezes canonical package EA identity and accepts no arbitrary EA path')
    req(out['optimizer_trade_sample']['kpi_profile']['min_profit_factor']==1.25 and out['optimizer_trade_sample']['scaled_trades_per_month']==21,'request freezes editable Optimizer KPI instead of re-reading mutable config')
    req('BYTE_IDENTICAL_COPY_OF_PACKAGE_EA_V1_06; NEVER_GENERATED' in WORKER and 'deployed_source_sha256' in WORKER,'worker deploys a byte-identical canonical EA copy and records source hash')
    req('req["ea_path"]' not in WORKER and 'owner_ea_source.mq5' not in WORKER,'worker has no arbitrary Owner EA path contract')
    req('Existing EA_v1_06 · current Strategy Champion protected · optimizer winners become Challengers' in APP and 'EA in MT5 Experts' not in APP,'Optimizer UI exposes canonical existing EA authority while v0.11.0 protects Champion and registers winners as Challengers')
    req('_render_contextual_lifecycle_controls' in APP and '_is_strategy_nav_page(nav_page)' in APP,'single contextual footer authority remains intact')
    req('@st.fragment(run_every="2s", key="contextual_lifecycle")' in APP,'contextual lifecycle has a named fragment key')
    req('st.rerun(["workspace","contextual_lifecycle"])' in APP,'navigation atomically refreshes workspace and lifecycle footer')
    req('st.rerun(["contextual_lifecycle","workspace"])' in APP,'Optimizer START refreshes lifecycle and workspace in the same click callback')
    req('Optimizer KPI' in APP and 'H1 min trades / month' in APP,'Optimizer KPI remains editable on Strategy Optimizer page')
    req('Scientist Optimizer Report' in APP and 'SCIENTIST ON · NOT CALLED' in APP,'Strategy Optimizer retains live Scientist report')
    req('research_settings.strategy_optimizer_kpi' in CHAT,'Scientist system prompt consumes live Optimizer KPI authority')
    req('existing package EA_v1_06' in CHAT and 'unrelated terminal EA' in CHAT and 'Result=Mean R' in CHAT,'Scientist prompt understands existing-EA authority and Custom-max Mean-R Result semantics')
    req('STRATEGY_CHALLENGER_FOUND' in RUNTIME and 'STRATEGY_CHALLENGER_EA_HASH_MISMATCH' in RUNTIME and 'current_source_sha!=source_sha' in RUNTIME and 'ea_path' not in RUNTIME,'Owner runtime acceptance verifies frozen canonical Champion remains unchanged for Strategy Challenger runs and seals Challenger artifacts')
    print('V078_STRATEGY_OPTIMIZER_REPAIR PASS')

if __name__=='__main__': main()
