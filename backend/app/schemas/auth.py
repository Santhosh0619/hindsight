import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.workspace import WorkspaceRole


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_demo: bool

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MembershipOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    workspace_is_demo: bool
    role: WorkspaceRole


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
