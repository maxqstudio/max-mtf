from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS',msg)

req('with st.expander("Research",expanded=True):' in APP,'Advanced groups Research controls under one top-level section')
req('with st.expander("Scientist",expanded=True):' in APP,'Advanced groups Scientist connection/creativity under one top-level section')
req('with st.expander("KPI & Evaluation",expanded=True):' in APP,'Advanced groups KPI and evaluation settings together')
req('with st.expander("Compute & hardware",expanded=True):' in APP,'Compute/hardware remains one dedicated top-level group')
req('with st.expander("Champion Factory settings"' not in APP and 'with st.expander("Research authority"' not in APP,'old fragmented Advanced groups are removed')

req('groups=["Execution","Labels"]' in APP,'Research Policy contains execution/label controls only')
for label in ['Trade sample authority','CPU threads','Walk-forward folds','Seed','Min edge R','Min margin R']:
    req(label in APP,f'policy field preserved: {label}')
req('SL/TP/MaxHold and execution gates are inherited from the promoted Strategy Champion' in APP,'Research UI makes upstream execution geometry inheritance explicit')
req('SL × ATR' not in APP and 'TP × ATR' not in APP and 'Horizon · Strategy locked' not in APP,'Research UI does not duplicate upstream Strategy geometry controls')

req('def render_gate_kpi_controls(cfg: dict):' in APP,'KPI by Gate has a dedicated authority renderer')
for label in ['Discovery','CPCV','Tournament','Monte Carlo','Fresh Forward','Champion Promotion']:
    req(f'_subsection_header("{label}"' in APP,f'KPI gate section preserved: {label}')
for label in ['WFA overall Mean R','WFA median Mean R','WFA worst Mean R','WFA median PF','Worst-fold DD R','Median PF','Worst Mean R','Min path sample ratio','P05 PF','P05 Exp R','P95 Max DD R','Max P(loss)','Max P(ruin)','Min survival','All upstream gates PASS','ONNX parity PASS']:
    req(label in APP,f'per-gate KPI field preserved: {label}')
req('Maximum PBO' in APP and 'cross-strategy CSCV-style PBO' in APP and 'evidence is insufficient, CPCV fails closed' in APP and 'pseudo-PBO is forbidden' in APP,'CPCV exposes optional computable PBO threshold/status semantics')
req('Benchmark Sharpe' in APP and 'cols[2].number_input("Benchmark Sharpe"' in APP,'PSR benchmark stays aligned inside the PSR metric row')
req('_subsection_header("Risk-adjusted metrics"' not in APP,'risk metrics do not create extra gate separators')
req('Each gate owns one independent profile.' in APP,'per-gate independence/freeze contract is visible')

req('section[data-testid="stMain"],.stMain{min-width:0!important;width:auto!important;height:100dvh!important;max-height:100dvh!important;min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important;' in APP,'main workspace is the single bounded vertical scroll owner')
req('[data-testid="stAppViewContainer"],.stApp{height:100dvh!important;max-height:100dvh!important;overflow:hidden!important;}' in APP,'outer app cannot become a competing scroll owner')
req('.block-container{max-width:none!important;width:100%!important;min-height:max-content!important;overflow:visible!important;' in APP,'Advanced content grows naturally inside main scroll owner')
print('ADVANCED_POLICY_LAYOUT_SELFTEST PASS')
