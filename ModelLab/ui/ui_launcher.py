from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import hashlib
import os
import shutil
import subprocess
import socket
import sys
import venv
from pathlib import Path

from host.accelerator_bootstrap import install_torch_for_host, nvidia_detected, torch_cuda_probe

ROOT = MODELLAB_ROOT
REQ = ROOT / "requirements" / "requirements-ui.txt"
BASE_REQ = ROOT / "requirements" / "requirements.txt"
TARGET = (3, 12)
APP_VERSION = "2.0.1"


def _is_writable_parent(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def select_venv() -> Path:
    override = os.environ.get("CPML_VENV")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    if os.name == "nt" and ROOT.drive:
        candidates.append(Path(ROOT.drive + "\\") / ".cpml" / "venv312")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "CPML" / "venv312")
    candidates.append(Path.home() / ".cpml" / "venv312")

    for candidate in candidates:
        parent = candidate.parent
        if _is_writable_parent(parent):
            return candidate
    raise RuntimeError("Tidak menemukan lokasi pendek yang writable untuk environment Python.")


VENV = select_venv()
MARKER = VENV / ".requirements.sha256"
LEGACY_VENV = ROOT / ".venv"


def digest_requirements() -> str:
    h = hashlib.sha256()
    for p in (REQ, BASE_REQ):
        h.update(p.read_bytes())
    return h.hexdigest()


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _host_version() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _check_host_python() -> None:
    if _host_version() != TARGET:
        raise RuntimeError(
            f"Max Research Agent · ONNX Factory v{APP_VERSION} membutuhkan Python 3.12. "
            f"Interpreter saat ini: {sys.version.split()[0]}. Jalankan START_UI.cmd."
        )


def _venv_version() -> tuple[int, int] | None:
    py = venv_python()
    if not py.exists():
        return None
    try:
        out = subprocess.check_output(
            [str(py), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=15,
        ).strip()
        major, minor = out.split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path, ignore_errors=False)


def _pip_env() -> dict[str, str]:
    env = os.environ.copy()
    short_tmp = VENV.parent / "tmp"
    short_cache = VENV.parent / "pip-cache"
    short_tmp.mkdir(parents=True, exist_ok=True)
    short_cache.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(short_tmp)
    env["TMP"] = str(short_tmp)
    env["PIP_CACHE_DIR"] = str(short_cache)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def ensure_env() -> None:
    _check_host_python()

    # v0.5.4 and older kept .venv inside the deeply nested project folder.
    # Ignore it completely; best-effort cleanup avoids confusion and frees disk.
    if LEGACY_VENV.exists():
        print(f"[1/6] Membersihkan legacy .venv panjang: {LEGACY_VENV}", flush=True)
        try:
            _remove_path(LEGACY_VENV)
        except Exception:
            print("[1/6] Legacy .venv tidak dapat dihapus sekarang; diabaikan.", flush=True)

    print(f"[2/6] Environment pendek: {VENV}", flush=True)
    vv = _venv_version()
    if VENV.exists() and vv != TARGET:
        print("[2/6] Environment lama/rusak, membangun ulang…", flush=True)
        _remove_path(VENV)
        vv = None

    if not venv_python().exists():
        VENV.parent.mkdir(parents=True, exist_ok=True)
        print("[2/6] Membuat Python 3.12 environment…", flush=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)

    wanted = digest_requirements()
    current = MARKER.read_text(encoding="utf-8").strip() if MARKER.exists() else ""
    py = str(venv_python())
    penv = _pip_env()

    print("[3/6] Memeriksa pip…", flush=True)
    subprocess.check_call([py, "-m", "pip", "--version"], cwd=ROOT, env=penv)

    if current != wanted:
        print(f"[4/6] Memasang dependency stack v{APP_VERSION}…", flush=True)
        subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT, env=penv)
        subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "-r", str(BASE_REQ)], cwd=ROOT, env=penv)
        accel = install_torch_for_host(py, pip_env=penv)
        (VENV / ".accelerator_bootstrap.json").write_text(__import__("json").dumps(accel,indent=2,sort_keys=True),encoding="utf-8")
        if accel.get("status") != "READY":
            raise RuntimeError(str(accel.get("error") or accel.get("status")))
        subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "-r", str(REQ)], cwd=ROOT, env=penv)
        MARKER.write_text(wanted, encoding="utf-8")
    else:
        print(f"[4/6] Dependency sudah sesuai v{APP_VERSION}.", flush=True)
        if nvidia_detected():
            probe=torch_cuda_probe(py)
            if not (probe.get("cuda_available") and probe.get("tensor_test")):
                print("[4/6] NVIDIA terdeteksi tetapi PyTorch CUDA tidak usable; repairing pinned CUDA wheel…",flush=True)
                accel=install_torch_for_host(py,pip_env=penv,force=True)
                (VENV / ".accelerator_bootstrap.json").write_text(__import__("json").dumps(accel,indent=2,sort_keys=True),encoding="utf-8")
                if accel.get("status") != "READY":
                    raise RuntimeError(str(accel.get("error") or accel.get("status")))

    print("[5/6] Memeriksa dependency conflicts…", flush=True)
    subprocess.check_call([py, "-m", "pip", "check"], cwd=ROOT, env=penv)


def _free_streamlit_port(start: int = 8501, end: int = 8510) -> int:
    for port in range(int(start),int(end)+1):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                s.bind(("127.0.0.1",port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Tidak ada port Streamlit kosong di {start}-{end}")


def main() -> None:
    ensure_env()
    py = str(venv_python())
    print(f"[6/6] Membuka Max Research Agent · ONNX Factory v{APP_VERSION}…", flush=True)
    print(f"[INFO] Python env: {VENV}", flush=True)
    port=_free_streamlit_port()
    if port!=8501:
        print(f"[INFO] Port 8501 sedang dipakai; memakai port {port} tanpa menghentikan proses lain.",flush=True)
    cmd = [
        py, "-m", "streamlit", "run", str(ROOT / "ui/app.py"),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ]
    raise SystemExit(subprocess.call(cmd, cwd=ROOT, env=_pip_env()))


if __name__ == "__main__":
    main()
