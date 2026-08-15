import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.logging import get_logger
from app.models.workspace import ApiKey
from app.services.workspace_service import write_audit_log

logger = get_logger(__name__)

_KEY_PREFIX = "hs_"
_PREFIX_DISPLAY_LENGTH = 12


def _generate_key() -> tuple[str, str, str]:
    """Returns (raw_key, display_prefix, key_hash).

    SHA-256, not argon2 -- see NFR "Security": the raw key already carries 256 bits of
    real entropy (secrets.token_urlsafe), unlike a human-chosen password, and this hash
    is looked up on every single webhook call, where argon2's deliberate slowness would
    cost real latency for no offsetting security benefit here.
    """
    raw_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    prefix = raw_key[:_PREFIX_DISPLAY_LENGTH]
    return raw_key, prefix, key_hash


async def create_key(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str, actor_user_id: uuid.UUID
) -> tuple[ApiKey, str]:
    raw_key, prefix, key_hash = _generate_key()
    key = ApiKey(
        workspace_id=workspace_id,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        created_by=actor_user_id,
    )
    db.add(key)
    await db.flush()

    await write_audit_log(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="api_key.created",
        target_type="api_key",
        target_id=key.id,
        meta={"name": name, "prefix": prefix},
    )
    await db.commit()
    await db.refresh(key)

    logger.info(
        "api_key_created",
        key_id=str(key.id),
        prefix=prefix,
        actor_user_id=str(actor_user_id),
    )
    return key, raw_key


async def list_keys(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.workspace_id == workspace_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_key(
    db: AsyncSession, *, workspace_id: uuid.UUID, key_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    key = await db.get(ApiKey, key_id)
    if key is None or key.workspace_id != workspace_id:
        raise NotFoundError("API key not found")
    if key.revoked_at is not None:
        raise ConflictError("API key is already revoked")

    key.revoked_at = datetime.now(UTC)
    await write_audit_log(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="api_key.revoked",
        target_type="api_key",
        target_id=key.id,
        meta={"name": key.name, "prefix": key.prefix},
    )
    await db.commit()
    logger.info("api_key_revoked", key_id=str(key.id), actor_user_id=str(actor_user_id))


async def authenticate_key(db: AsyncSession, *, raw_key: str) -> ApiKey:
    """Returns the ApiKey row itself (not just its workspace) -- the ingest route
    needs `key.created_by` to attribute the postmortem to the key's own creator, since
    there's no session user on this path."""
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    key = result.scalars().first()
    # Same error, same message, whether the key never existed or was revoked -- a
    # caller can't distinguish "wrong key" from "right key, revoked" either way.
    if key is None or key.revoked_at is not None:
        raise UnauthorizedError("Invalid or revoked API key")

    key.last_used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(key)
    return key
