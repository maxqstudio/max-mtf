# Experiment Design

## PURPOSE
Choose the smallest informative experiment that reduces uncertainty or qualification distance without turning research into undirected search.

## INPUT EVIDENCE
Dominant failed gate, failure margins, candidate family/topology, prior experiments, parameter bounds, budget, compute constraints and learning-policy recommendations.

## DECISION PROCEDURE
Classify intervention as local refinement, selectivity, feature ablation, memory, capacity, architecture, hybrid, seed stability, regime or label separation. Prefer one mechanism per block. Define anchor/control. Allocate enough trials for evidence but do not spend budget on already falsified neighborhoods. Escalate to family/topology escape only when local mechanisms are exhausted or clearly mismatched.

## FAILURE PATTERNS
Changing family, features, threshold and memory simultaneously; repeating identical failed regions; spending all budget on the top score; selecting interventions solely because they are novel.

## ALLOWED ACTIONS
Bounded experiment blocks, controlled ablations, sensitivity neighborhoods, explicit rechecks when contract changed.

## FORBIDDEN ACTIONS
Unbounded Bayesian/black-box optimization over protected outcomes, post-hoc expansion after Fresh, gate tuning.

## OUTPUT SCHEMA
{action_kind, anchor, variables, fixed_dimensions, budget, expected_metric_movements, falsification, escalation_rule}

## TEST / REGRESSION FIXTURES
- **Single mechanism:** Two unrelated interventions in one trial are rejected for causal attribution unless explicitly designed as a factorial/control experiment.
- **Smallest test:** Prefer the lowest-cost experiment capable of falsifying the mechanism before widening capacity/search.
- **Frozen contract:** Experiment design cannot alter deterministic KPI, chronology, protected partitions, or promotion authority.

## REFERENCES
MAX Experiment Block lifecycle and deterministic candidate compiler.
