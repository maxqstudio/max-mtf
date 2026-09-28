# v0.6.2 · Hierarchical Routing + Survival Authority + Compact Grouped UI

This revision repairs three coupled defects instead of adding another patch layer.

## 1. Pipeline hierarchy is now manifest-driven

Primary operator tabs are:

1. `1 · Research`
2. `2 · Pipeline`
3. `3 · Champion`
4. `Advanced`

`Pipeline` shows only the legal branch for the selected lineage. Policy Discovery is optional and appears only when that lineage actually requires it.

Run discovery is manifest-driven and includes `AGENT_*`, `POLICY_*`, `FRESH_*`, and any future run directory with `historical external: model_manifest.json`.

`NEEDS_FRESH_HOLDOUT` no longer redirects to an old source run. The legal action is directly:

`VALIDATE FROZEN MODEL · FRESH DATA`

Deleted/retired historical runs therefore cannot haunt the operator UI as a navigation target.

## 2. Dataset / holdout provenance is explicit

New runs persist `DATASET_ID_V2`:

- symbol
- numeric period
- human timeframe
- source CSV name + SHA-256
- row count
- source start/end

Holdout identity is `HOLDOUT_ID_V2` and includes symbol + timeframe/period + date range + source hash + label/split contract.

Legacy registry collisions are ignored only when existing evidence proves the old and current timeframe identities differ. Ambiguous legacy state remains fail-closed.

## 3. KPI authority is hierarchical, not a total-score contest

Schema: `KPI_V5_HIERARCHICAL`.

Composite ranking: `CV_SCORE_V3_SURVIVAL_FIRST`.

PASS requires all mandatory gates. Score is never PASS authority.

Priority is locked:

`Drawdown > Recovery Factor > Profit Factor`

PF remains mandatory, but high PF cannot rescue bad DD/RF.

Walk-forward now also gates worst-fold DD and worst-fold Recovery so medians cannot hide one dangerous fold. Time/regime and stress robustness are mandatory, not decorative score components.

## 4. UI grouping

Primary KPI evidence is compact and grouped into contrasting panels:

- Survival · highest priority
- Economic Edge
- Robustness
- Execution / Stress

Full scorecard, leaderboards, Scientist journal, and artifacts are collapsed secondary details.

Research input is grouped by Dataset / Engines / Scientist / Start. Provider internals and tuning controls remain under Advanced or the Scientist connection expander.

## 5. Fail-closed routing

- `RESEARCH_REJECTED` -> stop / new research hypothesis
- `NEEDS_FRESH_HOLDOUT` -> frozen model + newer same-symbol/timeframe data
- original locked FAIL -> OOF Policy Discovery
- Policy OOF PASS -> fresh holdout
- fresh holdout PASS -> `ELIGIBLE_CHALLENGER`
- only `ELIGIBLE_CHALLENGER` exposes MT5 / shadow installation and Champion path

## Acceptance

`ModelLab/tests/acceptance_selftest.py` now proves, among other things:

- score weights sum to 100
- DD combined weight > Recovery combined weight > PF weight
- PF 3.0 cannot rescue failed DD/RF
- worst-fold survival failure fails closed
- time/regime and stress failures fail closed
- AGENT/POLICY/FRESH lineages are all discoverable
- M15 and H1 produce different holdout identities even with the same supplied legacy hash
- invalid fresh-model and post-locked routes fail before data access
- promotion revalidates current KPI policy

`ModelLab/research/post_locked_smoke.py` exercises a real bounded XGBoost OOF Policy Discovery transition without re-opening the retired locked test.
