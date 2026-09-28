from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

from ui.ui_bootstrap import ensure_python312, log
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs

ROOT = MODELLAB_ROOT
REQ = ROOT / "requirements" / "requirements-ui-acceptance.txt"
EXPECTED_PLAYWRIGHT = "1.57.0"


def _acceptance_venv() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "CPML" / "ui-acceptance312"
    return Path.home() / ".cpml" / "ui-acceptance312"


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _digest() -> str:
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def _ensure_acceptance_env(py312: str) -> Path:
    target = _acceptance_venv()
    marker = target / ".requirements.sha256"
    py = _venv_python(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not py.exists():
        log(f"[UI ACCEPTANCE] membuat acceptance-only venv: {target}")
        subprocess.check_call([py312, "-m", "venv", str(target)], cwd=ROOT, env=acceptance_utf8_env())

    wanted = _digest()
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    version_ok = False
    try:
        actual = subprocess.check_output(
            [str(py), "-c", "import importlib.metadata as m; print(m.version('playwright'))"],
            cwd=ROOT, env=acceptance_utf8_env(), text=True, stderr=subprocess.DEVNULL, timeout=20,
            **utf8_text_subprocess_kwargs(),
        ).strip()
        version_ok = actual == EXPECTED_PLAYWRIGHT
    except Exception:
        pass

    if current != wanted or not version_ok:
        log("[UI ACCEPTANCE] memasang acceptance-only Playwright Python package...")
        env = acceptance_utf8_env(os.environ)
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "-r", str(REQ)], cwd=ROOT, env=env)
        marker.write_text(wanted, encoding="utf-8")
    else:
        log("[UI ACCEPTANCE] acceptance dependency sudah sesuai.")

    subprocess.check_call([str(py), "-m", "pip", "check"], cwd=ROOT, env=acceptance_utf8_env())
    return py


def main() -> int:
    log("[UI ACCEPTANCE] mencari Python 3.12...")
    exe = ensure_python312()
    if not exe:
        log("[UI ACCEPTANCE] GAGAL menemukan/memasang Python 3.12.")
        return 103
    log(f"[UI ACCEPTANCE] Python 3.12 terverifikasi: {exe}")

    try:
        accept_py = _ensure_acceptance_env(exe)
    except Exception as exc:
        log(f"[UI ACCEPTANCE] GAGAL menyiapkan acceptance environment: {exc}")
        return 104

    log("[UI ACCEPTANCE] menjalankan real Streamlit browser acceptance...")
    return subprocess.call([str(accept_py), "-m", "acceptance.runners.ui_runtime_browser_acceptance"], cwd=ROOT, env=acceptance_utf8_env())


if __name__ == "__main__":
    raise SystemExit(main())
