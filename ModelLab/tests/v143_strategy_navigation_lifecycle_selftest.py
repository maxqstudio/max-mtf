from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def main():
    req('STRATEGY_NAV_PAGES=frozenset({"Strategy Optimizer","Strategy Challengers","Strategy Champion"})' in APP,
        'canonical Strategy navigation domain contains Optimizer + Challengers + Champion')
    req('def _is_strategy_nav_page(page: str) -> bool:' in APP and 'return str(page) in STRATEGY_NAV_PAGES' in APP,
        'single Strategy-domain predicate owns contextual routing')
    lifecycle=APP.split('def _render_contextual_lifecycle_controls',1)[1].split('def _render_left_panel',1)[0]
    req('if _is_strategy_nav_page(nav_page):' in lifecycle and '_rehydrate_persisted_ui_state(prefix="strategy_opt_")' in lifecycle and '_render_global_optimizer_controls_body(cfg)' in lifecycle and '_render_global_research_controls_body(cfg)' in lifecycle,
        'all Strategy pages restore durable Optimizer setup and route footer lifecycle to Optimizer while non-Strategy pages route to Research')
    req('if nav_page=="Strategy Optimizer"' not in lifecycle,
        'contextual footer no longer special-cases only Strategy Optimizer')
    workspace=APP.split('def _workspace_fragment',1)[1].split('@st.fragment(run_every="1s", key="scientist")',1)[0]
    req('if _is_strategy_nav_page(nav_page):' in workspace and 'OPTIMIZER IDLE' in workspace and 'MT5 round' in workspace,
        'all Strategy pages render Optimizer status chips instead of Research status')
    nav=APP.split('def _render_nav_page',1)[1].split('def _set_left_open',1)[0]
    req('if _is_strategy_nav_page(page):' in nav and '_rehydrate_persisted_ui_state(prefix="strategy_opt_")' in nav,
        'Optimizer durable settings rehydrate on Strategy Challengers/Champion pages too')
    req('START AUTO OPTIMIZER' in APP and 'global_optimizer_start' in APP,
        'Strategy-domain footer preserves canonical START AUTO OPTIMIZER action')
    req('START RESEARCH' in APP and '_render_global_research_controls_body' in APP,
        'Research lifecycle remains available outside Strategy domain')
    print('V143_STRATEGY_NAVIGATION_LIFECYCLE_SELFTEST PASS')


if __name__=='__main__':
    main()
