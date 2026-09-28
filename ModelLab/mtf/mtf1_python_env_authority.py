from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from host.accelerator_bootstrap import TORCH_VERSION
from mtf.mtf1_closure_run import read_run

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
EVIDENCE = PKG / 'owner_acceptance/runtime/MTF1_CLOSURE_PYTHON_ENV.json'
SCHEMA = 'MAX_MTF1_CLOSURE_PYTHON_ENV_V1'
ENV_REQUIRED = 'MAX_MTF_CLOSURE_ENV_REQUIRED'
ENV_EVIDENCE = 'MAX_MTF_CLOSURE_PYTHON_ENV_EVIDENCE'
ENV_EXPECTED_PYTHON = 'MAX_MTF_CLOSURE_EXPECTED_PYTHON'
TARGET_PYTHON = (3, 12)

CLOSURE_STAGE_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('closure_run_start', 'mtf.mtf1_closure_run', ('--start',)),
    ('local_acceptance', 'acceptance.runners.run_acceptance', ()),
    ('owner_runtime_acceptance', 'acceptance.runners.owner_mtf1_runtime_acceptance', ()),
    ('owner_metaeditor_acceptance', 'acceptance.runners.owner_mtf1_metaeditor_acceptance', ()),
    ('final_closure_write', 'mtf.mtf1_final_closure', ()),
    ('final_closure_verify', 'mtf.mtf1_final_closure', ('--verify-existing',)),
)


class ClosurePythonEnvironmentError(RuntimeError):
    pass


def _norm_path(value: str | Path) -> str:
    p = Path(str(value)).expanduser()
    try:
        p = p.resolve()
    except Exception:
        p = p.absolute()
    text = str(p)
    return os.path.normcase(text) if os.name == 'nt' else text


def build_stage_plan(canonical_python: str | Path) -> list[dict[str, Any]]:
    py = _norm_path(canonical_python)
    rows: list[dict[str, Any]] = []
    for stage, module, args in CLOSURE_STAGE_SPECS:
        rows.append({
            'stage': stage,
            'module': module,
            'script': module.rsplit('.', 1)[-1] + '.py',
            'interpreter': py,
            'args': list(args),
            'command': [py, '-m', module, *args],
        })
    return rows


def _probe_code() -> str:
    return r'''import json, sys
out={
 "sys_executable":sys.executable,
 "python_version":sys.version.split()[0],
 "python_major_minor":[sys.version_info.major,sys.version_info.minor],
 "sys_prefix":sys.prefix,
 "sys_base_prefix":getattr(sys,"base_prefix",sys.prefix),
 "in_venv":bool(sys.prefix != getattr(sys,"base_prefix",sys.prefix)),
 "torch_installed":False,
 "torch_version":None,
 "torch_cuda_version":None,
 "cuda_available":False,
 "cpu_tensor_test":False,
 "cuda_tensor_test":False,
}
try:
 import torch
 out["torch_installed"]=True
 out["torch_version"]=str(torch.__version__)
 out["torch_cuda_version"]=str(torch.version.cuda or "") or None
 try:
  x=torch.arange(16,dtype=torch.float32,device="cpu").reshape(4,4)
  out["cpu_tensor_test"]=bool(float((x @ x.T).sum().detach().cpu()) > 0)
 except Exception as exc:
  out["cpu_error"]=str(exc)
 out["cuda_available"]=bool(torch.cuda.is_available())
 if out["cuda_available"]:
  try:
   x=torch.arange(16,dtype=torch.float32,device="cuda").reshape(4,4)
   y=(x @ x.T).sum(); torch.cuda.synchronize()
   out["cuda_tensor_test"]=bool(float(y.detach().cpu()) > 0)
  except Exception as exc:
   out["cuda_error"]=str(exc)
except Exception as exc:
 out["torch_error"]=str(exc)
print(json.dumps(out,sort_keys=True))'''


def probe_interpreter(python_exe: str | Path) -> dict[str, Any]:
    py = _norm_path(python_exe)
    try:
        cp = subprocess.run(
            [py, '-c', _probe_code()], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=90,
        )
    except Exception as exc:
        raise ClosurePythonEnvironmentError(f'CANONICAL_PYTHON_PROBE_FAILED: {exc}') from exc
    if cp.returncode != 0:
        raise ClosurePythonEnvironmentError(
            f'CANONICAL_PYTHON_PROBE_EXIT_NONZERO: {cp.returncode}: {(cp.stderr or cp.stdout or "")[-1200:]}'
        )
    try:
        payload = json.loads((cp.stdout or '').strip().splitlines()[-1])
    except Exception as exc:
        raise ClosurePythonEnvironmentError('CANONICAL_PYTHON_PROBE_JSON_INVALID') from exc
    if not isinstance(payload, dict):
        raise ClosurePythonEnvironmentError('CANONICAL_PYTHON_PROBE_NOT_OBJECT')
    return payload


