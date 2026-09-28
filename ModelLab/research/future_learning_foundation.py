from __future__ import annotations

from copy import deepcopy

SCHEMA="MAX_FUTURE_LEARNING_FOUNDATION_V1"


def foundation_snapshot(cfg: dict) -> dict:
    ls=((cfg.get("agent") or {}).get("learning_system") or {}) if isinstance((cfg.get("agent") or {}).get("learning_system"),dict) else {}
    future=ls.get("future_foundations") if isinstance(ls.get("future_foundations"),dict) else {}
    embed=deepcopy(future.get("embedder") or {"enabled":False,"provider":"NONE"})
    rag=deepcopy(future.get("rag") or {"enabled":False,"backend":"NONE"})
    rl=deepcopy(future.get("rl") or {"enabled":False,"mode":"OFF"})
    active=[name for name,row in (("embedder",embed),("rag",rag),("rl",rl)) if bool(row.get("enabled",False))]
    if active:
        raise RuntimeError("FUTURE_LEARNING_FOUNDATION_NOT_IMPLEMENTED: "+",".join(active)+" must remain disabled in v1.4.3")
    return {
        "schema":SCHEMA,
        "embedder":embed,
        "rag":rag,
        "rl":rl,
        "research_transition_schema":"MAX_RESEARCH_EXPERIENCE_V1",
        "protected_oos_reward_allowed":False,
        "protected_oos_embedding_allowed":False,
        "authority":"FOUNDATION_ONLY_DISABLED_FAIL_CLOSED",
    }


class EmbedderFoundation:
    interface_version="MAX_EMBEDDER_INTERFACE_V1"
    def embed(self, texts):
        raise RuntimeError("EMBEDDER_DISABLED_FOUNDATION_ONLY")


class RAGFoundation:
    interface_version="MAX_RAG_INTERFACE_V1"
    def retrieve(self, query, **kwargs):
        raise RuntimeError("RAG_DISABLED_FOUNDATION_ONLY")


class RLPolicyFoundation:
    interface_version="MAX_RL_POLICY_INTERFACE_V1"
    def recommend(self, state, actions):
        raise RuntimeError("RL_DISABLED_FOUNDATION_ONLY")
