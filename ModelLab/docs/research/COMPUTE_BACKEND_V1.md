# Compute Backend V1

Persisted setting: `AUTO`, `CUDA`, `ROCM` (UI meaning ROCm/HIP), `VULKAN`, `CPU`.

- AUTO: scans runtime/hardware and selects verified backend per workload. PyTorch temporal DL may use CUDA or ROCm/HIP; XGBoost may use CUDA; LightGBM may use verified OpenCL GPU; RF remains CPU.
- CUDA manual: forces CUDA-capable workloads; unsupported workloads use CPU only when fallback is enabled.
- ROCm/HIP manual: forces PyTorch ROCm/HIP temporal workloads; non-ROCm libraries remain CPU rather than silently switching to CUDA/OpenCL.
- Vulkan manual: Vulkan is scanned, but current CPMF training libraries have no verified general Vulkan training backend. With CPU fallback enabled it reports this and uses CPU; with fallback disabled it fails clearly.
- CPU manual: all research training stays CPU.

ONNX generation/parity is a separate deployment authority and is not silently moved to a GPU provider without explicit parity verification.
