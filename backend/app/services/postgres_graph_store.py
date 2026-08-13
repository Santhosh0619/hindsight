import uuid
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.graph_store import (
    DEFAULT_MAX_DEPTH,
    BlastRadius,
    BlastRadiusEntry,
    GraphPath,
)


class ReachRow(TypedDict):
    service_id: uuid.UUID
    depth: int
    path: list[uuid.UUID]
    criticalities: list[str]


# Blast-radius scoring weights (plan.md §4 Phase 4 checkpoint: "hard vs soft scoring
# ordering"). Tunable constants, not magic numbers scattered through the query — see
# docs/decisions/ for the full rationale.
_EDGE_CRITICALITY_WEIGHT = {"hard": 1.0, "soft": 0.4}
# ServiceTier is the one enum that stores the Python member *name* as its Postgres
# label (app/db/types.py's enum_values helper deliberately skips it — see Phase 1's
# ADR) -- so a raw-SQL query sees "TIER_1", not 1. Keyed to match what the DB actually
# returns, not the enum's underlying int value.
_TIER_WEIGHT = {"TIER_1": 1.0, "TIER_2": 0.6, "TIER_3": 0.3}
_DEFAULT_TIER_WEIGHT = 0.3

# Recursion has to terminate even with no depth cap (shortest_path has none) — this is
# a hard backstop, not a tunable product parameter.
_SHORTEST_PATH_DEPTH_CEILING = 20


def _reach_cte(*, reverse: bool) -> str:
    """The shared recursive CTE for downstream (reverse=False) or upstream (reverse=True).

    Cycle-safe via the `path` array guard (`NOT (next_id = ANY(path))`) -- a cycle in
    the data can only ever grow `reach` to at most one row per service in the
    workspace, so recursion always terminates. Diamond-safe via the caller's
    `DISTINCT ON (service_id) ... ORDER BY depth ASC`, which keeps only the shortest
    path to each reached service.
    """
    from_col, to_col = (
        ("to_service_id", "from_service_id") if reverse else ("from_service_id", "to_service_id")
    )
    return f"""
    WITH RECURSIVE reach(service_id, depth, path, criticalities) AS (
        SELECT s.id, 0, ARRAY[s.id]::uuid[], ARRAY[]::text[]
        FROM services s
        WHERE s.id = ANY(:start_ids ::uuid[]) AND s.workspace_id = :workspace_id

        UNION ALL

        SELECT e.{to_col}, r.depth + 1, r.path || e.{to_col}, r.criticalities || e.criticality::text
        FROM reach r
        JOIN service_edges e ON e.{from_col} = r.service_id
        WHERE e.workspace_id = :workspace_id
          AND r.depth < :max_depth
          AND NOT (e.{to_col} = ANY(r.path))
    )
    SELECT DISTINCT ON (service_id) service_id, depth, path, criticalities
    FROM reach
    WHERE depth > 0
    ORDER BY service_id, depth ASC
    """


class PostgresGraphStore:
    """`GraphStore` implemented with Postgres recursive CTEs (plan.md §7)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _reach(
        self,
        *,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int,
        reverse: bool,
    ) -> list[ReachRow]:
        result = await self._db.execute(
            text(_reach_cte(reverse=reverse)),
            {
                "start_ids": [str(sid) for sid in service_ids],
                "workspace_id": workspace_id,
                "max_depth": max_depth,
            },
        )
        return [
            ReachRow(
                service_id=row.service_id,
                depth=row.depth,
                path=row.path,
                criticalities=row.criticalities,
            )
            for row in result
        ]

    async def downstream(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[GraphPath]:
        rows = await self._reach(
            workspace_id=workspace_id, service_ids=service_ids, max_depth=max_depth, reverse=False
        )
        return [GraphPath(service_ids=row["path"]) for row in rows]

    async def upstream(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[GraphPath]:
        rows = await self._reach(
            workspace_id=workspace_id, service_ids=service_ids, max_depth=max_depth, reverse=True
        )
        return [GraphPath(service_ids=row["path"]) for row in rows]

    async def neighborhood(
        self, workspace_id: uuid.UUID, service_ids: list[uuid.UUID], k: int = 2
    ) -> set[uuid.UUID]:
        down = await self._reach(
            workspace_id=workspace_id, service_ids=service_ids, max_depth=k, reverse=False
        )
        up = await self._reach(
            workspace_id=workspace_id, service_ids=service_ids, max_depth=k, reverse=True
        )
        return {row["service_id"] for row in (*down, *up)}

    async def blast_radius(
        self,
        workspace_id: uuid.UUID,
        service_ids: list[uuid.UUID],
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> BlastRadius:
        rows = await self._reach(
            workspace_id=workspace_id, service_ids=service_ids, max_depth=max_depth, reverse=False
        )
        if not rows:
            return BlastRadius(entries=[])

        reached_ids = [row["service_id"] for row in rows]
        tier_result = await self._db.execute(
            text("SELECT id, tier FROM services WHERE id = ANY(:ids ::uuid[])"),
            {"ids": [str(sid) for sid in reached_ids]},
        )
        tier_by_service: dict[uuid.UUID, str] = {row.id: row.tier for row in tier_result}

        entries = []
        for row in rows:
            service_id = row["service_id"]
            depth = row["depth"]
            criticalities = row["criticalities"]
            tier = tier_by_service.get(service_id)
            tier_weight = (
                _TIER_WEIGHT.get(tier, _DEFAULT_TIER_WEIGHT)
                if tier is not None
                else _DEFAULT_TIER_WEIGHT
            )
            edge_weight = sum(_EDGE_CRITICALITY_WEIGHT.get(c, 0.0) for c in criticalities) / max(
                len(criticalities), 1
            )
            score = (edge_weight * tier_weight) / depth
            entries.append(
                BlastRadiusEntry(
                    service_id=service_id,
                    score=round(score, 4),
                    path=GraphPath(service_ids=row["path"]),
                    depth=depth,
                )
            )

        entries.sort(key=lambda e: e.score, reverse=True)
        return BlastRadius(entries=entries)

    async def shortest_path(
        self, workspace_id: uuid.UUID, from_service_id: uuid.UUID, to_service_id: uuid.UUID
    ) -> GraphPath | None:
        rows = await self._reach(
            workspace_id=workspace_id,
            service_ids=[from_service_id],
            max_depth=_SHORTEST_PATH_DEPTH_CEILING,
            reverse=False,
        )
        for row in rows:
            if row["service_id"] == to_service_id:
                return GraphPath(service_ids=row["path"])
        return None
