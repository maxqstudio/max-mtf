# Temporal GRU · Active in v0.6.6

GRU is now a deployable research family rather than an optional stub.

```text
CP32 H1 rows
  -> causal window [N,T,32]
  -> GRU (1–2 layers, hidden 16–48)
  -> Linear 3 + softmax
  -> SELL / SKIP / BUY
```

Research searches `sequence_length` from 8–24 H1 bars plus bounded hidden size, layers, dropout, learning rate, batch size, epochs, weight decay, and `training_memory_months`. Class weighting, temporal inner validation, early stopping, and gradient clipping are implemented in `ModelLab/research/gru_research.py`.

Python and EA share the same warmup rule: causal sequence windows are left-padded with the oldest currently available CP32 row. The exported GRU ONNX includes feature normalization and has a frozen input shape `[1,T,32]`.

EA v1.06 has independent `InpChampionSequenceLength` and `InpChallengerSequenceLength` inputs. Use `1` for tree models and the exact frozen manifest `sequence_length` for GRU.

Local self-test trains and joblib-roundtrips a real PyTorch GRU. Actual ONNX conversion/ONNX Runtime parity requires the pinned converter stack installed by the Windows environment; actual MetaEditor + MT5 sequence inference remains an Owner-machine acceptance gate.


## v0.6.6 hybrid use

Standalone GRU remains a benchmark. Hybrid GRU direction signals are stacked OOF into a classical SELL/SKIP/BUY policy; see `ModelLab/docs/research/HYBRID_GRU_CLASSICAL.md`.
