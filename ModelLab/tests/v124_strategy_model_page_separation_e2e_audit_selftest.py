from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
GOV=(ROOT/'factory/governance.py').read_text(encoding='utf-8')
E2E=(ROOT/'research/research_e2e.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond: raise AssertionError(msg)

pages='pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]'
req(pages in APP,'navigation must separate model and strategy Challenger/Champion authorities')
req('def _render_model_challengers_stage' in APP and 'def _render_model_champion_stage' in APP,'dedicated model pages missing')
req('def _render_strategy_challengers_stage' in APP and 'def _render_strategy_champion_stage' in APP,'dedicated strategy pages missing')
req('_render_strategy_challenger_registry(cfg)' in APP and '_render_model_challenger_registry(cfg)' in APP,'registry renderers missing')
req('"Strategy + Model registries"' not in APP and '"Strategy + Model"' not in APP,'combined Strategy+Model page authority must be removed')
req('elif page=="Model Challengers": _render_model_challengers_stage(cfg)' in APP,'Model Challengers route missing')
req('elif page=="Model Champion": _render_model_champion_stage(cfg)' in APP,'Model Champion route missing')
req('elif page=="Strategy Challengers": _render_strategy_challengers_stage(cfg)' in APP,'Strategy Challengers route missing')
req('elif page=="Strategy Champion": _render_strategy_champion_stage(cfg)' in APP,'Strategy Champion route missing')
req('state["current_champion"] = entry' in GOV,'post-promotion supervisor state must point to newly promoted Champion')
req("'factory_lifecycle_status':('ELIGIBLE_CHALLENGER' if core.get('status') in {'FACTORY_WINNER','CHAMPION'} else core.get('status'))" in E2E,'E2E report must disambiguate legacy internal CHAMPION from Model lifecycle authority')
print('V1.2.4 STRATEGY/MODEL PAGE SEPARATION + E2E AUDIT SELFTEST PASS')
