import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, DbSession, require_role
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.schemas.apikey import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.services import apikey_service

router = APIRouter(prefix="/workspaces/{workspace_id}/apikeys", tags=["apikeys"])

OwnerMember = Annotated[WorkspaceMember, Depends(require_role(WorkspaceRole.OWNER))]


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    workspace_id: uuid.UUID,
    payload: ApiKeyCreate,
    membership: OwnerMember,
    current_user: CurrentUser,
    db: DbSession,
) -> ApiKeyCreatedOut:
    key, raw_key = await apikey_service.create_key(
        db, workspace_id=workspace_id, name=payload.name, actor_user_id=current_user.id
    )
    return ApiKeyCreatedOut(
        id=key.id, name=key.name, prefix=key.prefix, raw_key=raw_key, created_at=key.created_at
    )


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    workspace_id: uuid.UUID, membership: OwnerMember, db: DbSession
) -> list[ApiKeyOut]:
    keys = await apikey_service.list_keys(db, workspace_id=workspace_id)
    return [ApiKeyOut.model_validate(key) for key in keys]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    workspace_id: uuid.UUID,
    key_id: uuid.UUID,
    membership: OwnerMember,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    await apikey_service.revoke_key(
        db, workspace_id=workspace_id, key_id=key_id, actor_user_id=current_user.id
    )
