from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from max_graph.runtime import sqlite_checkpointer
from max_graph.state import ScientistChatGraphState

SCHEMA="MAX_SCIENTIST_CHAT_LANGGRAPH_V1"


def _build_graph(discuss_fn: Callable, *, runtime_api_key: str, progress_callback=None):
    from langgraph.graph import END, START, StateGraph

    def guard(state: ScientistChatGraphState):
        req=str(state.get("request_id") or "")
        if req and req==str(state.get("last_request_id") or "") and isinstance(state.get("last_answer"),dict):
            return {"status":"CACHED","answer":deepcopy(state["last_answer"])}
        return {"status":"RUNNING","error":None}

    def route(state: ScientistChatGraphState):
        return "cached" if state.get("status")=="CACHED" else "answer"

    def answer(state: ScientistChatGraphState):
        result=discuss_fn(
            state.get("llm_cfg") or {}, selected_model=str(state.get("selected_model") or ""),
            api_key=str(runtime_api_key or ""), history=state.get("history") or [],
            user_prompt=str(state.get("user_prompt") or ""), context=state.get("context") or {},
            allow_fallback=bool(state.get("allow_fallback",False)), progress_callback=progress_callback,
        )
        req=str(state.get("request_id") or "")
        return {"answer":result,"last_answer":deepcopy(result),"last_request_id":req,"status":"COMPLETED"}

    g=StateGraph(ScientistChatGraphState)
    g.add_node("guard",guard); g.add_node("read_only_answer",answer)
    g.add_edge(START,"guard")
    g.add_conditional_edges("guard",route,{"cached":END,"answer":"read_only_answer"})
    g.add_edge("read_only_answer",END)
    return g


def run_scientist_chat_graph(*, app_dir: str | Path, request_id: str, thread_id: str, discuss_fn: Callable,
                             llm_cfg: dict, selected_model: str, api_key: str, history: list[dict], user_prompt: str,
                             context: dict, allow_fallback: bool=False, progress_callback=None) -> dict:
    """Isolated read-only Chat graph. There are intentionally no execution nodes/edges."""
    db=Path(app_dir)/"runtime"/"langgraph"/"scientist_chat.sqlite"
    state: ScientistChatGraphState={
        "schema":SCHEMA,"request_id":str(request_id),"thread_id":str(thread_id),"llm_cfg":deepcopy(llm_cfg),
        "selected_model":str(selected_model),"history":deepcopy(history),
        "user_prompt":str(user_prompt),"context":deepcopy(context),"allow_fallback":bool(allow_fallback),"status":"STARTED",
    }
    with sqlite_checkpointer(db) as saver:
        graph=_build_graph(discuss_fn,runtime_api_key=str(api_key),progress_callback=progress_callback).compile(checkpointer=saver)
        final=graph.invoke(state,config={"configurable":{"thread_id":str(thread_id)}})
    return deepcopy(final.get("answer") or final.get("last_answer") or {})
