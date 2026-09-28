from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import mtf.mtf1_closure_bootstrap as bootstrap
import mtf.mtf1_python_env_authority as envauth
ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / 'RUN_MTF1_FINAL_CLOSURE.cmd'


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)


cmd_text = CMD.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n')
req('python -m mtf.mtf1_closure_bootstrap' in cmd_text or 'py -m mtf.mtf1_closure_bootstrap' in cmd_text, 'one-click closure enters production environment bootstrap')
req('set "PYTHONPATH=%~dp0;%PYTHONPATH%"' in cmd_text, 'one-click closure exposes ModelLab import root before bootstrap Python imports core/ui authority')
for stage_script in (
    'mtf1_closure_run.py', 'run_acceptance.py', 'owner_mtf1_runtime_acceptance.py',
    'owner_mtf1_metaeditor_acceptance.py', 'mtf1_final_closure.py',
):
    raw = f'python {stage_script}'
    req(raw not in cmd_text, f'CMD has no raw system-Python stage call: {stage_script}')

bootstrap_source = (ROOT / 'mtf/mtf1_closure_bootstrap.py').read_text(encoding='utf-8')
req('ui_bootstrap.ensure_python312()' in bootstrap_source, 'closure bootstrap reuses existing Python 3.12 discovery/install authority')
req('ui_launcher.ensure_env()' in bootstrap_source and 'ui_launcher.venv_python()' in bootstrap_source,
    'closure bootstrap reuses canonical MAX venv creation/dependency authority')
req('install_torch_for_host' in bootstrap_source and 'torch_cuda_probe' in bootstrap_source,
    'closure bootstrap verifies/repairs pinned accelerator dependency stack')

fake_py = Path('C:/MAX_CANONICAL/.cpml/venv312/Scripts/python.exe')
plan = envauth.build_stage_plan(fake_py)
req(len(plan) == 6, 'production closure plan contains exactly six required child stages')
req([row['stage'] for row in plan] == [x[0] for x in envauth.CLOSURE_STAGE_SPECS], 'production stage order is canonical')
canon = envauth._norm_path(fake_py)
req(all(row['interpreter'] == canon and row['command'][0] == canon for row in plan), 'every production child stage uses one canonical venv interpreter')
req(plan[0]['module'] == 'mtf.mtf1_closure_run' and plan[0]['args'] == ['--start'], 'shared closure_run_id starts under canonical interpreter')
req(plan[-1]['module'] == 'mtf.mtf1_final_closure' and plan[-1]['args'] == ['--verify-existing'], 'read-only final verification uses same canonical interpreter')

# Execute the production bootstrap CLI while actively making torch unavailable to the bootstrap/system interpreter.
# --audit-plan does not execute Owner stages, but it proves bootstrap discovery/planning itself has no torch dependency.
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / 'sitecustomize.py').write_text(
        "import builtins\n_orig=builtins.__import__\n"
        "def _guard(name,*a,**k):\n"
        "    if name == 'torch' or name.startswith('torch.'): raise ModuleNotFoundError(\"No module named 'torch'\")\n"
        "    return _orig(name,*a,**k)\n"
        "builtins.__import__=_guard\n",
        encoding='utf-8',
    )
    env = os.environ.copy()
    env['PYTHONPATH'] = str(td) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    cp = subprocess.run(
        [sys.executable, str(ROOT / 'mtf/mtf1_closure_bootstrap.py'), '--audit-plan', str(fake_py)],
        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    req(cp.returncode == 0, 'production bootstrap can resolve/plan closure even when bootstrap/system Python cannot import torch')
    audit = json.loads(cp.stdout)
    req(all(row['command'][0] == canon for row in audit['stage_plan']), 'executed production bootstrap plan never substitutes system Python for closure stages')

fake_venv = fake_py.parents[1]
identity = {
    'sys_executable': canon,
    'python_version': '3.12.9',
    'python_major_minor': [3, 12],
    'sys_prefix': envauth._norm_path(fake_venv),
    'sys_base_prefix': envauth._norm_path(Path('C:/Python312')),
    'in_venv': True,
    'torch_installed': True,
    'torch_version': '2.6.0+cpu',
    'torch_cuda_version': None,
    'cuda_available': False,
    'cpu_tensor_test': True,
    'cuda_tensor_test': False,
}
envauth.validate_identity(identity, canonical_python=fake_py, canonical_venv=fake_venv, accelerator_target='CPU')
req(True, 'canonical Python 3.12 venv + pinned Torch CPU capability is accepted')

bad = dict(identity); bad['torch_installed'] = False; bad['torch_version'] = None
try:
    envauth.validate_identity(bad, canonical_python=fake_py, canonical_venv=fake_venv, accelerator_target='CPU')
    accepted = True
except envauth.ClosurePythonEnvironmentError:
    accepted = False
req(not accepted, 'missing Torch in canonical MAX venv fails closed')

bad = dict(identity); bad['python_major_minor'] = [3, 13]
try:
    envauth.validate_identity(bad, canonical_python=fake_py, canonical_venv=fake_venv, accelerator_target='CPU')
    accepted = True
except envauth.ClosurePythonEnvironmentError:
    accepted = False
req(not accepted, 'non-3.12 canonical runtime fails closed')

for rel, stage in (
    ('acceptance/runners/run_acceptance.py', 'local_acceptance'),
    ('acceptance/runners/owner_mtf1_runtime_acceptance.py', 'owner_runtime_acceptance'),
    ('acceptance/runners/owner_mtf1_metaeditor_acceptance.py', 'owner_metaeditor_acceptance'),
    ('mtf/mtf1_final_closure.py', 'final_closure'),
):
    src = (ROOT / rel).read_text(encoding='utf-8')
    req('assert_current_process_if_required' in src, f'{stage} asserts canonical interpreter when run by closure bootstrap')

final_src = (ROOT / 'mtf/mtf1_final_closure.py').read_text(encoding='utf-8')
req("'python_environment': python_binding" in final_src and 'final_closure_binding' in final_src,
    'final closure evidence records and verifies canonical Python/Torch environment identity')

print('V201_FINAL_CLOSURE_PYTHON_ENV_AUTHORITY PASS')
