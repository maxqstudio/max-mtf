from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import ui.ui_bootstrap as ui_bootstrap
ROOT = MODELLAB_ROOT


def _norm(value: str | Path) -> str:
    p = Path(str(value)).expanduser()
    try:
        p = p.resolve()
    except Exception:
        p = p.absolute()
    text = str(p)
    return os.path.normcase(text) if os.name == 'nt' else text


def _run_bootstrap_entry() -> int:
    exe = ui_bootstrap.ensure_python312()
    if not exe:
        print(json.dumps({'status': 'FAIL', 'reason': 'PYTHON_3_12_BOOTSTRAP_UNAVAILABLE'}, indent=2), file=sys.stderr)
        return 103
    cp = subprocess.run([str(exe), str(Path(__file__).resolve()), '--canonical'], cwd=ROOT, check=False)
    return int(cp.returncode)


def _ensure_canonical_environment():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(f'CLOSURE_BOOTSTRAP_REQUIRES_PYTHON_3_12: {sys.version.split()[0]}')
    import ui.ui_launcher as ui_launcher
    from host.accelerator_bootstrap import TORCH_VERSION, install_torch_for_host, nvidia_detected, torch_cuda_probe
    from mtf.mtf1_python_env_authority import probe_interpreter, validate_identity

    ui_launcher.ensure_env()
    canonical_python = ui_launcher.venv_python()
    if not canonical_python.is_file():
        raise RuntimeError(f'CANONICAL_VENV_PYTHON_MISSING: {canonical_python}')

    probe = torch_cuda_probe(str(canonical_python))
    torch_base = str(probe.get('torch_version') or '').split('+', 1)[0]
    need_repair = (
        not bool(probe.get('installed'))
        or torch_base != TORCH_VERSION
        or (nvidia_detected() and not (probe.get('cuda_available') and probe.get('tensor_test')))
    )
    if need_repair:
        accel = install_torch_for_host(str(canonical_python), pip_env=ui_launcher._pip_env(), force=True)
    else:
        accel = install_torch_for_host(str(canonical_python), pip_env=ui_launcher._pip_env(), force=False)
    (ui_launcher.VENV / '.accelerator_bootstrap.json').write_text(json.dumps(accel, indent=2, sort_keys=True), encoding='utf-8')
    if accel.get('status') != 'READY':
        raise RuntimeError(f'CANONICAL_ACCELERATOR_BOOTSTRAP_FAILED: {accel.get("error") or accel.get("status")}')

    identity = probe_interpreter(canonical_python)
    validate_identity(
        identity, canonical_python=canonical_python, canonical_venv=ui_launcher.VENV,
        accelerator_target=str(accel.get('target') or ''),
    )
    return ui_launcher, canonical_python, accel, identity


def _run_canonical_chain() -> int:
    from mtf.mtf1_closure_run import read_run
    from mtf.mtf1_python_env_authority import (
        ENV_EVIDENCE, ENV_EXPECTED_PYTHON, ENV_REQUIRED, EVIDENCE,
        build_stage_plan, write_environment_evidence,
    )

    ui_launcher, canonical_python, accel, identity = _ensure_canonical_environment()
    plan = build_stage_plan(canonical_python)
    if not plan:
        raise RuntimeError('CLOSURE_STAGE_PLAN_EMPTY')

    # Start the shared closure nonce with the canonical venv interpreter first.
    first = plan[0]
    cp = subprocess.run(first['command'], cwd=ROOT, check=False)
    if cp.returncode != 0:
        return int(cp.returncode)
    run = read_run(required=True)
    run_id = str(run.get('closure_run_id') or '')
    if not run_id:
        raise RuntimeError('CLOSURE_RUN_ID_MISSING_AFTER_START')

    write_environment_evidence(
        closure_run_id=run_id,
        canonical_python=canonical_python,
        canonical_venv=ui_launcher.VENV,
        identity=identity,
        accelerator_result=accel,
        requirements_digest=ui_launcher.digest_requirements(),
        path=EVIDENCE,
    )

    env = os.environ.copy()
    env[ENV_REQUIRED] = '1'
    env[ENV_EVIDENCE] = str(EVIDENCE)
    env[ENV_EXPECTED_PYTHON] = _norm(canonical_python)

    for row in plan[1:]:
        cp = subprocess.run(row['command'], cwd=ROOT, env=env, check=False)
        if cp.returncode != 0:
            return int(cp.returncode)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--canonical', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--audit-plan', metavar='CANONICAL_PYTHON', help='Print the production closure stage plan without executing stages.')
    args = ap.parse_args()
    try:
        if args.audit_plan:
            from mtf.mtf1_python_env_authority import build_stage_plan
            print(json.dumps({'status': 'PASS', 'stage_plan': build_stage_plan(args.audit_plan)}, indent=2))
            return 0
        return _run_canonical_chain() if args.canonical else _run_bootstrap_entry()
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'reason': str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
