from __future__ import annotations
import host.compute_backend as cb
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def caps(torch_acc=None,xgb=False,lgb=False,vulkan=False):
    return {'schema':cb.SCHEMA,'nvidia':{'detected':torch_acc=='CUDA'},'torch':{'accelerator':torch_acc,'torch_device':'cuda' if torch_acc else 'cpu'},'vulkan':{'detected':vulkan},'opencl':{'detected':lgb},'xgboost_cuda':{'usable':xgb},'lightgbm_gpu':{'usable':lgb},'cpu':{'usable':True}}

def main():
    old=cb.detect_compute_capabilities
    try:
        cb.detect_compute_capabilities=lambda: caps('CUDA',True,True,True)
        p=cb.resolve_compute_plan({'compute':{'mode':'AUTO'}})
        req(p['temporal_dl']['backend']=='CUDA','AUTO uses verified CUDA for temporal DL')
        req(p['xgboost']['backend']=='CUDA','AUTO uses verified CUDA for XGBoost')
        req(p['lightgbm']['backend']=='OPENCL_GPU','AUTO uses verified OpenCL for LightGBM')
        req(p['vulkan']['state']=='DETECTED_SCAN_ONLY' and not p['vulkan']['training_backend'],'AUTO scans Vulkan without false training claim')
        p=cb.resolve_compute_plan({'compute':{'mode':'CUDA','fallback_cpu':True}})
        req(p['temporal_dl']['backend']=='CUDA' and p['xgboost']['backend']=='CUDA' and p['lightgbm']['backend']=='CPU','manual CUDA forces CUDA-capable workloads only')
        cb.detect_compute_capabilities=lambda: caps('ROCM',False,True,True)
        p=cb.resolve_compute_plan({'compute':{'mode':'ROCM','fallback_cpu':True}})
        req(p['temporal_dl']['backend']=='ROCM' and p['temporal_dl']['torch_device']=='cuda','manual ROCm/HIP uses verified PyTorch HIP')
        req(p['xgboost']['backend']=='CPU' and p['lightgbm']['backend']=='CPU','manual ROCm does not silently switch to another GPU API')
        cb.detect_compute_capabilities=lambda: caps(None,False,False,True)
        p=cb.resolve_compute_plan({'compute':{'mode':'VULKAN','fallback_cpu':True}})
        req(p['temporal_dl']['backend']=='CPU' and p['vulkan']['state']=='DETECTED_SCAN_ONLY','manual Vulkan falls back clearly when training backend unsupported')
        try:
            cb.resolve_compute_plan({'compute':{'mode':'VULKAN','fallback_cpu':False}})
        except RuntimeError:
            req(True,'manual unsupported Vulkan fail-closed when CPU fallback disabled')
        else:
            raise AssertionError('manual Vulkan must fail without fallback')
    finally:
        cb.detect_compute_capabilities=old
    print('COMPUTE_BACKEND_SELFTEST PASS')
if __name__=='__main__': main()
