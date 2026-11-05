"""Open a provision by citation. See services/law_lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import User
from app.services.act_browser import act_browser, citation_for, search_acts
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


class ActSummary(BaseModel):
    id: str
    name: str
    section_count: int


class ActListResponse(BaseModel):
    # False while the index is being built for the first time. Ask again shortly.
    ready: bool
    acts: list[ActSummary]
    total: int


class ActSection(BaseModel):
    section: str
    citation: str


class ActSectionsResponse(BaseModel):
    ready: bool
    id: str
    name: str | None
    sections: list[ActSection]


def _current_index(http_request: Request):
    index = act_browser.current(http_request.app.state.retrieval_service.client)
    if index is None and act_browser.failing:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The legal corpus is not reachable right now.")
    return index


@router.get("/acts", response_model=ActListResponse)
async def list_acts(
    http_request: Request,
    name: str = Query(default="", max_length=160),
    _: User = Depends(require_permission(CHAT_USE)),
) -> dict:
    index = _current_index(http_request)
    if index is None:
        return {"ready": False, "acts": [], "total": 0}
    found, total = search_acts(index, name)
    return {
        "ready": True,
        "acts": [{"id": act.id, "name": act.name, "section_count": len(act.sections)} for act in found],
        "total": total,
    }


@router.get("/acts/{act_id}/sections", response_model=ActSectionsResponse)
async def list_act_sections(
    act_id: str,
    http_request: Request,
    _: User = Depends(require_permission(CHAT_USE)),
) -> dict:
    index = _current_index(http_request)
    if index is None:
        return {"ready": False, "id": act_id, "name": None, "sections": []}
    act = index.by_id.get(act_id)
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That Act is not held in the corpus.")
    rows = ((section, citation_for(act.name, section)) for section in act.sections)
    return {
        "ready": True,
        "id": act.id,
        "name": act.name,
        "sections": [{"section": section, "citation": citation} for section, citation in rows if citation],
    }