def _torch_base_version(value: Any) -> str:
    return str(value or '').split('+', 1)[0]


def validate_identity(
    identity: Mapping[str, Any], *, canonical_python: str | Path, canonical_venv: str | Path,
    accelerator_target: str,
) -> dict[str, Any]:
    expected_py = _norm_path(canonical_python)
    actual_py = _norm_path(str(identity.get('sys_executable') or ''))
    if actual_py != expected_py:
        raise ClosurePythonEnvironmentError(f'CANONICAL_PYTHON_IDENTITY_MISMATCH: expected={expected_py} actual={actual_py}')
    major_minor = identity.get('python_major_minor')
    if list(major_minor or []) != list(TARGET_PYTHON):
        raise ClosurePythonEnvironmentError(f'CANONICAL_PYTHON_VERSION_MISMATCH: {major_minor!r}')
    if not bool(identity.get('in_venv')):
        raise ClosurePythonEnvironmentError('CANONICAL_PYTHON_NOT_VENV')
    expected_venv = _norm_path(canonical_venv)
    actual_prefix = _norm_path(str(identity.get('sys_prefix') or ''))
    if actual_prefix != expected_venv:
        raise ClosurePythonEnvironmentError(f'CANONICAL_VENV_PREFIX_MISMATCH: expected={expected_venv} actual={actual_prefix}')
    if not bool(identity.get('torch_installed')):
        raise ClosurePythonEnvironmentError('CANONICAL_TORCH_MISSING')
    if _torch_base_version(identity.get('torch_version')) != TORCH_VERSION:
        raise ClosurePythonEnvironmentError(
            f'CANONICAL_TORCH_VERSION_MISMATCH: expected={TORCH_VERSION} actual={identity.get("torch_version")!r}'
        )
    if not bool(identity.get('cpu_tensor_test')):
        raise ClosurePythonEnvironmentError('CANONICAL_TORCH_CPU_CAPABILITY_FAIL')
    target = str(accelerator_target or '').upper()
    if target not in {'CPU', 'CUDA'}:
        raise ClosurePythonEnvironmentError(f'CANONICAL_ACCELERATOR_TARGET_INVALID: {target!r}')
    if target == 'CUDA' and not (bool(identity.get('cuda_available')) and bool(identity.get('cuda_tensor_test'))):
        raise ClosurePythonEnvironmentError('CANONICAL_TORCH_CUDA_CAPABILITY_FAIL')
    return dict(identity)


