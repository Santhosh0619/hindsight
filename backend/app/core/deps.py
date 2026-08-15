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
from app.models.workspace import ApiKey, Workspace, WorkspaceMember, WorkspaceRole
from app.services.apikey_service import authenticate_key

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


def require_role_or_demo(
    *roles: WorkspaceRole,
) -> Callable[[WorkspaceMember, User, AsyncSession], Coroutine[Any, Any, WorkspaceMember]]:
    """Same as `require_role`, plus an escape hatch for demo guests — scoped to the
    demo workspace itself, not just the caller's account.

    A demo guest is always a VIEWER of the demo workspace (Phase 2's
    `create_demo_guest`), but nothing stops that same account from later joining a
    real workspace via invite code, where it should be bound by that workspace's own
    role like any other member. Checking `current_user.is_demo` alone would still
    widen access there too, since the flag is permanent on the account rather than
    scoped to a particular membership — so the carve-out only fires when the
    workspace being accessed is itself the demo workspace.
    """

    async def _check(
        membership: CurrentWorkspaceMember, current_user: CurrentUser, db: DbSession
    ) -> WorkspaceMember:
        if membership.role in roles:
            return membership
        if current_user.is_demo:
            workspace = await db.get(Workspace, membership.workspace_id)
            if workspace is not None and workspace.is_demo:
                return membership
        raise ForbiddenError(
            f"Role '{membership.role.value}' is not permitted to perform this action"
        )

    return _check


async def get_api_key(
    db: DbSession,
    x_api_key: Annotated[str | None, Header()] = None,
) -> ApiKey:
    """Resolves the caller for `POST /ingest/postmortem` -- authenticated by a
    workspace API key (`X-API-Key`), never a user session. Distinct from
    `get_current_workspace`: there's no `workspace_id` path parameter to check
    membership against here, since an external caller only knows its own key, never a
    workspace id — both the workspace and the attribution for the postmortem it
    creates (`created_by`) come from the key itself.
    """
    if x_api_key is None:
        raise UnauthorizedError("Missing X-API-Key header")
    return await authenticate_key(db, raw_key=x_api_key)


CurrentApiKey = Annotated[ApiKey, Depends(get_api_key)]
