# CPMF v0.7.3 R5 — Research Workflow V3

## Authority

Canonical route:

`Data → Discovery Proposal → Cheap Screen → Full WFA → Pool 12 → CPCV Finalists → Tournament → Monte Carlo → Forward Championship → Champion`

Only **Full WFA** can qualify a Discovery candidate for Pool 12. Cheap Screen is a disposable CPU-allocation stage and has no promotion authority beyond deciding which proposals receive Full WFA compute.

## R1 foundation retained

- CPCV remains removed from every Discovery generation.
- Discovery freezes exactly 12 candidates that PASS the existing Full WFA/OOF acceptance authority.
- CPCV remains a separate progressive finalist stage after Pool 12 is frozen.
- Finalist order is frozen from WFA evidence before CPCV opens.
- Default CPCV resource policy remains target 3 survivors, batch 3, maximum 12 finalists, minimum 1 survivor to open Tournament.
- CPCV outcomes are not fed into active Discovery Research Memory or Director generation prompts.
- Existing KPI thresholds, Research Kernel V2 temporal chronology, GRU+Classical models, Tournament, Monte Carlo and Forward acceptance semantics remain unchanged.

## R2 Fidelity Ladder

Every Discovery proposal follows the same scientific CandidateSpec but receives compute in two stages:

1. **Cheap Screen** — fewer chronological WFA folds and reduced disposable training resource only (tree count / epochs where supported).
2. **Full WFA** — promoted proposals are rerun from the original unmodified CandidateSpec under the full WFA contract.

Cheap Screen PASS does not count as WFA PASS, cannot enter Pool 12, and cannot satisfy any downstream gate. It is only a resource allocator.

Default R2 resource policy:

- cheap WFA folds: 2 (never greater than the configured full WFA folds),
- cheap resource scale: 50%, bounded by each model-family registry minimum,
- promote fraction: 33% per completed screen batch,
- minimum promotions per round: 2,
- maximum promotions per round: 3,
- qualification authority: `FULL_WFA_ONLY`.

These are compute-allocation settings, not trading KPI thresholds.

## Failure Topology and Failure Margins

R2 records hard-gate failures without weakening them.

**Failure Margin** reports how far a candidate is from each existing WFA gate. A non-negative margin means the existing gate is met; a negative margin is a diagnostic shortfall. Margins are never summed into an acceptance score and cannot compensate for another failed gate.

**Failure Topology** aggregates first-failed gates, all failed gates, failure groups and family-level breakdowns across Full WFA candidates. Screen topology is stored separately and is explicitly diagnostic-only.

This gives the Research Director and operator a factual answer to "where are candidates failing?" while keeping the original hierarchical KPI authority intact.

## All-Trial Ledger

Every Cheap Screen and every Full WFA execution is retained in an append-only JSONL research ledger. Factory aggregation preserves generation and source-run lineage. Failed trials are not discarded.

The Factory-level ledger is research evidence only. It does not contain CPCV/Tournament/Monte Carlo/Forward outcomes as tuning feedback.

## CPCV finalist authority

After Pool 12 is frozen, CPCV opens as the same separate progressive finalist stage introduced in R1. CPCV PASS/FAIL remains hard authority. Ranking or Failure Margin cannot convert a CPCV FAIL into PASS.

Tournament cannot open from `DISCOVERY_POOL_READY`; it requires `CPCV_SURVIVORS_READY`. If no finalist survives CPCV, the cycle terminates `CPCV_NO_SURVIVOR` and downstream holdouts remain sealed.

## Fail closed

- Cheap Screen cannot write directly to Pool 12.
- A proposal discarded at Cheap Screen is not declared scientifically failed; it simply did not receive Full WFA budget in that block.
- Only an original CandidateSpec rerun under Full WFA can produce `cv_gate_pass=true` for Pool authority.
- No Failure Margin, ranking score, LLM directive or screen PASS can override a hard WFA gate.
- CPCV remains outside active Discovery adaptation.

## Next v0.7.3 revisions (not implemented in R2)

R3: Experiment Blocks + hypothesis lifecycle + Research Director bounded scientific directives and falsification/retirement rules.

R4: CPU calibration/resource scheduler and adversarial leakage CI.

