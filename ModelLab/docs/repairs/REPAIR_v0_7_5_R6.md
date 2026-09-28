# CPMF v0.7.5 R6 — Per-Family Model Size Priority Repair

R6 adds complete Owner-controlled per-family model-size preferences while preserving automatic capacity sizing. The change is wired through registry metadata, Advanced UI, persisted config, research-plan freeze, effective deterministic bounds, dynamic hybrids, Scientist/Director context, deterministic candidate generation/validation, capacity provenance, release docs and cumulative acceptance.

Key rule: `0.50` is backward-compatible neutral AUTO. `0.00/1.00` narrow only model-size dimensions inside the current safe capacity envelope; they never widen legal/dataset/hardware ceilings.

## Post-seal Repair1
A later Control Room audit found hybrid safe-envelope, true-intersection, and executable RAM/VRAM/time preflight gaps. These are closed in `ModelLab/docs/repairs/REPAIR_v0_7_5_R6_REPAIR1.md`; cumulative acceptance is now 70/70 PASS.
