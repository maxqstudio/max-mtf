# Runtime Repair5 — Scientist Live Hardware Context

## Owner runtime defect

Before START RESEARCH, Scientist Chat could receive `MAX_RESEARCH_SETTINGS_SNAPSHOT_V1` while receiving no actual hardware profile because `build_read_only_context()` returned early when no Factory directory existed. The model therefore treated configured accelerator allowances as possibilities and asked the Owner whether a dedicated GPU existed.

## Root cause

Current-host hardware was only loaded from `historical external: <factory>/hardware_profile.json`, which by definition does not exist before the first Factory is created.

## Repair

- `build_read_only_context()` accepts `live_hardware` and `live_compute_plan` independently of Factory state.
- `ModelLab/ui/app.py` supplies the cached current-host hardware probe and the effective `resolve_compute_plan(cfg)` result for every new Scientist Chat request.
- Context provenance adds `LIVE_HW` and `LIVE_COMPUTE`.
- Live/current hardware remains separate from any frozen active Factory hardware/resource plan.
- Scientist prompt forbids asking for hardware already present and forbids inferring accelerators from configured allowances.
- Stage 10 adversarial coverage now includes the pre-Factory hardware-truth case.

No research execution, KPI, model topology, or promotion authority is changed.

## Runtime reconcile reliability amendment

Owner runtime also showed intermittent Scientist Chat settlement: a response could remain loading until Stop even after the provider/worker had progressed. Repair4 used a one-shot hidden `reconcile` state pulse. If that single V2 state notification was coalesced or lost, no further reconciliation was guaranteed.

Repair5 replaces the one-shot pending-job pulse with a recurring bounded interval (~650 ms) tied to the exact `pending_job_id`. The interval is cleared when no job is pending or the job id changes. It has no conversation authority; it only requests another server read of the existing job state. Terminal CAS, thread identity, idempotency, and Stop semantics remain unchanged.
