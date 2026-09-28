# Scientist Python Analysis Runtime V1 — Max MTF v2.0.1

## Scope

Scientist Python is optional **analytical support only** for the existing LLM Scientist. It is not deterministic PASS/FAIL authority, candidate admission authority, Champion promotion authority, model training runtime, local acceptance authority, MT5 authority, governance authority, or canonical MAX Python.

MTF-2 remains blocked. This capability does not activate MTF research strategy execution.

## Interpreter authority

Production uses one dedicated user-local environment:

`%LOCALAPPDATA%\\MaxMTF\\ScientistPython\\venv`

The live invariant is `scientist_python_executable != canonical_max_python_executable`. Normal MAX startup never creates, installs, repairs, or mutates this environment. If it is absent or unhealthy, Scientist continues as `REASONING_ONLY`.

Owner diagnostic controls remain available:

- `ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd`
- `ModelLab/tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd`

Canonical Owner runtime acceptance is integrated in-candidate:

- `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd` — one click: pre-setup immutability snapshot -> setup -> health -> fresh cumulative acceptance -> live Windows Scientist runtime/security matrix -> read-only evidence verification.
- `ModelLab/acceptance/runners/owner_scientist_python_runtime_acceptance.py` — canonical live verifier and `--verify-existing` fail-closed evidence validator.
- `ModelLab/acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd` — optional read-only verification of already-generated Owner evidence.
- Owner evidence: `historical external: owner_acceptance/evidence/scientist_python/OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE.json`.

Owner runtime evidence is outside production source-signature authority. It binds the current source tree, suite, fresh local acceptance, dedicated interpreter/package identity, production analytical execution, Windows transitive file/process/network guards, fallback, Factory authority, and pre/post MAX/source immutability. Static/local tests never substitute for this live Windows proof.

The Scientist-specific pinned dependency identity is `requirements-scientist-python.txt`. V1 intentionally excludes Torch and other model-training packages.

## Shared execution capability

All supported Scientist entrypoints reuse the same deterministic host capability:

`run_scientist_python_analysis(...)`

The LLM may request one analysis attempt using only purpose, generated code, authorized opaque input IDs, seed, and bounded timeout. It cannot choose an interpreter, working directory, or arbitrary filesystem path.

Host flow:

`LLM Scientist -> structured analysis request -> deterministic validation -> dedicated Scientist Python child -> structured ANALYTICAL_EVIDENCE_ONLY -> LLM interpretation -> existing deterministic Factory admission`

One requested analysis permits one execution attempt. There is no automatic repair/retry loop.

## Guarded executor boundary

V1 is a **guarded local scientific executor, not an OS-secure sandbox**. The primary authority boundary is a deterministic capability/allowlist surface. Generated-code import spellings such as `numpy`, `pandas`, `scipy.stats`, and approved `sklearn` modules resolve to guarded proxy objects; raw scientific module objects are never placed in generated-code globals. Proxy outputs are primitive JSON values or guarded in-memory wrappers, so transitive native/system surfaces such as `numpy.ctypeslib.ctypes`, ndarray `.ctypes`/`.data`, arbitrary file readers/writers, native library loaders, process launchers, and sockets are not exposed.

The host AST validator uses the same governed capability vocabulary and rejects every attribute outside that allowlist, including private/dunder access and absolute path/URL literals in both text and bytes form. The child independently enforces the proxy boundary even if host validation is deliberately bypassed. Python-level file/process/network/thread monkeypatches remain defense in depth, and native math-library thread pools remain capped to one thread. These controls do **not** constitute VM/container/AppContainer isolation.

Allowed analytical imports remain `math`, `statistics`, `json`, NumPy, pandas, SciPy, and bounded scikit-learn analytical modules, but only the approved in-memory analytical operations listed by `ModelLab/scientist/python/scientist_python_capabilities.py` are reachable. Import-from names are checked against that same manifest. Capability wrappers also reject generated callbacks or unsupported keyword surfaces that would cause a real third-party library to invoke Scientist code while holding raw internal scientific objects.

