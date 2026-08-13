import uuid
from typing import Protocol

from pydantic import BaseModel

DEFAULT_MAX_DEPTH = 4


class GraphPath(BaseModel):
    """Root-to-target path, inclusive of both endpoints."""

    service_ids: list[uuid.UUID]


class BlastRadiusEntry(BaseModel):
    service_id: uuid.UUID
    score: float
    path: GraphPath
    depth: int


class BlastRadius(BaseModel):
    entries: list[BlastRadiusEntry]  # sorted by score, descending


class GraphStore(Protocol):
    """Workspace-scoped graph traversal over the service dependency graph.

    plan.md §7: Postgres recursive CTEs behind this protocol, not a dedicated graph
    database — the graph is small and highly relational at this project's scale. A
    different implementation (e.g. a Neo4j-backed one) could satisfy this same
    protocol if that threshold were ever crossed.
    """

    async def upstream(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[GraphPath]: ...

    async def downstream(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[GraphPath]: ...

    async def neighborhood(
        self, workspace_id: uuid.UUID, service_ids: list[uuid.UUID], k: int = 2
    ) -> set[uuid.UUID]: ...

    async def blast_radius(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> BlastRadius: ...

    async def shortest_path(
        self, workspace_id: uuid.UUID, from_service_id: uuid.UUID, to_service_id: uuid.UUID
    ) -> GraphPath | None: ...
