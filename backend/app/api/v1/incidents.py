import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.deps import CurrentUser, CurrentWorkspaceMember, DbSession, require_role
from app.core.pagination import CursorPage
from app.db.session import get_session_factory
from app.models.incident import IncidentStatus
from app.models.postmortem import Severity
from app.models.workspace import WorkspaceRole
from app.schemas.incident_api import (
    BriefFeedbackCreate,
    BriefFeedbackOut,
    BriefOut,
    IncidentCreate,
    IncidentOut,
    IncidentUpdate,
)
from app.services import incidents_service
from app.services.llm.router import build_router
from app.services.postgres_graph_store import PostgresGraphStore

router = APIRouter(prefix="/workspaces/{workspace_id}/incidents", tags=["incidents"])

OwnerOrResponder = Annotated[
    object, Depends(require_role(WorkspaceRole.OWNER, WorkspaceRole.RESPONDER))
]


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
async def create_incident(
    workspace_id: uuid.UUID,
    payload: IncidentCreate,
    membership: OwnerOrResponder,
    current_user: CurrentUser,
    db: DbSession,
) -> IncidentOut:
    incident = await incidents_service.create_incident(
        db, workspace_id=workspace_id, opened_by=current_user.id, payload=payload
    )
    return IncidentOut.model_validate(incident)


@router.get("", response_model=CursorPage[IncidentOut])
async def list_incidents(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    severity: Annotated[Severity | None, Query()] = None,
    service_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CursorPage[IncidentOut]:
    rows, next_cursor = await incidents_service.list_incidents(
        db,
        workspace_id=workspace_id,
        status=status_filter,
        severity=severity.value if severity else None,
        service_id=service_id,
        cursor=cursor,
        limit=limit,
    )
    return CursorPage[IncidentOut](
        items=[IncidentOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
) -> IncidentOut:
    incident = await incidents_service.get_incident(db, workspace_id, incident_id)
    return IncidentOut.model_validate(incident)


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    membership: OwnerOrResponder,
    db: DbSession,
) -> IncidentOut:
    incident = await incidents_service.get_incident(db, workspace_id, incident_id)
    incident = await incidents_service.update_incident(db, incident=incident, payload=payload)
    return IncidentOut.model_validate(incident)


@router.post("/{incident_id}/brief", response_model=BriefOut)
async def generate_brief(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    membership: OwnerOrResponder,
    db: DbSession,
) -> BriefOut:
    incident = await incidents_service.get_incident(db, workspace_id, incident_id)
    graph_store = PostgresGraphStore(db)
    router_ = build_router(get_settings())
    return await incidents_service.generate_brief(db, graph_store, router_, incident=incident)


@router.get("/{incident_id}/brief/stream")
async def stream_brief(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    membership: OwnerOrResponder,
    db: DbSession,
) -> EventSourceResponse:
    # `db` (FastAPI's request-scoped session) is closed by the dependency's own
    # AsyncExitStack as soon as this handler returns the response object -- before
    # Starlette ever starts iterating the SSE body. The generator below must own a
    # session scoped to its own lifetime, not borrow one that's already gone by the
    # time it actually runs (same discipline already applied to the checkpointer).
    incident = await incidents_service.get_incident(db, workspace_id, incident_id)

    async def _sse_events() -> AsyncIterator[dict[str, str]]:
        async with get_session_factory()() as stream_db:
            graph_store = PostgresGraphStore(stream_db)
            router_ = build_router(get_settings())
            async for event in incidents_service.stream_brief_generation(
                stream_db, graph_store, router_, incident=incident
            ):
                yield {"event": str(event["type"]), "data": json.dumps(event)}

    return EventSourceResponse(_sse_events())


@router.get("/{incident_id}/briefs", response_model=list[BriefOut])
async def list_briefs(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
) -> list[BriefOut]:
    await incidents_service.get_incident(db, workspace_id, incident_id)
    return await incidents_service.list_briefs(
        db, incident_id=incident_id, workspace_id=workspace_id
    )


@router.post(
    "/{incident_id}/brief/{brief_id}/feedback",
    response_model=BriefFeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    brief_id: uuid.UUID,
    payload: BriefFeedbackCreate,
    membership: CurrentWorkspaceMember,
    current_user: CurrentUser,
    db: DbSession,
) -> BriefFeedbackOut:
    await incidents_service.get_incident(db, workspace_id, incident_id)
    await incidents_service.get_brief(db, incident_id=incident_id, brief_id=brief_id)
    return await incidents_service.record_feedback(
        db, brief_id=brief_id, user_id=current_user.id, payload=payload
    )
