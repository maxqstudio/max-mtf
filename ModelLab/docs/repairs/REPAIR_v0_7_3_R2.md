# CPMF v0.7.3 R2 — Scientific Research Engine Repair

## Problem

R1 correctly moved CPCV behind Pool 12, but Discovery still spent full WFA compute on every generated candidate and represented failure mainly as a binary PASS/NO frontier. Losing trials were scattered across generation leaderboards rather than retained in one explicit Factory ledger.

## Repair

R2 adds a bounded two-level Fidelity Ladder, hard-gate Failure Margins, Failure Topology and an All-Trial Ledger. Full WFA remains the only Discovery qualification authority. CPCV remains finalist-only after Pool 12.

## Non-goals

No model family, KPI threshold, label, feature contract, chronology rule, Tournament rule, Monte Carlo rule or Forward rule is changed.
