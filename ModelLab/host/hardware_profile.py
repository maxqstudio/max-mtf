from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

SCHEMA = "CP_HARDWARE_PROFILE_V1"


def _cmd(args: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        cp = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=timeout, check=False)
        return int(cp.returncode), str(cp.stdout or "").strip()
    except Exception as exc:
        return 999, str(exc)


def _cpu_name() -> str:
    name = str(platform.processor() or "").strip()
    if name:
        return name
    if os.name == "nt":
        rc, out = _cmd(["wmic", "cpu", "get", "name", "/value"], timeout=5)
        if rc == 0:
            for line in out.splitlines():
                if line.lower().startswith("name="):
                    return line.split("=", 1)[1].strip()
    return str(platform.machine() or "unknown")


def _memory() -> dict[str, Any]:
    """Return host RAM without requiring psutil.

    psutil remains the preferred source. On Windows, where a frozen/lean Python
    environment may not have psutil installed, GlobalMemoryStatusEx is the OS
    authority and avoids silently reporting 0 GiB. On POSIX, sysconf is a final
    best-effort fallback. Unknown values stay None; they are never fabricated.
    """
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            return {
                "total_bytes": int(vm.total),
                "available_bytes": int(vm.available),
                "total_gib": round(float(vm.total) / (1024**3), 3),
                "available_gib": round(float(vm.available) / (1024**3), 3),
                "source": "PSUTIL",
            }
        except Exception:
            pass
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            ms = MEMORYSTATUSEX(); ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                total=int(ms.ullTotalPhys); avail=int(ms.ullAvailPhys)
                return {
                    "total_bytes": total, "available_bytes": avail,
                    "total_gib": round(float(total)/(1024**3),3),
                    "available_gib": round(float(avail)/(1024**3),3),
                    "source": "WINDOWS_GLOBALMEMORYSTATUSEX",
                }
        except Exception:
            pass
    try:
        page=int(os.sysconf("SC_PAGE_SIZE")); pages=int(os.sysconf("SC_PHYS_PAGES")); avail_pages=int(os.sysconf("SC_AVPHYS_PAGES"))
        total=page*pages; avail=page*avail_pages
        if total > 0:
            return {
                "total_bytes": total, "available_bytes": avail,
                "total_gib": round(float(total)/(1024**3),3),
                "available_gib": round(float(avail)/(1024**3),3),
                "source": "POSIX_SYSCONF",
            }
    except Exception:
        pass
    return {"total_bytes": None, "available_bytes": None, "total_gib": None, "available_gib": None, "source": "UNAVAILABLE"}


