from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = MODELLAB_ROOT
TARGET = (3, 12)
APP_VERSION = "2.0.1"
LOG = ROOT / "bootstrap.log"


def log(msg: str) -> None:
    print(msg, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _run_capture(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        log(f"[BOOT] Gagal menjalankan {' '.join(cmd)}: {exc}")
        return None


def _is_target(exe: str | Path) -> bool:
    exe = str(exe)
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "-c", "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 19)"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _registry_candidates() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except Exception:
        return []

    result: list[Path] = []
    hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = (0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0))
    keys = (
        r"Software\Python\PythonCore\3.12\InstallPath",
        r"Software\Python\PythonCore\3.12-64\InstallPath",
    )
    for hive in hives:
        for view in views:
            for key_name in keys:
                try:
                    with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view) as k:
                        install, _ = winreg.QueryValueEx(k, None)
                        result.append(Path(install) / "python.exe")
                except Exception:
                    pass
    return result


def _filesystem_candidates() -> list[Path]:
    result: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if local:
        result.extend([
            Path(local) / "Programs" / "Python" / "Python312" / "python.exe",
            Path(local) / "Python" / "pythoncore-3.12-64" / "python.exe",
            Path(local) / "Python" / "pythoncore-3.12" / "python.exe",
        ])
    for base in (program_files, program_files_x86):
        if base:
            result.extend([
                Path(base) / "Python312" / "python.exe",
                Path(base) / "Python 3.12" / "python.exe",
            ])
    return result


def discover_python312() -> str | None:
    candidates: list[str | Path] = []

    # Current bootstrap interpreter may itself already be the desired runtime.
    if sys.version_info[:2] == TARGET:
        candidates.append(sys.executable)

    # Direct executable aliases.
    for name in ("python3.12", "python312"):
        p = shutil.which(name)
        if p:
            candidates.append(p)

    # Ask py.exe, but use the concrete sys.executable it reports afterwards.
    py = shutil.which("py")
    if py:
        r = _run_capture([py, "-3.12", "-c", "import sys; print(sys.executable)"], timeout=20)
        if r and r.returncode == 0 and r.stdout:
            lines = [x.strip() for x in r.stdout.splitlines() if x.strip()]
            if lines:
                candidates.append(lines[-1])

    candidates.extend(_registry_candidates())
    candidates.extend(_filesystem_candidates())

    seen: set[str] = set()
    for c in candidates:
        try:
            key = str(Path(c).resolve()).lower()
        except Exception:
            key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        if _is_target(c):
            return str(c)
    return None


def _install_with_python_manager() -> bool:
    py = shutil.which("py")
    if not py:
        return False
    # New Python Install Manager supports `py install 3.12`.
    probe = _run_capture([py, "help", "install"], timeout=15)
    if not probe or probe.returncode != 0:
        return False
    log("[BOOT] Python 3.12 belum ada. Mencoba Python Install Manager...")
    try:
        rc = subprocess.call([py, "install", "3.12"], cwd=ROOT)
        return rc == 0
    except Exception as exc:
        log(f"[BOOT] Python Install Manager gagal: {exc}")
        return False


def _install_with_legacy_launcher() -> bool:
    py = shutil.which("py")
    if not py:
        return False
    env = os.environ.copy()
    env["PYLAUNCHER_ALLOW_INSTALL"] = "1"
    log("[BOOT] Mencoba auto-install Python 3.12 melalui Python Launcher/WinGet...")
    try:
        rc = subprocess.call(
            [py, "-3.12", "-c", "import sys; print(sys.executable)"],
            cwd=ROOT,
            env=env,
        )
        return rc == 0
    except Exception as exc:
        log(f"[BOOT] Auto-install launcher gagal: {exc}")
        return False


def _install_with_winget() -> bool:
    winget = shutil.which("winget")
    if not winget:
        return False
    log("[BOOT] Menginstal Python 3.12 per-user melalui WinGet...")
    cmd = [
        winget, "install", "-e", "--id", "Python.Python.3.12",
        "--scope", "user", "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity", "--silent",
    ]
    try:
        return subprocess.call(cmd, cwd=ROOT) == 0
    except Exception as exc:
        log(f"[BOOT] WinGet gagal: {exc}")
        return False


def ensure_python312() -> str | None:
    exe = discover_python312()
    if exe:
        return exe

    # Try each installer path independently, rediscovering the concrete executable after each.
    for installer in (_install_with_python_manager, _install_with_legacy_launcher, _install_with_winget):
        try:
            installer()
        except Exception as exc:
            log(f"[BOOT] Installer error: {exc}")
        exe = discover_python312()
        if exe:
            return exe
    return None


def main() -> int:
    if "--layout-smoke" in sys.argv:
        import importlib.util, json
        target = ROOT / "ui" / "ui_launcher.py"
        ok = ROOT.is_dir() and target.is_file() and importlib.util.find_spec("ui.ui_launcher") is not None
        print(json.dumps({"status":"PASS" if ok else "FAIL","modellab_root":str(ROOT),"target":str(target),"module":"ui.ui_launcher"}, sort_keys=True))
        return 0 if ok else 2
    try:
        LOG.write_text("", encoding="utf-8")
    except Exception:
        pass
    log(f"[BOOT] Max Research Agent · ONNX Factory v{APP_VERSION}: mencari Python 3.12...")
    exe = ensure_python312()
    if not exe:
        log("")
        log("[BOOT] GAGAL menemukan/memasang Python 3.12.")
        log("[BOOT] Python lain di komputer TIDAK dihapus atau diubah.")
        log("[BOOT] Detail percobaan tersimpan di bootstrap.log.")
        log("[BOOT] Install Python 3.12 x64 side-by-side, lalu jalankan START_UI.cmd lagi.")
        return 103

    log(f"[BOOT] Python 3.12 terverifikasi: {exe}")
    # Important: invoke the concrete interpreter path, never `py -3.12` again.
    return subprocess.call([exe, "-m", "ui.ui_launcher"], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
