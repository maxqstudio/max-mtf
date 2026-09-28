from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.project_paths import MODELLAB_ROOT, PACKAGE_ROOT
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs

ROOT = MODELLAB_ROOT
PKG = PACKAGE_ROOT
MANIFEST_PATH = ROOT / "governance" / "MODELLAB_LAYOUT_MANIFEST.json"
EVIDENCE_PATH = ROOT / "evidence" / "current" / "V201_MODELLAB_CANONICAL_LAYOUT_MIGRATION.json"
SCHEMA = "MAX_MTF_V201_MODELLAB_CANONICAL_LAYOUT_MIGRATION_V1"
ENV_CANONICAL_PYTHON = "MAX_MTF_CANONICAL_PYTHON"

# Runtime-only entrypoint whose dependency has a dedicated external acceptance gate.
# Its source/package references are still compiled/path-audited here. Every other
# production Python module must import in one fresh process from an unrelated CWD.
EXTERNAL_RUNTIME_IMPORTS = {
    "ui.app": {
        "dependency": "streamlit",
        "requirements": "requirements/requirements-ui.txt",
        "required_pin": "streamlit==1.63.0",
        "external_gate": "STREAMLIT_1_63_RUNTIME_RENDER_ACCEPTANCE",
    },
    "acceptance.runners.ui_runtime_browser_acceptance": {
        "dependency": "playwright",
        "requirements": "requirements/requirements-ui-acceptance.txt",
        "required_pin": "playwright==1.57.0",
        "external_gate": "STREAMLIT_1_63_RUNTIME_RENDER_ACCEPTANCE",
        "bootstrap_module": "acceptance.runners.ui_runtime_acceptance_bootstrap",
    },
}

ROOT_LAUNCHER_MODULES = {
    "START_UI.cmd": "ui.ui_bootstrap",
    "RUN_ACCEPTANCE.cmd": "acceptance.runners.run_acceptance",
    "RUN_CUDA_ACCEPTANCE.cmd": "acceptance.runners.cuda_runtime_acceptance",
    "RUN_LANGGRAPH_ACCEPTANCE.cmd": "acceptance.runners.langgraph_runtime_acceptance",
    "RUN_MTF1_ACCEPTANCE.cmd": "acceptance.runners.run_acceptance",
    "RUN_MTF1_OWNER_ACCEPTANCE.cmd": "acceptance.runners.owner_mtf1_runtime_acceptance",
    "RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd": "acceptance.runners.owner_mtf1_metaeditor_acceptance",
    "RUN_MTF1_FINAL_CLOSURE.cmd": "mtf.mtf1_closure_bootstrap",
    "RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd": "acceptance.runners.owner_scientist_python_runtime_acceptance",
}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON object required: {path}")
    return value


def _req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _manifest() -> dict[str, Any]:
    m = _read_json(MANIFEST_PATH)
    _req(m.get("schema") == "MAX_MTF_MODELLAB_LAYOUT_MANIFEST_V1", "layout manifest schema")
    return m


def _production_modules() -> list[str]:
    excluded_top = {"tests", "runtime", "evidence", "docs", "governance", "skills"}
    modules: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if not rel.parts or rel.parts[0] in excluded_top or "__pycache__" in rel.parts:
            continue
        if path.name == "__init__.py":
            if len(rel.parts) == 1:
                continue
            module = ".".join(rel.parent.parts)
        else:
            module = ".".join(rel.with_suffix("").parts)
        modules.append(module)
    return modules


def _module_path(root: Path, module: str) -> Path:
    return root / Path(*module.split(".")).with_suffix(".py")


def _external_gate_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = registry.get("gates") or []
    _req(isinstance(gates, list), "external runtime gate registry gates must be a list")
    rows: dict[str, dict[str, Any]] = {}
    for row in gates:
        _req(isinstance(row, dict) and bool(row.get("gate")), "external runtime gate row malformed")
        gate = str(row["gate"])
        _req(gate not in rows, f"duplicate external runtime gate: {gate}")
        rows[gate] = row
    return rows


