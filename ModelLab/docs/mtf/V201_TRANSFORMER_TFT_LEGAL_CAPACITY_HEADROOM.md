# MAX MTF v2.0.1 — Transformer + TFT Legal Capacity Headroom

Scope: legal architecture headroom only. Canonical version remains **MAX MTF v2.0.1**.

- Transformer legal `d_model`: `16..816`; executable reachable max at registry maxima: **64,444,419** parameters (old reachable max **25,493,507**).
- TFT legal `d_model`: `16..480`; executable reachable max at registry maxima: **16,875,459** parameters (old reachable max **4,814,627**).
- All other family registry bounds and hard legal ceilings are unchanged.
- Effective candidate ceiling remains exactly `min(LEGAL, RESOURCE, SCIENTIFIC)` on actual executable parameter count.
- Recommended/starting envelopes are not raised into hard targets. AUTO, MANUAL, and Scientist remain bound by the same deterministic capacity authority.
- Cumulative exact-family Full-WFA EXPAND/HOLD/CONTRACT evidence changes search location only and cannot widen any hard ceiling.
- Training methodology, labels, features, WFA/CPCV/Tournament/Monte Carlo/Forward, MoE routing, and Owner MT5/MetaEditor closure are unchanged.

Focused acceptance authority: `V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM`. Machine-readable evidence: `historical external: ModelLab/evidence/current/V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM.json`.
