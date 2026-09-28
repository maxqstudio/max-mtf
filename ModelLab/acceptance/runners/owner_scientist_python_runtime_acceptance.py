from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import acceptance.runners.run_acceptance as run_acceptance
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs
from acceptance.runners.max_python_bootstrap import (
    ENV_BOOTSTRAP_PYTHON, ENV_CANONICAL_PYTHON, validate_current_is_canonical,
)
from scientist.python.scientist_python_runtime import (
    CHILD_RUNNER,
    EVIDENCE_CLASS,
    run_scientist_python_analysis,
    scientist_python_health,
    validate_scientist_code,
)

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
EVIDENCE_DIR = PKG / "owner_acceptance/evidence/scientist_python"
EVIDENCE = EVIDENCE_DIR / "OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE.json"
PRE_SETUP = EVIDENCE_DIR / "OWNER_SCIENTIST_PYTHON_PRE_SETUP_SNAPSHOT.json"
SETUP_LOG = EVIDENCE_DIR / "setup_output.txt"
HEALTH_LOG = EVIDENCE_DIR / "health_output.txt"
LOCAL_ACCEPTANCE_LOG = EVIDENCE_DIR / "local_acceptance_output.txt"
SCHEMA = "MAX_MTF_OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE_V1"
SNAPSHOT_SCHEMA = "MAX_MTF_OWNER_SCIENTIST_PYTHON_PRE_SETUP_V1"
AUTHORITY = "ANALYTICAL_EVIDENCE_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY"
PINNED = {
    "numpy": "2.3.5",
    "pandas": "2.2.3",
    "scipy": "1.17.0",
    "scikit-learn": "1.8.0",
}
REQUIRED_CHECKS = (
    "EXACT_LOCAL_ACCEPTANCE_BINDING",
    "SCIENTIST_PYTHON_SETUP_READY",
    "SCIENTIST_PYTHON_HEALTH_READY",
    "SEPARATE_INTERPRETER",
    "PINNED_PACKAGE_VERSIONS",
    "PRODUCTION_ANALYTICAL_EXECUTION",
    "PANDAS_FILTERING",
    "NUMPY_ANALYSIS",
    "SCIPY_ANALYSIS",
    "SKLEARN_ANALYSIS",
    "NUMPY_CTYPES_GUARD",
    "PANDAS_CTYPES_GUARD",
    "SKLEARN_OS_GUARD",
    "WINDOWS_NATIVE_FILE_GUARD",
    "WINDOWS_PROCESS_GUARD",
    "WINDOWS_NETWORK_GUARD",
    "RAW_OBJECT_GUARD",
    "CALLBACK_GUARD",
    "REASONING_ONLY_FALLBACK",
    "FACTORY_AUTHORITY_PRESERVED",
    "SOURCE_IMMUTABILITY",
)


class OwnerScientistPythonAcceptanceError(RuntimeError):
    pass


def _canonical_max_python() -> str:
    try:
        return str(validate_current_is_canonical())
    except Exception as exc:
        raise OwnerScientistPythonAcceptanceError(f"CANONICAL_MAX_PYTHON_IDENTITY_INVALID: {exc}") from exc


def _bootstrap_python_identity() -> str | None:
    value = str(os.environ.get(ENV_BOOTSTRAP_PYTHON) or "").strip()
    return str(Path(value).resolve()) if value else None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_hash(value: Any) -> str:
    return _sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_UNREADABLE: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_NOT_OBJECT: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _excerpt(path: Path, limit: int = 5000) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "sha256": None, "excerpt": ""}
    data = path.read_bytes()
    return {
        "exists": True,
        "sha256": _sha_bytes(data),
        "excerpt": data.decode("utf-8", errors="replace")[-limit:],
    }


