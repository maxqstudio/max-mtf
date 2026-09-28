# Data Quality and Point-in-Time Discipline

## PURPOSE
Prevent a model from learning information that was unavailable at decision time or from being evaluated on corrupted/ambiguous market data.

## INPUT EVIDENCE
Canonical schema/DQ results, timestamps, source lineage, feature availability time, broker metadata, gap diagnostics, duplicate checks, non-finite checks and dataset identity.

## DECISION PROCEDURE
Verify single symbol/timeframe authority; causal ordering; feature availability at decision timestamp; no future-filled transforms; train-only fitting for learned transforms; gap/duplicate handling; immutable source digest; consistent bid/ask semantics. Treat DQ verdict from MAX code as authoritative.

## FAILURE PATTERNS
Centered rolling windows, global normalization fitted before split, future join, repaired rows without provenance, silent duplicate candles, source mixing, mutable feature-store lookup, resetting temporal identity so gaps disappear.

## ALLOWED ACTIONS
Request DQ evidence, propose diagnostic checks, recommend fail-closed repairs through authorized data paths.

## FORBIDDEN ACTIONS
Invent/reconstruct missing broker data, waive DQ failure, silently interpolate authority rows, alter immutable source evidence.

## OUTPUT SCHEMA
{dq_observation, point_in_time_risk, affected_features, evidence, proposed_check, severity, authority_note}

## TEST / REGRESSION FIXTURES
- **Point-in-time:** A feature requiring information unavailable at the decision timestamp is rejected as leakage.
- **Train-only transform:** A learned scaler/encoder fitted using validation/Fresh rows is rejected.
- **Temporal gaps:** Dropped source rows may remain unavailable as supervised targets but chronology/source-row identity must not be silently bridged.

## REFERENCES
MAX CP32/Data Quality contracts and point-in-time time-series practice.
