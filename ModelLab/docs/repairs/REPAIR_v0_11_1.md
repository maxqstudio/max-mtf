# Repair v0.11.1 — Staged Data Quality Audit / MT5 Repair

v0.11.1 repairs two real Owner-runtime defects without changing strategy, optimizer, model, Challenger, or Champion semantics.

## Defects

1. `Max.set` produced by MT5 can be UTF-16 LE with BOM `FF FE`. The gap-repair launcher previously forced UTF-8 decoding and could fail before Strategy Tester started with `UnicodeDecodeError`.
2. Data Quality AUDIT / initial Auto Research preflight could initialize MetaTrader5 during the audit stage. Owner contract requires MT5 to remain closed unless the audit fails and repair/verification is actually required.

## Staged authority

```text
AUDIT / AUTO RESEARCH PREFLIGHT
→ local CP32 validation + exact-SHA cached broker proof only
→ NEVER initialize/open MT5

PASS
→ start Research immediately

repairable FAIL
→ enter REPAIR / VERIFY stage
→ only now may MT5 open
→ exact broker/feed verification
→ if broker-backed gaps exist: dedicated Max_GapRepair.set + Strategy Tester EA writer
→ post-repair broker verification must prove missing=0
→ cache broker proof for the exact repaired CSV SHA only
→ continue Research automatically

non-repairable FAIL
→ fail closed without opening MT5
```

The broker-proof cache is keyed by the full SHA-256 of `Max_Training.csv`; proof for any other byte revision is ignored.

## MT5 preset encoding

Gap repair now auto-detects MT5 preset encoding:

- UTF-16 BOM (`FF FE` / `FE FF`)
- UTF-8 BOM
- plain UTF-8
- BOM-less UTF-16 LE fallback when NUL-byte structure is present

`Max_GapRepair.set` preserves the detected source encoding. No conversion to UTF-8 is forced.

## Repair writer authority

The v0.9.1 first-write-wins repair contract remains unchanged:

- canonical Strategy Champion parameters are preserved;
- training writer is forced ON only in `Max_GapRepair.set`;
- live trading, ONNX Champion/Shadow execution, and trade-audit writers are disabled;
- interpolation, forward-fill, and synthetic CP32 rows remain forbidden;
- repair is not PASS until post-repair broker reconciliation proves zero source-backed missing bars.

## Auto Research

AUTO, MANUAL, and DISCOVERY worker preflight now use the same staged flow. A valid unchanged dataset with exact-SHA cached broker proof proceeds directly to Research without opening MT5. A proof miss or cached broker-backed gap is repairable and enters the MT5 repair stage. Structural corruption such as invalid OHLC/quotes/features remains fail-closed and does not launch MT5.

## Regression

`ModelLab/tests/v0111_data_quality_staged_repair_selftest.py` proves:

- UI AUDIT is local/cached only;
- Auto Research performs local audit before any MT5 repair call;
- broker proof cannot cross dataset SHA;
- MT5 UTF-16 `Max.set` is decoded and re-emitted safely;
- post-repair verification is mandatory.
