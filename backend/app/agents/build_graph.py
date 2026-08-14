from functools import partial
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.edges import route_after_critic
from app.agents.nodes import (
    analyst_node,
    briefer_node,
    correlator_node,
    critic_node,
    normalizer_node,
    retriever_node,
)
from app.agents.state import TriageState
from app.core.config import Settings
from app.services.graph_store import GraphStore
from app.services.llm.router import LLMRouter


def checkpointer_conn_string(settings: Settings) -> str:
    """AsyncPostgresSaver needs a plain psycopg-style DSN -- Settings.database_url is
    SQLAlchemy's driver-qualified form (postgresql+asyncpg://...)."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_graph(
    db: AsyncSession,
    graph_store: GraphStore,
    router: LLMRouter,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    graph = StateGraph(TriageState)
    graph.add_node("normalizer", partial(normalizer_node, db=db, router=router))
    graph.add_node("retriever", partial(retriever_node, db=db, graph_store=graph_store))
    graph.add_node("correlator", partial(correlator_node, db=db, graph_store=graph_store))
    graph.add_node("analyst", partial(analyst_node, db=db, router=router))
    graph.add_node("critic", partial(critic_node, router=router))
    graph.add_node("briefer", partial(briefer_node, db=db))

    graph.add_edge(START, "normalizer")
    graph.add_edge("normalizer", "retriever")
    graph.add_edge("retriever", "correlator")
    graph.add_edge("correlator", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges(
        "critic", route_after_critic, {"retriever": "retriever", "briefer": "briefer"}
    )
    graph.add_edge("briefer", END)

    return graph.compile(checkpointer=checkpointer)
