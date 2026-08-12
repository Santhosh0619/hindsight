import re
import secrets
import uuid

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.models.user import User
from app.models.workspace import AuditLog, Workspace, WorkspaceMember, WorkspaceRole

logger = get_logger(__name__)

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _base_slug(name: str) -> str:
    slug = _SLUG_INVALID_CHARS.sub("-", name.lower()).strip("-")
    return slug or "workspace"


async def slugify_unique(db: AsyncSession, name: str) -> str:
    base = _base_slug(name)
    candidate = base
    suffix = 2
    while True:
        result = await db.execute(select(Workspace.id).where(Workspace.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


async def write_audit_log(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    meta: dict[str, object],
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
        )
    )


async def create_workspace(db: AsyncSession, *, owner: User, name: str) -> Workspace:
    workspace = Workspace(name=name, slug=await slugify_unique(db, name))
    db.add(workspace)
    await db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role=WorkspaceRole.OWNER))
    await write_audit_log(
        db,
        workspace_id=workspace.id,
        actor_user_id=owner.id,
        action="workspace.created",
        target_type="workspace",
        target_id=workspace.id,
        meta={},
    )
    await db.commit()
    await db.refresh(workspace)
    logger.info("workspace_created", workspace_id=str(workspace.id), actor_user_id=str(owner.id))
    return workspace


async def list_my_workspaces(db: AsyncSession, user: User) -> list[tuple[Workspace, WorkspaceRole]]:
    result = await db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return [(workspace, role) for workspace, role in result.all()]


async def get_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    return workspace


async def update_workspace(
    db: AsyncSession,
    *,
    workspace: Workspace,
    actor_user_id: uuid.UUID,
    name: str | None,
    slug: str | None,
) -> Workspace:
    if name is not None:
        workspace.name = name
    if slug is not None:
        existing = await db.execute(
            select(Workspace.id).where(Workspace.slug == slug, Workspace.id != workspace.id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("That slug is already taken")
        workspace.slug = slug

    await write_audit_log(
        db,
        workspace_id=workspace.id,
        actor_user_id=actor_user_id,
        action="workspace.updated",
        target_type="workspace",
        target_id=workspace.id,
        meta={"name": name, "slug": slug},
    )
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def delete_workspace(db: AsyncSession, *, workspace: Workspace) -> None:
    await db.delete(workspace)
    await db.commit()


async def list_members(
    db: AsyncSession, workspace_id: uuid.UUID
) -> list[tuple[User, WorkspaceMember]]:
    result = await db.execute(
        select(User, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.joined_at)
    )
    return [(user, member) for user, member in result.all()]


async def rotate_invite_code(
    db: AsyncSession, *, workspace: Workspace, actor_user_id: uuid.UUID
) -> str:
    code = secrets.token_urlsafe(9)
    workspace.invite_code = code

    await write_audit_log(
        db,
        workspace_id=workspace.id,
        actor_user_id=actor_user_id,
        action="workspace.invite_code_rotated",
        target_type="workspace",
        target_id=workspace.id,
        meta={},
    )
    await db.commit()
    return code


async def join_by_code(db: AsyncSession, *, user: User, code: str) -> Workspace:
    result = await db.execute(select(Workspace).where(Workspace.invite_code == code))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise NotFoundError("Invalid invite code")

    existing = await db.get(WorkspaceMember, (workspace.id, user.id))
    if existing is not None:
        raise ConflictError("Already a member of this workspace")

    db.add(
        WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.RESPONDER)
    )
    await write_audit_log(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        action="workspace.member_joined",
        target_type="workspace_member",
        target_id=user.id,
        meta={"via": "invite_code"},
    )
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def _count_owners(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    )
    return result.scalar_one()


async def change_member_role(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: WorkspaceRole,
    actor_user_id: uuid.UUID,
) -> WorkspaceMember:
    member = await db.get(WorkspaceMember, (workspace_id, target_user_id))
    if member is None:
        raise NotFoundError("Member not found")

    if (
        member.role == WorkspaceRole.OWNER
        and new_role != WorkspaceRole.OWNER
        and await _count_owners(db, workspace_id) <= 1
    ):
        raise ConflictError("A workspace must always have at least one owner")

    member.role = new_role
    await write_audit_log(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="workspace.member_role_changed",
        target_type="workspace_member",
        target_id=target_user_id,
        meta={"role": new_role.value},
    )
    await db.commit()
    await db.refresh(member)
    logger.info(
        "workspace_member_role_changed",
        workspace_id=str(workspace_id),
        target_user_id=str(target_user_id),
        new_role=new_role.value,
        actor_user_id=str(actor_user_id),
    )
    return member


async def remove_member(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    member = await db.get(WorkspaceMember, (workspace_id, target_user_id))
    if member is None:
        raise NotFoundError("Member not found")

    if member.role == WorkspaceRole.OWNER and await _count_owners(db, workspace_id) <= 1:
        raise ConflictError("A workspace must always have at least one owner")

    await db.delete(member)
    await write_audit_log(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="workspace.member_removed",
        target_type="workspace_member",
        target_id=target_user_id,
        meta={},
    )
    await db.commit()


async def list_audit_log(
    db: AsyncSession, *, workspace_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[list[AuditLog], str | None]:
    # Returns raw ORM rows, not a CursorPage — CursorPage is a Pydantic generic model
    # and AuditLog (the SQLAlchemy class) isn't Pydantic-schema-generatable. The route
    # layer maps these rows into CursorPage[AuditLogEntryOut].
    query = select(AuditLog).where(AuditLog.workspace_id == workspace_id)

    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            tuple_(AuditLog.created_at, AuditLog.id) < (cursor_created_at, cursor_id)
        )

    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return rows, next_cursor
