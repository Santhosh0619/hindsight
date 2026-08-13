import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentWorkspaceMember, DbSession, require_role
from app.models.catalog import ServiceTier
from app.models.workspace import WorkspaceRole
from app.schemas.catalog import (
    BlastRadiusEntryOut,
    BlastRadiusOut,
    CatalogGraphOut,
    CatalogImport,
    CatalogImportResult,
    EdgeCreate,
    EdgeOut,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)
from app.services import catalog_service
from app.services.graph_store import DEFAULT_MAX_DEPTH
from app.services.postgres_graph_store import PostgresGraphStore

router = APIRouter(prefix="/workspaces/{workspace_id}/catalog", tags=["catalog"])

OwnerOrResponder = Annotated[
    object, Depends(require_role(WorkspaceRole.OWNER, WorkspaceRole.RESPONDER))
]


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> list[TeamOut]:
    teams = await catalog_service.list_teams(db, workspace_id)
    return [TeamOut.model_validate(t) for t in teams]


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    workspace_id: uuid.UUID, payload: TeamCreate, membership: OwnerOrResponder, db: DbSession
) -> TeamOut:
    team = await catalog_service.create_team(
        db,
        workspace_id=workspace_id,
        name=payload.name,
        slack_handle=payload.slack_handle,
        escalation_contact=payload.escalation_contact,
    )
    return TeamOut.model_validate(team)


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(
    workspace_id: uuid.UUID,
    team_id: uuid.UUID,
    payload: TeamUpdate,
    membership: OwnerOrResponder,
    db: DbSession,
) -> TeamOut:
    team = await catalog_service.get_team(db, workspace_id, team_id)
    team = await catalog_service.update_team(
        db, team=team, **payload.model_dump(exclude_unset=True)
    )
    return TeamOut.model_validate(team)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    workspace_id: uuid.UUID, team_id: uuid.UUID, membership: OwnerOrResponder, db: DbSession
) -> None:
    team = await catalog_service.get_team(db, workspace_id, team_id)
    await catalog_service.delete_team(db, team=team)


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    tier: Annotated[ServiceTier | None, Query()] = None,
) -> list[ServiceOut]:
    services = await catalog_service.list_services(db, workspace_id, team_id=team_id, tier=tier)
    return [ServiceOut.model_validate(s) for s in services]


@router.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    workspace_id: uuid.UUID, payload: ServiceCreate, membership: OwnerOrResponder, db: DbSession
) -> ServiceOut:
    service = await catalog_service.create_service(
        db, workspace_id=workspace_id, **payload.model_dump()
    )
    return ServiceOut.model_validate(service)


@router.get("/services/{service_id}", response_model=ServiceOut)
async def get_service(
    workspace_id: uuid.UUID,
    service_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
) -> ServiceOut:
    service = await catalog_service.get_service(db, workspace_id, service_id)
    return ServiceOut.model_validate(service)


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def update_service(
    workspace_id: uuid.UUID,
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    membership: OwnerOrResponder,
    db: DbSession,
) -> ServiceOut:
    service = await catalog_service.get_service(db, workspace_id, service_id)
    service = await catalog_service.update_service(
        db, service=service, **payload.model_dump(exclude_unset=True)
    )
    return ServiceOut.model_validate(service)


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    workspace_id: uuid.UUID, service_id: uuid.UUID, membership: OwnerOrResponder, db: DbSession
) -> None:
    service = await catalog_service.get_service(db, workspace_id, service_id)
    await catalog_service.delete_service(db, service=service)


@router.get("/services/{service_id}/blast-radius", response_model=BlastRadiusOut)
async def get_blast_radius(
    workspace_id: uuid.UUID,
    service_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    depth: int = Query(default=DEFAULT_MAX_DEPTH, ge=1, le=10),
) -> BlastRadiusOut:
    await catalog_service.get_service(db, workspace_id, service_id)
    store = PostgresGraphStore(db)
    radius = await store.blast_radius(workspace_id, [service_id], max_depth=depth)

    referenced_ids = {entry.service_id for entry in radius.entries}
    for entry in radius.entries:
        referenced_ids.update(entry.path.service_ids)
    services_by_id = await catalog_service.get_services_by_ids(
        db, workspace_id, list(referenced_ids)
    )

    entries = [
        BlastRadiusEntryOut(
            service=ServiceOut.model_validate(services_by_id[entry.service_id]),
            score=entry.score,
            path=[ServiceOut.model_validate(services_by_id[sid]) for sid in entry.path.service_ids],
            depth=entry.depth,
        )
        for entry in radius.entries
    ]
    return BlastRadiusOut(services=entries)


@router.get("/edges", response_model=list[EdgeOut])
async def list_edges(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> list[EdgeOut]:
    edges = await catalog_service.list_edges(db, workspace_id)
    return [EdgeOut.model_validate(e) for e in edges]


@router.post("/edges", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def create_edge(
    workspace_id: uuid.UUID, payload: EdgeCreate, membership: OwnerOrResponder, db: DbSession
) -> EdgeOut:
    edge = await catalog_service.create_edge(
        db,
        workspace_id=workspace_id,
        from_service_id=payload.from_service_id,
        to_service_id=payload.to_service_id,
        kind=payload.kind,
        criticality=payload.criticality,
    )
    return EdgeOut.model_validate(edge)


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    workspace_id: uuid.UUID, edge_id: uuid.UUID, membership: OwnerOrResponder, db: DbSession
) -> None:
    edge = await catalog_service.get_edge(db, workspace_id, edge_id)
    await catalog_service.delete_edge(db, edge=edge)


@router.post("/import", response_model=CatalogImportResult)
async def import_catalog(
    workspace_id: uuid.UUID, payload: CatalogImport, membership: OwnerOrResponder, db: DbSession
) -> CatalogImportResult:
    return await catalog_service.import_catalog(db, workspace_id=workspace_id, payload=payload)


@router.get("/graph", response_model=CatalogGraphOut)
async def get_graph(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> CatalogGraphOut:
    services, edges = await catalog_service.get_graph(db, workspace_id)
    return CatalogGraphOut(
        nodes=[ServiceOut.model_validate(s) for s in services],
        edges=[EdgeOut.model_validate(e) for e in edges],
    )
