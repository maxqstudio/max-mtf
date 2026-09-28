# CPMF v0.7.2 R4 — Windows Worker Lifecycle + Research Truth Repair

## Trigger

Owner runtime exposed two critical runtime defects in R3:

1. Navigating to another Streamlit page could flip an active Factory to `INTERRUPTED`.
2. STOP/ABORT could report a stopped state while backend research still consumed CPU, forcing the Owner to terminate Python from Task Manager.

The same runtime also showed an all-FAIL WFA leaderboard while the LLM report described `OPTIMAL_FAMILY_CONVERGENCE`.

## Root causes

### 1. Destructive Windows liveness probe

R3 used `os.kill(pid, 0)` inside `_pid_alive()`. On Windows, CPython maps signals other than CTRL_C/CTRL_BREAK to `TerminateProcess`; therefore a UI read intended only to test liveness could terminate the Factory worker. Streamlit navigation reruns the app and repeatedly calls `latest_job()/load_job()`, making navigation capable of killing the worker and then reconciling it as `INTERRUPTED`.

### 2. STOP was not verified

R3 `request_stop()` only wrote a sentinel and depended on later progress callbacks. `force_stop()` called `taskkill` but ignored its return status and unconditionally wrote `STOPPED`. A failed kill could therefore leave research alive while UI claimed completion.

### 3. Spawn ownership race

The launcher returned the worker PID to the current UI call but intentionally did not persist it until the worker claimed the job JSON. During that gap another rerun could see `QUEUED + pid=None` and lacked a durable process owner.

### 4. LLM did not receive explicit WFA truth in its top-results payload

`_safe_top_rows()` omitted `cv_gate_pass`, `cv_first_failed_gate`, and `cv_gate_reasons`. The Scientist could see attractive PF/expectancy values without seeing that every candidate had failed mandatory gates.

## R4 repair

- Windows liveness uses non-destructive Win32 `OpenProcess + GetExitCodeProcess`; Windows never calls `os.kill(pid, 0)`.
- A `historical external: *.process.json` sidecar is written immediately after worker spawn. It stores the owned PID without violating worker ownership of the main job JSON.
- Page/navigation reads are read-only for a live worker and cannot convert it to `INTERRUPTED`.
- `STOP RESEARCH NOW` is now a verified hard stop. It writes the stop sentinel, terminates the worker tree, waits for liveness to clear, and commits `STOPPED` only after verification.
- Failed termination is `STOP_FAILED`, retains the live PID, and exposes FORCE STOP. It never lies as `STOPPED`.
- PAUSE remains cooperative/safe-boundary; STOP means immediate termination with only previously committed atomic checkpoint work retained.
- Resume checks all known worker PID authorities (job JSON, process sidecar, heartbeat) before allowing a second worker.
- Candidate leaderboard exposes `First fail` and failed-gate count.
- A deterministic `RESEARCH HEALTH` panel reports `NO WFA SURVIVOR` vs `WFA SURVIVORS PRESENT` independently of LLM text.
- Scientist input now includes WFA PASS count, total count, first-failed-gate distribution, and per-candidate gate state.
- If deterministic WFA state is `NO_WFA_SURVIVOR`, Scientist/Director output is guarded so it cannot present the frontier as optimal/converged/robust.
- `historical external: research_diagnostics.json` now records first/all failed-gate distributions and near-miss candidates.

## Scientific authority deliberately unchanged

R4 does **not** relax KPI thresholds, bypass CPCV, change holdouts, add model families, or change Research Kernel V2 chronology. The all-FAIL condition must first be diagnosed using trustworthy runtime/evidence. Changing gates before that would hide whether the model/search or the acceptance design is the actual bottleneck.

## Follow-up research-kernel question

Source audit identified a separate design issue that is not silently changed in this runtime repair: WFA currently requires 16 mandatory gates before a candidate can reach CPCV, and some gates overlap logically (for example worst-fold Recovery >= 1.0 already implies every fold is net-positive under the current Recovery definition, making a separate 66% positive-fold requirement largely redundant). This should be redesigned as a stage-specific research qualification contract only after R4 produces clean failure-distribution evidence.
