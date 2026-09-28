from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = MODELLAB_ROOT
EVIDENCE = ROOT / "evidence" / "current" / "LANGGRAPH_RUNTIME_ACCEPTANCE_v1_3_3.json"
REQ = ROOT / "requirements" / "requirements-langgraph.txt"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(results: list[dict], first_failed_gate: str | None, status: str, extra: dict | None = None) -> None:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "MAX_LANGGRAPH_RUNTIME_ACCEPTANCE_V130_R1",
        "version": "1.3.2",
        "overall_status": status,
        "first_failed_gate": first_failed_gate,
        "generated_utc": _utc(),
        "results": results,
        "gate_count": 7,
        "strict_msgpack": str(os.environ.get("LANGGRAPH_STRICT_MSGPACK", "")).lower() == "true",
    }
    if extra:
        payload.update(extra)
    EVIDENCE.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _gate(results: list[dict], name: str, fn) -> bool:
    t0 = time.monotonic()
    try:
        detail = fn()
        row = {"gate": name, "status": "PASS", "elapsed_seconds": round(time.monotonic() - t0, 3)}
        if detail is not None:
            row["detail"] = detail
        results.append(row)
        print("PASS", name)
        _write(results, None, "RUNNING")
        return True
    except Exception as exc:
        row = {
            "gate": name,
            "status": "FAIL",
            "elapsed_seconds": round(time.monotonic() - t0, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }
        results.append(row)
        print("FAIL", name, row["error"])
        _write(results, name, "FAIL")
        return False


def _ensure_dependencies(install: bool) -> dict:
    # Import is deliberately local: this runner must still be able to emit evidence
    # when LangGraph is absent and installation itself fails.
    from max_graph.runtime import LANGGRAPH_VERSION, SQLITE_CHECKPOINT_VERSION, runtime_versions

    before = runtime_versions()
    exact = before.get("langgraph") == LANGGRAPH_VERSION and before.get("checkpoint_sqlite") == SQLITE_CHECKPOINT_VERSION
    if exact:
        return {"action": "ALREADY_EXACT", "versions": before}
    if not install:
        raise RuntimeError(f"LANGGRAPH_DEPENDENCIES_NOT_EXACT: actual={before} expected={{'langgraph':'{LANGGRAPH_VERSION}','checkpoint_sqlite':'{SQLITE_CHECKPOINT_VERSION}'}}")
    cp = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQ)],
        cwd=str(ROOT), env=acceptance_utf8_env(), text=True, capture_output=True,
        **utf8_text_subprocess_kwargs(),
    )
    if cp.returncode != 0:
        tail = (cp.stderr or cp.stdout or "")[-4000:]
        raise RuntimeError(f"PIP_INSTALL_FAILED exit={cp.returncode}: {tail}")
    after = runtime_versions()
    if after.get("langgraph") != LANGGRAPH_VERSION or after.get("checkpoint_sqlite") != SQLITE_CHECKPOINT_VERSION:
        raise RuntimeError(f"DEPENDENCY_VERSION_MISMATCH_AFTER_INSTALL: {after}")
    return {"action": "INSTALLED", "versions": after}


def _version_gate() -> dict:
    from max_graph.runtime import require_langgraph
    versions = require_langgraph()
    if versions.get("langgraph") != "1.2.11":
        raise AssertionError("Pinned LangGraph runtime mismatch")
    if versions.get("checkpoint_sqlite") != "3.1.1":
        raise AssertionError("Pinned SQLite checkpoint runtime mismatch")
    return versions


def _factory_compile_gate(tmp: Path) -> dict:
    from max_graph.factory_graph import _Runtime, _build_graph
    from max_graph.runtime import sqlite_checkpointer

    rt = _Runtime(
        root=tmp / "factory", dataset=None, config_path=str(ROOT / "config" / "config.json"),
        discovery_from="2020-01-01", discovery_to="2020-12-31",
        tournament_from="2021-01-01", tournament_to="2021-03-31",
        fresh_from="2021-04-01", fresh_to="2021-06-30",
        progress=None, llm_api_key=None, resume=False, max_cycles=1,
    )
    db = tmp / "factory" / "compile.sqlite"
    with sqlite_checkpointer(db) as saver:
        graph = _build_graph(rt).compile(checkpointer=saver)
        if graph is None:
            raise AssertionError("Factory StateGraph compile returned None")
    return {"checkpoint_db_created": db.exists()}


