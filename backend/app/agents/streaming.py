import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agents.state import TriageState
from app.db.session import get_session_factory
from app.models.agent import AgentRunStep

_NODE_NAMES = {"normalizer", "retriever", "correlator", "analyst", "critic", "briefer"}


async def stream_graph_events(
    graph: CompiledStateGraph,  # type: ignore[type-arg]
    state: TriageState,
    *,
    thread_id: str,
    run_id: uuid.UUID,
) -> AsyncIterator[dict[str, object]]:
    seq = 0
    node_starts: dict[str, float] = {}
    retriever_seen_once = False
    brief_id: uuid.UUID | None = None

    try:
        async for event in graph.astream_events(
            state, config={"configurable": {"thread_id": thread_id}}, version="v2"
        ):
            name = event.get("name")
            if name not in _NODE_NAMES:
                continue

            if event["event"] == "on_chain_start":
                node_starts[name] = time.monotonic()
                if name == "retriever":
                    if retriever_seen_once:
                        yield {"type": "retry"}
                    retriever_seen_once = True
                yield {"type": "node_start", "node": name}

            elif event["event"] == "on_chain_end":
                started_at = node_starts.get(name, time.monotonic())
                latency_ms = int((time.monotonic() - started_at) * 1000)
                output: dict[str, Any] = event["data"].get("output") or {}
                if name == "briefer":
                    final_brief = output.get("final")
                    if final_brief is not None:
                        brief_id = final_brief.id

                seq += 1
                # A fresh session, not whatever session the graph's own nodes are
                # bound to -- astream_events runs the graph as its own concurrent
                # task, so writing through the nodes' session here raced with the
                # nodes' own queries (the exact class of bug ADR 0007 §1 documents
                # for Phase 7's concurrent retrievers, here between the observer
                # loop and the graph run instead of between sibling retrievers).
                async with get_session_factory()() as step_db:
                    step_db.add(
                        AgentRunStep(
                            run_id=run_id,
                            seq=seq,
                            node_name=name,
                            status="done",
                            latency_ms=latency_ms,
                            tokens_in=int(output.get("step_tokens_in") or 0),
                            tokens_out=int(output.get("step_tokens_out") or 0),
                            input_summary={},
                            output_summary=_summarize(name, output),
                        )
                    )
                    await step_db.commit()

                yield {"type": "node_end", "node": name, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller as a stream event
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "done", "brief_id": str(brief_id) if brief_id else None}


def _summarize(name: str, output: dict[str, Any]) -> dict[str, object]:
    # Never the full state (chunk text, prompts, hypothesis text) -- just enough to
    # show what a step actually produced on F12's waterfall (FR-01/FR-06).
    summary: dict[str, object] = {"updated_keys": sorted(output.keys())}

    if name == "normalizer":
        signal = output.get("signal")
        if signal is not None:
            summary["affected_service_count"] = len(signal.affected_service_ids)
            summary["unresolved_mention_count"] = len(signal.unresolved_mentions)
    elif name == "retriever":
        retrieval = output.get("retrieval")
        if retrieval is not None:
            summary["result_count"] = len(retrieval.results)
    elif name == "correlator":
        candidates = output.get("candidates")
        if candidates is not None:
            summary["candidate_count"] = len(candidates)
            if candidates:
                summary["top_overall_score"] = candidates[0].overall_score
    elif name == "analyst":
        draft = output.get("draft")
        if draft is not None:
            summary["hypothesis_count"] = len(draft.hypotheses)
            summary["runbook_step_count"] = len(draft.runbook_steps)
    elif name == "critic":
        verification = output.get("verification")
        if verification is not None:
            summary["score"] = verification.score
            summary["invalid_citation_count"] = len(verification.invalid_citations)

    return summary