def _pip_freeze(python_exe: str) -> dict[str, Any]:
    try:
        cp = subprocess.run(
            [python_exe, "-m", "pip", "freeze", "--all"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90, check=False,
            env=acceptance_utf8_env(os.environ), **utf8_text_subprocess_kwargs(),
        )
        text = "\n".join(sorted(x.strip() for x in (cp.stdout or "").splitlines() if x.strip()))
        return {"exit_code": cp.returncode, "sha256": _sha_bytes(text.encode("utf-8")), "line_count": len(text.splitlines())}
    except Exception as exc:
        return {"exit_code": None, "sha256": None, "error": f"{type(exc).__name__}: {exc}"}


def _governance_hash() -> str:
    h = hashlib.sha256()
    gov = PKG / "governance"
    for p in sorted(gov.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(PKG).as_posix()
        h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def _current_binding() -> dict[str, Any]:
    accepted = run_acceptance.validate_local_acceptance_report(
        run_acceptance.OUT,
        require_current_tree=True,
        require_current_suite=True,
        require_fresh_full=True,
    )
    return {
        "source_tree_signature": str(accepted["source_tree_signature"]),
        "suite_signature": str(accepted["suite_signature"]),
        "local_acceptance_gate_count": int(accepted["gate_count"]),
        "local_acceptance_execution_mode": str(accepted["execution_mode"]),
        "local_acceptance_report_sha256": _sha_file(run_acceptance.OUT),
    }


def capture_pre_setup_snapshot(path: Path = PRE_SETUP) -> dict[str, Any]:
    python = _canonical_max_python()
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "generated_utc": _utcnow(),
        "source_tree_signature": run_acceptance._tree_sig(),
        "suite_signature": run_acceptance._suite_sig(),
        "bootstrap_python_executable": _bootstrap_python_identity(),
        "canonical_max_python_executable": python,
        "max_python_executable": python,
        "max_python_executable_sha256": _sha_file(Path(python)) if Path(python).is_file() else None,
        "max_python_packages": _pip_freeze(python),
        "governance_sha256": _governance_hash(),
    }
    _write_json(path, payload)
    return payload


def _clean_child_env() -> dict[str, str]:
    keep = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATH", "HOME", "USERPROFILE", "COMSPEC", "PATHEXT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep and isinstance(v, str)}
    env.update({
        "MAX_SCIENTIST_PYTHON_CHILD": "1",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    })
    return acceptance_utf8_env(env)


def _direct_child(scientist_exe: str, code: str, inputs: Mapping[str, Any], seed: int, cwd: Path) -> dict[str, Any]:
    request = json.dumps({"code": code, "inputs": dict(inputs), "seed": int(seed), "max_result_bytes": 512000}, ensure_ascii=False, separators=(",", ":"))
    try:
        cp = subprocess.run(
            [str(scientist_exe), "-I", str(CHILD_RUNNER)],
            input=request, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(cwd), env=_clean_child_env(), timeout=30, check=False,
            **utf8_text_subprocess_kwargs(),
        )
    except Exception as exc:
        return {"exit_code": None, "status": "HARNESS_ERROR", "error": f"{type(exc).__name__}: {exc}"}
    payload = None
    try:
        lines = [x for x in (cp.stdout or "").splitlines() if x.strip()]
        payload = json.loads(lines[-1]) if lines else None
    except Exception:
        payload = None
    return {
        "exit_code": cp.returncode,
        "child_payload": payload,
        "stdout_excerpt": (cp.stdout or "")[-3000:],
        "stderr_excerpt": (cp.stderr or "")[-3000:],
    }


