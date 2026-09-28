from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scientist.python.scientist_python_capabilities import (
    ALLOWED_IMPORTS,
    SAFE_ATTRIBUTE_NAMES,
    SAFE_IMPORT_SURFACE,
    TRANSITIVE_DANGEROUS_ATTRIBUTES,
)

ROOT = MODELLAB_ROOT
PACKAGE_ROOT = ROOT.parent
RUNTIME_ROOT = ROOT / "runtime" / "scientist_analysis"
REQUIREMENTS_FILE = ROOT / "requirements" / "requirements-scientist-python.txt"
CHILD_RUNNER = Path(__file__).resolve().with_name("scientist_python_child.py")

SCHEMA = "MAX_SCIENTIST_PYTHON_ANALYSIS_V1"
HEALTH_SCHEMA = "MAX_SCIENTIST_PYTHON_HEALTH_V1"
EVIDENCE_CLASS = "ANALYTICAL_EVIDENCE_ONLY"
DEFAULT_SEED = 42
DEFAULT_TIMEOUT_SEC = 30
MAX_TIMEOUT_SEC = 120
MAX_CODE_CHARS = 20_000
MAX_INPUT_BYTES = 2_000_000
MAX_RESULT_BYTES = 512_000
MAX_STDIO_CHARS = 12_000
MAX_INPUT_IDS = 16

# Generated imports resolve to governed capability proxies in the child.
DENIED_IMPORT_ROOTS = {
    "os", "subprocess", "socket", "pathlib", "shutil", "requests", "urllib", "http",
    "ctypes", "multiprocessing", "threading", "importlib", "inspect", "pickle", "marshal",
    "builtins", "sys", "asyncio", "webbrowser", "ftplib", "smtplib", "telnetlib", "ssl",
}
DENIED_NAMES = {
    "open", "exec", "eval", "compile", "input", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "breakpoint", "help", "memoryview",
}
# Guard common file/network/process escape surfaces reachable through otherwise-allowed
# scientific packages. This is a guarded executor, not a claim of OS-level sandboxing.
# Attribute authority is allowlist-based. Raw scientific modules are never exposed to generated code.
PATH_LITERAL_RE = re.compile(r"(?:^[A-Za-z]:[\\/]|^\\\\|^/|file://|https?://)", re.I)

# Deterministic host-side input aliases. The LLM may choose only these opaque IDs, never
# paths. The values are copied from already-authorized Scientist context/user payloads.
INPUT_KEY_TO_ID = {
    "top_walk_forward_results": "WFA_ROWS",
    "latest_generation": "WFA_ROWS",
    "candidate_summaries": "CANDIDATE_METRICS",
    "candidate_pool": "CANDIDATE_POOL",
    "live_candidates": "LIVE_CANDIDATES",
    "family_statistics": "FAMILY_STATISTICS",
    "family_stats": "FAMILY_STATISTICS",
    "fold_forensics": "FOLD_FORENSICS",
    "cpcv": "CPCV_METRICS",
    "tournament": "TOURNAMENT_EVIDENCE",
    "monte_carlo": "MONTE_CARLO_DISTRIBUTIONS",
    "data_quality": "DATA_QUALITY_SUMMARY",
    "dataset_capacity": "DATASET_CAPACITY",
    "capacity_evidence": "CAPACITY_EVIDENCE",
    "capacity_evidence_by_family": "CAPACITY_EVIDENCE_BY_FAMILY",
    "failure_topology": "FAILURE_TOPOLOGY",
    "stage_evidence": "STAGE_EVIDENCE",
    "generation_summary": "GENERATION_SUMMARY",
    "research_memory": "RESEARCH_MEMORY",
    "research_plan": "RESEARCH_PLAN",
    "research_settings": "RESEARCH_SETTINGS",
    "structured_learning_policy": "LEARNING_POLICY",
    "learning_policy": "LEARNING_POLICY",
    "topology_allocation": "TOPOLOGY_ALLOCATION",
    "compute_allocation": "COMPUTE_ALLOCATION",
    "live_hardware": "LIVE_HARDWARE",
    "hardware": "HARDWARE_PROFILE",
    "live_compute_plan": "LIVE_COMPUTE_PLAN",
    "recent_trials": "RECENT_TRIALS",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_json(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return _sha_bytes(raw)


def _json_size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))


def _safe_excerpt(value: Any, limit: int = MAX_STDIO_CHARS) -> str:
    text = str(value or "")
    return text[:limit]


