# Scientific Method for MAX Research

## PURPOSE
Make autonomous research falsifiable, attributable and cumulative rather than a sequence of plausible-looking parameter changes.

## INPUT EVIDENCE
Parent/child experiments, hypothesis lifecycle, failure topology, current experiment budget, candidate metrics, fold distributions, stage authority and prior controlled outcomes.

## DECISION PROCEDURE
1. Convert a failure or opportunity into a specific hypothesis.
2. State the mechanism and expected observable change before execution.
3. Choose a control/ablation where practical; vary the fewest dimensions needed.
4. Define a falsification criterion and evidence sufficiency requirement.
5. Run within deterministic bounds.
6. Compare predicted vs observed outcome; record supported, partially supported, falsified or inconclusive.
7. Do not generalize from one lucky candidate or one seed.
8. Retire repeated dead ends and preserve negative results.

## FAILURE PATTERNS
HARKing after results; optional stopping; changing multiple unrelated variables; interpreting correlation as mechanism; hiding failed trials; treating one near-miss as proof; reusing protected validation for iterative tuning.

## ALLOWED ACTIONS
Control experiments, ablations, sensitivity checks, replication/recheck when preregistered, family/topology escape after evidence supports local exhaustion.

## FORBIDDEN ACTIONS
Outcome rewriting, gate changes, deletion of failures, same-snapshot Fresh retuning, arbitrary search expansion after seeing protected outcomes.

## OUTPUT SCHEMA
{observation, hypothesis, intervention, control, expected_observation, falsification, evidence_sufficiency, conclusion_status, next_experiment}

## TEST / REGRESSION FIXTURES
- **Pre-registration:** An experiment without a stated mechanism, expected observation, and falsification condition is incomplete and must not be treated as a supported hypothesis.
- **Negative result:** A falsified hypothesis remains retained evidence and must not be silently rewritten post-hoc.
- **Authority conflict:** If an LLM interpretation conflicts with deterministic gate evidence, deterministic evidence wins.

## REFERENCES
Falsification and controlled experimental design; MAX hypothesis lifecycle and Experiment Block contracts.
