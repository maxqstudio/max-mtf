# REPAIR v1.3.1 — CUDA Backend Authority

## Scope

Repair two pre-freeze v1.3.0 gaps without changing Strategy Champion, scientific KPI, labels, CPCV, or promotion authority.

1. **PyTorch CUDA environment determinism.** Generic `torch>=2.4,<3` did not guarantee a CUDA-capable wheel. `ModelLab/host/accelerator_bootstrap.py` now selects a pinned official PyTorch wheel. NVIDIA hosts use `torch==2.6.0` from the `cu124` index; non-NVIDIA hosts use the pinned CPU path. The launcher verifies `torch.cuda.is_available()` and executes/synchronizes a real CUDA tensor operation. NVIDIA-detected hosts must not silently fall back to CPU because the CUDA PyTorch install is broken.
2. **Per-family planning authority.** Research Architect no longer treats PyTorch CUDA as universal GPU truth. The Factory freezes `resolve_compute_plan()` before Scientist/Architect planning. Temporal PyTorch, XGBoost CUDA, LightGBM OpenCL GPU, and RandomForest CPU are independent backend authorities. Capacity envelopes consume those resolved backends.

## Regression

`R50_V131_CUDA_BACKEND_AUTHORITY` proves a synthetic case where PyTorch CUDA is unavailable while XGBoost CUDA is available: XGBoost receives its GPU envelope, while temporal families remain CPU-safe.

## External runtime evidence

Source acceptance cannot prove the Owner NVIDIA driver/runtime. Owner runtime must demonstrate the pinned CUDA install and actual tensor execution.

## One-click Owner runtime proof

Run `ModelLab/RUN_CUDA_ACCEPTANCE.cmd`. It verifies NVIDIA detection, app venv, PyTorch CUDA availability, a real CUDA tensor operation, and the resolved per-family compute plan. Evidence: `historical external: evidence/current/CUDA_RUNTIME_ACCEPTANCE_v1_3_1.json`.
