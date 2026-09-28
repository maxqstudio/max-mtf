from copy import deepcopy
from pathlib import Path
from models.model_lab import load_cfg
from research.research_control import default_manual_candidate, compile_manual_runtime

ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)

def manual_cfg(candidate):
    cfg=load_cfg(ROOT/'config/config.json')
    cfg.setdefault('champion_factory',{})['research_mode']='MANUAL'
    cfg['champion_factory']['manual_research']={'enabled':True,'candidates':[candidate]}
    return cfg

def must_reject(candidate,needle):
    try:
        compile_manual_runtime(manual_cfg(candidate))
    except ValueError as exc:
        req(needle in str(exc),f'wrong rejection: {exc}')
        return
    raise AssertionError('manual candidate unexpectedly accepted')

def main():
    exact=default_manual_candidate('random_forest',1)
    _,rows=compile_manual_runtime(manual_cfg(deepcopy(exact)))
    req(rows[0]['params']==exact['params'],'exact legal manual candidate drifted')

    unknown=deepcopy(exact); unknown['params']['totally_fake_param']=123
    must_reject(unknown,'unknown parameter')

    missing=deepcopy(exact); missing['params'].pop(next(iter(missing['params'])))
    must_reject(missing,'missing required')

    changed=deepcopy(exact); changed['params']['max_depth']=10**6
    must_reject(changed,'would be coerced')
    print('V201_MANUAL_EXACT_PARAMETER_IDENTITY PASS')

if __name__=='__main__': main()
