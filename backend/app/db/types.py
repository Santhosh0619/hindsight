import enum

from pgvector.sqlalchemy import Vector


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    # SQLAlchemy's Enum type defaults to persisting the Python member *name*
    # (e.g. "QUEUED") as the Postgres enum label. Every str-Enum model class in
    # this project is defined with lowercase `.value`s instead (e.g. "queued"),
    # so every such column must pass this as `values_callable` to keep the DB
    # label consistent with the value the rest of the app compares against.
    return [member.value for member in enum_cls]


# Fixed to match `sentence-transformers/all-MiniLM-L6-v2` (see plan.md §8/§10). This is a
# schema constant, not a runtime setting: changing it means re-embedding the entire
# corpus and a new Alembic migration, not an env var flip. Kept separate from
# `app.core.config.Settings` so model files don't depend on full app settings at import
# time (e.g. during Alembic autogenerate).
EMBEDDING_DIM = 384

EmbeddingVector = Vector(EMBEDDING_DIM)
