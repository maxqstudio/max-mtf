# REPAIR v0.8.9 — Strategy Optimizer cache/frame recovery

## Runtime defect
Real MT5 Fast Genetic evidence showed `historical external: Max.xml` with 9665 unique parameter vectors but `Max_metrics.csv` with only 3745 frame-backed vectors. The sidecar was a strict subset of XML and the highest-ranked XML rows had no frame evidence. MT5 can reuse optimization-cache results without replaying `OnTesterPass`/`OnTesterDeinit` frame handling.

## Repair
1. `Max.mq5` declares `#property tester_no_cache`, forcing every optimization pass to be recalculated so `OnTester()` can emit fresh Mean-R/Weighted-R frames.
2. Missing frame evidence is row-local incompleteness, not a reason to discard the whole multi-hour XML round.
3. Evidence-incomplete rows cannot pass Weighted-R or become Champion.
4. If an incomplete row passes every native/XML gate, Champion selection is blocked until that contender is revalidated; refinement preserves the strongest unresolved contender.
5. Extra sidecar parameter vectors remain fail-closed provenance errors.

The v0.8.8 `FrameInputs` parameter-vector join remains authoritative.
