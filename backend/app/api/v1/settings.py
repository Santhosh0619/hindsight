import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import require_role
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.schemas.settings import LLMProviderTestOut
from app.services import llm_test_service

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])

OwnerMember = Annotated[WorkspaceMember, Depends(require_role(WorkspaceRole.OWNER))]


@router.post("/llm/test", response_model=list[LLMProviderTestOut])
async def test_llm_providers(
    workspace_id: uuid.UUID, membership: OwnerMember
) -> list[LLMProviderTestOut]:
    return await llm_test_service.test_all_providers(get_settings())
