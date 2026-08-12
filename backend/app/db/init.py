from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def ensure_vector_extension(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
