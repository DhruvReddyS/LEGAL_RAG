"""A case's events in order, from its own files. See services/case_chronology."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from qdrant_client import models
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.case_scope import collection_for_case_role
from app.core.database import get_db_session
from app.core.permissions import CASE_READ_OWN
from app.core.rbac import require_permission
from app.models import Case, User
from app.services.case_chronology import build_chronology

router = APIRouter(tags=["case-chronology"])

_SCROLL_PAGE = 256


class ChronologyEventResponse(BaseModel):
    date: str
    precision: str
    text: str
    document_id: str
    title: str
    page_start: int
    page_end: int


class ChronologyResponse(BaseModel):
    events: list[ChronologyEventResponse]
    total_events: int
    documents_read: int


@router.get("/cases/{case_id}/chronology", response_model=ChronologyResponse)
async def case_chronology(
    case_id: uuid.UUID,
    http_request: Request,
    user: User = Depends(require_permission(CASE_READ_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    # The owner only, with no administrator exception. This reads the whole file.
    if case.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this case")
    client = http_request.app.state.retrieval_service.client
    chunks: list[dict] = []
    offset = None
    try:
        while True:
            batch, offset = await client.scroll(
                collection_name=collection_for_case_role(case.role_type),
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="case_id", match=models.MatchValue(value=str(case_id)))]
                ),
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=["text", "title", "document_id", "page_start", "page_end"],
                with_vectors=False,
            )
            chunks.extend(dict(point.payload or {}) for point in batch)
            if offset is None:
                break
    except Exception as exc:  # noqa: BLE001 - the store being down is not an empty case
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The case files could not be read right now."
        ) from exc
    return await asyncio.to_thread(build_chronology, chunks)
