from __future__ import annotations

import contextlib
import importlib.metadata
import os
from pathlib import Path

LANGGRAPH_VERSION = "1.2.11"
SQLITE_CHECKPOINT_VERSION = "3.1.1"

class LangGraphRuntimeUnavailable(RuntimeError):
    pass


def runtime_versions() -> dict:
    out={}
    for dist,key in (("langgraph","langgraph"),("langgraph-checkpoint-sqlite","checkpoint_sqlite")):
        try: out[key]=importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError: out[key]=None
    return out


def require_langgraph() -> dict:
    versions=runtime_versions()
    missing=[k for k,v in versions.items() if not v]
    if missing:
        raise LangGraphRuntimeUnavailable(
            "LANGGRAPH_RUNTIME_UNAVAILABLE: install ModelLab/requirements/requirements-langgraph.txt "
            f"(missing={','.join(missing)})"
        )
    if versions.get("langgraph") != LANGGRAPH_VERSION:
        raise LangGraphRuntimeUnavailable(
            f"LANGGRAPH_VERSION_MISMATCH: expected={LANGGRAPH_VERSION} actual={versions.get('langgraph')}"
        )
    if versions.get("checkpoint_sqlite") != SQLITE_CHECKPOINT_VERSION:
        raise LangGraphRuntimeUnavailable(
            "LANGGRAPH_CHECKPOINT_SQLITE_VERSION_MISMATCH: "
            f"expected={SQLITE_CHECKPOINT_VERSION} actual={versions.get('checkpoint_sqlite')}"
        )
    return versions


@contextlib.contextmanager
def sqlite_checkpointer(path: str | Path):
    """Open the local MAX LangGraph checkpoint DB with strict msgpack enabled."""
    require_langgraph()
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK","true")
    from langgraph.checkpoint.sqlite import SqliteSaver
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with SqliteSaver.from_conn_string(str(p)) as saver:
        setup=getattr(saver,"setup",None)
        if callable(setup): setup()
        yield saver
