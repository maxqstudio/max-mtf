from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
TREE=ast.parse(APP)

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)

def func_node(name):
    for n in TREE.body:
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name:
            return n
    raise AssertionError(f'missing function: {name}')

def main():
    # Owner visual contract: preserve the proven grouping; repair spacing only.
    req('key="advanced_section"' not in APP,'no Advanced multiple-choice/radio navigation')
    req('key="scientist_settings_section"' not in APP,'no Scientist multiple-choice/radio navigation')
    req('key="advanced_gate_kpi_selected"' not in APP,'KPI by Gate stays one vertical flow, not radio navigation')

    # Related controls remain together on the same Advanced page.
    groups=(
        'with st.expander("Research",expanded=True):',
        'with st.expander("Scientist",expanded=True):',
        'with st.expander("KPI & Evaluation",expanded=True):',
        'with st.expander("Compute & hardware",expanded=True):',
        'with st.expander("Legacy diagnostics",expanded=False):',
    )
    for label in groups:
        req(label in APP,f'Advanced top-level grouping preserved: {label}')
    for stale in ('Research Control · AUTO / MANUAL','Supervisor & Scientist creativity','Champion Factory settings','Research authority'):
        req(f'with st.expander("{stale}"' not in APP,f'fragmented Advanced group removed: {stale}')


    llm=func_node('llm_provider_controls')
    src=ast.get_source_segment(APP,llm) or ''
    for text in (
        'Provider','OpenAI-compatible base URL','Primary model','Fallback models · ordered',
        'Scientist Chat fallback · explicit/manual','Scientist Chat · per-model profile',
        'Token pricing · optional cost estimator',
    ):
        req(text in src,f'Scientist related control retained in one grouped flow: {text}')

    # Secondary detail disclosures are visually flattened, not card-in-card.
    req('Nested disclosures are semantic detail rows, not cards-in-cards.' in APP,'nested detail disclosure visual contract present')
    req('[data-testid="stExpander"] [data-testid="stExpander"]{border:0!important' in APP,'nested disclosures are borderless/flat')

    # Proven Data/stage grouping from the accepted pre-hierarchy visual baseline is restored.
    req('with st.expander("Dataset identity · Clean master CSV", expanded=True)' in APP,'Data identity grouping restored')
    req('_subsection_header("Adaptive model research"' in APP and '_render_adaptive_model_research(cfg)' in APP,'adaptive model research is grouped inside the Research section')

    # Scientific/runtime authorities remain present.
    for text in ('global_research_start','factory_global_pause_','factory_global_stop_','factory_global_resume_','factory_global_abort_'):
        req(text in APP,f'global lifecycle authority preserved: {text}')

    print('UI_GROUPING_R1_SELFTEST PASS')

if __name__=='__main__':
    main()
