import uuid

from fastapi import APIRouter

from app.core.deps import CurrentWorkspaceMember, DbSession
from app.schemas.dashboard import DashboardOut
from app.services import dashboard_service
from app.services.postgres_graph_store import PostgresGraphStore

router = APIRouter(prefix="/workspaces/{workspace_id}/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    workspace_id: uuid.UUID, membership: CurrentWorkspaceMember, db: DbSession
) -> DashboardOut:
    graph_store = PostgresGraphStore(db)
    return await dashboard_service.get_dashboard(db, graph_store, workspace_id=workspace_id)
