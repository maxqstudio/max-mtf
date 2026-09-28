from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def req(x,m):
    if not x: raise AssertionError(m)

def main():
    boot=(ROOT/'host/accelerator_bootstrap.py').read_text(encoding='utf-8')
    launch=(ROOT/'ui/ui_launcher.py').read_text(encoding='utf-8')
    reqs=(ROOT/'requirements/requirements.txt').read_text(encoding='utf-8')
    arch=(ROOT/'research/research_architect.py').read_text(encoding='utf-8')
    factory=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('TORCH_VERSION = "2.6.0"' in boot and '/whl/cu124' in boot,'Pinned official CUDA PyTorch wheel configured')
    req('tensor_test' in boot and 'torch.cuda.synchronize()' in boot,'CUDA tensor execution verified')
    req('NVIDIA GPU detected but pinned CUDA PyTorch did not pass' in boot,'NVIDIA CUDA failure explicit')
    req('install_torch_for_host' in launch and 'torch_cuda_probe' in launch,'Launcher installs/verifies accelerator stack')
    req('torch>=2.4,<3' not in reqs,'Generic unpinned torch removed')
    req('backend_for_family' in arch and 'resolved_compute' in arch,'Architect consumes per-family resolved backend')
    req('xgb_accel=xgb_backend == "CUDA"' in arch,'XGBoost capacity independent of torch.cuda')
    req('compute authority must be resolved before Scientist/Architect capacity planning' in factory,'Factory freezes compute authority before planning')
    req((ROOT/'RUN_CUDA_ACCEPTANCE.cmd').exists() and (ROOT/'acceptance/runners/cuda_runtime_acceptance.py').exists(),'One-click CUDA runtime acceptance exists')
    cra=(ROOT/'acceptance/runners/cuda_runtime_acceptance.py').read_text(encoding='utf-8')
    req('CUDA_RUNTIME_ACCEPTANCE_v1_3_3.json' in cra and 'CUDA_TENSOR_EXECUTION' in cra and 'RESOLVED_COMPUTE_PLAN' in cra,'CUDA runtime acceptance emits machine-readable tensor/backend evidence')

    from research.research_architect import capability_catalog, recommended_parameter_envelopes
    profile={'memory':{'total_gib':32},'nvidia':{'devices':[{'memory_total_gib':8}]},'torch':{'cuda_available':False},'cpu':{'physical_cores':6,'logical_threads':12}}
    cfg={'research_architecture':{'family_selection_mode':'AUTO'},'resolved_compute':{
        'temporal_dl':{'backend':'CPU'},'xgboost':{'backend':'CUDA'},'lightgbm':{'backend':'CPU'},'random_forest':{'backend':'CPU'}}}
    cat=capability_catalog(profile,cfg)
    req(cat['families']['xgboost']['preferred_backend']=='CUDA','XGBoost planner uses own CUDA authority')
    req(cat['families']['gru']['preferred_backend']=='CPU','Temporal planner respects PyTorch CPU authority')
    env=recommended_parameter_envelopes(profile,None,cfg['resolved_compute'])
    req(env['xgboost']['max_depth'][1]==14,'XGBoost GPU envelope follows XGB CUDA')
    req(env['gru']['sequence_length'][1]==128,'Temporal envelope stays CPU-safe')
    print('V131_CUDA_AUTHORITY_SELFTEST PASS')

if __name__=='__main__': main()