def write_environment_evidence(
    *, closure_run_id: str, canonical_python: str | Path, canonical_venv: str | Path,
    identity: Mapping[str, Any], accelerator_result: Mapping[str, Any],
    requirements_digest: str, path: Path = EVIDENCE,
) -> dict[str, Any]:
    validated = validate_identity(
        identity, canonical_python=canonical_python, canonical_venv=canonical_venv,
        accelerator_target=str(accelerator_result.get('target') or ''),
    )
    payload = {
        'schema': SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': 'MTF_1_FINAL_CLOSURE',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'authority': 'ONE_CANONICAL_MAX_VENV_INTERPRETER_FOR_FULL_CLOSURE_CHAIN',
        'closure_run_id': str(closure_run_id),
        'canonical_python': _norm_path(canonical_python),
        'canonical_venv': _norm_path(canonical_venv),
        'requirements_digest': str(requirements_digest),
        'accelerator_bootstrap': {
            'schema': accelerator_result.get('schema'),
            'status': accelerator_result.get('status'),
            'target': accelerator_result.get('target'),
        },
        'interpreter_identity': validated,
        'stage_plan': build_stage_plan(canonical_python),
        'rule': 'Every final-closure child stage must be launched with canonical_python; no arbitrary system Python stage execution is allowed.',
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    tmp.replace(p)
    return payload


def read_environment_evidence(path: Path = EVIDENCE) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ClosurePythonEnvironmentError(f'CLOSURE_PYTHON_ENV_EVIDENCE_MISSING: {p}')
    try:
        payload = json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc:
        raise ClosurePythonEnvironmentError(f'CLOSURE_PYTHON_ENV_EVIDENCE_UNREADABLE: {exc}') from exc
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA:
        raise ClosurePythonEnvironmentError('CLOSURE_PYTHON_ENV_SCHEMA_MISMATCH')
    return payload


def verify_environment_evidence(
    payload_or_path: Mapping[str, Any] | Path = EVIDENCE, *, closure_run_id: str | None = None,
    require_current_process: bool = False,
) -> dict[str, Any]:
    payload = read_environment_evidence(Path(payload_or_path)) if isinstance(payload_or_path, (str, Path)) else dict(payload_or_path)
    if payload.get('schema') != SCHEMA or payload.get('project') != 'Max MTF' or payload.get('version') != '2.0.1':
        raise ClosurePythonEnvironmentError('CLOSURE_PYTHON_ENV_IDENTITY_MISMATCH')
    run_id = str(closure_run_id or payload.get('closure_run_id') or '')
    if not run_id or str(payload.get('closure_run_id') or '') != run_id:
        raise ClosurePythonEnvironmentError('CLOSURE_PYTHON_ENV_RUN_ID_MISMATCH')
    canonical_python = str(payload.get('canonical_python') or '')
    canonical_venv = str(payload.get('canonical_venv') or '')
    accelerator = payload.get('accelerator_bootstrap') or {}
    identity = payload.get('interpreter_identity') or {}
    validate_identity(
        identity, canonical_python=canonical_python, canonical_venv=canonical_venv,
        accelerator_target=str(accelerator.get('target') or ''),
    )
    expected_plan = build_stage_plan(canonical_python)
    actual_plan = payload.get('stage_plan')
    if actual_plan != expected_plan:
        raise ClosurePythonEnvironmentError('CLOSURE_PYTHON_ENV_STAGE_PLAN_MISMATCH')
    if any(_norm_path(row.get('interpreter') or '') != _norm_path(canonical_python) for row in expected_plan):
        raise ClosurePythonEnvironmentError('CLOSURE_PYTHON_ENV_STAGE_INTERPRETER_DIVERGENCE')
    if require_current_process:
        if _norm_path(sys.executable) != _norm_path(canonical_python):
            raise ClosurePythonEnvironmentError(
                f'CLOSURE_CURRENT_PROCESS_INTERPRETER_MISMATCH: expected={canonical_python} actual={sys.executable}'
            )
        if sys.version_info[:2] != TARGET_PYTHON:
            raise ClosurePythonEnvironmentError(f'CLOSURE_CURRENT_PROCESS_PYTHON_VERSION_MISMATCH: {sys.version.split()[0]}')
    return payload


def assert_current_process_if_required(stage: str, *, path: Path | None = None) -> dict[str, Any] | None:
    if os.environ.get(ENV_REQUIRED) != '1':
        return None
    evidence_path = Path(path or os.environ.get(ENV_EVIDENCE) or EVIDENCE)
    run = read_run(required=True)
    payload = verify_environment_evidence(
        evidence_path, closure_run_id=str(run.get('closure_run_id') or ''), require_current_process=True,
    )
    stages = {str(row.get('stage')) for row in (payload.get('stage_plan') or []) if isinstance(row, Mapping)}
    if stage not in stages:
        raise ClosurePythonEnvironmentError(f'CLOSURE_STAGE_NOT_AUTHORIZED: {stage}')
    expected = os.environ.get(ENV_EXPECTED_PYTHON)
    if expected and _norm_path(expected) != _norm_path(payload.get('canonical_python') or ''):
        raise ClosurePythonEnvironmentError('CLOSURE_EXPECTED_PYTHON_ENV_MISMATCH')
    return payload


def final_closure_binding(*, closure_run_id: str, path: Path = EVIDENCE, require_current_process: bool = True) -> dict[str, Any]:
    path = Path(path)
    payload = verify_environment_evidence(path, closure_run_id=closure_run_id, require_current_process=require_current_process)
    evidence_sha256 = __import__('hashlib').sha256(path.read_bytes()).hexdigest()
    identity = payload['interpreter_identity']
    accel = payload['accelerator_bootstrap']
    return {
        'schema': payload['schema'],
        'closure_run_id': payload['closure_run_id'],
        'environment_evidence_sha256': evidence_sha256,
        'sys_executable': identity['sys_executable'],
        'python_version': identity['python_version'],
        'venv_path': payload['canonical_venv'],
        'torch_version': identity['torch_version'],
        'torch_cpu_tensor_test': bool(identity['cpu_tensor_test']),
        'torch_cuda_available': bool(identity['cuda_available']),
        'torch_cuda_tensor_test': bool(identity['cuda_tensor_test']),
        'torch_cuda_version': identity.get('torch_cuda_version'),
        'accelerator_target': accel.get('target'),
        'requirements_digest': payload.get('requirements_digest'),
        'stage_interpreter_authority': 'ONE_CANONICAL_MAX_VENV_INTERPRETER_FOR_FULL_CLOSURE_CHAIN',
    }