Pandas boolean filtering is an explicitly governed in-memory capability. `_SafeDataFrame.__getitem__` accepts only column-name selection, column-name lists, and type-restricted governed boolean `_SafeSeries` / `_SafeArray` masks. Mask conversion to a real pandas boolean object occurs only inside trusted proxy implementation and the filtered result is immediately re-wrapped. Governed Series comparisons (`>`, `>=`, `<`, `<=`, `==`, `!=`) and boolean composition (`&`, `|`, `~`) remain wrapper-to-wrapper operations; no public/raw unwrap, callback bridge, `query`, or `eval` authority is exposed.

Generated code cannot use shell/process, network, arbitrary file I/O, package installation, MT5/MQL5, source/governance/acceptance mutation, Factory state mutation, Champion promotion, C-FFI/native library authority, or raw scientific-module authority. The child host itself necessarily uses Python compilation/execution primitives after deterministic validation; those primitives are not exposed to generated Scientist code.

## Authorized inputs

The LLM selects only host-authorized opaque evidence IDs. Examples include candidate metrics, WFA rows, CPCV metrics, Tournament evidence, Monte Carlo distributions, Data Quality summaries, capacity evidence, experiment tables, feature diagnostics, and related already-authorized Scientist context.

No local path supplied by the LLM becomes data authority. Missing evidence returns `INPUT_UNAVAILABLE` and `REASONING_ONLY`.

## Execution states and fallback

States are:

- `EXECUTED` -> `PYTHON_ASSISTED`
- `UNAVAILABLE` -> `REASONING_ONLY`
- `INPUT_UNAVAILABLE` -> `REASONING_ONLY`
- `REJECTED` -> `REASONING_ONLY`
- `ERROR` -> `REASONING_ONLY`
- `TIMEOUT` -> `REASONING_ONLY`

A timeout kills the analysis child. A failed attempt never authorizes fabricated Python-derived numbers and never crashes MAX merely because Scientist Python is unavailable.

## Bounds and reproducibility

Default seed: `42`.

Default timeout: `30 seconds`.

Maximum timeout: `120 seconds`.

Code, input payload, structured result, stdout/stderr excerpts, and requested input cardinality are bounded by deterministic host policy.

Each attempt writes runtime evidence under:

`ModelLab/runtime/scientist_analysis/<analysis_id>/`

Evidence records analysis identity/time/purpose/mode, exact generated code and SHA256, input identities/hashes, Scientist interpreter identity, Python/package versions, seed/timeout, execution state/exit code, bounded stdout/stderr, structured result/result hash, artifact hashes, and fallback reason.

Runtime analysis evidence is operational data and does not become production source authority.

## Deterministic authority preservation

Python may calculate or recommend, including a textual recommendation such as `PASS`, but that output remains `ANALYTICAL_EVIDENCE_ONLY`. Existing deterministic Factory validation remains the sole authority for PASS/FAIL, executable admission, promotion, and research lifecycle state.

Static Scientist Knowledge describes this capability but cannot prove live interpreter health. `scientist_python_health()` and deterministic runtime policy are live authority.

## Transitive native-authority adversarial proof

Mandatory gate `V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME` includes the Control Room escape class itself. Cases N-W prove: NumPy ctypes transitive access is rejected; the exact native disposable-file write primitive cannot create/modify bytes; Win32/native file paths are structurally fail-closed cross-platform and execute as a real Windows fixture on Windows; transitive native process/network attempts cannot run; bytes-path bypass is denied; the exposed capability manifest contains no known dangerous native/system attributes; legitimate NumPy, pandas, SciPy and approved sklearn in-memory analyses still execute; all unsafe attempts fall back to `REASONING_ONLY`; deterministic Factory authority is unchanged.

The capability surface is production authority in `ModelLab/scientist/python/scientist_python_capabilities.py` and is separately hashed in release provenance. A raw third-party module object must never be returned by the generated-code import hook.

Cases X1-X10 additionally prove governed pandas boolean filtering (simple, compound AND/OR, inversion, column/list selection, comparison operators, groupby/aggregation and governed NumPy boolean masks), no raw-mask leakage, callback-security preservation, transitive-security regression, and unchanged NumPy/SciPy/sklearn analytical execution.
