import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, CurrentWorkspaceMember, DbSession, require_role
from app.core.pagination import CursorPage
from app.models.postmortem import PostmortemStatus
from app.models.workspace import WorkspaceRole
from app.schemas.postmortem import (
    PostmortemBulkCreate,
    PostmortemChunkOut,
    PostmortemCreate,
    PostmortemDetailOut,
    PostmortemOut,
    PostmortemStatusOut,
)
from app.services import postmortem_service

router = APIRouter(prefix="/workspaces/{workspace_id}/postmortems", tags=["postmortems"])

OwnerOrResponder = Annotated[
    object, Depends(require_role(WorkspaceRole.OWNER, WorkspaceRole.RESPONDER))
]


@router.post("", response_model=PostmortemOut, status_code=status.HTTP_201_CREATED)
async def create_postmortem(
    workspace_id: uuid.UUID,
    payload: PostmortemCreate,
    membership: OwnerOrResponder,
    current_user: CurrentUser,
    db: DbSession,
) -> PostmortemOut:
    postmortem = await postmortem_service.create_postmortem(
        db, workspace_id=workspace_id, created_by=current_user.id, payload=payload
    )
    return PostmortemOut.model_validate(postmortem)


@router.post("/bulk", response_model=list[PostmortemOut], status_code=status.HTTP_201_CREATED)
async def create_postmortems_bulk(
    workspace_id: uuid.UUID,
    payload: PostmortemBulkCreate,
    membership: OwnerOrResponder,
    current_user: CurrentUser,
    db: DbSession,
) -> list[PostmortemOut]:
    postmortems = await postmortem_service.create_postmortems_bulk(
        db, workspace_id=workspace_id, created_by=current_user.id, items=payload.items
    )
    return [PostmortemOut.model_validate(p) for p in postmortems]


@router.get("", response_model=CursorPage[PostmortemOut])
async def list_postmortems(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    status_filter: Annotated[PostmortemStatus | None, Query(alias="status")] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CursorPage[PostmortemOut]:
    rows, next_cursor = await postmortem_service.list_postmortems(
        db, workspace_id=workspace_id, status=status_filter, cursor=cursor, limit=limit
    )
    return CursorPage[PostmortemOut](
        items=[PostmortemOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@router.get("/{postmortem_id}", response_model=PostmortemDetailOut)
async def get_postmortem(
    workspace_id: uuid.UUID,
    postmortem_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
) -> PostmortemDetailOut:
    postmortem = await postmortem_service.get_postmortem(db, workspace_id, postmortem_id)
    chunks = await postmortem_service.list_chunks(db, postmortem_id)
    return PostmortemDetailOut(
        **PostmortemOut.model_validate(postmortem).model_dump(),
        chunks=[PostmortemChunkOut.model_validate(c) for c in chunks],
    )


@router.get("/{postmortem_id}/status", response_model=PostmortemStatusOut)
async def get_postmortem_status(
    workspace_id: uuid.UUID,
    postmortem_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
) -> PostmortemStatusOut:
    postmortem = await postmortem_service.get_postmortem(db, workspace_id, postmortem_id)
    return PostmortemStatusOut(
        status=postmortem.status,
        injection_flagged=postmortem.injection_flagged,
        failure_reason=postmortem.failure_reason,
    )


@router.delete("/{postmortem_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_postmortem(
    workspace_id: uuid.UUID,
    postmortem_id: uuid.UUID,
    membership: OwnerOrResponder,
    db: DbSession,
) -> None:
    postmortem = await postmortem_service.get_postmortem(db, workspace_id, postmortem_id)
    await postmortem_service.delete_postmortem(db, postmortem=postmortem)
