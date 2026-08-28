from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.permissions import CORPUS_READ
from app.core.case_scope import (
    AuthorizedCaseScope,
    collection_for_case_role,
    resolve_authorized_case_scope,
)
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.core.rbac import require_permission
from app.models import User
from app.schemas.retrieval import (
    RetrievalHitResponse,
    RetrievalRequest,
    RetrievalResponse,
    ScopedRetrievalResponse,
)
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalTarget,
)


router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_retrieval_service(request: Request) -> HybridRetrievalService:
    """Return the lifespan-managed service; kept injectable for focused tests."""
    return request.app.state.retrieval_service


@router.post("/search", response_model=RetrievalResponse)
async def hybrid_search(
    request: RetrievalRequest,
    service: Annotated[HybridRetrievalService, Depends(get_retrieval_service)],
    _: User | None = Depends(require_permission(CORPUS_READ, allow_anonymous=True)),
) -> RetrievalResponse:
    hits = await service.search(
        request.query,
        filters=RetrievalFilters(**request.filters.model_dump()),
        candidate_limit=request.candidate_limit,
        result_limit=request.result_limit,
    )
    return RetrievalResponse(
        query=request.query,
        results=[RetrievalHitResponse(**hit.__dict__) for hit in hits],
    )


@router.post("/scoped-search", response_model=ScopedRetrievalResponse)
async def scoped_hybrid_search(
    request: RetrievalRequest,
    scope: Annotated[AuthorizedCaseScope, Depends(resolve_authorized_case_scope)],
    service: Annotated[HybridRetrievalService, Depends(get_retrieval_service)],
) -> ScopedRetrievalResponse:
    targets = [
        RetrievalTarget(
            collection_name=GLOBAL_LEGAL_CORPUS,
            filters=RetrievalFilters(**request.filters.model_dump()),
        )
    ]
    authorized_case_ids: list[str] = []
    for role, case_ids in scope.case_ids_by_role.items():
        if not case_ids:
            continue
        string_ids = [str(case_id) for case_id in case_ids]
        authorized_case_ids.extend(string_ids)
        targets.append(
            RetrievalTarget(
                collection_name=collection_for_case_role(role),
                filters=RetrievalFilters(corpus_tiers=[], case_ids=string_ids),
            )
        )
    hits, _ = await service.search_across_collections_with_timings(
        request.query,
        targets=targets,
        candidate_limit=request.candidate_limit,
        result_limit=request.result_limit,
    )
    return ScopedRetrievalResponse(
        query=request.query,
        mode=scope.mode,
        authorized_case_ids=authorized_case_ids,
        results=[RetrievalHitResponse(**hit.__dict__) for hit in hits],
    )