def _validate_external_runtime_contracts(
    *,
    root: Path = ROOT,
    pkg: Path = PKG,
    contracts: dict[str, dict[str, Any]] | None = None,
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    governed = contracts if contracts is not None else EXTERNAL_RUNTIME_IMPORTS
    external_registry = registry if registry is not None else _read_json(pkg / "governance" / "EXTERNAL_RUNTIME_GATES.json")
    gate_map = _external_gate_map(external_registry)
    rows: list[dict[str, Any]] = []
    for module, contract in governed.items():
        path = _module_path(root, module)
        _req(path.is_file(), f"external runtime module missing: {module}")
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        req_path = root / str(contract["requirements"])
        _req(req_path.is_file(), f"requirements missing for {module}")
        pins = {line.strip() for line in req_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")}
        _req(str(contract["required_pin"]) in pins, f"dependency pin missing for {module}: {contract['required_pin']}")

        gate_name = str(contract["external_gate"])
        gate = gate_map.get(gate_name)
        _req(gate is not None, f"external runtime gate missing for {module}: {gate_name}")

        bootstrap_module = str(contract.get("bootstrap_module") or "").strip()
        if bootstrap_module:
            bootstrap_path = _module_path(root, bootstrap_module)
            _req(bootstrap_path.is_file(), f"external runtime bootstrap missing for {module}: {bootstrap_module}")
            bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
            ast.parse(bootstrap_text, filename=str(bootstrap_path))
            _req(module in bootstrap_text, f"external bootstrap does not launch governed module: {bootstrap_module} -> {module}")
            _req(str(contract["requirements"]) in bootstrap_text or Path(str(contract["requirements"])).name in bootstrap_text,
                 f"external bootstrap does not bind governed requirements: {bootstrap_module}")
            # The registry is the canonical runtime obligation, so its metadata must
            # identify the same bootstrap/runner/dependency contract when supplied.
            if gate.get("bootstrap_module") is not None:
                _req(gate.get("bootstrap_module") == bootstrap_module, f"external gate bootstrap mismatch: {gate_name}")
            if gate.get("browser_module") is not None:
                _req(gate.get("browser_module") == module, f"external gate browser module mismatch: {gate_name}")
            if gate.get("requirements") is not None:
                _req(gate.get("requirements") == f"ModelLab/{contract['requirements']}", f"external gate requirements mismatch: {gate_name}")
            if gate.get("required_pin") is not None:
                _req(gate.get("required_pin") == contract["required_pin"], f"external gate pin mismatch: {gate_name}")

        rows.append({"module": module, "status": "EXTERNAL_RUNTIME_GATED", **contract})
    return rows


def _fresh_import_rows(
    modules: list[str],
    *,
    root: Path = ROOT,
    python_executable: str | None = None,
    blocked_dependencies: set[str] | None = None,
    timeout: int = 90,
) -> list[dict[str, Any]]:
    py = str(python_executable or sys.executable)
    blocked = sorted(set(blocked_dependencies or set()))
    code = (
        "import importlib,json,sys,importlib.abc\n"
        f"sys.path.insert(0,{str(root)!r})\n"
        f"mods={modules!r}\n"
        f"blocked={blocked!r}\n"
        "class _Block(importlib.abc.MetaPathFinder):\n"
        "  def find_spec(self, fullname, path=None, target=None):\n"
        "    if fullname.split('.')[0] in blocked:\n"
        "      raise ModuleNotFoundError('blocked dependency for acceptance test: '+fullname)\n"
        "    return None\n"
        "if blocked: sys.meta_path.insert(0,_Block())\n"
        "rows=[]\n"
        "for m in mods:\n"
        "  try:\n"
        "    obj=importlib.import_module(m); rows.append({'module':m,'status':'PASS','file':getattr(obj,'__file__',None)})\n"
        "  except Exception as e:\n"
        "    rows.append({'module':m,'status':'FAIL','error':type(e).__name__+': '+str(e)})\n"
        "    print(json.dumps(rows)); raise\n"
        "print(json.dumps(rows))\n"
    )
    cp = subprocess.run(
        [py, "-I", "-c", code],
        cwd=str(Path(os.environ.get("TEMP") or "/tmp")),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=acceptance_utf8_env(os.environ),
        timeout=timeout,
        check=False,
        **utf8_text_subprocess_kwargs(),
    )
    _req(cp.returncode == 0, f"fresh-process production import sweep failed: {(cp.stderr or cp.stdout)[-4000:]}")
    rows = json.loads((cp.stdout or "[]").splitlines()[-1])
    _req(len(rows) == len(modules), "import sweep result count")
    return rows


def _import_sweep(*, blocked_dependencies: set[str] | None = None) -> dict[str, Any]:
    modules = _production_modules()
    external = set(EXTERNAL_RUNTIME_IMPORTS)
    unknown = external.difference(modules)
    _req(not unknown, f"external runtime classification references non-production modules: {sorted(unknown)}")
    importable = [m for m in modules if m not in external]

    canonical_expected = str(os.environ.get(ENV_CANONICAL_PYTHON) or "").strip()
    if canonical_expected:
        actual = str(Path(sys.executable).resolve())
        expected = str(Path(canonical_expected).resolve())
        if os.name == "nt":
            actual, expected = os.path.normcase(actual), os.path.normcase(expected)
        _req(actual == expected, f"fresh import sweep interpreter is not canonical MAX Python: actual={actual} expected={expected}")

    rows = _fresh_import_rows(importable, blocked_dependencies=blocked_dependencies)
    ext_rows = _validate_external_runtime_contracts()
    return {
        "fresh_process_imported": rows,
        "external_runtime_gated": ext_rows,
        "production_module_count": len(modules),
        "import_sweep_python_executable": str(Path(sys.executable).resolve()),
        "canonical_max_python_required": bool(canonical_expected),
        "canonical_max_python_executable": canonical_expected or None,
        "blocked_dependencies_for_test": sorted(blocked_dependencies or set()),
    }

def _root_contract(m: dict[str, Any]) -> dict[str, Any]:
    rc = m["root_contract"]
    allowed_files = set(rc["allowed_root_files"])
    allowed_dirs = set(rc["allowed_root_directories"])
    actual_files = {p.name for p in ROOT.iterdir() if p.is_file()}
    actual_dirs = {p.name for p in ROOT.iterdir() if p.is_dir()}
    _req(actual_files == allowed_files, f"ModelLab root files mismatch missing={sorted(allowed_files-actual_files)} extra={sorted(actual_files-allowed_files)}")
    _req(actual_dirs == allowed_dirs, f"ModelLab root directories mismatch missing={sorted(allowed_dirs-actual_dirs)} extra={sorted(actual_dirs-allowed_dirs)}")
    for ext in (".py", ".json", ".txt", ".ps1"):
        _req(not any(p.is_file() and p.suffix.lower() == ext for p in ROOT.iterdir()), f"forbidden root extension {ext}")
    return {"files": sorted(actual_files), "directories": sorted(actual_dirs)}


def _relocation_contract(m: dict[str, Any]) -> dict[str, Any]:
    rows = m.get("relocations") or []
    _req(len(rows) == int(m.get("pre_migration_direct_entry_count", -1)) == 151, "relocation ledger must account for all 151 pre-migration root entries")
    old_paths = [str(r.get("old_path")) for r in rows]
    _req(len(old_paths) == len(set(old_paths)), "duplicate old_path in relocation manifest")
    statuses = {"RETAINED_ROOT_ENTRY", "MOVED", "ARCHIVED"}
    _req(all(r.get("status") in statuses for r in rows), "invalid relocation status")
    for row in rows:
        for key in ("old_path", "new_path", "domain", "item_type", "authority_role", "reason", "status"):
            _req(bool(row.get(key)), f"relocation field missing: {row.get('old_path')}:{key}")
        new = ROOT / str(row["new_path"])
        _req(new.exists(), f"relocation destination missing: {row['old_path']} -> {row['new_path']}")
        if row["item_type"] == "file":
            pre = str(row.get("pre_migration_sha256") or "")
            post = str(row.get("post_migration_sha256") or "")
            _req(len(pre) == 64 and all(c in "0123456789abcdef" for c in pre.lower()), f"invalid pre-migration hash: {row['old_path']}")
            _req(len(post) == 64 and all(c in "0123456789abcdef" for c in post.lower()), f"invalid post-migration hash: {row['old_path']}")
            if not bool(row.get("mutable_after_migration", False)) and not bool(row.get("generated_after_migration", False)):
                _req(_sha(new) == post, f"relocation post-migration hash stale: {row['old_path']} -> {row['new_path']}")
        if row["status"] in {"MOVED", "ARCHIVED"}:
            _req(not (ROOT / str(row["old_path"])).exists(), f"old root authority still exists: {row['old_path']}")
    _req(sum(1 for r in rows if r["item_type"] == "file") == 140, "pre-migration direct file count")
    _req(sum(1 for r in rows if r["item_type"] == "directory") == 11, "pre-migration direct directory count")
    return {"entry_count": len(rows), "moved": sum(r["status"] == "MOVED" for r in rows), "archived": sum(r["status"] == "ARCHIVED" for r in rows)}


def _duplicate_source_contract() -> dict[str, Any]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if "__pycache__" in rel.parts or rel.parts[0] in {"tests", "evidence", "runtime"} or path.name == "__init__.py":
            continue
        by_name[path.name].append(rel.as_posix())
    duplicates = {k: v for k, v in by_name.items() if len(v) > 1}
    _req(not duplicates, f"ambiguous duplicate production module identity: {duplicates}")
    return {"unique_production_python_basenames": len(by_name), "duplicates": duplicates}


def _active_old_path_scan(m: dict[str, Any]) -> dict[str, Any]:
    moved = {str(r["old_path"]): str(r["new_path"]) for r in m["relocations"] if r["status"] == "MOVED" and r["item_type"] == "file"}
    candidates = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT)
        if rel.parts[0] in {"evidence", "runtime", "docs"} or path == MANIFEST_PATH:
            continue
        if path.suffix.lower() not in {".py", ".cmd", ".ps1", ".json", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for old, new in moved.items():
            signatures = (f'ModelLab/{old}', f'ModelLab\\{old}', f'ROOT / "{old}"', f"ROOT / '{old}'")
            if any(sig in text for sig in signatures):
                candidates.append({"file": rel.as_posix(), "old_path": old, "new_path": new})
    _req(not candidates, f"active source still references old ModelLab root authority: {candidates[:12]}")
    return {"stale_active_path_references": candidates}


def _launcher_contract(m: dict[str, Any]) -> dict[str, Any]:
    allowed = set(m["root_contract"]["allowed_root_files"])
    _req(set(ROOT_LAUNCHER_MODULES) == allowed, "launcher map must equal canonical root file allowlist")
    rows = []
    for name, module in ROOT_LAUNCHER_MODULES.items():
        path = ROOT / name
        text = path.read_text(encoding="utf-8", errors="replace")
        _req('cd /d "%~dp0"' in text, f"{name} must resolve from its own directory")
        _req(module in text, f"{name} does not reference canonical target module {module}")
        _req("ModelLab\\" not in text and "/mnt/data/" not in text, f"{name} embeds nonportable build path")
        rows.append({"launcher": name, "module": module, "sha256": _sha(path)})

    # START_UI smoke is non-installing and non-rendering.
    cp = subprocess.run(
        [sys.executable, "-m", "ui.ui_bootstrap", "--layout-smoke"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=acceptance_utf8_env(os.environ),
        timeout=20,
        check=False,
        **utf8_text_subprocess_kwargs(),
    )
    _req(cp.returncode == 0 and '"status": "PASS"' in (cp.stdout or ""), f"START_UI target smoke failed: {(cp.stderr or cp.stdout)[-2000:]}")

    nested = {
        "acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd": "mtf.mtf1_final_closure",
        "acceptance/verification/VERIFY_MTF1_METAEDITOR_ACCEPTANCE.cmd": "acceptance.runners.owner_mtf1_metaeditor_acceptance",
        "acceptance/verification/VERIFY_MTF1_OWNER_ACCEPTANCE.cmd": "acceptance.runners.owner_mtf1_runtime_acceptance",
        "acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd": "acceptance.runners.owner_scientist_python_runtime_acceptance",
        "tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd": "scientist.python.scientist_python_setup",
        "tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd": "scientist.python.scientist_python_setup",
    }
    for rel, module in nested.items():
        p = ROOT / rel
        _req(p.is_file(), f"nested launcher missing: {rel}")
        text = p.read_text(encoding="utf-8", errors="replace")
        _req(module in text and " -m " in text, f"nested launcher not package-based: {rel}")
    return {"root_launchers": rows, "start_ui_smoke": "PASS", "nested_launchers": sorted(nested)}


def verify_layout(*, write_evidence: bool = True) -> dict[str, Any]:
    m = _manifest()
    payload = {
        "schema": SCHEMA,
        "project": "Max MTF",
        "version": "2.0.1",
        "build_scope": "MAX_MTF_V2_0_1_MODELLAB_CANONICAL_LAYOUT_MIGRATION",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": _sha(MANIFEST_PATH),
        "root_contract": _root_contract(m),
        "relocation_contract": _relocation_contract(m),
        "duplicate_source_contract": _duplicate_source_contract(),
        "path_authority_audit": _active_old_path_scan(m),
        "launcher_contract": _launcher_contract(m),
        "import_sweep": _import_sweep(),
        "overall_status": "PASS",
        "first_failed_check": None,
    }
    if write_evidence:
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    try:
        payload = verify_layout(write_evidence=True)
    except Exception as exc:
        payload = {
            "schema": SCHEMA,
            "project": "Max MTF",
            "version": "2.0.1",
            "build_scope": "MAX_MTF_V2_0_1_MODELLAB_CANONICAL_LAYOUT_MIGRATION",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "overall_status": "FAIL",
            "first_failed_check": type(exc).__name__,
            "error": str(exc),
        }
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"V201_MODELLAB_CANONICAL_LAYOUT FAIL: {type(exc).__name__}: {exc}")
        return 1
    print(f"V201_MODELLAB_CANONICAL_LAYOUT PASS root_files={len(payload['root_contract']['files'])} relocations={payload['relocation_contract']['entry_count']} modules={payload['import_sweep']['production_module_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
