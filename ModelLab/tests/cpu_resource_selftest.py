from pathlib import Path
import tempfile
from host.cpu_resource import *
def req(c,m):
    if not c: raise AssertionError(m)
p=physical_core_count(); xs=candidate_thread_counts(p); req(xs==sorted(set(xs)) and max(xs)<=p,'thread candidates exceed physical cores')
with tempfile.TemporaryDirectory() as td:
    prof=calibrate_cpu_profile(Path(td)/'cpu.json'); req(prof['outer_trial_concurrency']==1 and prof['selected_model_threads']<=prof['physical_cores'],'calibration policy invalid')
    cfg={'cpu_threads':99,'compute':{'cpu_resource':{'enabled':True,'max_model_threads':p}}}; out=apply_cpu_profile(cfg,prof); req(out['cpu_threads']<=p and out['compute']['cpu_resource']['outer_trial_concurrency']==1,'resource scheduler failed')
print('CPU_RESOURCE_SELFTEST PASS')
