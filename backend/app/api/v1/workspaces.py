import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, CurrentWorkspaceMember, DbSession, require_role
from app.core.pagination import CursorPage
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.schemas.workspace import (
    AuditLogEntryOut,
    InviteCodeOut,
    JoinRequest,
    MemberOut,
    RoleUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services import workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

OwnerMember = Annotated[WorkspaceMember, Depends(require_role(WorkspaceRole.OWNER))]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate, current_user: CurrentUser, db: DbSession
) -> WorkspaceOut:
    workspace = await workspace_service.create_workspace(db, owner=current_user, name=payload.name)
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        is_demo=workspace.is_demo,
        created_at=workspace.created_at,
        role=WorkspaceRole.OWNER,
    )


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(current_user: CurrentUser, db: DbSession) -> list[WorkspaceOut]:
    memberships = await workspace_service.list_my_workspaces(db, current_user)
    return [
        WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            is_demo=workspace.is_demo,
            created_at=workspace.created_at,
            role=role,
        )
        for workspace, role in memberships
    ]


@router.post("/join", response_model=WorkspaceOut)
async def join_workspace(
    payload: JoinRequest, current_user: CurrentUser, db: DbSession
) -> WorkspaceOut:
    workspace = await workspace_service.join_by_code(db, user=current_user, code=payload.code)
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        is_demo=workspace.is_demo,
        created_at=workspace.created_at,
        role=WorkspaceRole.RESPONDER,
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> WorkspaceOut:
    workspace = await workspace_service.get_workspace(db, workspace_id)
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        is_demo=workspace.is_demo,
        created_at=workspace.created_at,
        role=membership.role,
    )


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    membership: OwnerMember,
    db: DbSession,
) -> WorkspaceOut:
    workspace = await workspace_service.get_workspace(db, workspace_id)
    workspace = await workspace_service.update_workspace(
        db,
        workspace=workspace,
        actor_user_id=membership.user_id,
        name=payload.name,
        slug=payload.slug,
    )
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        is_demo=workspace.is_demo,
        created_at=workspace.created_at,
        role=WorkspaceRole.OWNER,
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: uuid.UUID, membership: OwnerMember, db: DbSession) -> None:
    workspace = await workspace_service.get_workspace(db, workspace_id)
    await workspace_service.delete_workspace(db, workspace=workspace)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> list[MemberOut]:
    members = await workspace_service.list_members(db, workspace_id)
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            joined_at=member.joined_at,
        )
        for user, member in members
    ]


@router.post("/{workspace_id}/members/invite-code", response_model=InviteCodeOut)
async def rotate_invite_code(
    workspace_id: uuid.UUID, membership: OwnerMember, db: DbSession
) -> InviteCodeOut:
    workspace = await workspace_service.get_workspace(db, workspace_id)
    code = await workspace_service.rotate_invite_code(
        db, workspace=workspace, actor_user_id=membership.user_id
    )
    return InviteCodeOut(code=code)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
async def change_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RoleUpdate,
    membership: OwnerMember,
    db: DbSession,
) -> MemberOut:
    updated = await workspace_service.change_member_role(
        db,
        workspace_id=workspace_id,
        target_user_id=user_id,
        new_role=payload.role,
        actor_user_id=membership.user_id,
    )
    user = await db.get(User, user_id)
    assert user is not None
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=updated.role,
        joined_at=updated.joined_at,
    )


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: OwnerMember,
    db: DbSession,
) -> None:
    await workspace_service.remove_member(
        db,
        workspace_id=workspace_id,
        target_user_id=user_id,
        actor_user_id=membership.user_id,
    )


@router.get("/{workspace_id}/audit-log", response_model=CursorPage[AuditLogEntryOut])
async def get_audit_log(
    workspace_id: uuid.UUID,
    membership: CurrentWorkspaceMember,
    db: DbSession,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
) -> CursorPage[AuditLogEntryOut]:
    rows, next_cursor = await workspace_service.list_audit_log(
        db,
        workspace_id=workspace_id,
        cursor=cursor,
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
    )
    return CursorPage[AuditLogEntryOut](
        items=[AuditLogEntryOut.model_validate(entry) for entry in rows],
        next_cursor=next_cursor,
    )
