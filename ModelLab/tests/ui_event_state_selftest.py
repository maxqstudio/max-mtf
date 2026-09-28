from __future__ import annotations
import ast
from pathlib import Path
from core.settings_store import sanitize_ui_state, is_persistable_ui_key

ROOT=Path(__file__).resolve().parents[1]

def check(cond,msg):
    if not cond:
        raise AssertionError(msg)

def _sample_key(expr):
    if expr is None:
        return None
    if isinstance(expr, ast.Constant):
        return str(expr.value)
    if isinstance(expr, ast.JoinedStr):
        out=[]
        for v in expr.values:
            if isinstance(v,ast.Constant): out.append(str(v.value))
            else: out.append('X')
        return ''.join(out)
    try:
        return ast.unparse(expr)
    except Exception:
        return '<dynamic>'

def main():
    # Safe persistence is allowlist-based. Unknown/new widget keys are transient by default.
    safe=['nav_page_v071','guided_run_select','factory_selected','factory_source','factory_path','main_research_date_range']
    for key in safe:
        check(is_persistable_ui_key(key), f'stable operator state should persist: {key}')
    for key in ['compute_rescan','factory_start_btn','global_research_start','new_future_button','llm_api_key_input','provider_token','my_secret','password_field']:
        check(not is_persistable_ui_key(key), f'event/sensitive/unknown key must not persist: {key}')

    clean=sanitize_ui_state({
        'nav_page_v071':'Advanced',
        'factory_selected':'FACTORY_X',
        'compute_rescan':True,
        'new_future_button':True,
        'llm_api_key_input':'SECRET_TEST_VALUE',
        'advanced_llm_enable':True,
    })
    check(clean=={'nav_page_v071':'Advanced','factory_selected':'FACTORY_X'}, f'allowlist leak: {clean}')

    # Static guard: every explicitly-keyed Streamlit button in app.py must be non-persistable.
    app_path=ROOT/'ui/app.py'
    tree=ast.parse(app_path.read_text(encoding='utf-8'))
    button_keys=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call): continue
        fn=node.func
        if not (isinstance(fn,ast.Attribute) and fn.attr=='button'): continue
        key_expr=None
        for kw in node.keywords:
            if kw.arg=='key': key_expr=kw.value; break
        if key_expr is None: continue
        sample=_sample_key(key_expr)
        button_keys.append((node.lineno,sample))
        check(not is_persistable_ui_key(sample), f'button key persistence regression line {node.lineno}: {sample}')
    check(len(button_keys)>=10, 'button AST audit unexpectedly found too few explicit keys')

    app=app_path.read_text(encoding='utf-8')
    check('key="global_research_start"' in app, 'global START RESEARCH widget missing')
    check('else "STOP"' in app and 'button("RESUME"' in app and 'button("PAUSE"' in app, 'global lifecycle controls incomplete')
    check('pending_research_start' in app and 'STARTING…' in app and 'cp-busy-spinner' in app, 'START RESEARCH must disable immediately and show visible startup loading')
    check('pending_research_stop' in app and 'STOPPING…' in app, 'STOP must expose immediate in-flight state')
    print(f'UI_EVENT_STATE_SELFTEST PASS · buttons audited {len(button_keys)}')

if __name__=='__main__':
    main()
