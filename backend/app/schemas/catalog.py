import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.catalog import EdgeCriticality, EdgeKind, ServiceTier


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slack_handle: str | None = Field(default=None, max_length=200)
    escalation_contact: str | None = Field(default=None, max_length=200)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slack_handle: str | None = None
    escalation_contact: str | None = None


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    slack_handle: str | None
    escalation_contact: str | None

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tier: ServiceTier
    team_id: uuid.UUID | None = None
    repo_url: str | None = None
    description: str | None = None
    runbook_url: str | None = None


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tier: ServiceTier | None = None
    team_id: uuid.UUID | None = None
    repo_url: str | None = None
    description: str | None = None
    runbook_url: str | None = None


class ServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    tier: ServiceTier
    team_id: uuid.UUID | None
    repo_url: str | None
    description: str | None
    runbook_url: str | None

    model_config = {"from_attributes": True}


class EdgeCreate(BaseModel):
    from_service_id: uuid.UUID
    to_service_id: uuid.UUID
    kind: EdgeKind
    criticality: EdgeCriticality

    @model_validator(mode="after")
    def no_self_edge(self) -> "EdgeCreate":
        if self.from_service_id == self.to_service_id:
            raise ValueError("A service cannot depend on itself")
        return self


class EdgeOut(BaseModel):
    id: uuid.UUID
    from_service_id: uuid.UUID
    to_service_id: uuid.UUID
    kind: EdgeKind
    criticality: EdgeCriticality

    model_config = {"from_attributes": True}


class BlastRadiusEntryOut(BaseModel):
    service: ServiceOut
    score: float
    path: list[uuid.UUID]
    depth: int


class BlastRadiusOut(BaseModel):
    services: list[BlastRadiusEntryOut]


class CatalogGraphOut(BaseModel):
    nodes: list[ServiceOut]
    edges: list[EdgeOut]


class TeamImport(BaseModel):
    name: str
    slack_handle: str | None = None
    escalation_contact: str | None = None


class ServiceImport(BaseModel):
    name: str
    tier: ServiceTier
    team_name: str | None = None
    repo_url: str | None = None
    description: str | None = None
    runbook_url: str | None = None


class EdgeImportByName(BaseModel):
    from_service_name: str
    to_service_name: str
    kind: EdgeKind
    criticality: EdgeCriticality


class CatalogImport(BaseModel):
    teams: list[TeamImport] = Field(default_factory=list)
    services: list[ServiceImport] = Field(default_factory=list)
    edges: list[EdgeImportByName] = Field(default_factory=list)


class CatalogImportResult(BaseModel):
    teams_created: int
    services_created: int
    edges_created: int
