from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from core.project_paths import MODELLAB_ROOT
from acceptance.runners.acceptance_process_env import acceptance_utf8_env
import ui.ui_bootstrap as ui_bootstrap

ROOT = MODELLAB_ROOT
ENV_CANONICAL_PYTHON = "MAX_MTF_CANONICAL_PYTHON"
ENV_CANONICAL_VENV = "MAX_MTF_CANONICAL_VENV"
ENV_BOOTSTRAP_PYTHON = "MAX_MTF_BOOTSTRAP_PYTHON"
SUPPORTED = (3, 12)
UNAVAILABLE_REASON = "CANONICAL_MAX_PYTHON_UNAVAILABLE"


def _norm(value: str | Path) -> str:
    p = Path(str(value)).expanduser()
    try:
        p = p.resolve()
    except Exception:
        p = p.absolute()
    text = str(p)
    return os.path.normcase(text) if os.name == "nt" else text


def _fail(reason: str, *, detail: str | None = None, exit_code: int = 103) -> int:
    payload = {"status": "FAIL", "reason": reason}
    if detail:
        payload["detail"] = detail
    print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
    return int(exit_code)


def resolve_bootstrap_python(ensure_func: Callable[[], str | None] | None = None) -> str | None:
    """Return the existing/supported Python 3.12 bootstrap executable.

    This is the *only* supported interpreter discovery/install authority.  PATH Python is
    allowed to execute this function, but is never accepted as the MAX runtime merely
    because it launched the bootstrap process.
    """
    func = ensure_func or ui_bootstrap.ensure_python312
    exe = func()
    return str(Path(exe).resolve()) if exe else None


def canonical_target_command(canonical_python: str | Path, module: str, args: Sequence[str] = ()) -> list[str]:
    return [str(Path(canonical_python)), "-m", str(module), *[str(x) for x in args]]


def _canonical_env(base: dict[str, str] | None, *, canonical_python: Path, canonical_venv: Path, bootstrap_python: str) -> dict[str, str]:
    env = dict(base or os.environ)
    env[ENV_CANONICAL_PYTHON] = str(canonical_python)
    env[ENV_CANONICAL_VENV] = str(canonical_venv)
    env[ENV_BOOTSTRAP_PYTHON] = str(bootstrap_python)
    return acceptance_utf8_env(env)


def validate_current_is_canonical(expected: str | Path | None = None) -> Path:
    expected_value = str(expected or os.environ.get(ENV_CANONICAL_PYTHON) or "").strip()
    if not expected_value:
        raise RuntimeError("CANONICAL_MAX_PYTHON_IDENTITY_UNBOUND")
    actual = Path(sys.executable).resolve()
    if _norm(actual) != _norm(expected_value):
        raise RuntimeError(f"CANONICAL_MAX_PYTHON_IDENTITY_MISMATCH: actual={actual} expected={expected_value}")
    if sys.version_info[:2] != SUPPORTED:
        raise RuntimeError(f"CANONICAL_MAX_PYTHON_VERSION_MISMATCH: {sys.version.split()[0]}")
    return actual


def _run_python312_stage(module: str, target_args: Sequence[str], *, bootstrap_python: str) -> int:
    if sys.version_info[:2] != SUPPORTED:
        return _fail(UNAVAILABLE_REASON, detail=f"bootstrap stage is {sys.version.split()[0]}, expected Python 3.12")

    try:
        import ui.ui_launcher as ui_launcher

        ui_launcher.ensure_env()
        canonical_python = ui_launcher.venv_python().resolve()
        canonical_venv = ui_launcher.VENV.resolve()
        if not canonical_python.is_file():
            return _fail(UNAVAILABLE_REASON, detail=f"canonical MAX venv Python missing: {canonical_python}")

        env = _canonical_env(
            os.environ,
            canonical_python=canonical_python,
            canonical_venv=canonical_venv,
            bootstrap_python=bootstrap_python,
        )
        cmd = canonical_target_command(canonical_python, module, target_args)
        cp = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
        return int(cp.returncode)
    except Exception as exc:
        return _fail(UNAVAILABLE_REASON, detail=f"{type(exc).__name__}: {exc}")


def run_target(module: str, target_args: Sequence[str] = ()) -> int:
    launch_python = str(Path(sys.executable).resolve())
    bootstrap_python = resolve_bootstrap_python()
    if not bootstrap_python:
        return _fail(UNAVAILABLE_REASON, detail="supported Python 3.12 could not be resolved or installed")

    # Always establish the canonical environment from the concrete supported Python 3.12
    # interpreter. This prevents an unsupported PATH Python (for example 3.14) from
    # becoming MAX runtime authority.
    if sys.version_info[:2] == SUPPORTED and _norm(sys.executable) == _norm(bootstrap_python):
        return _run_python312_stage(module, target_args, bootstrap_python=launch_python)

    cmd = [bootstrap_python, "-m", "acceptance.runners.max_python_bootstrap", "--python312-stage", "--bootstrap-python", launch_python, "--run-module", module]
    if target_args:
        cmd.extend(["--", *[str(x) for x in target_args]])
    try:
        cp = subprocess.run(cmd, cwd=ROOT, env=acceptance_utf8_env(os.environ), check=False)
        return int(cp.returncode)
    except Exception as exc:
        return _fail(UNAVAILABLE_REASON, detail=f"failed to enter Python 3.12 bootstrap: {type(exc).__name__}: {exc}")


def _split_target_args(values: list[str]) -> list[str]:
    return values[1:] if values and values[0] == "--" else values


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-module", required=True)
    ap.add_argument("--python312-stage", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--bootstrap-python", default=None, help=argparse.SUPPRESS)
    args, rest = ap.parse_known_args()
    target_args = _split_target_args(rest)

    if args.python312_stage:
        bootstrap = str(args.bootstrap_python or Path(sys.executable).resolve())
        return _run_python312_stage(args.run_module, target_args, bootstrap_python=bootstrap)
    return run_target(args.run_module, target_args)


if __name__ == "__main__":
    raise SystemExit(main())
