import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db as _get_db
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole

get_db = _get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedError("Access token missing subject claim")

    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_workspace(
    workspace_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMember:
    """Resolve the caller's membership in `workspace_id`.

    Returns 404 (not 403) when the caller isn't a member, so a request for another
    workspace's resources doesn't leak that the workspace exists — see plan.md §5/Phase 2.
    """
    membership = await db.get(WorkspaceMember, (workspace_id, current_user.id))
    if membership is None:
        raise NotFoundError("Workspace not found")
    return membership


CurrentWorkspaceMember = Annotated[WorkspaceMember, Depends(get_current_workspace)]


def require_role(
    *roles: WorkspaceRole,
) -> Callable[[WorkspaceMember], Coroutine[Any, Any, WorkspaceMember]]:
    async def _check(membership: CurrentWorkspaceMember) -> WorkspaceMember:
        if membership.role not in roles:
            raise ForbiddenError(
                f"Role '{membership.role.value}' is not permitted to perform this action"
            )
        return membership

    return _check
