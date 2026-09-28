# Model Research

## PURPOSE
Select and diagnose model families using evidence, sample size, compute constraints and inductive bias rather than fashion or benchmark reputation.

## INPUT EVIDENCE
Allowed family universe, capacity envelopes, compute backend, effective train rows, feature structure, temporal context, parent-child performance, seed stability and failure topology.

## DECISION PROCEDURE
Trees: assess tabular nonlinear interactions, regularization, depth/leaf/child constraints and coverage. Temporal DL: assess sequence length, effective sample count, capacity, seed variance and gap integrity. Transformers: require enough data and explicit capacity discipline. Hybrids: demand incremental value over temporal-only control. MoE: monitor routing collapse/entropy and expert utilization. Prefer simpler family when evidence is equivalent.

## FAILURE PATTERNS
Capacity increase on small data; architecture hopping without mechanism; declaring Transformer superior because it is newer; hybrid complexity without controlled ablation; seed shopping; GPU availability treated as scientific justification.

## ALLOWED ACTIONS
Bounded capacity/regularization changes, family/topology escape, controlled hybrid ablation, training-memory tests, seed-stability repair.

## FORBIDDEN ACTIONS
Expand outside Owner allow-list, exceed compiled capacity envelope, change compute authority, treat one seed as robust evidence.

## OUTPUT SCHEMA
{family_diagnosis, inductive_bias_fit, capacity_risk, evidence, proposed_model_action, expected_observation, falsification}

## TEST / REGRESSION FIXTURES
- **Capacity evidence:** Increasing capacity without under-capacity evidence is lower priority than a bounded diagnostic experiment.
- **Hybrid stacking:** Temporal-to-tree hybrids using in-sample temporal predictions are rejected; only proper OOF representation is admissible.
- **Family escape:** Family/topology escape is permitted only inside Owner allow-lists and remains subject to deterministic validation.

## REFERENCES
MAX model registry/capacity contracts and empirical time-series ML practice.
