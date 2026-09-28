from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TORCH_VERSION = "2.6.0"
CUDA_INDEX = "https://download.pytorch.org/whl/cu124"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
SCHEMA = "MAX_ACCELERATOR_BOOTSTRAP_V1"


def _run(args: list[str], *, env: dict | None = None, timeout: int = 300) -> tuple[int, str]:
    try:
        cp = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False, timeout=timeout, env=env)
        return int(cp.returncode), str(cp.stdout or "")
    except Exception as exc:
        return 999, str(exc)


def nvidia_detected() -> bool:
    exe = shutil.which("nvidia-smi")
    if not exe and os.name == "nt":
        pf = os.environ.get("ProgramFiles")
        cand = Path(pf) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe" if pf else None
        if cand and cand.exists():
            exe = str(cand)
    if not exe:
        return False
    rc, _ = _run([str(exe), "--query-gpu=name", "--format=csv,noheader"], timeout=15)
    return rc == 0


def torch_cuda_probe(python_exe: str | None = None) -> dict:
    py = python_exe or sys.executable
    code = '''import json
out={"installed":False,"cuda_available":False,"cuda_version":None,"torch_version":None,"tensor_test":False}
try:
 import torch
 out["installed"]=True
 out["torch_version"]=str(torch.__version__)
 out["cuda_version"]=str(torch.version.cuda or "") or None
 out["cuda_available"]=bool(torch.cuda.is_available())
 if out["cuda_available"]:
  x=torch.arange(16,dtype=torch.float32,device="cuda").reshape(4,4)
  y=(x @ x.T).sum()
  torch.cuda.synchronize()
  out["tensor_test"]=bool(float(y.detach().cpu()) > 0)
except Exception as exc:
 out["error"]=str(exc)
print(json.dumps(out,sort_keys=True))'''
    rc, out = _run([py, "-c", code], timeout=45)
    payload = {"installed": False, "cuda_available": False, "tensor_test": False, "probe_rc": rc}
    for line in reversed(out.splitlines()):
        try:
            obj=json.loads(line.strip())
            if isinstance(obj,dict) and "cuda_available" in obj:
                payload.update(obj); break
        except Exception:
            continue
    if rc != 0 and "error" not in payload:
        payload["error"] = out[-1000:]
    return payload


def install_torch_for_host(python_exe: str, *, pip_env: dict | None = None, force: bool = False) -> dict:
    """Install deterministic PyTorch wheel appropriate for the local host."""
    has_nvidia = nvidia_detected()
    before = torch_cuda_probe(python_exe)
    target = "CUDA" if has_nvidia else "CPU"
    if has_nvidia and before.get("cuda_available") and before.get("tensor_test") and not force:
        return {"schema":SCHEMA,"status":"READY","target":target,"installed":False,"before":before,"after":before}
    if (not has_nvidia) and before.get("installed") and not force:
        return {"schema":SCHEMA,"status":"READY","target":target,"installed":False,"before":before,"after":before}

    index = CUDA_INDEX if has_nvidia else CPU_INDEX
    spec = f"torch=={TORCH_VERSION}"
    rc, output = _run([python_exe,"-m","pip","install","--upgrade","--force-reinstall",spec,"--index-url",index], env=pip_env, timeout=1200)
    after = torch_cuda_probe(python_exe)
    result={"schema":SCHEMA,"target":target,"installed":True,"pip_rc":rc,"before":before,"after":after,"index":index}
    if rc != 0:
        result["status"]="INSTALL_FAILED"; result["error"] = output[-2000:]
        return result
    if has_nvidia and not (after.get("cuda_available") and after.get("tensor_test")):
        result["status"]="CUDA_VERIFY_FAILED"
        result["error"]=("NVIDIA GPU detected but pinned CUDA PyTorch did not pass torch.cuda + tensor execution. "
                         "Fix NVIDIA driver/runtime or explicitly choose CPU mode; MAX must not silently research on CPU.")
        return result
    result["status"]="READY"
    return result