No TCN, MiniROCKET, HMM, Transformer, new KPI, or broader model family is introduced in R2.

## R5 bounded closed-loop failure learning

A downstream failure is a research event, not permission to mutate the failed validator in place. The R5 loop is:

`Discovery → Pool → CPCV → Tournament → Monte Carlo`

At Discovery/Pool, CPCV, Tournament, or Monte-Carlo failure, the deterministic evidence is committed first. The LLM Scientist then produces a post-mortem plus a bounded executable hypothesis for the **next** Discovery cycle. The new cycle must re-enter through Discovery/WFA and earn every downstream gate again. Per-stage feedback exposure budgets prevent unlimited same-dataset tuning. Forward/fresh failure never loops against the same forward snapshot.

Dataset scope is fail-closed: the exact research contract includes the immutable Discovery snapshot **and source-master SHA-256**. If the master dataset changes, exact-contract learning does not silently transfer as authority.

CPCV terminology in R5 is explicit: the current N=6, k=2 implementation evaluates up to 15 **combinatorial purged splits**. Legacy `paths` fields remain for schema compatibility; R5 does not claim those 15 objects are canonical reconstructed CPCV backtest paths.


## R10 Discovery topology fairness

Within Discovery, standalone and hybrid candidates are allocated by the persisted Owner topology priority. Both use the same immutable snapshot, chronology, final SELL/SKIP/BUY schema and WFA/CPCV KPI authority. Hybrid internal OOF temporal meta-features do not change downstream stage authority.


## R6 per-family model-size priority
Every base model family has an Owner `Small 0.00 ↔ 1.00 Large` search preference. It is frozen at Factory start and propagated to Scientist/Supervisor context, but it does not hard-slice executable bounds. Temporal candidates are admitted by actual executable parameter count under `min(LEGAL, RESOURCE, SCIENTIFIC)` dynamic capacity; Large may reach the upper justified region while never overriding those hard ceilings.


## Research Control R1 — AUTO vs MANUAL

The canonical validation chain is unchanged, but candidate proposal authority is selectable.

**AUTO FACTORY:** existing bounded LLM Scientist/Director + deterministic Discovery. Full WFA remains the only Pool qualification authority; downstream CPCV/Tournament/Monte Carlo/Forward rules are unchanged.

**MANUAL RESEARCH:** the Owner exact candidate list is injected directly into the Full-WFA intake. No LLM proposal/review call and no deterministic candidate generation/replacement is allowed. WFA survivors continue through the exact same CPCV/Tournament/Monte Carlo/Forward/Champion validators. Manual failure is terminal for that candidate set; the Factory must not generate replacement candidates or open an automatic learning/restart loop.

## Scientist Knowledge R1 — capability awareness

The canonical workflow is additionally represented in `ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json` and `ModelLab/docs/contracts/MAX_WORKFLOW_CONTRACT_E2E.md` for Scientist Chat and room-transfer audit. This does not create a new research stage or modify PASS/FAIL.

Scientist may recommend capabilities outside Max, but must first perform a novelty check against existing authorities such as Single/Hybrid topology allocation, per-family size priority, Fidelity Ladder, Policy Discovery, training-memory/window discovery, Research Memory, hypothesis blocks, CPCV seed stability, Monte Carlo and Fresh/Forward separation. Existing capability must be named before an extension is proposed.

Any production-code or canonical-contract change invalidates the knowledge provenance manifest until `ModelLab/scientist/knowledge/scientist_knowledge.py` regenerates the knowledge/audit artifacts and `ModelLab/tests/scientist_knowledge_sync_selftest.py` passes.

## v0.7.6 KPI/sample authority

Research statistical acceptance is per gate through `MAX_GATE_KPI_PROFILES_V1`: Discovery, CPCV, Tournament, Monte Carlo and Fresh Forward. Champion is promotion/integrity/runtime authority, not an additional market test. The full profile snapshot is frozen with the Factory. Research AUTO sample uses H1 baseline 8 trades/month and the shared sqrt timeframe engine; the scaled monthly rate and final exact-range requirement are rounded up to integers. Strategy Optimizer is upstream and separate, with H1 baseline 20 trades/month.
