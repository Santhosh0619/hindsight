from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text

from app.agents.build_graph import checkpointer_conn_string
from app.api.v1.auth import router as auth_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.postmortems import router as postmortems_router
from app.api.v1.search import router as search_router
from app.api.v1.workspaces import router as workspaces_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import RequestIDMiddleware, configure_logging, get_logger
from app.db.init import ensure_vector_extension
from app.db.session import dispose_engine, get_engine

__version__ = "0.1.0"

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    engine = get_engine()
    await ensure_vector_extension(engine)
    # AsyncPostgresSaver.setup() issues CREATE INDEX CONCURRENTLY, which blocks until
    # every transaction open anywhere on the database at the time it starts has
    # ended. Running it here, before any request-scoped session can be mid-transaction,
    # avoids a real deadlock: a brief-generation request's own session sits inside an
    # open (SQLAlchemy-autobegun) transaction for the duration of the graph run, and
    # setup() run from that same request would wait on a transaction that can't
    # finish until setup() returns. The checkpoint tables/indexes only need creating
    # once per database, so this is a one-time cost at boot, not per-request.
    async with AsyncPostgresSaver.from_conn_string(
        checkpointer_conn_string(get_settings())
    ) as saver:
        await saver.setup()
    logger.info("app_startup", llm_configured=get_settings().llm_configured)
    yield
    await dispose_engine()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Hindsight API", version=__version__, lifespan=lifespan)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(workspaces_router, prefix="/api/v1")
    app.include_router(catalog_router, prefix="/api/v1")
    app.include_router(postmortems_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, object]:
        db_connected = True
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — health check must never raise, only report
            db_connected = False

        return {
            "status": "ok" if db_connected else "degraded",
            "version": __version__,
            "db_connected": db_connected,
            "llm_configured": settings.llm_configured,
        }

    return app


app = create_app()
