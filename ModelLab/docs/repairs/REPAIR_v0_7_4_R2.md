# CPMF v0.7.4 R2 — Family + Compute Control

R2 keeps the v0.7.4 hardware-adaptive Scientist architecture and adds explicit Owner control over the legal model-family universe and a registry-driven compute view.

## Family selection
- `AUTO`: all registered base families are permitted; deterministic hardware feasibility decides the executable universe and Scientist chooses the research portfolio/hybrids.
- `MANUAL`: the Owner checklist is the hard allowed base-family universe. Scientist may choose any subset and may compose compatible temporal→policy hybrids only from checked components.
- Manual selection never silently re-enables an unchecked LightGBM/XGBoost baseline.
- Empty MANUAL selection fails closed before Factory research.

## Compute
- Advanced compute UI is registry-driven; GRU/LSTM/TCN/Transformer inherit the verified temporal PyTorch backend automatically.
- XGBoost and LightGBM keep their own verified accelerator resolution.
- AUTO resolves backend per family; CPU fallback remains explicit.
- Vulkan is detection/scan evidence only; no verified Vulkan training claim is made.
