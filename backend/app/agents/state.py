import uuid
from typing import TypedDict

from pydantic import BaseModel

from app.schemas.incident import (
    CandidateMatch,
    DraftBrief,
    IncidentBrief,
    NormalizedSignal,
    VerificationResult,
)
from app.schemas.search import SearchResponseOut
from app.services.graph_store import BlastRadius


class TraceEntry(BaseModel):
    node: str
    note: str


class TriageState(TypedDict):
    incident_id: uuid.UUID
    workspace_id: uuid.UUID
    raw_text: str
    signal: NormalizedSignal | None
    retrieval: SearchResponseOut | None
    candidates: list[CandidateMatch]
    blast_radius: BlastRadius | None
    draft: DraftBrief | None
    verification: VerificationResult | None
    final: IncidentBrief | None
    retry_count: int
    llm_used: bool
    from_cache: bool
    trace: list[TraceEntry]
    messages: list[dict[str, str]]
    # Set by whichever node most recently made an LLM call this step (0 otherwise) --
    # not a running total. `stream_graph_events` reads these straight off each node's
    # own returned dict (not the graph's merged cumulative state) to populate that
    # step's own `AgentRunStep.tokens_in/out`, so they only need to be "this node's
    # own cost," not accumulated here.
    step_tokens_in: int
    step_tokens_out: int


def initial_state(*, incident_id: uuid.UUID, workspace_id: uuid.UUID, raw_text: str) -> TriageState:
    return TriageState(
        incident_id=incident_id,
        workspace_id=workspace_id,
        raw_text=raw_text,
        signal=None,
        retrieval=None,
        candidates=[],
        blast_radius=None,
        draft=None,
        verification=None,
        final=None,
        retry_count=0,
        llm_used=True,
        from_cache=False,
        trace=[],
        messages=[],
        step_tokens_in=0,
        step_tokens_out=0,
    )
