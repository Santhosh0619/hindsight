import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.services.workspace_service import slugify_unique, write_audit_log

logger = get_logger(__name__)


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    settings = get_settings()
    raw_refresh = generate_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    access_token = create_access_token(user_id=str(user.id))
    return access_token, raw_refresh


async def signup(
    db: AsyncSession, *, email: str, password: str, full_name: str
) -> tuple[User, str, str]:
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError("An account with this email already exists") from exc

    workspace = Workspace(
        name=f"{full_name}'s workspace",
        slug=await slugify_unique(db, full_name),
    )
    db.add(workspace)
    await db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
    await write_audit_log(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        action="workspace.created",
        target_type="workspace",
        target_id=workspace.id,
        meta={"via": "signup"},
    )

    access_token, raw_refresh = await issue_token_pair(db, user)
    await db.commit()
    logger.info("user_signed_up", user_id=str(user.id))
    logger.info("workspace_created", workspace_id=str(workspace.id), actor_user_id=str(user.id))
    return user, access_token, raw_refresh


async def login(db: AsyncSession, *, email: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    access_token, raw_refresh = await issue_token_pair(db, user)
    await db.commit()
    logger.info("user_logged_in", user_id=str(user.id))
    return user, access_token, raw_refresh


# One message for every failure branch below — deliberately not distinguishing
# "not found" from "expired" from "reused" from "inactive user" in what the caller
# sees, for the same no-enumeration reason login() uses a single message. The reuse
# case in particular must not have a distinguishable message: telling a caller "this
# token was already used" is itself a tell to whoever is holding the replayed token.
_REFRESH_FAILURE_MESSAGE = "Invalid refresh token"


async def refresh(db: AsyncSession, *, raw_token: str) -> tuple[User, str, str]:
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token_row = result.scalar_one_or_none()

    if token_row is None:
        raise UnauthorizedError(_REFRESH_FAILURE_MESSAGE)

    if token_row.revoked_at is not None:
        # Reuse of an already-spent token: revoke the whole family for this user so a
        # stolen-and-replayed token can't be used to keep extending a session.
        logger.warning("refresh_token_reused", user_id=str(token_row.user_id))
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == token_row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
        raise UnauthorizedError(_REFRESH_FAILURE_MESSAGE)

    if token_row.expires_at < datetime.now(UTC):
        raise UnauthorizedError(_REFRESH_FAILURE_MESSAGE)

    token_row.revoked_at = datetime.now(UTC)

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError(_REFRESH_FAILURE_MESSAGE)

    access_token, raw_refresh = await issue_token_pair(db, user)
    await db.commit()
    return user, access_token, raw_refresh


async def logout(db: AsyncSession, *, raw_token: str | None) -> None:
    if not raw_token:
        return

    token_hash = hash_refresh_token(raw_token)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def create_demo_guest(db: AsyncSession) -> tuple[User, str, str]:
    result = await db.execute(select(Workspace).where(Workspace.is_demo.is_(True)).limit(1))
    demo_workspace = result.scalar_one_or_none()

    if demo_workspace is None:
        demo_workspace = Workspace(
            name="Demo Workspace",
            slug=await slugify_unique(db, "demo-workspace"),
            is_demo=True,
        )
        db.add(demo_workspace)
        await db.flush()

    guest = User(
        email=f"guest-{uuid.uuid4().hex[:12]}@demo.hindsight.local",
        # Never meant to be logged into with a password — argon2-hash a random value
        # so there is no known plaintext that verifies against it.
        password_hash=hash_password(uuid.uuid4().hex),
        full_name="Demo Guest",
        is_demo=True,
    )
    db.add(guest)
    await db.flush()

    db.add(
        WorkspaceMember(workspace_id=demo_workspace.id, user_id=guest.id, role=WorkspaceRole.VIEWER)
    )
    access_token, raw_refresh = await issue_token_pair(db, guest)
    await db.commit()
    logger.info("demo_guest_provisioned", user_id=str(guest.id))
    return guest, access_token, raw_refresh