def _director_gate(tmp: Path) -> dict:
    from max_graph.scientist_director_graph import run_agentic_scientist_round
    from models.models import random_candidate

    cfg = deepcopy(json.loads((ROOT / "config" / "config.json").read_text(encoding="utf-8")))
    cfg.setdefault("agent", {})["research_plan"] = {
        "active_families": ["xgboost"],
        "parameter_envelopes": {},
        "topology_priority": {"mode": "SCIENTIST_DIRECTED", "single": 1.0, "hybrid": 0.0, "allowed_topologies": ["SINGLE"]},
    }

    class FakeScientist:
        def __init__(self):
            self.calls = 0
            self.last_call_provenance = {}

        def _call_with_phase(self, messages, *, temperature, phase):
            self.calls += 1
            self.last_call_provenance = {"phase": phase, "fake": True}
            return json.dumps({
                "observation": "trade scarcity after regularization",
                "diagnosis": "selectivity bottleneck",
                "focus_candidate": "xgb_parent",
                "evidence_requests": [
                    {"tool": "FOLD_FORENSICS", "candidate": "xgb_parent", "reason": "inspect trade scarcity"},
                    {"tool": "FAILURE_TOPOLOGY", "reason": "confirm dominant gate"},
                ],
            })

        def propose(self, context, cfg, max_n=5):
            import random
            self.calls += 1
            spec = random_candidate(cfg, "xgboost", random.Random(7), "agentic_xgb_01")
            return {
                "summary": "refine coverage while preserving risk",
                "report": {"condition": "CV_MIN_TRADES", "interpretation": "selectivity bottleneck", "next_action": "bounded coverage refinement", "confidence": 0.8},
                "stop_research": False,
                "stop_research_advisory": False,
                "strategy": {"exploration_ratio": 0.35},
                "proposals": [spec],
                "hypotheses": [{"kind": "TRAINING_MEMORY", "title": "coverage memory", "rationale": "increase coverage", "expected_observation": "trades rise without DD blowout", "payload": {"months": [24, 36]}, "execution_stage": "CURRENT_OR_NEXT_MODEL_SEARCH", "executable": True}],
                "deterministic_state": "NO_WFA_SURVIVOR",
                "llm_provenance": {"fake": True},
            }

    ctx = {
        "round": 2, "budget_remaining": 10,
        "top_results": [{"name": "xgb_parent", "family": "xgboost", "cv_gate_pass": False, "cv_first_failed_gate": "CV_MIN_TRADES", "overall_expectancy_r": 0.48, "median_max_drawdown_r": 1.0, "total_validation_trades": 27}],
        "fold_forensics": [{"name": "xgb_parent", "family": "xgboost", "first_failed_gate": "CV_MIN_TRADES", "trades": 27}],
        "failure_topology": {"dominant_first_failed_gate": "CV_MIN_TRADES"},
        "family_stats": {}, "fidelity_ladder": {"enabled": True}, "scientific_agenda": [], "hypothesis_lifecycle": [],
    }
    sci = FakeScientist()
    out = tmp / "director"
    r1 = run_agentic_scientist_round(scientist=sci, context=ctx, cfg=cfg, out_dir=out, thread_id="T-DIRECTOR", request_id="ROUND_002", max_n=3)
    if not r1.get("proposals"):
        raise AssertionError("Director graph emitted no validated proposal")
    if (r1.get("agentic_metadata") or {}).get("proposal_lineage_count") != 1:
        raise AssertionError("Proposal lineage was not persisted")
    calls_after = sci.calls
    # Re-open graph/checkpointer on a second invocation. Same request must be served
    # from persisted graph state and must not call Scientist again.
    r2 = run_agentic_scientist_round(scientist=sci, context=ctx, cfg=cfg, out_dir=out, thread_id="T-DIRECTOR", request_id="ROUND_002", max_n=3)
    if sci.calls != calls_after:
        raise AssertionError("Duplicate request_id re-called Scientist instead of checkpoint cache")
    if r2.get("langgraph_thread_id") != "T-DIRECTOR":
        raise AssertionError("Director thread identity changed across resume")
    db = out / "langgraph" / "scientist_director.sqlite"
    if not db.exists() or db.stat().st_size <= 0:
        raise AssertionError("Director SQLite checkpoint DB was not created")
    return {"calls": sci.calls, "checkpoint_db": str(db), "checkpoint_bytes": db.stat().st_size}


