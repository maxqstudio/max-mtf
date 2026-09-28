from __future__ import annotations

from typing import Any, TypedDict

class FactoryGraphState(TypedDict, total=False):
    schema: str
    orchestrator_id: str
    status: str
    stage: str
    cycle: int
    max_cycles: int
    current_factory_id: str | None
    factory_dir: str | None
    manifest_status: str
    terminal_factory: str | None
    terminal_failure_stage: str | None
    champion_factory: str | None
    completed_factories: list[dict[str,Any]]
    consecutive_empty_cycles: int
    last_learning_stage: str | None
    result_payload: dict[str,Any]
    error: dict[str,Any] | None
    created_utc: str
    updated_utc: str

class ScientistDirectorState(TypedDict, total=False):
    schema: str
    thread_id: str
    request_id: str
    round_no: int
    context: dict[str,Any]
    evidence_requests: list[dict[str,Any]]
    inspected_evidence: list[dict[str,Any]]
    inspection_plan: dict[str,Any]
    prior_attribution: list[dict[str,Any]]
    hypothesis_memory: list[dict[str,Any]]
    proposal_lineage: list[dict[str,Any]]
    response: dict[str,Any]
    last_request_id: str | None
    last_response: dict[str,Any] | None
    status: str
    error: dict[str,Any] | None

class ScientistChatGraphState(TypedDict, total=False):
    schema: str
    thread_id: str
    request_id: str
    llm_cfg: dict[str,Any]
    selected_model: str
    history: list[dict[str,Any]]
    user_prompt: str
    context: dict[str,Any]
    allow_fallback: bool
    answer: dict[str,Any]
    last_request_id: str | None
    last_answer: dict[str,Any] | None
    status: str
    error: dict[str,Any] | None
