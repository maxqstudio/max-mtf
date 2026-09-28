# Champion Factory V3 — v0.7.3 R6

## Canonical workflow authority

`Data → Discovery Proposal → Cheap Screen → Full WFA → Pool 12 → CPCV Finalists → Tournament → Monte Carlo → Forward Championship → Champion`

## Discovery authority

Discovery generates proposals under the existing model/search contracts. When Fidelity Ladder is enabled, every proposal first receives a disposable Cheap Screen. Only bounded promoted proposals receive Full WFA compute, and they are rerun from the original CandidateSpec rather than the resource-reduced screen spec.

Only Full WFA candidates that PASS the existing hierarchical WFA/OOF acceptance authority may enter Pool 12. Cheap Screen results, Failure Margins, selection score and LLM recommendations have no qualification authority.

The Factory aggregates an all-trial ledger and Full-WFA Failure Topology across generations so failed trials remain scientific evidence rather than disappearing from history.

Candidate label/feature contracts produced by Guided Research remain frozen into each qualified pool entry. Cross-Factory Global Research Memory remains restricted to legal Discovery-side evidence.

## CPCV finalist authority

CPCV is not executed inside Discovery generations. After the WFA Pool 12 is frozen, finalist order is frozen from WFA evidence and CPCV opens as a separate progressive stage.

CPCV PASS/FAIL remains hard authority. Ranking cannot compensate for CPCV FAIL. CPCV outcomes are not fed into active Discovery Research Memory or per-generation Director prompts. Tournament cannot open until the Factory reaches `CPCV_SURVIVORS_READY`.

Default resource policy: target 3 CPCV survivors, batch 3, maximum 12 finalists, minimum 1 survivor to open Tournament. These are compute-allocation settings, not trading KPI thresholds.

## Downstream selection authority

`CPCV survivors → Tournament KPI survivors → Monte Carlo KPI survivors → Forward Championship KPI PASS → Top-1 Champion`

Tournament does not pick one winner. Monte Carlo receives every Tournament KPI survivor. Monte Carlo simulation count remains configurable/persisted, default 10,000; no new Monte Carlo-specific KPI thresholds are added. Forward Championship receives every Monte Carlo survivor and ranks only candidates that PASS Forward KPI.

If no survivor remains at CPCV, Tournament, Monte Carlo or Forward, the Factory is terminal for that cycle and downstream stages fail closed.

## Runtime authority

The ONNX generator is preserved. One-time Factory preflight validates enabled model converters. Forward Top-1 is exported to Champion ONNX artifacts and parity checked. `CHAMPION_RUNTIME_BLOCKED` means research selection succeeded but runtime generation/parity did not; do not rerun research to repair a runtime-only defect.

## R5 failure-cycle governance

Pool/CPCV/Tournament/Monte-Carlo failure may restart research only after a committed, actionable Scientist plan exists and the exact-contract exposure budget permits another cycle. API failure does not consume exposure and leaves the Factory waiting for Scientist review; resume retries the report without refitting or reopening the failed stage. Forward remains a terminal/report-only boundary for the same snapshot.

## R6 CPCV methodology and hypothesis authority

CPCV retains the 15 purged combinatorial stress splits for the legacy economic/stress gates. R6 additionally records deterministic 5-path chronological reconstruction and per-group attribution; the seven new Advanced risk/research KPI use the reconstructed chronological paths as CPCV hard-gate evidence. Canonical DD/recovery do not silently replace the existing stress-split DD/recovery gates.

Full-WFA/CV and CPCV worst aggregate expectancy both use the hard threshold **`>= 0.00R`**, with a small numerical epsilon only for floating-point noise.

For hypotheses created by a CPCV/Tournament/Monte-Carlo failure, Full-WFA is a proxy/safety screen only. `SUPPORTED`, `PARTIALLY_SUPPORTED`, or `FALSIFIED` closure is decided from matching evidence at the originating downstream stage.


## Backend E2E Audit R1 — sealed stage chain

Active physical chain:

`Data Flow → Discovery → CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion`

Hard invariants:
- exact Data Quality source hash before Discovery; no non-finite CP32 features; purge >= label horizon;
- AUTO Discovery Pool exactly 12; Full-WFA independently revalidated; scientific/windows and downstream history frozen;
- CPCV mandatory exact 6C2=15; purge and embargo >= label horizon; temporal/hybrid 42→11→77, all PASS;
- every downstream stage verifies the previous terminal seal and exact candidate identity; CP_POLICY_V1 is replayed rather than silently falling back to base threshold;
- Monte Carlo remains IID bootstrap with replacement and preserves strategy identity;
- Forward is predeclared, DQ-gated and append-only; insufficient sample waits, sufficient all-fail is terminal;
- Champion final fit uses frozen pre-Forward history only, locks CP32 feature order and SELL/SKIP/BUY class order, requires ONNX parity, and seals runtime artifacts.

Dedicated Stage 1–7 gates are part of the 93-gate cumulative suite. Historical 86-gate UI acceptance does not substitute for backend closure.