def _chat_gate(tmp: Path) -> dict:
    from max_graph.scientist_chat_graph import run_scientist_chat_graph

    calls = {"n": 0}
    secret = "MAX_RUNTIME_SECRET_MUST_NOT_BE_CHECKPOINTED_130"

    def fake_discuss(llm_cfg, **kwargs):
        calls["n"] += 1
        if kwargs.get("api_key") != secret:
            raise AssertionError("Runtime API key did not reach discuss function")
        return {"content": "read-only answer", "answered_by": "fake", "context_sources": []}

    kwargs = dict(
        app_dir=tmp, request_id="REQ-1", thread_id="CHAT-1", discuss_fn=fake_discuss,
        llm_cfg={"provider": "fake"}, selected_model="fake", api_key=secret, history=[],
        user_prompt="why?", context={"authority": "READ_ONLY"}, allow_fallback=False,
    )
    a1 = run_scientist_chat_graph(**kwargs)
    a2 = run_scientist_chat_graph(**kwargs)
    if a1.get("content") != "read-only answer" or a2.get("content") != "read-only answer":
        raise AssertionError("Scientist Chat graph did not preserve answer")
    if calls["n"] != 1:
        raise AssertionError("Scientist Chat duplicate request was not checkpoint-idempotent")
    db = tmp / "runtime" / "langgraph" / "scientist_chat.sqlite"
    if not db.exists() or db.stat().st_size <= 0:
        raise AssertionError("Scientist Chat SQLite checkpoint DB was not created")
    if secret.encode("utf-8") in db.read_bytes():
        raise AssertionError("Runtime API key leaked into LangGraph checkpoint SQLite")
    return {"calls": calls["n"], "checkpoint_db": str(db), "checkpoint_bytes": db.stat().st_size, "secret_persisted": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="Install pinned LangGraph dependencies if exact versions are not already present.")
    args = ap.parse_args()

    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    results: list[dict] = []
    _write(results, None, "RUNNING")

    if not _gate(results, "LANGGRAPH_DEPENDENCY_INSTALL", lambda: _ensure_dependencies(args.install)):
        return 1
    if not _gate(results, "LANGGRAPH_EXACT_VERSION", _version_gate):
        return 1
    if not _gate(results, "STRICT_MSGPACK_ENABLED", lambda: {"LANGGRAPH_STRICT_MSGPACK": os.environ.get("LANGGRAPH_STRICT_MSGPACK") if str(os.environ.get("LANGGRAPH_STRICT_MSGPACK", "")).lower() == "true" else (_ for _ in ()).throw(AssertionError("LANGGRAPH_STRICT_MSGPACK is not true"))}):
        return 1

    with tempfile.TemporaryDirectory(prefix="max_v130_lg_") as td:
        root = Path(td)
        if not _gate(results, "FACTORY_STATEGRAPH_COMPILE", lambda: _factory_compile_gate(root)):
            return 1
        if not _gate(results, "SCIENTIST_DIRECTOR_SQLITE_RESUME_IDEMPOTENCY", lambda: _director_gate(root)):
            return 1
        if not _gate(results, "SCIENTIST_CHAT_SQLITE_RESUME_IDEMPOTENCY", lambda: _chat_gate(root)):
            return 1
        if not _gate(results, "SCIENTIST_CHAT_SECRET_NON_PERSISTENCE", lambda: {"verified_by": "Scientist Chat SQLite byte scan in prior gate", "status": "PASS"}):
            return 1

    from max_graph.runtime import runtime_versions
    _write(results, None, "PASS", {"runtime_versions": runtime_versions()})
    print("LANGGRAPH_RUNTIME_ACCEPTANCE PASS")
    print("EVIDENCE", EVIDENCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
