from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

from scientist.python.scientist_python_runtime import REQUIREMENTS_FILE, scientist_python_home, scientist_python_executable, scientist_python_health


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def setup(*, repair: bool = False) -> dict:
    home = scientist_python_home()
    venv_dir = home / "venv"
    exe = scientist_python_executable()
    home.mkdir(parents=True, exist_ok=True)
    if repair and venv_dir.exists():
        shutil.rmtree(venv_dir)
    if not exe.exists():
        # The host Python is used only to CREATE another isolated interpreter. Packages are
        # installed only through that new interpreter; canonical MAX site-packages are not modified.
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=False, upgrade=False).create(str(venv_dir))
    if not exe.exists():
        return {"status": "UNAVAILABLE", "analysis_mode": "REASONING_ONLY", "reason": "DEDICATED_VENV_CREATION_FAILED", "home": str(home)}
    cp = subprocess.run(
        [str(exe), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(REQUIREMENTS_FILE)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if cp.returncode != 0:
        return {"status": "ERROR", "analysis_mode": "REASONING_ONLY", "reason": "SCIENTIST_DEPENDENCY_INSTALL_FAILED", "exit_code": cp.returncode, "stderr": cp.stderr[-4000:], "home": str(home)}
    return scientist_python_health()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["setup", "repair", "health"], nargs="?", default="health")
    args = ap.parse_args()
    if args.action == "health":
        obj = scientist_python_health()
        _print(obj)
        return 0 if obj.get("status") in {"READY", "UNAVAILABLE"} else 1
    obj = setup(repair=args.action == "repair")
    _print(obj)
    return 0 if obj.get("status") == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
