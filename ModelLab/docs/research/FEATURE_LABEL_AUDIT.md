# FEATURE + LABEL AUDIT v0.6.3

This is now an executable stage, not a report-only status.

## Legal entry states

- `POLICY_CV_REJECTED`
- `RESEARCH_REJECTED`
- failed historical/fresh validation that requires a new research hypothesis

## Audit authority

The audit reconstructs the original upstream pre-holdout region and does not calculate metrics on the retired locked segment.

It produces:

- label class balance and retention;
- bounded one-factor label sensitivity for horizon, SL, TP, min edge, and margin;
- chronological feature drift;
- high-correlation feature redundancy;
- frozen-model feature-importance stability across walk-forward folds;
- policy over-selection diagnostics such as too few trades, regime concentration, and unstable PF;
- bounded Guided Research hypotheses.

## Guided Research

Executable v0.6.3 hypotheses preserve the exact CP32 input semantics and change label policy only. Feature-ablation results remain diagnostic until a deployment-safe feature-contract change is explicitly implemented.

Guided Research evaluates every hypothesis using upstream OOF only. Hierarchical KPI authority remains mandatory. Composite Score ranks peers but has no PASS authority.

A Guided PASS can launch a new-generation model search with the historical locked test explicitly skipped. The next legal validation is a genuinely newer fresh holdout.