def _default_scientist_home() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "MaxMTF" / "ScientistPython"
        return Path.home() / "AppData" / "Local" / "MaxMTF" / "ScientistPython"
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "MaxMTF" / "ScientistPython"
    return Path.home() / ".local" / "share" / "MaxMTF" / "ScientistPython"


def scientist_python_home(runtime_home: str | Path | None = None) -> Path:
    # runtime_home is deterministic host/test configuration. It is never sourced from an
    # LLM request. Production callers omit it and therefore always use the governed path.
    return Path(runtime_home).expanduser().resolve() if runtime_home is not None else _default_scientist_home().resolve()


def scientist_python_executable(runtime_home: str | Path | None = None) -> Path:
    home = scientist_python_home(runtime_home)
    return home / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _same_executable(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except Exception:
        pass
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _read_required_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    if not REQUIREMENTS_FILE.exists():
        return out
    for raw in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            continue
        name, ver = line.split("==", 1)
        out[name.strip().lower()] = ver.strip()
    return out


def scientist_python_health(runtime_home: str | Path | None = None, *, canonical_python: str | Path | None = None, verify_packages: bool = True) -> dict:
    exe = scientist_python_executable(runtime_home)
    canonical = Path(canonical_python or sys.executable).resolve()
    base = {
        "schema": HEALTH_SCHEMA,
        "status": "UNAVAILABLE",
        "analysis_mode": "REASONING_ONLY",
        "scientist_python_executable": str(exe),
        "canonical_max_python_executable": str(canonical),
        "separate_interpreter": False,
        "requirements_file": str(REQUIREMENTS_FILE),
        "required_packages": _read_required_versions(),
    }
    if not exe.is_file():
        return {**base, "reason": "SCIENTIST_PYTHON_ENV_MISSING"}
    if _same_executable(exe, canonical):
        return {**base, "status": "ERROR", "reason": "SCIENTIST_PYTHON_MUST_NOT_REUSE_CANONICAL_MAX_PYTHON"}
    probe = """import json,sys,importlib.metadata as m
mods={'numpy':'numpy','pandas':'pandas','scipy':'scipy','scikit-learn':'sklearn'}
packages={}; import_errors={}
for dist,mod in mods.items():
    try: packages[dist]=m.version(dist)
    except m.PackageNotFoundError: packages[dist]=None
    try: __import__(mod); import_errors[dist]=None
    except Exception as exc: import_errors[dist]=f'{type(exc).__name__}: {exc}'[:500]
print(json.dumps({'exe':sys.executable,'version':sys.version.split()[0],'packages':packages,'import_errors':import_errors}))
"""
    try:
        cp = subprocess.run([str(exe), "-I", "-c", probe], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    except Exception as exc:
        return {**base, "status": "ERROR", "reason": "SCIENTIST_PYTHON_HEALTH_PROBE_FAILED", "error": _safe_excerpt(exc, 600)}
    if cp.returncode != 0:
        return {**base, "status": "ERROR", "reason": "SCIENTIST_PYTHON_HEALTH_PROBE_NONZERO", "exit_code": cp.returncode, "stderr": _safe_excerpt(cp.stderr, 1200)}
    try:
        payload = json.loads((cp.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        return {**base, "status": "ERROR", "reason": "SCIENTIST_PYTHON_HEALTH_PROBE_INVALID_JSON", "error": str(exc)[:500]}
    required = _read_required_versions()
    packages = payload.get("packages") if isinstance(payload.get("packages"), dict) else {}
    import_errors = payload.get("import_errors") if isinstance(payload.get("import_errors"), dict) else {}
    mismatch = {}
    for name, expected in required.items():
        actual = str(packages.get(name) or packages.get("scikit-learn" if name == "scikit-learn" else name) or "")
        if actual != expected:
            mismatch[name] = {"expected": expected, "actual": actual or None}
    live_import_errors = {k: v for k, v in import_errors.items() if v}
    if live_import_errors and verify_packages:
        return {
            **base,
            "status": "ERROR",
            "reason": "SCIENTIST_PYTHON_PACKAGE_IMPORT_FAILED",
            "separate_interpreter": True,
            "python_version": payload.get("version"),
            "package_versions": packages,
            "package_import_errors": live_import_errors,
        }
    if mismatch and verify_packages:
        return {
            **base,
            "status": "ERROR",
            "reason": "SCIENTIST_PYTHON_PACKAGE_IDENTITY_MISMATCH",
            "separate_interpreter": True,
            "python_version": payload.get("version"),
            "package_versions": packages,
            "package_mismatch": mismatch,
        }
    return {
        **base,
        "status": "READY",
        "analysis_mode": "PYTHON_ASSISTED_AVAILABLE",
        "reason": None,
        "separate_interpreter": True,
        "python_version": payload.get("version"),
        "package_versions": packages,
    }


class ScientistPythonValidationError(ValueError):
    pass


class _Guard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, node: ast.AST, reason: str) -> None:
        self.errors.append(f"line {getattr(node, 'lineno', '?')}: {reason}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = str(alias.name or "")
            root = name.split(".", 1)[0]
            if root in DENIED_IMPORT_ROOTS or name not in ALLOWED_IMPORTS:
                self.fail(node, f"import not allowed: {name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        name = str(node.module or "")
        root = name.split(".", 1)[0]
        if node.level or root in DENIED_IMPORT_ROOTS or name not in ALLOWED_IMPORTS:
            self.fail(node, f"import not allowed: {name or '<relative>'}")
        allowed_names = SAFE_IMPORT_SURFACE.get(name, frozenset())
        for alias in node.names:
            imported = str(alias.name or "")
            if imported.startswith("_") or "__" in imported:
                self.fail(node, f"private/dunder import not allowed: {imported}")
            elif imported == "*" or imported not in allowed_names:
                self.fail(node, f"imported capability not allowed: {name}.{imported}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        name = str(node.id or "")
        if name in DENIED_NAMES or name.startswith("_") or "__" in name:
            self.fail(node, f"name not allowed: {name}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = str(node.attr or "")
        if attr.startswith("_") or "__" in attr:
            self.fail(node, f"private/dunder attribute not allowed: {attr}")
        elif attr not in SAFE_ATTRIBUTE_NAMES:
            self.fail(node, f"attribute outside Scientist capability surface: {attr}")
        if attr in TRANSITIVE_DANGEROUS_ATTRIBUTES:
            self.fail(node, f"transitive system/native capability not allowed: {attr}")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        value = node.value
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="ignore")
            except Exception:
                value = ""
        if isinstance(value, str):
            value = value.strip()
            if PATH_LITERAL_RE.search(value):
                self.fail(node, "absolute path/URL literal not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in DENIED_NAMES:
            self.fail(node, f"call not allowed: {node.func.id}")
        if isinstance(node.func, ast.Attribute):
            attr = str(node.func.attr or "")
            if attr not in SAFE_ATTRIBUTE_NAMES or attr in TRANSITIVE_DANGEROUS_ATTRIBUTES:
                self.fail(node, f"call outside Scientist capability surface: {attr}")
        for kw in node.keywords:
            if str(kw.arg or "").lower() in {"n_jobs", "nthreads", "num_threads", "thread_count", "nthread", "workers"}:
                if not (isinstance(kw.value, ast.Constant) and kw.value.value in (None, 1)):
                    self.fail(kw, f"parallel worker request not allowed: {kw.arg}")
        self.generic_visit(node)


def validate_scientist_code(code: str) -> dict:
    code = str(code or "")
    if not code.strip():
        return {"ok": False, "errors": ["empty code"]}
    if len(code) > MAX_CODE_CHARS:
        return {"ok": False, "errors": [f"code exceeds {MAX_CODE_CHARS} characters"]}
    try:
        tree = ast.parse(code, filename="<scientist_analysis>", mode="exec")
    except SyntaxError as exc:
        return {"ok": False, "errors": [f"syntax error: {exc}"]}
    guard = _Guard(); guard.visit(tree)
    # V1 result contract is explicit. The generated program may print diagnostics but
    # analytical evidence is taken only from the structured variable named `result`.
    has_result = any(isinstance(n, (ast.Assign, ast.AnnAssign)) and (
        (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets)) or
        (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "result")
    ) for n in ast.walk(tree))
    if not has_result:
        guard.errors.append("code must assign structured analytical output to variable 'result'")
    return {"ok": not guard.errors, "errors": guard.errors}


def authorized_analysis_inputs(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        iid = INPUT_KEY_TO_ID.get(str(key))
        if not iid or value in (None, {}, []):
            continue
        # Same semantic ID may be available under multiple aliases. Prefer the first
        # non-empty source so the LLM cannot create duplicate copies of one evidence class.
        if iid not in out:
            out[iid] = deepcopy(value)
    return out


def authorized_analysis_inputs_from_messages(messages: list[dict]) -> dict[str, Any]:
    # Production Scientist messages contain one host-generated JSON user payload. Parsing
    # that payload does not grant the LLM path authority; only whitelisted top-level keys
    # are exported as opaque in-memory IDs.
    for msg in reversed(messages or []):
        if str((msg or {}).get("role") or "") != "user":
            continue
        content = str((msg or {}).get("content") or "").strip()
        if not content.startswith("{"):
            continue
        try:
            obj = json.loads(content)
        except Exception:
            continue
        if isinstance(obj, dict):
            return authorized_analysis_inputs(obj)
    return {}


def analysis_capability_instruction(authorized_inputs: Mapping[str, Any], health: Mapping[str, Any] | None = None) -> str:
    health = dict(health or {})
    status = str(health.get("status") or "UNAVAILABLE")
    ids = sorted(str(x) for x in authorized_inputs)
    return (
        "OPTIONAL SCIENTIST PYTHON ANALYSIS V1. This capability is analytical support only; deterministic MAX remains the sole PASS/FAIL, admission, promotion, training, and acceptance authority. "
        f"Live Python status={status}. Authorized opaque input IDs={ids}. "
        "Use Python only when numerical/statistical/data-volume complexity makes language-only reasoning unreliable; do not use it for trivial reasoning. "
        "If Python is needed, return ONLY one JSON object of this exact shape instead of your final answer: "
        '{"python_analysis":{"purpose":"short purpose","input_ids":["AUTHORIZED_ID"],"seed":42,"timeout_sec":30,"code":"Python code assigning a JSON-serializable value to result"}}. '
        "Do not include interpreter names or paths. Code receives only `inputs` (dict keyed by requested input IDs) and `seed`. Allowed analytical imports are math, statistics, json, numpy, pandas, scipy/scipy.stats and bounded sklearn analytical modules, but these names resolve to governed capability views rather than raw module objects. Only approved in-memory operations/attributes are exposed. "
        "Never request/read files, network, shell, subprocess, MT5, source/governance/acceptance mutation, package installation, or Champion actions. "
        "After the host executes or rejects that single request, you will receive structured ANALYTICAL_EVIDENCE_ONLY and must return the original requested final response schema. "
        "If execution is UNAVAILABLE, REJECTED, INPUT_UNAVAILABLE, ERROR or TIMEOUT, continue REASONING_ONLY and never fabricate Python-derived numbers or claim Python was used."
    )


def parse_python_analysis_request(text: str) -> dict | None:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    req = obj.get("python_analysis")
    return dict(req) if isinstance(req, dict) else None


def _request_rejection(request: Mapping[str, Any]) -> str | None:
    allowed = {"purpose", "code", "input_ids", "seed", "timeout_sec"}
    extra = sorted(set(str(k) for k in request.keys()) - allowed)
    if extra:
        return "unsupported request fields: " + ", ".join(extra)
    # Defense in depth against a model trying to smuggle host path/interpreter authority.
    blob = json.dumps(request, ensure_ascii=False, default=str)
    if re.search(r'(?i)"(?:path|file|filename|interpreter|executable|cwd|working_directory)"\s*:', blob):
        return "LLM may not choose interpreter or filesystem paths"
    return None


def _clean_child_env(exe: Path) -> dict[str, str]:
    keep = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATH", "HOME", "USERPROFILE", "COMSPEC", "PATHEXT")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep and isinstance(v, str)}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["MAX_SCIENTIST_PYTHON_CHILD"] = "1"
    # Prevent scientific libraries from silently expanding into large native thread pools.
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[key] = "1"
    return env


def _analysis_dir(analysis_id: str, runtime_root: str | Path | None = None) -> Path:
    root = Path(runtime_root).resolve() if runtime_root is not None else RUNTIME_ROOT
    path = root / analysis_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _artifact_hashes(path: Path) -> dict[str, str]:
    out = {}
    for p in sorted(path.iterdir()):
        if p.is_file():
            out[p.name] = _sha_bytes(p.read_bytes())
    return out


def run_scientist_python_analysis(
    request: Mapping[str, Any] | None,
    authorized_inputs: Mapping[str, Any] | None,
    *,
    runtime_home: str | Path | None = None,
    runtime_root: str | Path | None = None,
    canonical_python: str | Path | None = None,
    verify_packages: bool = True,
) -> dict:
    """Execute one guarded Scientist analytical request in the dedicated interpreter.

    This function intentionally has no Factory/PASS/promotion hooks. It returns analytical
    evidence only. Any non-EXECUTED outcome explicitly falls back to REASONING_ONLY.
    """
    analysis_id = "ANL_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:8]
    created = utcnow()
    request = dict(request or {})
    authorized_inputs = dict(authorized_inputs or {})
    analysis_path = _analysis_dir(analysis_id, runtime_root)

    purpose = str(request.get("purpose") or "").strip()[:500]
    code = str(request.get("code") or "")
    code_sha = _sha_bytes(code.encode("utf-8"))
    raw_ids = request.get("input_ids") if isinstance(request.get("input_ids"), list) else []
    input_ids = [str(x) for x in raw_ids[:MAX_INPUT_IDS]]
    try:
        seed = int(request.get("seed", DEFAULT_SEED))
    except Exception:
        seed = DEFAULT_SEED
    seed = max(0, min(2**32 - 1, seed))
    try:
        timeout = int(request.get("timeout_sec", DEFAULT_TIMEOUT_SEC))
    except Exception:
        timeout = DEFAULT_TIMEOUT_SEC
    timeout = max(1, min(MAX_TIMEOUT_SEC, timeout))

    selected_inputs = {iid: deepcopy(authorized_inputs[iid]) for iid in input_ids if iid in authorized_inputs}
    missing_ids = [iid for iid in input_ids if iid not in authorized_inputs]
    input_hashes = {iid: _sha_json(value) for iid, value in selected_inputs.items()}
    health = scientist_python_health(runtime_home, canonical_python=canonical_python, verify_packages=verify_packages)

    request_record = {
        "schema": SCHEMA,
        "analysis_id": analysis_id,
        "timestamp": created,
        "purpose": purpose,
        "requested_input_ids": input_ids,
        "seed": seed,
        "timeout_sec": timeout,
        "code_sha256": code_sha,
        "evidence_class": EVIDENCE_CLASS,
    }
    _write_json(analysis_path / "request.json", request_record)
    (analysis_path / "generated_code.py").write_text(code, encoding="utf-8")

    def finalize(status: str, *, structured_result: Any = None, reason: str | None = None, exit_code: int | None = None, stdout: str = "", stderr: str = "", validation: Any = None) -> dict:
        mode = "PYTHON_ASSISTED" if status == "EXECUTED" else "REASONING_ONLY"
        payload = {
            "schema": SCHEMA,
            "analysis_id": analysis_id,
            "timestamp": created,
            "purpose": purpose,
            "analysis_mode": mode,
            "evidence_class": EVIDENCE_CLASS,
            "execution_status": status,
            "status": status,
            "fallback_reason": reason,
            "generated_code": code,
            "code_sha256": code_sha,
            "input_identities": input_ids,
            "input_hashes": input_hashes,
            "scientist_interpreter_identity": str(health.get("scientist_python_executable") or scientist_python_executable(runtime_home)),
            "canonical_max_python_executable": str(health.get("canonical_max_python_executable") or canonical_python or sys.executable),
            "python_version": health.get("python_version"),
            "package_versions": deepcopy(health.get("package_versions") or {}),
            "host_executor_sha256": _sha_bytes(Path(__file__).read_bytes()),
            "child_runner_sha256": _sha_bytes(CHILD_RUNNER.read_bytes()) if CHILD_RUNNER.is_file() else None,
            "requirements_sha256": _sha_bytes(REQUIREMENTS_FILE.read_bytes()) if REQUIREMENTS_FILE.is_file() else None,
            "seed": seed,
            "timeout_sec": timeout,
            "exit_code": exit_code,
            "stdout_excerpt": _safe_excerpt(stdout),
            "stderr_excerpt": _safe_excerpt(stderr),
            "structured_result": structured_result if status == "EXECUTED" else None,
            "result_hash": _sha_json(structured_result) if status == "EXECUTED" else None,
            "validation": validation,
            "authority": "ANALYTICAL_SUPPORT_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY",
        }
        _write_json(analysis_path / "result.json", payload)
        payload["artifact_hashes"] = _artifact_hashes(analysis_path)
        _write_json(analysis_path / "provenance.json", payload)
        payload["artifact_hashes"] = _artifact_hashes(analysis_path)
        return payload

    reject = _request_rejection(request)
    if reject:
        return finalize("REJECTED", reason=reject)
    if not purpose:
        return finalize("REJECTED", reason="purpose is required")
    if not input_ids:
        return finalize("INPUT_UNAVAILABLE", reason="no authorized input IDs requested")
    if missing_ids:
        return finalize("INPUT_UNAVAILABLE", reason="authorized input unavailable: " + ", ".join(missing_ids))
    if _json_size(selected_inputs) > MAX_INPUT_BYTES:
        return finalize("REJECTED", reason=f"selected analytical inputs exceed {MAX_INPUT_BYTES} bytes")
    validation = validate_scientist_code(code)
    if not validation.get("ok"):
        return finalize("REJECTED", reason="guarded code validation failed", validation=validation)
    if str(health.get("status") or "") != "READY":
        return finalize("UNAVAILABLE", reason=str(health.get("reason") or "SCIENTIST_PYTHON_NOT_READY"), validation=validation)

    child_request = {"code": code, "inputs": selected_inputs, "seed": seed, "max_result_bytes": MAX_RESULT_BYTES}
    stdin_blob = json.dumps(child_request, ensure_ascii=False, separators=(",", ":"), default=str)
    exe = Path(str(health["scientist_python_executable"]))
    try:
        proc = subprocess.Popen(
            [str(exe), "-I", str(CHILD_RUNNER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=str(analysis_path), env=_clean_child_env(exe),
        )
        try:
            stdout, stderr = proc.communicate(stdin_blob, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return finalize("TIMEOUT", reason=f"analysis exceeded {timeout}s and child was killed", exit_code=proc.returncode, stdout=stdout, stderr=stderr, validation=validation)
    except Exception as exc:
        return finalize("ERROR", reason=f"child launch failed: {type(exc).__name__}: {exc}", validation=validation)

    if proc.returncode != 0:
        return finalize("ERROR", reason="analysis child returned nonzero", exit_code=proc.returncode, stdout=stdout, stderr=stderr, validation=validation)
    try:
        child = json.loads((stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        return finalize("ERROR", reason=f"invalid child result: {type(exc).__name__}: {exc}", exit_code=proc.returncode, stdout=stdout, stderr=stderr, validation=validation)
    if not isinstance(child, dict) or child.get("status") != "EXECUTED":
        return finalize("ERROR", reason=str((child or {}).get("error") if isinstance(child, dict) else "child result invalid"), exit_code=proc.returncode, stdout=(child or {}).get("captured_stdout", stdout) if isinstance(child, dict) else stdout, stderr=(child or {}).get("captured_stderr", stderr) if isinstance(child, dict) else stderr, validation=validation)
    result = child.get("result")
    if _json_size(result) > MAX_RESULT_BYTES:
        return finalize("ERROR", reason=f"structured result exceeds {MAX_RESULT_BYTES} bytes", exit_code=proc.returncode, stdout=child.get("captured_stdout", ""), stderr=child.get("captured_stderr", ""), validation=validation)
    return finalize("EXECUTED", structured_result=result, exit_code=proc.returncode, stdout=child.get("captured_stdout", ""), stderr=child.get("captured_stderr", ""), validation=validation)


def python_analysis_evidence_for_llm(result: Mapping[str, Any] | None) -> dict:
    r = dict(result or {})
    # Never feed source paths/artifact directories back as analytical authority. The LLM
    # receives only execution state, provenance identities/hashes and bounded result.
    return {
        "schema": SCHEMA,
        "analysis_id": r.get("analysis_id"),
        "analysis_mode": r.get("analysis_mode") or "REASONING_ONLY",
        "execution_status": r.get("execution_status") or "UNAVAILABLE",
        "evidence_class": EVIDENCE_CLASS,
        "purpose": r.get("purpose"),
        "input_identities": deepcopy(r.get("input_identities") or []),
        "input_hashes": deepcopy(r.get("input_hashes") or {}),
        "code_sha256": r.get("code_sha256"),
        "seed": r.get("seed"),
        "timeout_sec": r.get("timeout_sec"),
        "structured_result": deepcopy(r.get("structured_result")) if r.get("execution_status") == "EXECUTED" else None,
        "fallback_reason": r.get("fallback_reason"),
        "authority": r.get("authority") or "ANALYTICAL_SUPPORT_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY",
    }
