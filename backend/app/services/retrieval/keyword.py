import re
import uuid

from pydantic import BaseModel
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postmortem import Postmortem, PostmortemChunk

# How much wider than top_k the Postgres candidate set is before the in-memory BM25
# rerank narrows it back down -- reranking cost scales with this window, not table size.
_CANDIDATE_MULTIPLIER = 4
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


class KeywordHit(BaseModel):
    chunk_id: uuid.UUID
    postmortem_id: uuid.UUID
    score: float
    rank: int


async def search_keyword(
    db: AsyncSession, *, workspace_id: uuid.UUID, query: str, top_k: int
) -> list[KeywordHit]:
    # websearch_to_tsquery (not to_tsquery) never raises a syntax error on arbitrary
    # user input -- required for a public-facing search box.
    tsquery = func.websearch_to_tsquery("english", query)
    rank_col = func.ts_rank_cd(PostmortemChunk.tsv, tsquery)
    candidate_query = (
        select(
            PostmortemChunk.id,
            PostmortemChunk.postmortem_id,
            PostmortemChunk.content,
            rank_col.label("rank"),
        )
        .join(Postmortem, Postmortem.id == PostmortemChunk.postmortem_id)
        .where(Postmortem.workspace_id == workspace_id, PostmortemChunk.tsv.op("@@")(tsquery))
        .order_by(rank_col.desc())
        .limit(top_k * _CANDIDATE_MULTIPLIER)
    )
    result = await db.execute(candidate_query)
    candidates = list(result)
    if not candidates:
        return []

    corpus = [_tokenize(row.content) for row in candidates]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))

    ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [
        KeywordHit(chunk_id=row.id, postmortem_id=row.postmortem_id, score=float(score), rank=i + 1)
        for i, (row, score) in enumerate(ranked[:top_k])
    ]
