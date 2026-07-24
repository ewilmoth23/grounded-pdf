"""Instant semantic quote search: deterministic retrieval with no model call.

Search reuses the retrieval trust boundary — the query is embedded locally, the
vector store is filtered to READY documents, and every candidate is rebuilt from
relational chunk records before it reaches the client — but it never involves a
chat provider. Recall matters more than precision here, so only the low
`retrieval_min_score` floor is applied; the stricter answer-time heuristics
(term overlap, deduplication, diversification) are deliberately skipped.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.exceptions import GroundedPdfError
from app.db.session import get_db
from app.models.entities import Document, ProcessingStatus
from app.rag.chat import validate_matches
from app.schemas.search import SearchMatchResponse, SearchResponse
from app.services.dependencies import get_embedding_provider, get_vector_store
from app.services.settings import effective_settings

router = APIRouter()

MAX_RESULTS = 25
# Mirrors the conversation document-selection cap; an unbounded filter list
# would grow the SQL IN clause and vector-store filter without limit.
MAX_FILTER_DOCUMENTS = 50
_EXCERPT_LIMIT = 320
# Over-fetch so results dropped by the score floor or relational revalidation
# do not leave the page short.
_OVERFETCH_FACTOR = 3


def _excerpt(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) > _EXCERPT_LIMIT:
        return collapsed[: _EXCERPT_LIMIT - 3] + "…"
    return collapsed


@router.get("", response_model=SearchResponse)
async def search_passages(
    q: str = Query(min_length=1, max_length=500, description="Phrase to search for"),
    document_ids: list[str] | None = Query(
        default=None, description="Restrict search to these documents (default: all ready)"
    ),
    limit: int | None = Query(default=None, ge=1, le=MAX_RESULTS),
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> SearchResponse:
    """Return exact stored passages ranked by semantic similarity. No generation."""
    query = q.strip()
    if not query:
        raise GroundedPdfError(
            "Search query must not be empty", code="validation_error", status_code=422
        )
    if document_ids and len(document_ids) > MAX_FILTER_DOCUMENTS:
        raise GroundedPdfError(
            f"At most {MAX_FILTER_DOCUMENTS} documents can be searched at once",
            code="validation_error",
            status_code=422,
        )

    def run() -> SearchResponse:
        runtime = effective_settings(db, base)
        result_limit = min(limit or runtime.retrieval_count, MAX_RESULTS)
        ready_query = select(Document.id).where(Document.status == ProcessingStatus.READY)
        if document_ids:
            ready_query = ready_query.where(Document.id.in_(list(dict.fromkeys(document_ids))))
        ready_ids = list(db.scalars(ready_query))
        if not ready_ids:
            return SearchResponse(query=query, documents_available=False, matches=[])
        query_vector = get_embedding_provider().embed([query])[0]
        candidates = get_vector_store().query(
            query_vector, ready_ids, result_limit * _OVERFETCH_FACTOR
        )
        candidates = [
            candidate for candidate in candidates if candidate.score >= runtime.retrieval_min_score
        ]
        validated = validate_matches(db, candidates, ready_ids)
        validated.sort(key=lambda match: match.score, reverse=True)
        return SearchResponse(
            query=query,
            documents_available=True,
            matches=[
                SearchMatchResponse(
                    document_id=str(match.metadata["document_id"]),
                    document_name=str(match.metadata["document_name"]),
                    page_number=int(match.metadata["page_number"]),
                    excerpt=_excerpt(match.text),
                    score=round(max(0.0, min(1.0, match.score)), 4),
                )
                for match in validated[:result_limit]
            ],
        )

    return await run_in_threadpool(run)
