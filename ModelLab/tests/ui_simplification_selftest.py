from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    exact='pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]'
    req(exact in app,'Research Control Room plus detailed stage inspectors are the top-level workflow')
    tail=app[app.index(exact):]
    req('"Pipeline","Guided Research"' not in tail,'Legacy Pipeline/Guided are not parallel top-level routes')
    req('elif page=="CPCV": _render_cpcv_stage(cfg)' in app,'CPCV remains a separate top-level stage inspector rather than a Discovery subflow')
    req('_render_advanced_stage' in app and 'Legacy diagnostics' in app,'Legacy evidence remains auditable under Advanced')
    print('UI_SIMPLIFICATION_SELFTEST PASS')

if __name__=='__main__': main()
