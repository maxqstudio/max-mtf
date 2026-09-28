from __future__ import annotations

import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP_PATH=ROOT/'ui/app.py'
APP=APP_PATH.read_text(encoding='utf-8')
TREE=ast.parse(APP)


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def func_node(name: str):
    for node in TREE.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name:
            return node
    raise AssertionError(f'function missing: {name}')


def is_expander_call(node):
    if not isinstance(node,ast.Call): return False
    f=node.func
    return isinstance(f,ast.Attribute) and isinstance(f.value,ast.Name) and f.value.id=='st' and f.attr=='expander'


def nested_expander_count(fn_name: str) -> int:
    node=func_node(fn_name)
    total=0
    def walk(n,depth=0):
        nonlocal total
        if isinstance(n,ast.With):
            here=any(is_expander_call(item.context_expr) for item in n.items)
            if here and depth>0:
                total+=1
            for child in n.body:
                walk(child,depth+(1 if here else 0))
            return
        for child in ast.iter_child_nodes(n):
            walk(child,depth)
    walk(node)
    return total


def main():
    # Major workflow pages use flat section hierarchy. Optional dense forensics may
    # still use a first-level disclosure, but decorative card-in-card is forbidden.
    for text in (
        '_section_header("Dataset identity", "Clean master CSV")',
        '_section_header("Research windows", f"Available {lo} → {hi}")',
        '_section_header("Discovery plan", "Research limits & qualification target")',
        '_section_header("Latest Factory evidence", str(fm.get("status") or "UNKNOWN"))',
        '_section_header("Qualified candidate pool", str(fm.get("status") or "UNKNOWN"))',
        '_section_header("Qualification progress", "Purged combinatorial stress qualification")',
        '_section_header("Tournament summary", str(fm.get("status") or "—"))',
        '_section_header("Stress summary", str(fm.get("status") or "—"))',
        '_section_header("Fresh-forward summary", str(fm.get("status") or "LOCKED"))',
        '_section_header("Champion authority", str(status or "UNKNOWN"))',
    ):
        req(text in APP,f'flat workflow section present: {text[:66]}')

    # Advanced is one-level navigation, not nine simultaneous cards.
    req('key="advanced_section"' in APP,'Advanced section selector is the single first-level authority')
    for label in ('Research Control','Scientist','Model Research','Validation','Compute','Factory','Authority','Diagnostics'):
        req(f'"{label}"' in APP,f'Advanced group retained: {label}')
    for obsolete in (
        'with st.expander("Research Control · AUTO / MANUAL"',
        'with st.expander("Scientist connection"',
        'with st.expander("Supervisor & Scientist creativity"',
        'with st.expander("Risk & research KPI gates"',
        'with st.expander("Adaptive model research"',
        'with st.expander("Compute & hardware"',
        'with st.expander("Champion Factory settings"',
        'with st.expander("Research authority"',
        'with st.expander("Legacy diagnostics"',
    ):
        req(obsolete not in APP,f'Advanced decorative card removed: {obsolete[17:58]}')

    # Scientist connection itself is grouped by concern and contains no inner cards.
    req('key="scientist_settings_section"' in APP,'Scientist connection has compact concern selector')
    for label in ('Connection','Routing','Chat profile','Cost'):
        req(f'"{label}"' in APP,f'Scientist configuration group retained: {label}')
    llm=func_node('llm_provider_controls')
    req(not any(is_expander_call(n) for n in ast.walk(llm)),'Scientist connection contains zero nested expanders/cards')

    # No nested expanders in Data→Champion stage renderers. First-level forensic
    # disclosures are allowed and intentionally low-noise.
    for fn in (
        '_render_data_stage','_render_discovery_stage','_render_pool_stage',
        '_render_cpcv_live_inspector','_render_tournament_stage','_render_monte_carlo_stage',
        '_render_forward_stage','_render_champion_stage','_render_advanced_stage',
    ):
        req(nested_expander_count(fn)==0,f'no card-in-card / nested expander in {fn}')

    # Dense evidence is still table-oriented, and optional deep evidence remains
    # collapsible rather than consuming primary whitespace.
    for label in ('Forensics · CPCV evidence','Forensics · Tournament','Forensics · Monte Carlo','Forensics · locked evidence'):
        req(label in APP,f'optional forensic disclosure preserved: {label}')
    req(APP.count('st.dataframe(')>=20,'dense evidence still uses tables')

    # Whitespace/hierarchy primitives and single-workspace scroll authority remain.
    for css in ('.cp-section-head','.cp-subsection','.cp-section-band'):
        req(css in APP,f'hierarchy/whitespace primitive present: {css}')

    # Backend lifecycle authority is untouched by presentation cleanup.
    for text in ('global_research_start','factory_global_pause_','factory_global_stop_','factory_global_resume_','factory_global_abort_'):
        req(text in APP,f'global lifecycle authority preserved: {text}')

    print('UI_INFORMATION_HIERARCHY_SELFTEST PASS')

if __name__=='__main__':
    main()