def _exec_analysis(label: str, code: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    return run_scientist_python_analysis(
        {"purpose": label, "input_ids": sorted(inputs), "seed": 42, "timeout_sec": 30, "code": code},
        inputs,
        canonical_python=_canonical_max_python(),
        verify_packages=True,
    )


def _is_executed(result: Mapping[str, Any]) -> bool:
    return (
        result.get("execution_status") == "EXECUTED"
        and result.get("analysis_mode") == "PYTHON_ASSISTED"
        and result.get("evidence_class") == EVIDENCE_CLASS
        and result.get("structured_result") is not None
    )


def _normalize_package_versions(health: Mapping[str, Any]) -> dict[str, str | None]:
    raw = health.get("package_versions") if isinstance(health.get("package_versions"), dict) else {}
    return {name: (str(raw.get(name)) if raw.get(name) is not None else None) for name in PINNED}


def _base_failure_payload(first_failed_check: str, reason: str) -> dict[str, Any]:
    canonical_python = _canonical_max_python()
    health = scientist_python_health(canonical_python=canonical_python, verify_packages=True)
    payload = {
        "schema": SCHEMA,
        "project": "Max MTF",
        "version": "2.0.1",
        "phase": "OWNER_SCIENTIST_PYTHON_WINDOWS_RUNTIME_ACCEPTANCE",
        "generated_utc": _utcnow(),
        "overall_status": "FAIL",
        "first_failed_check": str(first_failed_check),
        "failure_reason": str(reason),
        "source_tree_signature": run_acceptance._tree_sig(),
        "suite_signature": run_acceptance._suite_sig(),
        "local_acceptance_gate_count": len(run_acceptance.TESTS),
        "local_acceptance_execution_mode": None,
        "scientist_python_executable": health.get("scientist_python_executable"),
        "bootstrap_python_executable": _bootstrap_python_identity(),
        "canonical_max_python_executable": canonical_python,
        "max_python_executable": canonical_python,
        "separate_interpreter": bool(health.get("separate_interpreter")),
        "python_version": health.get("python_version"),
        "numpy_version": (health.get("package_versions") or {}).get("numpy"),
        "pandas_version": (health.get("package_versions") or {}).get("pandas"),
        "scipy_version": (health.get("package_versions") or {}).get("scipy"),
        "sklearn_version": (health.get("package_versions") or {}).get("scikit-learn"),
        "setup_status": "FAIL" if first_failed_check == "SCIENTIST_PYTHON_SETUP_READY" else "UNKNOWN",
        "health_status": health.get("status"),
        "checks": [{"check": str(first_failed_check), "status": "FAIL", "details": str(reason)}],
    }
    return payload


def record_stage_failure(stage: str, exit_code: int | None = None) -> dict[str, Any]:
    mapping = {
        "SETUP": "SCIENTIST_PYTHON_SETUP_READY",
        "HEALTH": "SCIENTIST_PYTHON_HEALTH_READY",
        "LOCAL_ACCEPTANCE": "EXACT_LOCAL_ACCEPTANCE_BINDING",
    }
    check = mapping.get(str(stage).upper(), str(stage).upper())
    payload = _base_failure_payload(check, f"one-click stage failed: stage={stage} exit_code={exit_code}")
    payload["stage_exit_code"] = exit_code
    payload["setup_output"] = _excerpt(SETUP_LOG)
    payload["health_output"] = _excerpt(HEALTH_LOG)
    payload["local_acceptance_output"] = _excerpt(LOCAL_ACCEPTANCE_LOG)
    _write_json(EVIDENCE, payload)
    return payload


def _run_live_acceptance() -> dict[str, Any]:
    started = _utcnow()
    canonical_python = _canonical_max_python()
    checks: list[dict[str, Any]] = []
    first_failed: str | None = None

    def check(name: str, condition: bool, details: Any = None) -> bool:
        nonlocal first_failed
        status = "PASS" if condition else "FAIL"
        checks.append({"check": name, "status": status, "details": details})
        if not condition and first_failed is None:
            first_failed = name
        return condition

    if os.name != "nt":
        raise OwnerScientistPythonAcceptanceError("OWNER_WINDOWS_RUNTIME_REQUIRED")
    if not PRE_SETUP.is_file():
        raise OwnerScientistPythonAcceptanceError("PRE_SETUP_IMMUTABILITY_SNAPSHOT_REQUIRED")
    pre = _read_json(PRE_SETUP)
    if pre.get("schema") != SNAPSHOT_SCHEMA:
        raise OwnerScientistPythonAcceptanceError("PRE_SETUP_SNAPSHOT_SCHEMA_MISMATCH")

    binding = _current_binding()
    check("EXACT_LOCAL_ACCEPTANCE_BINDING", binding["local_acceptance_gate_count"] == len(run_acceptance.TESTS) and binding["local_acceptance_execution_mode"] == "FRESH_FULL", binding)

    health = scientist_python_health(canonical_python=canonical_python, verify_packages=True)
    check("SCIENTIST_PYTHON_SETUP_READY", health.get("status") == "READY", {"health": health, "setup_output": _excerpt(SETUP_LOG)})
    check("SCIENTIST_PYTHON_HEALTH_READY", health.get("status") == "READY", {"health": health, "health_output": _excerpt(HEALTH_LOG)})
    scientist_exe = str(health.get("scientist_python_executable") or "")
    max_exe = canonical_python
    separate = bool(health.get("separate_interpreter")) and bool(scientist_exe) and os.path.normcase(str(Path(scientist_exe).resolve())) != os.path.normcase(max_exe)
    check("SEPARATE_INTERPRETER", separate, {"scientist_python_executable": scientist_exe, "max_python_executable": max_exe})
    versions = _normalize_package_versions(health)
    check("PINNED_PACKAGE_VERSIONS", versions == PINNED, {"expected": PINNED, "actual": versions})

    inputs = {"WFA_ROWS": [
        {"expectancy": 0.10, "pf": 1.10, "regime": "A"},
        {"expectancy": 0.20, "pf": 1.20, "regime": "A"},
        {"expectancy": 0.35, "pf": 1.40, "regime": "B"},
        {"expectancy": 0.50, "pf": 1.60, "regime": "B"},
        {"expectancy": 0.80, "pf": 1.90, "regime": "B"},
    ]}

    production = _exec_analysis(
        "Owner WFA statistical summary",
        "import numpy as np\nxs=np.array([float(r['expectancy']) for r in inputs['WFA_ROWS']])\nys=np.array([float(r['pf']) for r in inputs['WFA_ROWS']])\nresult={'mean':np.mean(xs),'median':np.median(xs),'std':np.std(xs),'p75':np.percentile(xs,75),'corr':np.corrcoef(xs,ys).tolist()}",
        inputs,
    )
    check("PRODUCTION_ANALYTICAL_EXECUTION", _is_executed(production), production)

    pandas_code = (
        "import pandas as pd\n"
        "df=pd.DataFrame({'x':[1,2,3],'y':[10,20,30],'name':['A','B','A']})\n"
        "simple=df[df['x']>1]\n"
        "and_rows=df[(df['x']>=2)&(df['y']<30)]\n"
        "or_rows=df[(df['x']>2)|(df['y']==10)]\n"
        "inv=df[~(df['x']>1)]\n"
        "cols=df[['x','y']]\n"
        "assigned=df.assign(z=df['x']*2).sort_values('x')\n"
        "grouped=df.groupby('name').mean()\n"
        "result={'simple':simple.to_dict(),'and':and_rows.to_dict(),'or':or_rows.to_dict(),'inv':inv.to_dict(),'col':df['x'].to_dict(),'cols':cols.to_dict(),'assigned':assigned.to_dict(),'grouped':grouped.to_dict()}")
    pandas_result = _exec_analysis("Owner pandas governed filtering matrix", pandas_code, inputs)
    check("PANDAS_FILTERING", _is_executed(pandas_result), pandas_result)

    numpy_result = _exec_analysis(
        "Owner NumPy matrix",
        "import numpy as np\na=np.array([1,2,3,4]); b=np.array([2,4,6,8])\nresult={'mean':np.mean(a),'std':np.std(a),'percentile':np.percentile(a,75),'quantile':np.quantile(a,0.5),'corr':np.corrcoef(a,b).tolist()}", inputs)
    check("NUMPY_ANALYSIS", _is_executed(numpy_result), numpy_result)

    scipy_result = _exec_analysis(
        "Owner SciPy matrix",
        "from scipy import stats\nx=[1,2,3,4]; y=[1.1,1.9,3.2,4.1]\nresult={'pearson':stats.pearsonr(x,y),'ttest':stats.ttest_ind(x,y)}", inputs)
    check("SCIPY_ANALYSIS", _is_executed(scipy_result), scipy_result)

    sklearn_result = _exec_analysis(
        "Owner sklearn matrix",
        "from sklearn.linear_model import LinearRegression\nX=[[1],[2],[3],[4]]; y=[2,4.2,5.9,8.1]\nm=LinearRegression().fit(X,y)\nresult={'coef':m.coef_.tolist(),'intercept':m.intercept_,'score':m.score(X,y)}", inputs)
    check("SKLEARN_ANALYSIS", _is_executed(sklearn_result), sklearn_result)

    # Historical/transitive host-path guards.
    security_cases = {
        "NUMPY_CTYPES_GUARD": "import numpy as np\nresult=str(np.ctypeslib)",
        "PANDAS_CTYPES_GUARD": "import pandas as pd\nresult=str(pd.errors.ctypes.CDLL)",
        "SKLEARN_OS_GUARD": "import sklearn\nresult=sklearn.os.listdir('..')",
        "RAW_OBJECT_GUARD": "import pandas as pd\ndf=pd.DataFrame({'x':[1,2]})\nresult=str(df._value)",
    }
    security_results: dict[str, Any] = {}
    for name, code in security_cases.items():
        validation = validate_scientist_code(code)
        result = _exec_analysis(f"Owner security probe {name}", code, inputs)
        security_results[name] = {"validation": validation, "execution": result}
        check(name, (not validation.get("ok")) and result.get("execution_status") == "REJECTED" and result.get("analysis_mode") == "REASONING_ONLY", security_results[name])

    callback = _exec_analysis(
        "Owner callback escape probe",
        "import pandas as pd\ndf=pd.DataFrame({'x':[1,2,3]})\nresult=df.assign(y=lambda row: row['x']).to_dict()", inputs)
    check("CALLBACK_GUARD", callback.get("execution_status") in {"ERROR", "REJECTED"} and callback.get("analysis_mode") == "REASONING_ONLY" and callback.get("structured_result") is None, callback)

    attack_root = Path(tempfile.mkdtemp(prefix="max_mtf_scientist_windows_guard_"))
    try:
        file_marker = attack_root / "native_file_marker.txt"
        file_path = str(file_marker).replace("\\", "\\\\")
        file_code = (
            "import numpy as np\n"
            "k=np.ctypeslib.ctypes.windll.kernel32\n"
            f'h=k.CreateFileW("{file_path}",0x40000000,0,None,2,0,None)\n'
            "result={'handle':h}")
        file_child = _direct_child(scientist_exe, file_code, inputs, 42, attack_root)
        check("WINDOWS_NATIVE_FILE_GUARD", file_child.get("exit_code") != 0 and not file_marker.exists(), {**file_child, "marker_exists": file_marker.exists()})

        process_marker = attack_root / "native_process_marker.txt"
        cmd = f'cmd /c echo ESCAPE>"{process_marker}"'.replace("\\", "\\\\")
        process_code = (
            "import numpy as np\n"
            "k=np.ctypeslib.ctypes.windll.kernel32\n"
            f'r=k.WinExec(b"{cmd}",0)\n'
            "result={'rc':r}")
        process_child = _direct_child(scientist_exe, process_code, inputs, 42, attack_root)
        time.sleep(0.5)
        check("WINDOWS_PROCESS_GUARD", process_child.get("exit_code") != 0 and not process_marker.exists(), {**process_child, "marker_exists": process_marker.exists()})

        network_code = "import numpy as np\nw=np.ctypeslib.ctypes.windll.ws2_32\ns=w.socket(2,1,6)\nresult={'socket':s}"
        network_child = _direct_child(scientist_exe, network_code, inputs, 42, attack_root)
        check("WINDOWS_NETWORK_GUARD", network_child.get("exit_code") != 0, network_child)
    finally:
        shutil.rmtree(attack_root, ignore_errors=True)

    # Explicit host-controlled missing-runtime fixture. The live installation is untouched.
    missing_home = Path(tempfile.mkdtemp(prefix="max_mtf_scientist_missing_")) / "absent"
    fallback = run_scientist_python_analysis(
        {"purpose": "Owner unavailable runtime fixture", "input_ids": ["WFA_ROWS"], "seed": 42, "timeout_sec": 30, "code": "result={'should_not_execute':True}"},
        inputs, runtime_home=missing_home, canonical_python=sys.executable, verify_packages=False,
    )
    live_after_fallback = scientist_python_health(canonical_python=sys.executable, verify_packages=True)
    check("REASONING_ONLY_FALLBACK", fallback.get("execution_status") == "UNAVAILABLE" and fallback.get("analysis_mode") == "REASONING_ONLY" and fallback.get("structured_result") is None and live_after_fallback.get("status") == "READY", {"fixture": fallback, "live_after": live_after_fallback})

    authority_probe = _exec_analysis(
        "Owner Factory authority preservation probe",
        "result={'candidate':'PASS','recommendation':'promote','requested_factory_action':'PASS'}", inputs)
    check("FACTORY_AUTHORITY_PRESERVED", _is_executed(authority_probe) and authority_probe.get("authority") == "ANALYTICAL_SUPPORT_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY", authority_probe)

    # Compare source/MAX identities captured before setup with identities after every live test.
    after_tree = run_acceptance._tree_sig()
    after_suite = run_acceptance._suite_sig()
    after_python = str(Path(sys.executable).resolve())
    after_python_sha = _sha_file(Path(after_python)) if Path(after_python).is_file() else None
    after_freeze = _pip_freeze(after_python)
    after_gov = _governance_hash()
    immutable = (
        pre.get("source_tree_signature") == after_tree == binding["source_tree_signature"]
        and pre.get("suite_signature") == after_suite == binding["suite_signature"]
        and os.path.normcase(str(pre.get("max_python_executable") or "")) == os.path.normcase(after_python)
        and pre.get("max_python_executable_sha256") == after_python_sha
        and (pre.get("max_python_packages") or {}).get("sha256") == after_freeze.get("sha256")
        and pre.get("governance_sha256") == after_gov
    )
    immutability = {
        "pre_setup": pre,
        "after_source_tree_signature": after_tree,
        "after_suite_signature": after_suite,
        "after_max_python_executable": after_python,
        "after_max_python_executable_sha256": after_python_sha,
        "after_max_python_packages": after_freeze,
        "after_governance_sha256": after_gov,
    }
    check("SOURCE_IMMUTABILITY", immutable, immutability)

    by_name = {row["check"]: row for row in checks}
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "project": "Max MTF",
        "version": "2.0.1",
        "phase": "OWNER_SCIENTIST_PYTHON_WINDOWS_RUNTIME_ACCEPTANCE",
        "generated_utc": started,
        "completed_utc": _utcnow(),
        "overall_status": "PASS" if first_failed is None else "FAIL",
        "first_failed_check": first_failed,
        **binding,
        "bootstrap_python_executable": _bootstrap_python_identity(),
        "canonical_max_python_executable": max_exe,
        "scientist_python_executable": scientist_exe,
        "max_python_executable": max_exe,
        "separate_interpreter": separate,
        "python_version": health.get("python_version"),
        "numpy_version": versions.get("numpy"),
        "pandas_version": versions.get("pandas"),
        "scipy_version": versions.get("scipy"),
        "sklearn_version": versions.get("scikit-learn"),
        "setup_status": "READY" if by_name.get("SCIENTIST_PYTHON_SETUP_READY", {}).get("status") == "PASS" else "ERROR",
        "health_status": health.get("status"),
        "production_analysis_status": by_name.get("PRODUCTION_ANALYTICAL_EXECUTION", {}).get("status"),
        "pandas_filtering_status": by_name.get("PANDAS_FILTERING", {}).get("status"),
        "numpy_status": by_name.get("NUMPY_ANALYSIS", {}).get("status"),
        "scipy_status": by_name.get("SCIPY_ANALYSIS", {}).get("status"),
        "sklearn_status": by_name.get("SKLEARN_ANALYSIS", {}).get("status"),
        "numpy_ctypes_guard": by_name.get("NUMPY_CTYPES_GUARD", {}).get("status"),
        "pandas_ctypes_guard": by_name.get("PANDAS_CTYPES_GUARD", {}).get("status"),
        "sklearn_os_guard": by_name.get("SKLEARN_OS_GUARD", {}).get("status"),
        "windows_file_guard": by_name.get("WINDOWS_NATIVE_FILE_GUARD", {}).get("status"),
        "windows_process_guard": by_name.get("WINDOWS_PROCESS_GUARD", {}).get("status"),
        "windows_network_guard": by_name.get("WINDOWS_NETWORK_GUARD", {}).get("status"),
        "raw_object_guard": by_name.get("RAW_OBJECT_GUARD", {}).get("status"),
        "callback_guard": by_name.get("CALLBACK_GUARD", {}).get("status"),
        "reasoning_only_fallback": by_name.get("REASONING_ONLY_FALLBACK", {}).get("status"),
        "factory_authority_preserved": by_name.get("FACTORY_AUTHORITY_PRESERVED", {}).get("status"),
        "source_immutability": by_name.get("SOURCE_IMMUTABILITY", {}).get("status"),
        "evidence_class": EVIDENCE_CLASS,
        "authority": AUTHORITY,
        "checks": checks,
        "production_analysis": production,
        "pandas_analysis": pandas_result,
        "numpy_analysis": numpy_result,
        "scipy_analysis": scipy_result,
        "sklearn_analysis": sklearn_result,
        "security_results": security_results,
        "callback_result": callback,
        "fallback_result": fallback,
        "factory_authority_probe": authority_probe,
        "immutability": immutability,
        "setup_output": _excerpt(SETUP_LOG),
        "health_output": _excerpt(HEALTH_LOG),
        "local_acceptance_output": _excerpt(LOCAL_ACCEPTANCE_LOG),
        "platform": platform.platform(),
    }
    _write_json(EVIDENCE, payload)
    return payload


