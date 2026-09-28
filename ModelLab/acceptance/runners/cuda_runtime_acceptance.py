from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from host.accelerator_bootstrap import nvidia_detected, torch_cuda_probe
from ui.ui_launcher import venv_python

ROOT=MODELLAB_ROOT
OUT=ROOT/'evidence'/'current'/'CUDA_RUNTIME_ACCEPTANCE_v1_3_3.json'


def main() -> int:
    OUT.parent.mkdir(parents=True,exist_ok=True)
    rows=[]; first=None
    def gate(name:str, ok:bool, detail=None):
        nonlocal first
        status='PASS' if ok else 'FAIL'
        rows.append({'gate':name,'status':status,'detail':detail})
        if not ok and first is None: first=name
        return ok

    py=venv_python()
    gate('APP_VENV_EXISTS',py.exists(),str(py))
    nvidia=nvidia_detected()
    gate('NVIDIA_DETECTED',nvidia,{'detected':nvidia})
    probe=torch_cuda_probe(str(py)) if py.exists() else {'installed':False,'cuda_available':False,'tensor_test':False}
    gate('PYTORCH_INSTALLED',bool(probe.get('installed')),probe)
    gate('PYTORCH_CUDA_AVAILABLE',bool(probe.get('cuda_available')),probe)
    gate('CUDA_TENSOR_EXECUTION',bool(probe.get('tensor_test')),probe)

    plan={}
    if py.exists():
        code='''import json\nfrom pathlib import Path\nfrom compute_backend import resolve_compute_plan\ncfg=json.loads(Path("config.json").read_text(encoding="utf-8"))\np=resolve_compute_plan(cfg,refresh=True)\nprint(json.dumps({"temporal_dl":p.get("temporal_dl"),"xgboost":p.get("xgboost"),"lightgbm":p.get("lightgbm"),"random_forest":p.get("random_forest")},sort_keys=True))'''
        try:
            cp=subprocess.run([str(py),'-c',code],cwd=ROOT,env=acceptance_utf8_env(),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90,check=False,**utf8_text_subprocess_kwargs())
            for line in reversed((cp.stdout or '').splitlines()):
                try:
                    obj=json.loads(line.strip())
                    if isinstance(obj,dict) and 'temporal_dl' in obj:
                        plan=obj; break
                except Exception: pass
            gate('RESOLVED_COMPUTE_PLAN',cp.returncode==0 and bool(plan),{'rc':cp.returncode,'plan':plan,'output_tail':(cp.stdout or '')[-1200:]})
        except Exception as exc:
            gate('RESOLVED_COMPUTE_PLAN',False,{'error':str(exc)})
    else:
        gate('RESOLVED_COMPUTE_PLAN',False,{'error':'app venv missing'})

    if plan:
        gate('TEMPORAL_DL_CUDA',str((plan.get('temporal_dl') or {}).get('backend'))=='CUDA',plan.get('temporal_dl'))
        # XGBoost/LightGBM are capability-probed independently. Record their actual resolved state;
        # CUDA/OpenCL may legitimately be unavailable because of wheel/runtime support.
        xgb=str((plan.get('xgboost') or {}).get('backend') or '')
        lgb=str((plan.get('lightgbm') or {}).get('backend') or '')
        gate('XGBOOST_BACKEND_REPORTED',xgb in {'CUDA','CPU'},plan.get('xgboost'))
        gate('LIGHTGBM_BACKEND_REPORTED',lgb in {'OPENCL_GPU','CPU'},plan.get('lightgbm'))
        gate('RANDOM_FOREST_CPU',str((plan.get('random_forest') or {}).get('backend'))=='CPU',plan.get('random_forest'))

    payload={'schema':'MAX_CUDA_RUNTIME_ACCEPTANCE_V1','version':'1.3.2','generated_utc':datetime.now(timezone.utc).isoformat(),'overall_status':'PASS' if first is None else 'FAIL','first_failed_gate':first,'results':rows,'torch_probe':probe,'resolved_compute':plan}
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))
    return 0 if first is None else 1

if __name__=='__main__': raise SystemExit(main())
