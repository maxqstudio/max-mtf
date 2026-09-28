from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import json, os, platform, time
from pathlib import Path

SCHEMA="CP_CPU_RESOURCE_PROFILE_V1"

def physical_core_count()->int:
    try:
        import psutil
        n=psutil.cpu_count(logical=False)
        if n: return max(1,int(n))
    except Exception: pass
    logical=max(1,int(os.cpu_count() or 1))
    # Conservative fallback for common SMT systems; never exceed logical count.
    return max(1,logical//2 if logical>=4 else logical)

def candidate_thread_counts(physical:int|None=None)->list[int]:
    p=max(1,int(physical or physical_core_count()))
    vals=[1,2,4,p]
    return sorted(set(max(1,min(p,v)) for v in vals))

def _numpy_probe(threads:int)->float:
    # Lightweight deterministic calibration proxy. Runtime model-specific timing is
    # still recorded separately; this probe only chooses a conservative local default.
    old_omp=os.environ.get('OMP_NUM_THREADS'); old_mkl=os.environ.get('MKL_NUM_THREADS')
    os.environ['OMP_NUM_THREADS']=str(threads); os.environ['MKL_NUM_THREADS']=str(threads)
    try:
        import numpy as np
        rng=np.random.default_rng(123)
        a=rng.standard_normal((512,256),dtype=np.float32); b=rng.standard_normal((256,128),dtype=np.float32)
        _=a@b
        t=time.perf_counter()
        for _ in range(3): _=a@b
        return max(1e-9,time.perf_counter()-t)
    finally:
        if old_omp is None: os.environ.pop('OMP_NUM_THREADS',None)
        else: os.environ['OMP_NUM_THREADS']=old_omp
        if old_mkl is None: os.environ.pop('MKL_NUM_THREADS',None)
        else: os.environ['MKL_NUM_THREADS']=old_mkl

def calibrate_cpu_profile(path:Path|str|None=None)->dict:
    physical=physical_core_count(); logical=max(1,int(os.cpu_count() or physical))
    rows=[]
    for t in candidate_thread_counts(physical):
        try: sec=_numpy_probe(t)
        except Exception: sec=None
        rows.append({'threads':t,'probe_seconds':sec})
    finite=[r for r in rows if r['probe_seconds'] is not None]
    # Prefer fastest measured count, but cap at physical cores and never assume SMT helps.
    selected=min(finite,key=lambda r:r['probe_seconds'])['threads'] if finite else min(physical,4)
    prof={'schema':SCHEMA,'machine':platform.machine(),'processor':platform.processor(),'physical_cores':physical,'logical_cores':logical,'candidate_threads':rows,'selected_model_threads':int(selected),'outer_trial_concurrency':1,'policy':'PARALLELIZE_MODEL_NOT_OUTER_HPO','created_utc':datetime.now(timezone.utc).isoformat()}
    if path:
        p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(prof,indent=2),encoding='utf-8')
    return prof

def load_or_calibrate(path:Path|str, cfg:dict)->dict:
    p=Path(path)
    rc=((cfg.get('compute') or {}).get('cpu_resource') or {})
    if bool(rc.get('reuse_calibration',True)) and p.exists():
        try:
            d=json.loads(p.read_text(encoding='utf-8'))
            if d.get('schema')==SCHEMA and int(d.get('physical_cores',0))==physical_core_count(): return d
        except Exception: pass
    return calibrate_cpu_profile(p)

def apply_cpu_profile(cfg:dict, profile:dict)->dict:
    out=deepcopy(cfg)
    rc=((out.get('compute') or {}).get('cpu_resource') or {})
    if not bool(rc.get('enabled',True)): return out
    max_threads=max(1,int(rc.get('max_model_threads',profile.get('physical_cores',1)) or 1))
    selected=max(1,min(max_threads,int(profile.get('selected_model_threads',1) or 1)))
    out['cpu_threads']=selected
    out.setdefault('compute',{}).setdefault('cpu_resource',{})['resolved_model_threads']=selected
    out['compute']['cpu_resource']['outer_trial_concurrency']=1
    return out
