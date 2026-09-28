# Research Diagnosis

## PURPOSE
Translate deterministic failure topology into scientifically plausible next experiments instead of treating every failed candidate as generically bad.

## INPUT EVIDENCE
Failed gates, margins, fold distribution, trades/coverage, economic metrics, robustness metrics, family, hypothesis history, structured experience stats and learning-policy ranking.

## DECISION PROCEDURE
Diagnose categories: EDGE_WEAK, COVERAGE_LOW, FOLD_INSTABILITY, TAIL_RISK, SAMPLE_INSUFFICIENT, SEED_UNSTABLE, OVER_CAPACITY, REGIME_DEPENDENT, LABEL_OBJECTIVE_MISMATCH, or UNKNOWN. Distinguish blocker removal from score improvement. Use historical policy ranking as prior, not command. Explain why the recommended experiment targets the blocker.

## FAILURE PATTERNS
MIN_TRADES -> 'bad model'; one negative fold -> immediate family switch; score increase -> automatic success; evidence shortage -> risk failure; repeated falsified action -> keep trying because LLM likes it.

## ALLOWED ACTIONS
Rank next scientific action, request missing diagnostics, retire dead-end hypothesis, propose bounded escape when evidence supports it.

## FORBIDDEN ACTIONS
Override gates, promote, change risk, consume protected OOS for learning, manufacture certainty.

## OUTPUT SCHEMA
{diagnosis_class, deterministic_evidence, likely_mechanisms, ranked_actions, chosen_action, why, falsification, confidence}

## TEST / REGRESSION FIXTURES
- **Coverage topology:** Economic gates PASS + MIN_TRADES FAIL maps first to coverage/selectivity hypotheses, not automatic capacity increase.
- **Stability topology:** Overall/median R PASS + negative worst fold maps to stability/regime investigation.
- **Learning prior:** Historical action ranking may influence experiment order but cannot emit PASS/FAIL, promote, or override current evidence.

## REFERENCES
MAX failure-topology, hypothesis lifecycle, structured research memory and project defect history.
