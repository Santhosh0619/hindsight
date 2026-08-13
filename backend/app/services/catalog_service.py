import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.catalog import Service, ServiceEdge, Team
from app.schemas.catalog import CatalogImport, CatalogImportResult

logger = get_logger(__name__)


async def list_teams(db: AsyncSession, workspace_id: uuid.UUID) -> list[Team]:
    result = await db.execute(select(Team).where(Team.workspace_id == workspace_id))
    return list(result.scalars().all())


async def create_team(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    slack_handle: str | None,
    escalation_contact: str | None,
) -> Team:
    team = Team(
        workspace_id=workspace_id,
        name=name,
        slack_handle=slack_handle,
        escalation_contact=escalation_contact,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


async def get_team(db: AsyncSession, workspace_id: uuid.UUID, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None or team.workspace_id != workspace_id:
        raise NotFoundError("Team not found")
    return team


async def update_team(db: AsyncSession, *, team: Team, **fields: object) -> Team:
    for key, value in fields.items():
        if value is not None:
            setattr(team, key, value)
    await db.commit()
    await db.refresh(team)
    return team


async def delete_team(db: AsyncSession, *, team: Team) -> None:
    await db.delete(team)
    await db.commit()


async def list_services(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    team_id: uuid.UUID | None = None,
    tier: int | None = None,
) -> list[Service]:
    query = select(Service).where(Service.workspace_id == workspace_id)
    if team_id is not None:
        query = query.where(Service.team_id == team_id)
    if tier is not None:
        query = query.where(Service.tier == tier)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_service(db: AsyncSession, *, workspace_id: uuid.UUID, **fields: object) -> Service:
    service = Service(workspace_id=workspace_id, **fields)
    db.add(service)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A service with this name already exists") from exc
    await db.refresh(service)
    logger.info("service_created", service_id=str(service.id), workspace_id=str(workspace_id))
    return service


async def get_service(db: AsyncSession, workspace_id: uuid.UUID, service_id: uuid.UUID) -> Service:
    service = await db.get(Service, service_id)
    if service is None or service.workspace_id != workspace_id:
        raise NotFoundError("Service not found")
    return service


async def update_service(db: AsyncSession, *, service: Service, **fields: object) -> Service:
    for key, value in fields.items():
        if value is not None:
            setattr(service, key, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A service with this name already exists") from exc
    await db.refresh(service)
    return service


async def delete_service(db: AsyncSession, *, service: Service) -> None:
    await db.delete(service)
    await db.commit()


async def list_edges(db: AsyncSession, workspace_id: uuid.UUID) -> list[ServiceEdge]:
    result = await db.execute(select(ServiceEdge).where(ServiceEdge.workspace_id == workspace_id))
    return list(result.scalars().all())


async def create_edge(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    from_service_id: uuid.UUID,
    to_service_id: uuid.UUID,
    kind: object,
    criticality: object,
) -> ServiceEdge:
    # Both endpoints must belong to this workspace -- a cross-workspace service_id
    # would otherwise silently create an edge that straddles two tenants.
    await get_service(db, workspace_id, from_service_id)
    await get_service(db, workspace_id, to_service_id)

    edge = ServiceEdge(
        workspace_id=workspace_id,
        from_service_id=from_service_id,
        to_service_id=to_service_id,
        kind=kind,
        criticality=criticality,
    )
    db.add(edge)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("This edge already exists") from exc
    await db.refresh(edge)
    logger.info("edge_created", edge_id=str(edge.id), workspace_id=str(workspace_id))
    return edge


async def get_edge(db: AsyncSession, workspace_id: uuid.UUID, edge_id: uuid.UUID) -> ServiceEdge:
    edge = await db.get(ServiceEdge, edge_id)
    if edge is None or edge.workspace_id != workspace_id:
        raise NotFoundError("Edge not found")
    return edge


async def delete_edge(db: AsyncSession, *, edge: ServiceEdge) -> None:
    await db.delete(edge)
    await db.commit()


async def get_graph(
    db: AsyncSession, workspace_id: uuid.UUID
) -> tuple[list[Service], list[ServiceEdge]]:
    services = await list_services(db, workspace_id)
    edges = await list_edges(db, workspace_id)
    return services, edges


async def import_catalog(
    db: AsyncSession, *, workspace_id: uuid.UUID, payload: CatalogImport
) -> CatalogImportResult:
    team_by_name: dict[str, uuid.UUID] = {}
    for team_row in payload.teams:
        team = Team(
            workspace_id=workspace_id,
            name=team_row.name,
            slack_handle=team_row.slack_handle,
            escalation_contact=team_row.escalation_contact,
        )
        db.add(team)
        await db.flush()
        team_by_name[team_row.name] = team.id

    service_by_name: dict[str, uuid.UUID] = {}
    existing_result = await db.execute(select(Service).where(Service.workspace_id == workspace_id))
    for existing in existing_result.scalars().all():
        service_by_name[existing.name] = existing.id

    for service_row in payload.services:
        team_id = team_by_name.get(service_row.team_name) if service_row.team_name else None
        service = Service(
            workspace_id=workspace_id,
            name=service_row.name,
            tier=service_row.tier,
            team_id=team_id,
            repo_url=service_row.repo_url,
            description=service_row.description,
            runbook_url=service_row.runbook_url,
        )
        db.add(service)
        await db.flush()
        service_by_name[service_row.name] = service.id

    for edge_row in payload.edges:
        from_id = service_by_name.get(edge_row.from_service_name)
        to_id = service_by_name.get(edge_row.to_service_name)
        if from_id is None or to_id is None:
            await db.rollback()
            raise ValidationAppError(
                "Import references a service name that doesn't exist",
                detail={"from": edge_row.from_service_name, "to": edge_row.to_service_name},
            )
        db.add(
            ServiceEdge(
                workspace_id=workspace_id,
                from_service_id=from_id,
                to_service_id=to_id,
                kind=edge_row.kind,
                criticality=edge_row.criticality,
            )
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ValidationAppError("Import contains a duplicate or invalid entry") from exc

    logger.info(
        "catalog_imported",
        workspace_id=str(workspace_id),
        teams=len(payload.teams),
        services=len(payload.services),
        edges=len(payload.edges),
    )
    return CatalogImportResult(
        teams_created=len(payload.teams),
        services_created=len(payload.services),
        edges_created=len(payload.edges),
    )