def _physical_core_topology() -> dict[str, Any]:
    """Return physical cores without relabelling logical SMT threads as physical.

    When physical topology cannot be observed, ``physical_cores`` remains None and
    ``planning_cores`` uses a conservative logical/2 estimate for scheduling only.
    """
    logical=max(1,int(os.cpu_count() or 1))
    if psutil is not None:
        try:
            n=psutil.cpu_count(logical=False)
            if n:
                return {"physical_cores":max(1,int(n)),"logical_threads":logical,"planning_cores":max(1,int(n)),"source":"PSUTIL"}
        except Exception:
            pass
    if os.name == "nt":
        # CIM is available on supported Windows 11 systems even when legacy WMIC is absent.
        ps=shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            rc,out=_cmd([ps,"-NoProfile","-NonInteractive","-Command",
                "($n=(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum); if($null -ne $n){[Console]::Write([int]$n)}"],timeout=8)
            if rc==0:
                try:
                    n=int(str(out).strip())
                    if n>0:
                        return {"physical_cores":n,"logical_threads":logical,"planning_cores":n,"source":"WINDOWS_CIM"}
                except Exception:
                    pass
        rc,out=_cmd(["wmic","cpu","get","NumberOfCores","/value"],timeout=5)
        if rc==0:
            vals=[]
            for line in out.splitlines():
                if line.lower().startswith("numberofcores="):
                    try: vals.append(int(line.split("=",1)[1].strip()))
                    except Exception: pass
            if vals and sum(vals)>0:
                n=sum(vals); return {"physical_cores":n,"logical_threads":logical,"planning_cores":n,"source":"WMIC"}
    planning=max(1,logical//2 if logical>=4 else logical)
    return {"physical_cores":None,"logical_threads":logical,"planning_cores":planning,"source":"CONSERVATIVE_LOGICAL_ESTIMATE"}


def _disk() -> dict[str, Any]:
    try:
        du = shutil.disk_usage(os.getcwd())
        return {
            "total_bytes": int(du.total),
            "free_bytes": int(du.free),
            "free_gib": round(float(du.free) / (1024**3), 3),
        }
    except Exception:
        return {"total_bytes": None, "free_bytes": None, "free_gib": None}


def _nvidia() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    fields = "name,memory.total,memory.free,driver_version,compute_cap"
    rc, out = _cmd([exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"], timeout=8)
    if rc != 0:
        # Older nvidia-smi builds may not expose compute_cap in the query interface.
        rc, out = _cmd([exe, "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"], timeout=8)
    if rc != 0:
        return []
    devices = []
    for idx, line in enumerate(out.splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        try:
            total_mb = int(float(parts[1])) if len(parts) > 1 and parts[1] else None
        except Exception:
            total_mb = None
        try:
            free_mb = int(float(parts[2])) if len(parts) > 2 and parts[2] else None
        except Exception:
            free_mb = None
        devices.append({
            "index": idx,
            "name": parts[0],
            "memory_total_mb": total_mb,
            "memory_free_mb": free_mb,
            "memory_total_gib": round(total_mb / 1024.0, 3) if total_mb is not None else None,
            "memory_free_gib": round(free_mb / 1024.0, 3) if free_mb is not None else None,
            "driver": parts[3] if len(parts) > 3 else None,
            "compute_capability": parts[4] if len(parts) > 4 else None,
        })
    return devices


def _torch() -> dict[str, Any]:
    result = {"installed": False, "cuda_available": False, "cuda_version": None, "torch_version": None, "devices": []}
    try:
        import torch
        result["installed"] = True
        result["torch_version"] = str(getattr(torch, "__version__", ""))
        result["cuda_version"] = str(getattr(getattr(torch, "version", None), "cuda", None) or "") or None
        result["cuda_available"] = bool(torch.cuda.is_available())
        if result["cuda_available"]:
            for i in range(int(torch.cuda.device_count())):
                p = torch.cuda.get_device_properties(i)
                result["devices"].append({
                    "index": i,
                    "name": str(p.name),
                    "memory_total_mb": int(p.total_memory // (1024 * 1024)),
                    "major": int(getattr(p, "major", 0)),
                    "minor": int(getattr(p, "minor", 0)),
                })
    except Exception as exc:
        result["error"] = str(exc)[:500]
    return result


def collect_hardware_profile() -> dict[str, Any]:
    mem = _memory()
    nvidia = _nvidia()
    torch = _torch()
    topology = _physical_core_topology()
    cpu = {
        "name": _cpu_name(),
        "physical_cores": topology.get("physical_cores"),
        "logical_threads": topology.get("logical_threads"),
        "planning_cores": topology.get("planning_cores"),
        "core_count_source": topology.get("source"),
        "architecture": platform.machine(),
    }
    payload = {
        "schema": SCHEMA,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version()},
        "cpu": cpu,
        "memory": mem,
        "disk": _disk(),
        "nvidia": {"detected": bool(nvidia), "devices": nvidia},
        "torch": torch,
    }
    canonical = json.dumps({k: v for k, v in payload.items() if k != "captured_utc"}, sort_keys=True, separators=(",", ":"), default=str)
    payload["profile_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def summarize_hardware_profile(profile: dict[str, Any]) -> dict[str, Any]:
    gpus = list(((profile.get("nvidia") or {}).get("devices") or []))
    primary = gpus[0] if gpus else {}
    mem = profile.get("memory") or {}
    return {
        "cpu": (profile.get("cpu") or {}).get("name"),
        "physical_cores": (profile.get("cpu") or {}).get("physical_cores"),
        "logical_threads": (profile.get("cpu") or {}).get("logical_threads"),
        "planning_cores": (profile.get("cpu") or {}).get("planning_cores"),
        "core_count_source": (profile.get("cpu") or {}).get("core_count_source"),
        "ram_total_gib": mem.get("total_gib"),
        "ram_source": mem.get("source"),
        "ram_available_gib": mem.get("available_gib"),
        "gpu": primary.get("name") if primary else None,
        "vram_total_gib": primary.get("memory_total_gib") if primary else None,
        "vram_free_gib": primary.get("memory_free_gib") if primary else None,
        "cuda_available": bool((profile.get("torch") or {}).get("cuda_available")),
        "profile_hash": profile.get("profile_hash"),
    }
