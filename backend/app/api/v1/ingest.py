from fastapi import APIRouter, status

from app.core.deps import CurrentApiKey, DbSession
from app.schemas.postmortem import PostmortemCreate, PostmortemOut
from app.services import postmortem_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/postmortem", response_model=PostmortemOut, status_code=status.HTTP_201_CREATED)
async def ingest_postmortem(
    payload: PostmortemCreate, api_key: CurrentApiKey, db: DbSession
) -> PostmortemOut:
    # Identical to the session-authenticated POST /workspaces/{id}/postmortems route --
    # same service function, so validation/redaction/chunking/embedding/queue-enqueue
    # behavior is guaranteed identical by construction, not by two implementations
    # kept in sync by hand. Attributed to the key's own creator (nullable, matching
    # Postmortem.created_by's existing nullability) -- there's no session user here.
    postmortem = await postmortem_service.create_postmortem(
        db, workspace_id=api_key.workspace_id, created_by=api_key.created_by, payload=payload
    )
    return PostmortemOut.model_validate(postmortem)
