from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
runner = (ROOT / 'acceptance/runners/ui_runtime_browser_acceptance.py').read_text(encoding='utf-8')
bootstrap = (ROOT / 'acceptance/runners/ui_runtime_acceptance_bootstrap.py').read_text(encoding='utf-8')
ps = (ROOT / 'acceptance/runners/RUN_UI_RUNTIME_ACCEPTANCE.ps1').read_text(encoding='utf-8')
req = (ROOT / 'requirements/requirements-ui.txt').read_text(encoding='utf-8')
accept_req = (ROOT / 'requirements/requirements-ui-acceptance.txt').read_text(encoding='utf-8')
app = (ROOT / 'ui/app.py').read_text(encoding='utf-8')


def req_gate(ok, msg):
    if not ok:
        raise AssertionError(msg)

req_gate('streamlit==1.63.0' in req, 'UI runtime must pin Streamlit 1.63.0')
req_gate('playwright==1.57.0' in accept_req, 'acceptance browser dependency must be pinned')
req_gate('REAL_STREAMLIT_1_63_BROWSER_RENDER' in runner, 'runtime evidence class missing')
req_gate('ISOLATED_TEMP_LOCALAPPDATA_WITH_NON_SENDING_CHAT_MODEL_FIXTURE' in runner, 'acceptance settings isolation missing')
req_gate('research_mutation_performed' in runner and 'False' in runner, 'runtime acceptance must declare no research mutation')
req_gate('external_calls_performed' in runner and 'False' in runner, 'runtime acceptance must declare no provider/LLM calls')
req_gate('sync_playwright' in runner and 'executable_path=str(browser_path)' in runner, 'real system-browser Playwright runner missing')
req_gate('CDPClient' not in runner and 'remote-debugging-port' not in runner, 'legacy raw-CDP authority must be removed')
req_gate('ui-acceptance312' in bootstrap, 'acceptance dependency must use isolated venv')
for token in [
    'draft_persists_left_hide', 'draft_persists_scientist_hide',
    'scientist_dom_stays_mounted_when_hidden', 'nav_all_pages_present',
    'history_only_scroll', 'owner_exact_resolution_render',
    'lifecycle_no_duplicate_controls', 'model_context_persist_after_navigation',
    'long_scientist_bubble_contained', 'long_scientist_reply_no_horizontal_overflow',
]:
    req_gate(token in runner, f'missing runtime gate: {token}')
req_gate('st.rerun("shell_state")' in app and 'st.rerun(["workspace","contextual_lifecycle"])' in app, 'event-scoped shell/workspace+lifecycle rerun contract missing')
req_gate('RUN_UI_RUNTIME_ACCEPTANCE.ps1' in ps or 'UI Runtime Acceptance' in ps, 'PowerShell one-click runner missing')
req_gate('_start_auto_background' not in ps and 'factory_start' not in ps.lower(), 'PowerShell acceptance must not invoke research lifecycle code')

# Playwright sync API: Page.wait_for_function(expression, *, arg=None, timeout=None, polling=None).
# Optional arguments must be keyword-only. This guards the Owner-runtime crash exposed by R2.
tree = ast.parse(runner)
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'wait_for_function':
        req_gate(len(node.args) <= 1, 'wait_for_function optional args must be keyword-only (use arg=...)')
req_gate('arg=(width <= 900)' in runner, 'responsive wait_for_function calls must pass slide mode with arg= keyword')

# The shell-state fragment is injected after the base stylesheet. It must scope
# desktop reflow margins so its late CSS cannot override the <=900px slide-over
# zero-margin authority observed in real Streamlit runtime.
req_gate('@media (min-width:901px)' in app, 'ShellState desktop margin rule must be scoped to min-width:901px')
req_gate('@media (max-width:900px)' in app, 'ShellState must explicitly preserve <=900px slide-over geometry')
req_gate('margin-left:0!important;margin-right:0!important;width:100%!important;max-width:100%!important;' in app, 'mobile/tablet ShellState must force full-width zero-margin main workspace')

print('UI_RUNTIME_ACCEPTANCE_CONTRACT_SELFTEST: PASS')
