# MAX MTF v2.0.1 — Windows Acceptance UTF-8 Process Contract Repair

**Build scope:** `MAX_MTF_V2_0_1_WINDOWS_ACCEPTANCE_UTF8_PROCESS_CONTRACT_REPAIR`  
**Version:** `MAX MTF v2.0.1`  
**MTF-2:** `BLOCKED`

## Failure authority

Owner Windows one-click reached cumulative local acceptance and failed at `INHERITED_CPCV_SEED_CONFIRMATION` while printing a successful assertion message containing `DL→ML`. The scientific assertion passed; redirected child stdout used a CP1252-like encoding and raised `UnicodeEncodeError` on `→`.

## Repair contract

Canonical MAX acceptance Python subprocesses use one shared environment helper:

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`
- `MAX_MTF_ACCEPTANCE_UTF8=1` as an acceptance-scope marker

Captured Python subprocess output is decoded explicitly as UTF-8 with replacement only at the parent decoding boundary. The child environment remains mandatory; parent `encoding="utf-8"` is not treated as a substitute.

The contract is scoped to acceptance execution. Normal UI/runtime processes are not globally modified. MetaEditor/MT5 subprocess semantics are unchanged.

## Regression coverage

Existing gate `V201_RELEASE_PORTABILITY` is extended without changing the cumulative gate count (75):

- UTF-A: `DL→ML`
- UTF-B: `→ ↔ — · … × ≥`
- UTF-C: redirected/captured stdout and the real CPCV seed-confirmation test
- UTF-D: full canonical local acceptance executed with redirected stdout during final build validation
- UTF-E: Owner logged stage → canonical Python → nested Python child propagation
- UTF-F: deterministic CP1252-like negative fixture, runnable on non-Windows CI
- UTF-G: ASCII output remains byte-compatible

The negative fixture must fail with `UnicodeEncodeError` when the UTF-8 child environment is intentionally removed.

## Scientific invariants

No model-training, CPCV, WFA, Tournament, Monte Carlo, Forward, MoE, candidate-generation, capacity formula, MT5 or MetaEditor semantics are changed. Transformer/TFT legal headroom remains unchanged. Scientist Python remains a separate dedicated environment. MTF-2 remains blocked pending live Owner Windows PASS evidence.

## Follow-up — Windows UTF-8 newline portability selftest repair

**Build scope:** `MAX_MTF_V2_0_1_WINDOWS_UTF8_NEWLINE_PORTABILITY_SELFTEST_REPAIR`

Owner Windows proved the UTF-8 process contract itself works: UTF-F, UTF-A and UTF-B pass, the child exits zero, strict UTF-8 decoding succeeds, and all required Unicode symbols survive. The remaining UTF-C failure was a portability-selftest defect: LF in `UTF_SAMPLE` was compared text-exactly against redirected Windows output that may use CRLF.

This follow-up changes selftest semantics only:

- strict UTF-8 decoding remains `errors="strict"`; malformed UTF-8 must fail;
- representative UTF-8 byte sequences (`→`, `↔`, `—`, `≥`) must be present in captured bytes;
- only standard newline representations (`CRLF`, `CR`, `LF`) are normalized for semantic comparison;
- UTF-C1 proves LF semantic equivalence and UTF-C2 proves CRLF semantic equivalence;
- UTF-C3 proves malformed UTF-8 still fails and UTF-C4 proves real content corruption still fails;
- the real captured `ModelLab/tests/cpcv_seed_confirmation_selftest.py` regression remains mandatory with `DL→ML`;
- nested UTF-E and ASCII UTF-G semantic checks explicitly accept native newline convention while preserving exact content.

No global stdout newline reconfiguration is introduced into MAX. The canonical contract is UTF-8 text fidelity, not Unix LF byte identity. The prior `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `MAX_MTF_ACCEPTANCE_UTF8=1`, canonical MAX Python binding, and Scientist Python separation remain unchanged. Gate count remains 75 and MTF-2 remains blocked.
