import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import TriageState
from app.models.agent import AgentRunStep

_NODE_NAMES = {"normalizer", "retriever", "correlator", "analyst", "critic", "briefer"}


async def stream_graph_events(
    graph: CompiledStateGraph,  # type: ignore[type-arg]
    state: TriageState,
    *,
    thread_id: str,
    db: AsyncSession,
    run_id: uuid.UUID,
) -> AsyncIterator[dict[str, object]]:
    seq = 0
    node_starts: dict[str, float] = {}
    retriever_seen_once = False
    error: str | None = None

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

                seq += 1
                db.add(
                    AgentRunStep(
                        run_id=run_id,
                        seq=seq,
                        node_name=name,
                        status="done",
                        latency_ms=latency_ms,
                        input_summary={},
                        output_summary=_summarize(output),
                    )
                )
                await db.commit()

                yield {"type": "node_end", "node": name, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller as a stream event
        error = str(exc)
        yield {"type": "error", "message": error}
        return

    yield {"type": "done"}


def _summarize(output: dict[str, Any]) -> dict[str, object]:
    # Never the full state (chunk text, prompts) -- just which keys a node touched.
    return {"updated_keys": sorted(output.keys())}
