# Time-Series Validation

## PURPOSE
Protect chronology and estimate robustness without contaminating model selection.

## INPUT EVIDENCE
Label horizon, purge/embargo, chronological folds, WFA evidence, CPCV split manifest, seed confirmation, trade/sample counts, stage contracts and protected partition identity.

## DECISION PROCEDURE
Use chronological splits; enforce purge/embargo at least as required by current contract; fit transforms only on training folds; keep threshold/policy selection out of held fold; distinguish Discovery WFA, CPCV robustness, Tournament, Monte Carlo and Fresh authority. Treat insufficient sample evidence separately from model-quality failure. Track all trials for multiple-testing diagnostics.

## FAILURE PATTERNS
Random K-fold; retuning on test fold; mixing CPCV and PBO semantics; comparing DSR/PBO computed under changing trial families; using Fresh repeatedly; ignoring trade-count sufficiency.

## ALLOWED ACTIONS
Review split integrity, request fold forensics, recommend additional Discovery evidence or a new campaign when validation is insufficient.

## FORBIDDEN ACTIONS
Generate alternate authoritative folds, alter fixed seeds, reopen Fresh for adaptive tuning, reinterpret deterministic gate verdicts.

## OUTPUT SCHEMA
{validation_observation, chronology_status, leakage_risk, sample_sufficiency, robustness_issue, allowed_next_action}

## TEST / REGRESSION FIXTURES
- **Chronology:** Any split that trains on later observations than its held evaluation window is rejected.
- **Purge/embargo:** Validation must respect the authoritative label/execution horizon; held-fold tuning is forbidden.
- **Protected boundary:** Fresh/Locked evidence cannot be fed back into same-cycle candidate refinement.

## REFERENCES
Walk-forward, purged/embargoed CV, CPCV, DSR/PBO methodology and MAX canonical validation contracts.
