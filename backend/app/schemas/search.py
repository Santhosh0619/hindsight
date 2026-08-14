import uuid
from typing import Literal

from pydantic import BaseModel

from app.models.postmortem import ServiceLinkRole
from app.schemas.postmortem import PostmortemOut

SearchMode = Literal["hybrid", "vector", "keyword", "graph"]
SourceName = Literal["vector", "keyword", "graph"]


class SourceHitOut(BaseModel):
    source: SourceName
    rank: int
    raw_score: float


class ChunkExcerptOut(BaseModel):
    chunk_id: uuid.UUID
    section_label: str | None
    content: str


class GraphReasonOut(BaseModel):
    matched_service_name: str
    via_service_name: str | None
    role: ServiceLinkRole


class SearchResultOut(BaseModel):
    postmortem: PostmortemOut
    score: float
    sources: list[SourceHitOut]
    chunk_excerpt: ChunkExcerptOut | None
    graph_reason: GraphReasonOut | None


class SearchResponseOut(BaseModel):
    results: list[SearchResultOut]
    mode: SearchMode
    timings_ms: dict[str, int]