def verify_owner_evidence_payload(
    payload: Mapping[str, Any],
    *,
    current_binding: Mapping[str, Any] | None = None,
    live_health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_NOT_OBJECT")
    if payload.get("schema") != SCHEMA or payload.get("project") != "Max MTF" or payload.get("version") != "2.0.1":
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_IDENTITY_MISMATCH")
    if str(payload.get("overall_status") or "").upper() != "PASS" or payload.get("first_failed_check") is not None:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_NOT_PASS")
    try:
        dt = datetime.fromisoformat(str(payload.get("generated_utc") or "").replace("Z", "+00:00"))
    except Exception as exc:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_TIMESTAMP_INVALID") from exc
    if dt.tzinfo is None:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_TIMESTAMP_NAIVE")

    binding = dict(current_binding or _current_binding())
    for key in ("source_tree_signature", "suite_signature", "local_acceptance_gate_count", "local_acceptance_execution_mode"):
        if payload.get(key) != binding.get(key):
            raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_BINDING_MISMATCH: {key}")
    if payload.get("local_acceptance_execution_mode") != "FRESH_FULL":
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_LOCAL_ACCEPTANCE_NOT_FRESH_FULL")

    rows = payload.get("checks")
    if not isinstance(rows, list):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_CHECKS_NOT_LIST")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("check"):
            raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_CHECK_ROW_INVALID")
        name = str(row["check"])
        if name in by_name:
            raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_DUPLICATE_CHECK: {name}")
        by_name[name] = row
    for name in REQUIRED_CHECKS:
        if name not in by_name:
            raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_MISSING_CHECK: {name}")
        if str(by_name[name].get("status") or "").upper() != "PASS":
            raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_CHECK_NOT_PASS: {name}")

    required_fields = {
        "setup_status": "READY",
        "health_status": "READY",
        "production_analysis_status": "PASS",
        "pandas_filtering_status": "PASS",
        "numpy_status": "PASS",
        "scipy_status": "PASS",
        "sklearn_status": "PASS",
        "numpy_ctypes_guard": "PASS",
        "pandas_ctypes_guard": "PASS",
        "sklearn_os_guard": "PASS",
        "windows_file_guard": "PASS",
        "windows_process_guard": "PASS",
        "windows_network_guard": "PASS",
        "raw_object_guard": "PASS",
        "callback_guard": "PASS",
        "reasoning_only_fallback": "PASS",
        "factory_authority_preserved": "PASS",
        "source_immutability": "PASS",
    }
    for key, expected in required_fields.items():
        if payload.get(key) != expected:
            raise OwnerScientistPythonAcceptanceError(f"OWNER_SCIENTIST_EVIDENCE_FIELD_NOT_PASS: {key}")
    if payload.get("evidence_class") != EVIDENCE_CLASS or payload.get("authority") != AUTHORITY:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_AUTHORITY_MISMATCH")

    scientist_exe = str(payload.get("scientist_python_executable") or "")
    max_exe = str(payload.get("max_python_executable") or "")
    canonical_field = str(payload.get("canonical_max_python_executable") or max_exe)
    if not scientist_exe or not max_exe or not bool(payload.get("separate_interpreter")):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_INTERPRETER_IDENTITY_MISSING")
    if os.path.normcase(scientist_exe) == os.path.normcase(max_exe):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_INTERPRETER_NOT_SEPARATE")
    if os.path.normcase(canonical_field) != os.path.normcase(max_exe):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_CANONICAL_MAX_INTERPRETER_MISMATCH")
    evidence_versions = {
        "numpy": str(payload.get("numpy_version") or ""),
        "pandas": str(payload.get("pandas_version") or ""),
        "scipy": str(payload.get("scipy_version") or ""),
        "scikit-learn": str(payload.get("sklearn_version") or ""),
    }
    if evidence_versions != PINNED:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_PACKAGE_IDENTITY_MISMATCH")

    health = dict(live_health or scientist_python_health(canonical_python=_canonical_max_python(), verify_packages=True))
    if str(health.get("status") or "") != "READY":
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_LIVE_HEALTH_NOT_READY")
    if os.path.normcase(str(health.get("scientist_python_executable") or "")) != os.path.normcase(scientist_exe):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_LIVE_INTERPRETER_MISMATCH")
    if os.path.normcase(str(health.get("canonical_max_python_executable") or "")) != os.path.normcase(max_exe):
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_EVIDENCE_LIVE_MAX_INTERPRETER_MISMATCH")
    if _normalize_package_versions(health) != PINNED:
        raise OwnerScientistPythonAcceptanceError("OWNER_SCIENTIST_LIVE_PACKAGE_IDENTITY_MISMATCH")
    return {"status": "PASS", "evidence": str(EVIDENCE), "source_tree_signature": binding["source_tree_signature"], "suite_signature": binding["suite_signature"]}


def verify_existing_evidence(path: Path = EVIDENCE) -> dict[str, Any]:
    return verify_owner_evidence_payload(_read_json(path))


def _print_summary(payload: Mapping[str, Any]) -> None:
    print(json.dumps({
        "overall_status": payload.get("overall_status"),
        "first_failed_check": payload.get("first_failed_check"),
        "evidence": str(EVIDENCE),
        "source_tree_signature": payload.get("source_tree_signature"),
        "suite_signature": payload.get("suite_signature"),
        "local_acceptance_gate_count": payload.get("local_acceptance_gate_count"),
        "bootstrap_python_executable": payload.get("bootstrap_python_executable"),
        "scientist_python_executable": payload.get("scientist_python_executable"),
        "canonical_max_python_executable": payload.get("canonical_max_python_executable"),
        "max_python_executable": payload.get("max_python_executable"),
        "health_status": payload.get("health_status"),
    }, indent=2, ensure_ascii=False, default=str))


def _run_logged_stage(command: list[str], log_path: Path, *, timeout: int | None = None) -> int:
    cp = subprocess.run(
        command, cwd=ROOT, env=acceptance_utf8_env(os.environ),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=timeout, check=False, **utf8_text_subprocess_kwargs(),
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(cp.stdout or "", encoding="utf-8")
    if cp.stdout:
        print(cp.stdout, end="" if cp.stdout.endswith("\n") else "\n")
    return int(cp.returncode)


def run_one_click_owner_acceptance() -> int:
    canonical = _canonical_max_python()
    capture_pre_setup_snapshot()

    rc = _run_logged_stage([canonical, "-m", "scientist.python.scientist_python_setup", "setup"], SETUP_LOG, timeout=1800)
    if rc != 0:
        payload = record_stage_failure("SETUP", rc); _print_summary(payload); return 1

    rc = _run_logged_stage([canonical, "-m", "scientist.python.scientist_python_setup", "health"], HEALTH_LOG, timeout=300)
    if rc != 0:
        payload = record_stage_failure("HEALTH", rc); _print_summary(payload); return 1

    # The exact same canonical MAX interpreter runs cumulative acceptance. PATH changes
    # after bootstrap cannot change authority because no stage rediscovery occurs here.
    rc = _run_logged_stage([canonical, "-m", "acceptance.runners.run_acceptance"], LOCAL_ACCEPTANCE_LOG, timeout=None)
    if rc != 0:
        payload = record_stage_failure("LOCAL_ACCEPTANCE", rc); _print_summary(payload); return 1

    payload = _run_live_acceptance()
    _print_summary(payload)
    if payload.get("overall_status") != "PASS":
        return 1
    verify_existing_evidence(EVIDENCE)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one-click", action="store_true")
    ap.add_argument("--snapshot-before-setup", action="store_true")
    ap.add_argument("--verify-existing", action="store_true")
    ap.add_argument("--record-stage-failure", choices=["SETUP", "HEALTH", "LOCAL_ACCEPTANCE"])
    ap.add_argument("--stage-exit-code", type=int, default=None)
    args = ap.parse_args()
    try:
        if args.one_click:
            return run_one_click_owner_acceptance()
        if args.snapshot_before_setup:
            snap = capture_pre_setup_snapshot()
            print(json.dumps({"status": "PASS", "snapshot": str(PRE_SETUP), "source_tree_signature": snap["source_tree_signature"], "suite_signature": snap["suite_signature"]}, indent=2))
            return 0
        if args.record_stage_failure:
            payload = record_stage_failure(args.record_stage_failure, args.stage_exit_code)
            _print_summary(payload)
            return 1
        if args.verify_existing:
            print(json.dumps(verify_existing_evidence(EVIDENCE), indent=2, ensure_ascii=False))
            return 0
        payload = _run_live_acceptance()
        _print_summary(payload)
        if payload.get("overall_status") != "PASS":
            return 1
        verify_existing_evidence(EVIDENCE)
        return 0
    except Exception as exc:
        payload = _base_failure_payload("OWNER_RUNTIME_ACCEPTANCE", f"{type(exc).__name__}: {exc}")
        payload["setup_output"] = _excerpt(SETUP_LOG)
        payload["health_output"] = _excerpt(HEALTH_LOG)
        payload["local_acceptance_output"] = _excerpt(LOCAL_ACCEPTANCE_LOG)
        _write_json(EVIDENCE, payload)
        print(json.dumps({"overall_status": "FAIL", "first_failed_check": payload.get("first_failed_check"), "reason": payload.get("failure_reason"), "evidence": str(EVIDENCE)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
