"""Open a provision by citation. See services/law_lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import User
from app.services.law_lookup import lookup_provision

router = APIRouter(prefix="/law", tags=["law"])


class ProvisionText(BaseModel):
    title: str
    act_name: str
    section: str
    text: str
    page_start: int
    page_end: int
    source_url: str | None
    jurisdiction: str | None
    currency_status: str
    superseded_by: str | None
    currency_basis: str | None


class Counterpart(BaseModel):
    from_code: str
    from_section: str
    to_code: str
    to_section: str | None
    subject: str
    ingredients_changed: bool
    note: str | None


class LawLookupResponse(BaseModel):
    query: str
    understood: bool
    act: str | None
    section: str | None
    provisions: list[ProvisionText]
    counterparts: list[Counterpart]


@router.get("/lookup", response_model=LawLookupResponse)
async def lookup(
    http_request: Request,
    q: str = Query(min_length=1, max_length=160),
    _: User = Depends(require_permission(CHAT_USE)),
) -> dict:
    try:
        return await lookup_provision(http_request.app.state.retrieval_service.client, q)
    except Exception as exc:  # noqa: BLE001 - the corpus store being down is not a bad citation
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The legal corpus is not reachable right now."
        ) from exc
