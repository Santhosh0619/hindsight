import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.workspace import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "WorkspaceUpdate":
        if self.name is None and self.slug is None:
            raise ValueError("At least one of 'name' or 'slug' must be provided")
        return self


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_demo: bool
    created_at: datetime
    role: WorkspaceRole

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: WorkspaceRole
    joined_at: datetime


class RoleUpdate(BaseModel):
    role: WorkspaceRole


class InviteCodeOut(BaseModel):
    code: str


class JoinRequest(BaseModel):
    code: str = Field(min_length=1)


class AuditLogEntryOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    meta: dict[str, object]
    created_at: datetime

    model_config = {"from_attributes": True}
