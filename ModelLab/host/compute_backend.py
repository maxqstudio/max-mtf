from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from typing import Any

import numpy as np

SCHEMA = "CP_COMPUTE_BACKEND_V1"


def _cmd(args: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, check=False)
        return int(p.returncode), str(p.stdout or "").strip()
    except Exception as exc:
        return 999, str(exc)


def _dll_available(name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        ctypes.WinDLL(name)
        return True
    except Exception:
        return False


def _nvidia_hardware() -> dict:
    exe = shutil.which("nvidia-smi")
    if not exe and os.name == "nt":
        p = os.environ.get("ProgramFiles")
        candidate = os.path.join(p, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe") if p else ""
        if candidate and os.path.exists(candidate):
            exe = candidate
    if not exe:
        return {"detected": False, "devices": []}
    rc, out = _cmd([exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
    devices=[]
    if rc == 0:
        for line in out.splitlines():
            parts=[x.strip() for x in line.split(",")]
            if not parts: continue
            devices.append({
                "name": parts[0],
                "memory_mb": int(float(parts[1])) if len(parts)>1 and parts[1] else None,
                "driver": parts[2] if len(parts)>2 else None,
            })
    return {"detected": bool(devices) or rc == 0, "devices": devices, "probe": out[:500]}


def _vulkan_runtime() -> dict:
    exe = shutil.which("vulkaninfo")
    if exe:
        rc,out=_cmd([exe,"--summary"], timeout=10)
        if rc == 0:
            names=[]
            for line in out.splitlines():
                if "deviceName" in line and "=" in line:
                    names.append(line.split("=",1)[1].strip())
            return {"detected": True, "devices": names, "probe": out[:1200]}
    dll = _dll_available("vulkan-1.dll")
    return {"detected": bool(dll), "devices": [], "probe": "vulkan-1.dll" if dll else ""}


def _opencl_runtime() -> dict:
    """Separate an installed OpenCL loader from actual device evidence.

    ``OpenCL.dll`` alone only proves that a loader/runtime is present. Treating that
    as a usable GPU hint caused LightGBM to execute its GPU TreeLearner probe and
    print a misleading ``[Fatal]`` line on CPU-only machines.
    """
    exe=shutil.which("clinfo")
    if exe:
        rc,out=_cmd([exe,"-l"], timeout=10)
        text=str(out or "").strip()
        device_evidence = rc == 0 and bool(text) and any(
            marker in text.lower() for marker in ("platform", "device", "gpu", "cpu")
        )
        if device_evidence:
            return {"detected": True, "runtime_detected": True, "device_evidence": True, "probe": text[:1200]}
    dll=_dll_available("OpenCL.dll")
    return {
        "detected": bool(dll),
        "runtime_detected": bool(dll),
        "device_evidence": False,
        "probe": "OpenCL.dll loader present; no OpenCL device evidence" if dll else "",
    }


def _torch_runtime() -> dict:
    out={"installed":False,"accelerator":None,"torch_device":"cpu","devices":[],"version":None,"hip":None,"cuda":None}
    try:
        import torch
        out["installed"]=True
        out["version"]=str(getattr(torch,"__version__",""))
        out["hip"]=str(getattr(getattr(torch,"version",None),"hip",None) or "") or None
        out["cuda"]=str(getattr(getattr(torch,"version",None),"cuda",None) or "") or None
        available=bool(torch.cuda.is_available())
        if available:
            accel="ROCM" if out["hip"] else "CUDA"
            out["accelerator"]=accel
            out["torch_device"]="cuda"
            try:
                for i in range(int(torch.cuda.device_count())):
                    p=torch.cuda.get_device_properties(i)
                    out["devices"].append({"index":i,"name":str(p.name),"memory_mb":int(p.total_memory//(1024*1024))})
            except Exception:
                pass
    except Exception as exc:
        out["error"]=str(exc)
    return out


def _probe_xgboost_cuda() -> dict:
    try:
        from xgboost import XGBClassifier
        X=np.asarray([[0.,0.],[1.,0.],[0.,1.],[1.,1.],[2.,0.],[0.,2.]],dtype=np.float32)
        y=np.asarray([0,1,2,0,1,2],dtype=np.int64)
        m=XGBClassifier(n_estimators=2,max_depth=2,objective="multi:softprob",num_class=3,
                        eval_metric="mlogloss",tree_method="hist",device="cuda",n_jobs=1,random_state=1)
        m.fit(X,y)
        _=m.predict_proba(X[:1])
        return {"usable":True}
    except Exception as exc:
        return {"usable":False,"error":str(exc)[:500]}


def _probe_lightgbm_gpu() -> dict:
    """Probe LightGBM GPU out-of-process so expected C++ fatal text stays captured.

    Some CPU-only LightGBM wheels print ``[Fatal] GPU Tree Learner...`` directly from
    native code before raising.  That message used to leak into CPMF logs even though
    AUTO correctly fell back to CPU.  A subprocess makes the capability probe silent
    and converts the native failure into structured capability evidence.
    """
    code = r'''
import json
try:
    import numpy as np
    from lightgbm import LGBMClassifier
    X=np.asarray([[0.,0.],[1.,0.],[0.,1.],[1.,1.],[2.,0.],[0.,2.],[2.,2.],[3.,0.],[0.,3.]],dtype=np.float32)
    y=np.asarray([0,1,2,0,1,2,0,1,2],dtype=np.int64)
    m=LGBMClassifier(n_estimators=2,num_leaves=3,objective="multiclass",num_class=3,
                     device_type="gpu",n_jobs=1,verbosity=-1,random_state=1)
    m.fit(X,y)
    _=m.predict_proba(X[:1])
    print(json.dumps({"usable":True}))
except Exception as exc:
    print(json.dumps({"usable":False,"error":str(exc)[:500]}))
'''
    try:
        cp=subprocess.run([sys.executable,"-c",code],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
        payload=None
        for line in reversed((cp.stdout or "").splitlines()):
            try:
                obj=json.loads(line.strip())
                if isinstance(obj,dict) and "usable" in obj:
                    payload=obj; break
            except Exception:
                continue
        if payload is not None:
            if not payload.get("usable") and cp.stderr:
                payload.setdefault("probe_note","LightGBM native GPU probe failed; stderr captured/suppressed")
            return payload
        err=(cp.stderr or cp.stdout or f"probe exit {cp.returncode}").strip()[-500:]
        return {"usable":False,"error":err or "LightGBM GPU probe returned no result"}
    except Exception as exc:
        return {"usable":False,"error":str(exc)[:500]}


@lru_cache(maxsize=1)
def detect_compute_capabilities() -> dict:
    nvidia=_nvidia_hardware()
    vulkan=_vulkan_runtime()
    opencl=_opencl_runtime()
    torch_rt=_torch_runtime()
    # Only run expensive estimator probes when hardware/runtime hints make them plausible.
    xgb={"usable":False,"reason":"NO_NVIDIA_HINT"}
    if nvidia.get("detected") or torch_rt.get("accelerator")=="CUDA":
        xgb=_probe_xgboost_cuda()
    lgb={"usable":False,"reason":"NO_OPENCL_DEVICE_EVIDENCE"}
    if opencl.get("device_evidence"):
        lgb=_probe_lightgbm_gpu()
    return {
        "schema":SCHEMA,
        "nvidia":nvidia,
        "torch":torch_rt,
        "vulkan":vulkan,
        "opencl":opencl,
        "xgboost_cuda":xgb,
        "lightgbm_gpu":lgb,
        "cpu":{"usable":True,"logical_threads":os.cpu_count() or 1},
    }


def resolve_compute_plan(cfg: dict, refresh: bool=False) -> dict:
    if refresh:
        detect_compute_capabilities.cache_clear()
    caps=detect_compute_capabilities()
    ccfg=cfg.get("compute") or {}
    mode=str(ccfg.get("mode","AUTO")).upper().replace("/HIP","")
    if mode not in {"AUTO","CPU","CUDA","ROCM","VULKAN"}:
        mode="AUTO"
    allow_cuda=bool(ccfg.get("allow_cuda",True)); allow_rocm=bool(ccfg.get("allow_rocm",True))
    allow_opencl=bool(ccfg.get("allow_opencl",True)); allow_vulkan=bool(ccfg.get("allow_vulkan",True))
    fallback=bool(ccfg.get("fallback_cpu",True))
    notes=[]

    torch_acc=str((caps.get("torch") or {}).get("accelerator") or "")
    dl_backend="CPU"; torch_device="cpu"
    xgb_backend="CPU"; lgb_backend="CPU"

    if mode=="AUTO":
        if torch_acc=="CUDA" and allow_cuda:
            dl_backend="CUDA"; torch_device="cuda"
        elif torch_acc=="ROCM" and allow_rocm:
            dl_backend="ROCM"; torch_device="cuda"  # PyTorch HIP intentionally uses torch.device('cuda').
        if allow_cuda and bool((caps.get("xgboost_cuda") or {}).get("usable")):
            xgb_backend="CUDA"
        if allow_opencl and bool((caps.get("lightgbm_gpu") or {}).get("usable")):
            lgb_backend="OPENCL_GPU"
    elif mode=="CUDA":
        if torch_acc=="CUDA" and allow_cuda:
            dl_backend="CUDA"; torch_device="cuda"
        elif not fallback:
            raise RuntimeError("Manual CUDA requested but PyTorch CUDA is unavailable")
        else:
            notes.append("Temporal DL CUDA unavailable -> CPU fallback")
        if allow_cuda and bool((caps.get("xgboost_cuda") or {}).get("usable")):
            xgb_backend="CUDA"
        elif not fallback:
            raise RuntimeError("Manual CUDA requested but XGBoost CUDA is unavailable")
        else:
            notes.append("XGBoost CUDA unavailable -> CPU fallback")
        notes.append("LightGBM has no CUDA training authority in CPMF -> CPU")
    elif mode=="ROCM":
        if torch_acc=="ROCM" and allow_rocm:
            dl_backend="ROCM"; torch_device="cuda"
        elif not fallback:
            raise RuntimeError("Manual ROCm/HIP requested but PyTorch ROCm is unavailable")
        else:
            notes.append("Temporal DL ROCm unavailable -> CPU fallback")
        notes.append("XGBoost has no ROCm GPU backend in CPMF -> CPU")
        notes.append("LightGBM ROCm is not used; manual ROCm keeps non-ROCm workloads on CPU")
    elif mode=="VULKAN":
        detected=allow_vulkan and bool((caps.get("vulkan") or {}).get("detected"))
        if not fallback:
            raise RuntimeError("Manual Vulkan requested, but current CPMF PyTorch/XGBoost/LightGBM training stack has no verified Vulkan training backend")
        notes.append(("Vulkan detected" if detected else "Vulkan unavailable") + "; no verified training backend -> CPU fallback")
    # CPU intentionally remains CPU for all workloads.

    vulkan_detected=allow_vulkan and bool((caps.get("vulkan") or {}).get("detected"))
    vulkan_state="DETECTED_SCAN_ONLY" if vulkan_detected else "UNAVAILABLE"
    plan={
        "schema":SCHEMA,"mode":mode,"fallback_cpu":fallback,
        "temporal_dl":{"backend":dl_backend,"torch_device":torch_device},
        "xgboost":{"backend":xgb_backend},
        "lightgbm":{"backend":lgb_backend},
        "random_forest":{"backend":"CPU"},
        "onnx":{"backend":"CPU","note":"ONNX generator/parity authority remains preserved; runtime provider changes require explicit verified parity."},
        "vulkan":{"state":vulkan_state,"training_backend":False},
        "notes":notes,
        "capabilities":caps,
    }
    return plan

def backend_for_family(plan: dict, family: str, spec: dict | None = None) -> str:
    """Resolve the effective training backend for any registry family.

    The mapping is role/capability driven so new temporal families automatically
    inherit the verified PyTorch accelerator instead of requiring a new UI row.
    """
    family = str(family or "").strip().lower()
    spec = spec or {}
    if family == "xgboost":
        return str((plan.get("xgboost") or {}).get("backend", "CPU"))
    if family == "lightgbm":
        return str((plan.get("lightgbm") or {}).get("backend", "CPU"))
    if bool(spec.get("requires_torch")) or str(spec.get("role") or "") == "temporal":
        return str((plan.get("temporal_dl") or {}).get("backend", "CPU"))
    return "CPU"


def compact_compute_status(plan: dict, cfg: dict | None = None) -> list[dict[str,Any]]:
    """Data-driven per-family compute view used by Advanced.

    No family names are hardcoded in the UI table. Any deployable base family added
    to the registry appears automatically.
    """
    from models.model_registry import registry_for_scientist
    reg = registry_for_scientist()
    active = set((((cfg or {}).get("agent") or {}).get("research_plan") or {}).get("active_families") or [])
    ra = ((cfg or {}).get("research_architecture") or {})
    mode = str(ra.get("family_selection_mode") or "AUTO").upper()
    allowed = set(str(x).lower() for x in (ra.get("allowed_families") or []))
    rows=[]
    for family, spec in (reg.get("base_families") or {}).items():
        permitted = True if mode == "AUTO" else family in allowed
        rows.append({
            "Family": family,
            "Class": spec.get("category"),
            "Role": spec.get("role"),
            "Backend": backend_for_family(plan, family, spec),
            "Allowed": "YES" if permitted else "NO",
            "Active": "YES" if family in active else "—",
        })
    return rows
