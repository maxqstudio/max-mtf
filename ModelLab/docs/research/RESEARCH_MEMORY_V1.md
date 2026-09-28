# Research Memory V1 · CPMF v0.6.8

## Purpose

A new Guided generation must learn from prior **OOF-only** evidence rather than restart broad model discovery from a blank board.

## Memory contents

`historical external: research_memory.json` records:

- top OOF elites and exact model parameters;
- first failed gate and survival/economic diagnostics;
- trade count / coverage and training-memory months;
- prior Guided winner;
- accepted LLM Scientist scientific agenda;
- source hash and parent/next research-contract fingerprints.

Locked historical holdout metrics and fresh validation metrics are forbidden from Research Memory.

## Generation policy

Default round-1 budget is anchored as:

1. up to 4 elite rechecks under the **new research contract**;
2. remaining round budget reserved for registry exploration;
3. later rounds use current-generation evidence plus bounded family bias from memory;
4. identical candidates are deduplicated inside the generation;
5. an exact prior elite may be re-tested when label/feature/source contract changed, because it is no longer the same experiment.

The goal is learning continuity without trapping the search in a local optimum.
